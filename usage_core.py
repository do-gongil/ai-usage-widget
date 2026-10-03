"""사용량 조회·파싱·설정 (UI 없음, 테스트 대상). 설정은 %APPDATA%\\UsageTray\\config.json / last.json."""
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

APP_NAME = "UsageTray"
HOME = Path.home()
CLAUDE_CREDENTIALS = HOME / ".claude" / ".credentials.json"
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or HOME / ".codex")
CONFIG_DIR = Path(os.environ.get("APPDATA", HOME)) / APP_NAME
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
MIN_INTERVAL = 300  # usage API 제한 창이 약 5분: 더 짧으면 429
MAX_INTERVAL = 86400
MAX_BACKOFF = 600  # 429 시 최대 대기(초)
MIN_OPACITY = 30  # 너무 투명하면 창을 잃어버린다
CODEX_TAIL_BYTES = 256 * 1024
TOOLTIP_MAX = 127  # Windows NOTIFYICONDATA szTip 제한

COLOR_OK, COLOR_WARN, COLOR_CRIT, COLOR_UNKNOWN = "#2f9e5b", "#d98a12", "#d33b3b", "#7a8090"


# ---------- 설정 ----------

def default_config():
    return {
        "agents": {"claude": CLAUDE_CREDENTIALS.exists(), "codex": CODEX_HOME.exists()},
        "interval": MIN_INTERVAL,
        "view": "five_hour",
        "pip": {"visible": True, "rect": None, "mini": False, "mini_rect": None,
                "topmost": True, "color": None, "opacity": 100},
    }


def _rect(value):
    if isinstance(value, list) and len(value) == 4 and all(isinstance(v, int) for v in value):
        return value
    return None


def _is_hex(value):
    return isinstance(value, str) and len(value) == 7 and value[0] == "#" and \
        all(c in "0123456789abcdefABCDEF" for c in value[1:])


def load_config():
    try:
        cfg = json.loads((CONFIG_DIR / "config.json").read_text(encoding="utf-8"))
        agents = cfg.get("agents") or {}
        pip = cfg.get("pip") or {}
        return {
            "agents": {"claude": bool(agents.get("claude")), "codex": bool(agents.get("codex"))},
            # 상한: 지나치게 큰 값으로 대기가 사실상 멈추지 않게
            "interval": min(MAX_INTERVAL, max(MIN_INTERVAL, int(cfg.get("interval", MIN_INTERVAL)))),
            "view": "weekly" if cfg.get("view") == "weekly" else "five_hour",
            "pip": {
                "visible": bool(pip.get("visible", True)),
                "rect": _rect(pip.get("rect")),
                "mini": bool(pip.get("mini", False)),
                "mini_rect": _rect(pip.get("mini_rect")),
                "topmost": bool(pip.get("topmost", True)),
                "color": pip.get("color") if _is_hex(pip.get("color")) else None,
                "opacity": min(100, max(MIN_OPACITY, int(pip.get("opacity", 100)))),
            },
        }
    except (OSError, ValueError, TypeError, AttributeError):
        cfg = default_config()
        save_config(cfg)
        return cfg


def _write_atomic(path, text):
    """임시 파일에 다 쓴 뒤 교체: 쓰는 도중 꺼져도 기존 파일이 반쯤 잘린 채 남지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save_config(cfg):
    try:
        _write_atomic(CONFIG_DIR / "config.json", json.dumps(cfg, indent=2))
    except OSError:
        pass  # 설정 저장 실패로 앱이 죽지 않게


def save_last(last):
    """마지막 성공 값 저장: 재시작 직후나 429 중에도 '?' 대신 직전 값을 보여주기 위함."""
    data = {agent: {k: [pct, reset.isoformat() if reset else None] for k, (pct, reset) in r["usage"].items()}
            for agent, r in last.items() if "usage" in r}
    try:
        _write_atomic(CONFIG_DIR / "last.json", json.dumps(data))
    except OSError:
        pass  # 캐시일 뿐


def load_last():
    try:
        data = json.loads((CONFIG_DIR / "last.json").read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        return {agent: {"usage": expire_passed(
                    {k: (_pct(w[0]), _parse_time(w[1])) for k, w in windows.items()
                     if k in ("five_hour", "weekly")}, now)}
                for agent, windows in data.items()
                if agent in ("claude", "codex") and {"five_hour", "weekly"} <= set(windows)}
    except (OSError, ValueError, TypeError, AttributeError, IndexError):
        return {}


# ---------- 파싱 ----------

def _pct(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if v != v else max(0.0, min(100.0, v))  # NaN 제외


def _parse_time(value):
    """ISO 문자열 또는 epoch 초 → aware datetime. 실패 시 None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def parse_claude_usage(data):
    """/api/oauth/usage 응답 → {'five_hour': (pct, reset), 'weekly': (pct, reset)}"""
    data = data if isinstance(data, dict) else {}
    limits = data.get("limits")
    # 새 형식은 legacy 키를 뺄 수 있다: 모델 scope 없는 limits[] 항목으로 대체
    unscoped = {l.get("kind"): l for l in (limits if isinstance(limits, list) else [])
                if isinstance(l, dict) and not l.get("scope")}

    def window(key, kind):
        w = data.get(key) if isinstance(data.get(key), dict) else unscoped.get(kind) or {}
        return _pct(w.get("utilization", w.get("percent"))), _parse_time(w.get("resets_at"))
    return {"five_hour": window("five_hour", "session"), "weekly": window("seven_day", "weekly_all")}


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
        w = limits.get(key) if isinstance(limits.get(key), dict) else {}
        reset = _parse_time(w.get("resets_at"))
        secs = w.get("resets_in_seconds")
        if reset is None and base is not None and isinstance(secs, (int, float)):
            reset = datetime.fromtimestamp(base.timestamp() + secs, timezone.utc)
        return _pct(w.get("used_percent")), reset
    return {"five_hour": window("primary"), "weekly": window("secondary")}


def expire_passed(usage, now):
    """리셋 시각이 지난 창은 0%로 본다 (오래된 Codex 기록 대응)."""
    return {k: ((0.0, None) if reset and reset <= now else (pct, reset)) for k, (pct, reset) in usage.items()}


# ---------- 표시 ----------

def color_for(pct):
    if pct is None:
        return COLOR_UNKNOWN
    if pct >= 80:
        return COLOR_CRIT
    if pct >= 60:
        return COLOR_WARN
    return COLOR_OK


def fmt_pct(pct):
    return "--" if pct is None else f"{pct:.0f}%"


def fmt_time(dt):
    if dt is None:
        return ""
    local = dt.astimezone()
    if local.date() == datetime.now().astimezone().date():
        return local.strftime("%H:%M")
    return local.strftime("%m/%d %H:%M")


def icon_text(pct):
    if pct is None:
        return "?"
    if pct >= 100:
        return "!"  # 16px에 세 자리는 안 읽힘. 한도 소진은 '!'로 99%와 구분
    return str(min(99, round(pct)))


def format_line(name, result, last=None):
    """툴팁 한 줄. 실패 시 마지막 성공 값(last)을 괄호로 덧붙인다."""
    if result.get("error"):
        line = f"{name}: {result['error']}"
        if last:
            line += f" (직전 5h {fmt_pct(last['usage']['five_hour'][0])})"
        return line
    u = result["usage"]
    (p5, r5), (pw, _) = u["five_hour"], u["weekly"]
    line = f"{name} 5h {fmt_pct(p5)} 주 {fmt_pct(pw)}"
    if r5:
        line += f" ↻{fmt_time(r5)}"
    if result.get("last_used"):
        line += f" ({fmt_time(result['last_used'])} 기준)"
    return line


def build_tooltip(lines):
    text = "\n".join(lines) or "사용할 agent를 메뉴에서 선택하세요"
    return text if len(text) <= TOOLTIP_MAX else text[: TOOLTIP_MAX - 1] + "…"


def icon_state(results, last, view="five_hour"):
    """(아이콘 숫자, 오래된 값 여부). Claude 우선, 꺼져 있으면 Codex.
    조회 실패 시 직전 성공 값을 회색으로, 직전 값도 없으면 (None, True)."""
    for agent in ("claude", "codex"):
        if agent in results:
            r = results[agent]
            if "usage" in r:
                return r["usage"][view][0], False
            if agent in last:
                return last[agent]["usage"][view][0], True
            return None, True
    return None, True


# ---------- 조회 ----------

def retry_delay(retry_after, previous):
    """429 대기 시간(초): Retry-After가 있으면 따르고, 없으면 120초부터 2배씩 늘려 최대 600초."""
    try:
        seconds = int(retry_after)
        if seconds > 0:
            return min(seconds, MAX_BACKOFF)
    except (TypeError, ValueError):
        pass
    return min(max(previous * 2, 120), MAX_BACKOFF)


def should_fetch(prev, now, backoff_until, last_ok_at):
    """Claude 조회 여부 (시각은 time.monotonic() 초).
    429 대기 중이거나 직전 성공 후 MIN_INTERVAL이 안 지났으면 조회하지 않는다:
    메뉴 토글·새로고침 연타가 5분 제한 창 안에서 다시 호출해 429를 받는 것을 막는다."""
    if prev is None:
        return True
    if now < backoff_until:
        return False
    # 5초 여유: 정기 조회(조회가 끝난 뒤 interval 대기)가 경계에서 막히지 않게
    return "usage" not in prev or now - last_ok_at >= MIN_INTERVAL - 5


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 따라가지 않는다. urllib은 다른 호스트로 갈 때도 Authorization 헤더를 넘기기 때문."""
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(
    _NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))


def fetch_claude():
    # 토큰 갱신은 Claude Code에 맡긴다. 여기서 credentials 파일을 쓰면 로그인이 깨질 수 있다.
    try:
        creds = json.loads(CLAUDE_CREDENTIALS.read_text(encoding="utf-8"))
        token = creds["claudeAiOauth"]["accessToken"]
        if not isinstance(token, str) or not token or any(c in token for c in "\r\n"):
            raise ValueError
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
            return {"error": "요청 제한, 잠시 후 재시도", "retry_after": e.headers.get("Retry-After") or ""}
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


def read_codex():
    try:
        files = sorted((CODEX_HOME / "sessions").rglob("*.jsonl"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        files = []
    # 최근 5개 파일의 끝 256KB만 본다. token_count가 그보다 앞에만 있으면 다음 파일로 넘어감.
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


class ClaudeFetcher:
    """429 백오프 + 성공 후 5분 재사용을 묶은 Claude 조회기 (조회 스레드에서만 사용)."""

    def __init__(self, fetch=fetch_claude, clock=time.monotonic):
        self._fetch, self._clock = fetch, clock
        self.prev, self.until, self.backoff, self.ok_at = None, 0.0, 0, 0.0

    def get(self):
        now = self._clock()
        if not should_fetch(self.prev, now, self.until, self.ok_at):
            return self.prev
        result = self._fetch()
        if "retry_after" in result:
            self.backoff = retry_delay(result["retry_after"], self.backoff)
            self.until = now + self.backoff
        else:
            self.backoff = 0
        if "usage" in result:
            self.ok_at = self._clock()
        self.prev = result
        return result


def clamp_to_work_area(rect, work):
    """크기가 바뀐 창 rect=[x,y,w,h]가 작업 영역 work=(left,top,right,bottom) 밖으로 나가면 안쪽으로 민다. 작업 영역보다 크면 왼쪽 위에 붙인다."""
    x, y, w, h = rect
    left, top, right, bottom = work
    return [min(max(x, left), max(left, right - w)), min(max(y, top), max(top, bottom - h)), w, h]
