"""python test_usage_core.py (또는 pytest) — 파싱·설정·조회 판단 자가 점검 (네트워크·UI 불필요)"""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import usage_core as uc


def ok(p5, pw=None):
    return {"usage": {"five_hour": (p5, None), "weekly": (pw, None)}}


def test_claude_parse():
    data = {"five_hour": {"utilization": 42.0, "resets_at": "2026-09-23T09:59:59.879814+00:00"},
            "seven_day": {"utilization": 26.0, "resets_at": "2026-09-27T23:59:59+00:00"}}
    u = uc.parse_claude_usage(data)
    assert u["five_hour"][0] == 42.0 and u["five_hour"][1].hour == 9
    assert u["weekly"][0] == 26.0
    assert uc.parse_claude_usage({"five_hour": None}) == {"five_hour": (None, None), "weekly": (None, None)}
    assert uc.parse_claude_usage(None)["five_hour"] == (None, None)
    # 새 형식: legacy 키 없이 limits[]만. 모델 scope 항목은 무시
    new = {"limits": [
        {"kind": "weekly_all", "percent": 30, "resets_at": "2026-09-27T23:59:59Z", "scope": {"model": {"id": "opus"}}},
        {"kind": "session", "percent": 55, "resets_at": "2026-09-23T09:00:00Z"},
        {"kind": "weekly_all", "utilization": 12, "resets_at": "2026-09-27T23:59:59Z", "scope": None},
    ]}
    u = uc.parse_claude_usage(new)
    assert u["five_hour"][0] == 55.0 and u["five_hour"][1].hour == 9
    assert u["weekly"][0] == 12.0
    assert uc.parse_claude_usage({**data, **new})["five_hour"][0] == 42.0  # legacy 키 우선
    assert uc.parse_claude_usage({"limits": "bad"})["weekly"] == (None, None)
    assert uc.parse_claude_usage([1, 2])["weekly"] == (None, None)  # dict가 아닌 응답


def test_codex_parse():
    line = json.dumps({"timestamp": "2026-09-23T05:00:00Z", "type": "event_msg", "payload": {
        "type": "token_count", "info": None,
        "rate_limits": {"primary": {"used_percent": 12.5, "window_minutes": 300, "resets_in_seconds": 3600},
                        "secondary": {"used_percent": 3, "resets_at": 1790000000}}}})
    u = uc.parse_codex_line(line)
    assert u["five_hour"][0] == 12.5 and u["five_hour"][1].hour == 6
    assert u["weekly"][0] == 3.0 and u["weekly"][1] is not None
    assert uc.parse_codex_line('{"payload":{"type":"agent_message"}}') is None
    assert uc.parse_codex_line('{"payload":{"type":"token_count"}}') is None
    assert uc.parse_codex_line("not json") is None
    assert uc.parse_codex_line("[1,2]") is None


def test_pct_and_time():
    assert uc._pct("55") == 55.0 and uc._pct(150) == 100.0 and uc._pct(-3) == 0.0
    assert uc._pct(float("nan")) is None and uc._pct("x") is None
    assert uc._parse_time("bad") is None and uc._parse_time(True) is None
    assert uc._parse_time("2026-09-23T05:00:00").tzinfo is not None  # 시간대 없으면 UTC로


def test_colors_and_text():
    assert uc.color_for(None) == uc.COLOR_UNKNOWN
    assert uc.color_for(59.9) == uc.COLOR_OK
    assert uc.color_for(60) == uc.COLOR_WARN
    assert uc.color_for(80) == uc.COLOR_CRIT
    assert [uc.icon_text(p) for p in (None, 5, 42.4, 99.6, 100)] == ["?", "5", "42", "99", "!"]
    assert uc.fmt_pct(None) == "--" and uc.fmt_pct(42.4) == "42%"


def test_icon_state_priority():
    err = {"error": "오프라인"}
    assert uc.icon_state({"claude": ok(42), "codex": ok(10)}, {}) == (42, False)
    assert uc.icon_state({"codex": ok(10)}, {}) == (10, False)
    assert uc.icon_state({"claude": err, "codex": ok(10)}, {}) == (None, True)
    assert uc.icon_state({"claude": err}, {"claude": ok(33)}) == (33, True)
    assert uc.icon_state({}, {}) == (None, True)
    assert uc.icon_state({"claude": ok(42, 71)}, {}, "weekly") == (71, False)


def test_retry_delay():
    assert uc.retry_delay("30", 0) == 30
    assert uc.retry_delay("0", 0) == 120
    assert uc.retry_delay(None, 120) == 240
    assert uc.retry_delay(None, 480) == uc.MAX_BACKOFF
    assert uc.retry_delay("99999", 0) == uc.MAX_BACKOFF


def test_should_fetch():
    now = 1_000_000.0
    err = {"error": "오프라인"}
    assert uc.should_fetch(None, now, 0, 0)
    assert not uc.should_fetch(ok(1), now, now + 60, 0)  # 429 대기 중
    assert not uc.should_fetch(ok(1), now, 0, now - 10)  # 성공 직후 연타
    assert uc.should_fetch(ok(1), now, 0, now - (uc.MIN_INTERVAL - 5))  # 정기 조회 경계
    assert uc.should_fetch(err, now, 0, now - 10)  # 직전 실패면 바로 재시도


def test_claude_fetcher_backoff_and_reuse():
    t = [1000.0]
    calls = []
    replies = [{"error": "요청 제한", "retry_after": ""}, ok(5)]

    def fake():
        calls.append(t[0])
        return replies.pop(0)
    f = uc.ClaudeFetcher(fetch=fake, clock=lambda: t[0])
    assert "retry_after" in f.get() and f.backoff == 120
    t[0] += 60
    assert "retry_after" in f.get() and len(calls) == 1  # 대기 중엔 호출 안 함
    t[0] += 61
    assert "usage" in f.get() and len(calls) == 2 and f.backoff == 0
    t[0] += 30
    assert "usage" in f.get() and len(calls) == 2  # 성공 후 5분 내 재사용


def test_expire_passed():
    now = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
    usage = {"five_hour": (50.0, now - timedelta(minutes=1)), "weekly": (20.0, now + timedelta(days=1))}
    out = uc.expire_passed(usage, now)
    assert out["five_hour"] == (0.0, None) and out["weekly"] == usage["weekly"]


def _with_config_dir(fn):
    orig = uc.CONFIG_DIR
    with tempfile.TemporaryDirectory() as d:
        uc.CONFIG_DIR = Path(d)
        try:
            fn(Path(d))
        finally:
            uc.CONFIG_DIR = orig


def test_config_compat_and_clamp():
    def run(d):
        # C# 버전이 쓴 설정 + 범위를 벗어난 값
        (d / "config.json").write_text(json.dumps({
            "agents": {"claude": True, "codex": False}, "interval": 999999999, "view": "weekly",
            "pip": {"visible": False, "rect": [1, 2, 300, 130], "mini": True, "mini_rect": [1, 2, 300, 48],
                    "topmost": False, "color": "#FFF4B8", "opacity": 5}}), encoding="utf-8")
        c = uc.load_config()
        assert c["interval"] == uc.MAX_INTERVAL and c["view"] == "weekly"
        p = c["pip"]
        assert p["rect"] == [1, 2, 300, 130] and p["mini"] and p["opacity"] == uc.MIN_OPACITY
        assert p["color"] == "#FFF4B8" and not p["topmost"]
        (d / "config.json").write_text('{"pip": {"color": "red", "rect": [1, 2]}}', encoding="utf-8")
        p = uc.load_config()["pip"]
        assert p["color"] is None and p["rect"] is None
        (d / "config.json").write_text("{broken", encoding="utf-8")
        assert uc.load_config()["interval"] == uc.MIN_INTERVAL  # 손상 → 기본값
    _with_config_dir(run)


def test_last_cache_roundtrip_atomic():
    def run(d):
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert uc.load_last() == {}
        uc.save_last({"claude": {"usage": {"five_hour": (42.0, past), "weekly": (27.0, future)}}})
        got = uc.load_last()["claude"]["usage"]
        assert got["five_hour"] == (0.0, None)
        assert got["weekly"][0] == 27.0 and got["weekly"][1] == future
        assert not list(d.glob("*.tmp"))  # 임시 파일이 남지 않음
    _with_config_dir(run)


def test_codex_tail_read():
    rl = {"primary": {"used_percent": 77}, "secondary": {"used_percent": 5}}
    line = json.dumps({"payload": {"type": "token_count", "rate_limits": rl}})
    orig = uc.CODEX_HOME
    with tempfile.TemporaryDirectory() as d:
        uc.CODEX_HOME = Path(d)
        try:
            assert uc.read_codex() == {"error": "기록 없음"}
            f = Path(d, "sessions", "2026", "rollout.jsonl")
            f.parent.mkdir(parents=True)
            f.write_text(("x" * 1000 + "\n") * 400 + line + "\n", encoding="utf-8")
            assert uc.read_codex()["usage"]["five_hour"][0] == 77.0
        finally:
            uc.CODEX_HOME = orig


def test_tooltip():
    assert uc.format_line("Claude", ok(42.0, 18.0)) == "Claude 5h 42% 주 18%"
    assert uc.format_line("Claude", {"error": "오프라인"}, ok(42.0)) == "Claude: 오프라인 (직전 5h 42%)"
    assert len(uc.build_tooltip(["x" * 300])) == uc.TOOLTIP_MAX


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
