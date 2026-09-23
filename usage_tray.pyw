"""Usage Tray — Claude Code / Codex 사용률을 Windows 트레이에 표시한다."""
import ctypes
import json
import os
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

APP_NAME = "UsageTray"
HOME = Path.home()
CLAUDE_CREDENTIALS = HOME / ".claude" / ".credentials.json"
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or HOME / ".codex")
CONFIG_PATH = Path(os.environ.get("APPDATA", HOME)) / APP_NAME / "config.json"
LAST_PATH = CONFIG_PATH.with_name("last.json")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
TOOLTIP_MAX = 127  # Windows NOTIFYICONDATA szTip 제한
MAX_BACKOFF = 600  # 429 시 최대 대기(초)
CODEX_TAIL_BYTES = 256 * 1024
MUTEX_NAME = "Local\\UsageTray.SingleInstance"
ERROR_ALREADY_EXISTS = 183

COLOR_OK, COLOR_WARN, COLOR_CRIT, COLOR_UNKNOWN = "#2f9e5b", "#d98a12", "#d33b3b", "#7a8090"


# ---------- 설정 ----------

def default_config():
    return {
        "agents": {"claude": CLAUDE_CREDENTIALS.exists(), "codex": CODEX_HOME.exists()},
        "interval": 60,
        "view": "five_hour",
        "stacked": False,
    }


def load_config():
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        agents = cfg.get("agents", {})
        return {
            "agents": {"claude": bool(agents.get("claude")), "codex": bool(agents.get("codex"))},
            "interval": max(30, int(cfg.get("interval", 60))),
            "view": "weekly" if cfg.get("view") == "weekly" else "five_hour",
            "stacked": cfg.get("stacked") is True,
        }
    except (OSError, ValueError, TypeError, AttributeError):
        cfg = default_config()
        save_config(cfg)
        return cfg


def save_config(cfg):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def save_last(last):
    """마지막 성공 값 저장: 재시작 직후나 429 중에도 '?' 대신 직전 값을 보여주기 위함."""
    data = {agent: {k: [pct, reset.isoformat() if reset else None] for k, (pct, reset) in r["usage"].items()}
            for agent, r in last.items()}
    try:
        LAST_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_PATH.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass  # 캐시일 뿐이라 실패해도 동작에 지장 없음


def load_last():
    try:
        data = json.loads(LAST_PATH.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        return {agent: {"usage": expire_passed(
                    {k: (_pct(w[0]), _parse_time(w[1])) for k, w in windows.items()
                     if k in ("five_hour", "weekly")}, now)}
                for agent, windows in data.items()
                if agent in ("claude", "codex") and {"five_hour", "weekly"} <= set(windows)}
    except (OSError, ValueError, TypeError, AttributeError, IndexError):
        return {}


# ---------- 파싱 (순수 함수, 테스트 대상) ----------

def _pct(value):
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def _parse_time(value):
    """ISO 문자열 또는 epoch 초 → aware datetime. 실패 시 None."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, OverflowError, OSError):
        return None


def parse_claude_usage(data):
    """/api/oauth/usage 응답 → {'five_hour': (pct, reset), 'weekly': (pct, reset)}"""
    def window(key):
        w = (data or {}).get(key) or {}
        return _pct(w.get("utilization")), _parse_time(w.get("resets_at"))
    return {"five_hour": window("five_hour"), "weekly": window("seven_day")}


def parse_codex_line(line, base_time=None):
    """rollout jsonl 한 줄 → 사용률 dict. token_count/rate_limits 가 아니면 None."""
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    payload = obj.get("payload") if isinstance(obj, dict) else None
    if not isinstance(payload, dict) or payload.get("type") != "token_count":
        return None
    limits = payload.get("rate_limits")
    if not isinstance(limits, dict):
        return None
    base = _parse_time(obj.get("timestamp")) or base_time

    def window(key):
        w = limits.get(key) or {}
        reset = _parse_time(w.get("resets_at"))
        secs = w.get("resets_in_seconds")
        if reset is None and base is not None and isinstance(secs, (int, float)):
            reset = datetime.fromtimestamp(base.timestamp() + secs, timezone.utc)
        return _pct(w.get("used_percent")), reset
    return {"five_hour": window("primary"), "weekly": window("secondary")}


def color_for(pct):
    if pct is None:
        return COLOR_UNKNOWN
    if pct >= 80:
        return COLOR_CRIT
    if pct >= 60:
        return COLOR_WARN
    return COLOR_OK


def _fmt_pct(pct):
    return "--" if pct is None else f"{pct:.0f}%"


def _fmt_time(dt):
    if dt is None:
        return ""
    local = dt.astimezone()
    if local.date() == datetime.now().astimezone().date():
        return local.strftime("%H:%M")
    return local.strftime("%m/%d %H:%M")


def format_line(name, result, last=None):
    """툴팁 한 줄. 실패 시 마지막 성공 값(last)을 괄호로 덧붙인다."""
    if result.get("error"):
        line = f"{name}: {result['error']}"
        if last:
            line += f" (직전 5h {_fmt_pct(last['usage']['five_hour'][0])})"
        return line
    u = result["usage"]
    (p5, r5), (pw, _) = u["five_hour"], u["weekly"]
    line = f"{name} 5h {_fmt_pct(p5)} 주 {_fmt_pct(pw)}"
    if r5:
        line += f" ↻{_fmt_time(r5)}"
    if result.get("last_used"):
        line += f" ({_fmt_time(result['last_used'])} 기준)"
    return line


def build_tooltip(lines):
    text = "\n".join(lines) or "사용할 agent를 메뉴에서 선택하세요"
    return text if len(text) <= TOOLTIP_MAX else text[: TOOLTIP_MAX - 1] + "…"


def icon_usage(results, last):
    """(아이콘에 쓸 usage dict 또는 None, 오래된 값 여부). Claude 우선, 꺼져 있으면 Codex.
    조회 실패 시 직전 성공 값을 회색으로, 직전 값도 없으면 (None, True) → 회색 '?'."""
    for agent in ("claude", "codex"):
        if agent in results:
            r = results[agent]
            if "usage" in r:
                return r["usage"], False
            if agent in last:
                return last[agent]["usage"], True
            return None, True
    return None, True


def icon_state(results, last, view="five_hour"):
    """(아이콘 숫자, 오래된 값 여부). view: 'five_hour' | 'weekly'."""
    usage, stale = icon_usage(results, last)
    return (usage[view][0] if usage else None), stale


# ---------- 조회 ----------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 따라가지 않는다. urllib은 다른 호스트로 갈 때도 Authorization 헤더를 그대로 넘기기 때문."""
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(
    _NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))


def retry_delay(retry_after, previous):
    """429 대기 시간(초): Retry-After가 있으면 따르고, 없으면 120초부터 2배씩 늘려 최대 600초."""
    try:
        seconds = int(retry_after)
        if seconds > 0:
            return min(seconds, MAX_BACKOFF)
    except (TypeError, ValueError):
        pass
    return min(max(previous * 2, 120), MAX_BACKOFF)


def fetch_claude():
    # ponytail: 토큰 갱신은 Claude Code에 맡긴다. 여기서 credentials 파일을 쓰면 로그인이 깨질 수 있다.
    try:
        creds = json.loads(CLAUDE_CREDENTIALS.read_text(encoding="utf-8"))
        token = creds["claudeAiOauth"]["accessToken"]
    except (OSError, ValueError, KeyError, TypeError):
        return {"error": "미로그인"}
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": APP_NAME,
    })
    try:
        with _OPENER.open(req, timeout=10) as resp:
            return {"usage": parse_claude_usage(json.load(resp))}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return {"error": "토큰 만료 (Claude Code 실행 필요)"}
        if e.code == 429:
            return {"error": "요청 제한, 잠시 후 재시도", "retry_after": e.headers.get("Retry-After")}
        return {"error": f"HTTP {e.code}"}
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"error": "오프라인"}
    except ValueError:
        return {"error": "응답 형식 오류"}


def _read_tail_lines(path):
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - CODEX_TAIL_BYTES))
        # 잘린 첫 줄은 JSON 파싱에 실패해 자연히 건너뛴다
        return f.read().decode("utf-8", errors="replace").splitlines()


def expire_passed(usage, now):
    """리셋 시각이 지난 창은 0%로 본다 (오래된 Codex 기록 대응)."""
    return {k: ((0.0, None) if reset and reset <= now else (pct, reset)) for k, (pct, reset) in usage.items()}


def read_codex():
    sessions = CODEX_HOME / "sessions"
    try:
        files = sorted(sessions.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        files = []
    # ponytail: 최근 5개 파일의 끝 256KB만 본다. token_count가 그보다 앞에만 있으면 다음 파일로 넘어감.
    for path in files[:5]:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            lines = _read_tail_lines(path)
        except OSError:
            continue
        for line in reversed(lines):
            usage = parse_codex_line(line, mtime)
            if usage:
                return {"usage": expire_passed(usage, datetime.now(timezone.utc)), "last_used": mtime}
    return {"error": "기록 없음"}


# ---------- 아이콘 ----------

def _font(size):
    for name in ("segoeuib.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def icon_text(pct):
    if pct is None:
        return "?"
    if pct >= 100:
        return "!"  # 16px에 세 자리는 안 읽힘. 한도 소진은 '!'로 99%와 구분
    return str(min(99, round(pct)))


def render_icon(pct, stale=False):
    """stale=True: 조회 실패로 직전 값을 보여주는 중 → 회색 배경."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fill = COLOR_UNKNOWN if stale else color_for(pct)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=10, fill=fill)
    text = icon_text(pct)
    font = _font(46 if len(text) == 1 else 40)
    draw.text((size / 2, size / 2), text, font=font, fill="white", anchor="mm")
    return img


def render_stacked_icon(p5, pw, stale=False):
    """세로 2단: 위 5시간, 아래 주간. 칸마다 자기 값 기준 색."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _font(34)
    for (top, bottom), pct in (((0, 31), p5), ((33, 63), pw)):
        fill = COLOR_UNKNOWN if stale else color_for(pct)
        draw.rounded_rectangle((0, top, size - 1, bottom), radius=6, fill=fill)
        draw.text((size / 2, (top + bottom) / 2 + 1), icon_text(pct), font=font, fill="white", anchor="mm")
    return img


# ---------- 시작 시 실행 ----------

def _launch_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" "{Path(__file__).resolve()}"'


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


# ---------- 앱 ----------

def acquire_single_instance():
    """이미 실행 중이면 None. 중복 실행은 트레이 아이콘을 늘리고 API 요청 제한(429)을 부른다."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle or ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return None
    return handle  # 프로세스 종료 시 OS가 해제


class App:
    def __init__(self):
        import pystray
        self.pystray = pystray
        self.cfg = load_config()
        self.last = load_last()  # agent → 마지막 성공 결과 (디스크 캐시에서 복원)
        self.claude_prev = None  # 대기 중에 재사용할 직전 Claude 결과
        self.claude_until = 0.0  # time.monotonic() 기준, 이 시각 전엔 Claude 조회 안 함
        self.claude_backoff = 0
        self.results = {}  # 직전 refresh 결과: 보기 전환 시 재조회 없이 다시 그림
        self.wake = threading.Event()
        self.stopped = False
        self.icon = pystray.Icon(APP_NAME, render_icon(None), "Usage Tray", menu=self._menu())

    def _menu(self):
        item, menu = self.pystray.MenuItem, self.pystray.Menu
        return menu(
            item("Claude", lambda: self._toggle("claude"), checked=lambda _: self.cfg["agents"]["claude"]),
            item("Codex", lambda: self._toggle("codex"), checked=lambda _: self.cfg["agents"]["codex"]),
            menu.SEPARATOR,
            # default=True → 아이콘 좌클릭 시 실행
            item(lambda _: "주간 보기" if self.cfg["view"] == "five_hour" else "5시간 보기",
                 self._toggle_view, default=True),
            item("세로 2단 아이콘 (위 5시간 / 아래 주간)", self._toggle_stacked,
                 checked=lambda _: self.cfg["stacked"]),
            item("지금 새로고침", lambda: self.wake.set()),
            item("시작 시 실행", lambda: set_autostart(not autostart_enabled()),
                 checked=lambda _: autostart_enabled()),
            item("종료", self._quit),
        )

    def _toggle(self, agent):
        self.cfg["agents"][agent] = not self.cfg["agents"][agent]
        save_config(self.cfg)
        self.wake.set()

    def _toggle_view(self):
        self.cfg["view"] = "weekly" if self.cfg["view"] == "five_hour" else "five_hour"
        save_config(self.cfg)
        self._draw_icon()

    def _toggle_stacked(self):
        self.cfg["stacked"] = not self.cfg["stacked"]
        save_config(self.cfg)
        self._draw_icon()

    def _draw_icon(self):
        if self.cfg["stacked"]:
            usage, stale = icon_usage(self.results, self.last)
            p5, pw = (usage["five_hour"][0], usage["weekly"][0]) if usage else (None, None)
            self.icon.icon = render_stacked_icon(p5, pw, stale)
        else:
            pct, stale = icon_state(self.results, self.last, self.cfg["view"])
            self.icon.icon = render_icon(pct, stale)

    def _quit(self):
        self.stopped = True
        self.wake.set()
        self.icon.stop()

    def _claude(self):
        now = time.monotonic()
        if self.claude_prev is not None and now < self.claude_until:
            return self.claude_prev  # 429 대기 중: 새로고침을 눌러도 조회하지 않음
        result = fetch_claude()
        if "retry_after" in result:
            self.claude_backoff = retry_delay(result["retry_after"], self.claude_backoff)
            self.claude_until = now + self.claude_backoff
        else:
            self.claude_backoff = 0
        self.claude_prev = result
        return result

    def refresh(self):
        results = {}
        if self.cfg["agents"]["claude"]:
            results["claude"] = self._claude()
        if self.cfg["agents"]["codex"]:
            results["codex"] = read_codex()

        lines = []
        for agent, name in (("claude", "Claude"), ("codex", "Codex")):
            if agent in results:
                lines.append(format_line(name, results[agent], self.last.get(agent)))
                if "usage" in results[agent]:
                    self.last[agent] = results[agent]
        if any("usage" in r for r in results.values()):
            save_last(self.last)
        if lines:
            lines.append(f"갱신 {datetime.now():%H:%M:%S}")

        if self.stopped:  # 조회 중 종료됐으면 해제된 아이콘을 건드리지 않음
            return
        self.results = results
        self._draw_icon()
        self.icon.title = build_tooltip(lines)

    def _loop(self, icon):
        # 첫 조회 전: 저장된 직전 값을 회색으로 먼저 표시
        self.results = {a: {"error": "조회 중"} for a, on in self.cfg["agents"].items() if on}
        self._draw_icon()
        icon.visible = True
        while not self.stopped:
            try:
                self.refresh()
            except Exception as e:  # 루프가 죽으면 아이콘이 멈춘 채 남으므로 사유를 툴팁으로
                self.icon.icon = render_icon(None)
                self.icon.title = build_tooltip([f"오류: {type(e).__name__}"])
            self.wake.wait(self.cfg["interval"])
            self.wake.clear()

    def run(self):
        self.icon.run(setup=self._loop)


if __name__ == "__main__":
    if acquire_single_instance():
        App().run()
