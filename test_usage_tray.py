"""python test_usage_tray.py — 파싱/표시 로직 자가 점검 (네트워크·트레이 불필요)"""
import importlib.machinery
import importlib.util
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_path = Path(__file__).with_name("usage_tray.pyw")
_loader = importlib.machinery.SourceFileLoader("usage_tray", str(_path))
_spec = importlib.util.spec_from_loader("usage_tray", _loader)
ut = importlib.util.module_from_spec(_spec)
_loader.exec_module(ut)


def test_claude_parse():
    data = {"five_hour": {"utilization": 42.0, "resets_at": "2026-09-23T09:59:59.879814+00:00"},
            "seven_day": {"utilization": 26.0, "resets_at": "2026-09-27T23:59:59+00:00"}}
    u = ut.parse_claude_usage(data)
    assert u["five_hour"][0] == 42.0 and u["five_hour"][1].hour == 9
    assert u["weekly"][0] == 26.0
    # 키 누락·null
    assert ut.parse_claude_usage({"five_hour": None}) == {"five_hour": (None, None), "weekly": (None, None)}
    assert ut.parse_claude_usage(None)["five_hour"] == (None, None)


def test_codex_parse():
    line = json.dumps({"timestamp": "2026-09-23T05:00:00Z", "type": "event_msg", "payload": {
        "type": "token_count", "info": None,
        "rate_limits": {"primary": {"used_percent": 12.5, "window_minutes": 300, "resets_in_seconds": 3600},
                        "secondary": {"used_percent": 3, "resets_at": 1790000000}}}})
    u = ut.parse_codex_line(line)
    assert u["five_hour"][0] == 12.5 and u["five_hour"][1].hour == 6
    assert u["weekly"][0] == 3.0 and u["weekly"][1] is not None
    assert ut.parse_codex_line('{"payload":{"type":"agent_message"}}') is None
    assert ut.parse_codex_line('{"payload":{"type":"token_count"}}') is None  # rate_limits 없음
    assert ut.parse_codex_line("not json") is None
    assert ut.parse_codex_line("[1,2]") is None


def test_colors():
    assert ut.color_for(None) == ut.COLOR_UNKNOWN
    assert ut.color_for(59.9) == ut.COLOR_OK
    assert ut.color_for(60) == ut.COLOR_WARN
    assert ut.color_for(79.9) == ut.COLOR_WARN
    assert ut.color_for(80) == ut.COLOR_CRIT


def test_icon_state_priority():
    ok = lambda p: {"usage": {"five_hour": (p, None), "weekly": (None, None)}}
    err = {"error": "오프라인"}
    assert ut.icon_state({"claude": ok(42), "codex": ok(10)}, {}) == (42, False)
    assert ut.icon_state({"codex": ok(10)}, {}) == (10, False)
    assert ut.icon_state({"claude": err, "codex": ok(10)}, {}) == (None, True)
    assert ut.icon_state({"claude": err}, {"claude": ok(33)}) == (33, True)  # 실패 시 직전 값을 회색으로
    assert ut.icon_state({}, {}) == (None, True)
    both = {"usage": {"five_hour": (42, None), "weekly": (71, None)}}
    assert ut.icon_state({"claude": both}, {}, "weekly") == (71, False)
    assert ut.icon_state({"claude": err}, {"claude": both}, "weekly") == (71, True)


def test_icon_text():
    assert [ut.icon_text(p) for p in (None, 5, 42.4, 99.6, 100)] == ["?", "5", "42", "99", "!"]


def test_retry_delay():
    assert ut.retry_delay("30", 0) == 30
    assert ut.retry_delay("0", 0) == 120  # Retry-After: 0 은 무시하고 백오프
    assert ut.retry_delay(None, 120) == 240
    assert ut.retry_delay(None, 480) == ut.MAX_BACKOFF
    assert ut.retry_delay("99999", 0) == ut.MAX_BACKOFF


def test_expire_passed():
    now = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
    usage = {"five_hour": (50.0, now - timedelta(minutes=1)), "weekly": (20.0, now + timedelta(days=1))}
    out = ut.expire_passed(usage, now)
    assert out["five_hour"] == (0.0, None) and out["weekly"] == usage["weekly"]


def test_codex_tail_read():
    rl = {"primary": {"used_percent": 77}, "secondary": {"used_percent": 5}}
    line = json.dumps({"payload": {"type": "token_count", "rate_limits": rl}})
    with tempfile.TemporaryDirectory() as d:
        orig = ut.CODEX_HOME
        ut.CODEX_HOME = Path(d)
        try:
            f = Path(d, "sessions", "2026", "rollout.jsonl")
            f.parent.mkdir(parents=True)
            # 앞부분을 tail 크기보다 크게 채워 잘린 첫 줄이 생기도록
            f.write_text(("x" * 1000 + "\n") * 400 + line + "\n", encoding="utf-8")
            r = ut.read_codex()
            assert r["usage"]["five_hour"][0] == 77.0, r
        finally:
            ut.CODEX_HOME = orig


def test_tooltip():
    ok = {"usage": {"five_hour": (42.0, None), "weekly": (18.0, None)}}
    assert ut.format_line("Claude", ok) == "Claude 5h 42% 주 18%"
    assert ut.format_line("Claude", {"error": "오프라인"}, ok) == "Claude: 오프라인 (직전 5h 42%)"
    assert len(ut.build_tooltip(["x" * 300])) == ut.TOOLTIP_MAX
    assert ut.render_icon(100).size == (64, 64)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
