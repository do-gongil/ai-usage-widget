"""python test_usage_tray.py — 파싱/표시 로직 자가 점검 (네트워크·트레이 불필요)"""
import importlib.machinery
import importlib.util
import json
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


def test_icon_percent_priority():
    ok = lambda p: {"usage": {"five_hour": (p, None), "weekly": (None, None)}}
    assert ut.icon_percent({"claude": ok(42), "codex": ok(10)}) == 42
    assert ut.icon_percent({"codex": ok(10)}) == 10
    assert ut.icon_percent({"claude": {"error": "오프라인"}, "codex": ok(10)}) is None
    assert ut.icon_percent({}) is None


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
