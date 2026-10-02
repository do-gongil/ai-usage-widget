"""AI Usage Widget (Python 버전) — 트레이 아이콘 + 항상 위 PiP 창.
pythonw usage_widget.pyw 로 실행. C# 버전과 설정 파일·단일 실행 뮤텍스를 공유한다(둘 중 하나만 실행됨).
스레드: tkinter(메인) / pystray(트레이) / 조회 작업 / 전역 단축키. UI 변경은 모두 큐를 거쳐 메인 스레드에서."""
import ctypes
import queue
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import usage_core as uc

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
MUTEX_NAME = "Local\\UsageTray.SingleInstance"  # C# 버전과 같은 이름: 둘이 동시에 돌면 API 호출이 두 배
VIEW_LABELS = {"five_hour": "5", "weekly": "W"}
COLOR_BADGE = "#1d2230"
PALETTE = [("기본", None), ("노랑", "#FFF4B8"), ("분홍", "#FFD9EC"), ("하늘", "#D6ECFF"),
           ("연두", "#DDF5D5"), ("보라", "#E8DCFF"), ("어두움", "#202428")]

user32 = ctypes.windll.user32
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


# ---------- 트레이 아이콘 ----------

def _font(size):
    for name in ("segoeuib.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def render_icon(pct, stale=False, label=None):
    """stale=True: 조회 실패로 직전 값 → 회색. label: 좌측 상단 뱃지('5' 5시간 / 'W' 주간)."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=8 if label else 10,
                           fill=uc.COLOR_UNKNOWN if stale else uc.color_for(pct))
    text = uc.icon_text(pct)
    if label:
        draw.rectangle((0, 0, 24, 26), fill=COLOR_BADGE)
        draw.text((12, 13), label, font=_font(26), fill="white", anchor="mm")
        draw.text((36, 43), text, font=_font(40), fill="white", anchor="mm")
    else:
        draw.text((size / 2, size / 2), text, font=_font(46 if len(text) == 1 else 40), fill="white", anchor="mm")
    return img


# ---------- 시작 시 실행 / 단일 실행 ----------

def _launch_command():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" "{Path(__file__).resolve()}"'


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, uc.APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, uc.APP_NAME, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, uc.APP_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        pass  # 레지스트리 정책 등으로 실패해도 앱은 계속 (메뉴 체크는 실제 상태를 다시 읽는다)


def acquire_single_instance():
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle or ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle  # 프로세스 종료 시 OS가 해제


def _on_screen(rect):
    """창 왼쪽 위 100x30 영역이 어느 모니터와 겹칠 때만 화면 안으로 본다 (1px만 걸친 창은 못 잡으므로)."""
    x, y, w, h = rect
    if w < 100 or h < 30:
        return False
    r = wintypes.RECT(x, y, x + 100, y + 30)
    return bool(user32.MonitorFromRect(ctypes.byref(r), 0))  # MONITOR_DEFAULTTONULL


# ---------- 테마 ----------

def _mix(hex_color, other, t):
    a = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def theme_for(color):
    bg = color or "#f3f3f3"
    r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
    dark = 0.299 * r + 0.587 * g + 0.114 * b < 128
    fg = "#ffffff" if dark else "#1b1b1b"
    return {"bg": bg, "fg": fg, "sub": _mix(bg, fg, 0.55), "track": _mix(bg, fg, 0.18), "hover": _mix(bg, fg, 0.1)}


# ---------- PiP 창 ----------

class Pip:
    def __init__(self, app, root):
        self.app, self.root, self.cfg = app, root, app.cfg
        self.scale = root.winfo_fpixels("1i") / 96.0
        self._last_update = None
        self._save_job = None
        self._popup = None
        root.overrideredirect(True)  # 테두리 없는 위젯 창 (작업 표시줄에도 안 뜸)
        root.title("AI Usage Widget")
        root.attributes("-topmost", self.cfg["pip"]["topmost"])
        self.apply_opacity()
        self.build()
        self.apply_mode(initial=True)
        root.bind("<Configure>", lambda e: self.schedule_save() if e.widget is root else None)
        root.bind("<Button-1>", self._click_outside_popup, add="+")  # 위젯 아무 곳 클릭 → 설정 팝업 닫기
        root.after(50, self._round_corners)

    def px(self, n):
        return round(n * self.scale)

    def _round_corners(self):
        # Windows 11: 테두리 없는 창도 둥근 모서리로 (지원 안 하는 OS에서는 무시됨)
        hwnd = user32.GetParent(self.root.winfo_id())
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        try:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
        except OSError:
            pass

    # ----- 구성 -----

    def build(self):
        for w in self.root.winfo_children():
            w.destroy()
        t = self.theme = theme_for(self.cfg["pip"]["color"])
        mini = self.cfg["pip"]["mini"]
        self.f_text = tkfont.Font(family="Segoe UI", size=9 if mini else 10)
        self.f_bold = tkfont.Font(family="Segoe UI", size=9 if mini else 10, weight="bold")
        self.f_small = tkfont.Font(family="Segoe UI", size=8 if mini else 9)
        self.f_icon = tkfont.Font(family="Segoe UI Symbol", size=10)
        self.root.configure(bg=t["bg"])

        self.header = tk.Frame(self.root, bg=t["bg"])
        self.header.columnconfigure(3, weight=1)
        self._button(self.header, "⟳", "지금 새로고침", self.app.refresh_now).grid(row=0, column=0)
        self.footer = tk.Label(self.header, text="조회 중…", font=self.f_small, bg=t["bg"], fg=t["sub"])
        self.footer.grid(row=0, column=1, padx=(2, 4))
        self.gear = self._button(self.header, "⚙", "설정", self.toggle_settings)
        self.gear.grid(row=0, column=2)
        spacer = tk.Frame(self.header, bg=t["bg"], height=self.px(24))
        spacer.grid(row=0, column=3, sticky="nsew")
        self._button(self.header, "—", "미니 모드 (Ctrl+Alt+U)", self.toggle_mini).grid(row=0, column=4)
        self._button(self.header, "✕", "숨기기 (종료는 트레이 메뉴)", lambda: self.set_visible(False)).grid(row=0, column=5)

        self.body = tk.Frame(self.root, bg=t["bg"])
        self.body.columnconfigure(0, weight=1)
        self.rows = tk.Frame(self.body, bg=t["bg"])
        self.rows.grid(row=0, column=0, sticky="nsew")
        self.restore = self._button(self.body, "↗", "일반 창으로 (Ctrl+Alt+U)", self.toggle_mini)

        grip = tk.Label(self.root, text="◢", font=self.f_small, bg=t["bg"], fg=t["track"], cursor="size_nw_se")
        grip.place(relx=1.0, rely=1.0, anchor="se")
        grip.bind("<ButtonPress-1>", self._resize_start)
        grip.bind("<B1-Motion>", self._resize_move)
        for w in (spacer, self.footer, self.header, self.body, self.rows):
            self._draggable(w)
        self._layout()

    def _button(self, parent, text, tip, command):
        t = self.theme
        b = tk.Label(parent, text=text, font=self.f_icon, bg=t["bg"], fg=t["fg"], padx=self.px(5), cursor="hand2")
        b.bind("<Button-1>", lambda e: command())
        b.bind("<Enter>", lambda e: b.configure(bg=t["hover"]))
        b.bind("<Leave>", lambda e: b.configure(bg=t["bg"]))
        b.tip = tip  # ponytail: 툴팁 팝업은 생략, 필요해지면 추가
        return b

    def _layout(self):
        mini = self.cfg["pip"]["mini"]
        self.header.pack_forget()
        self.body.pack_forget()
        if not mini:
            self.header.pack(fill="x", padx=self.px(8), pady=(self.px(6), 0))
        self.body.pack(fill="both", expand=True, padx=(self.px(10), self.px(14)),
                       pady=self.px(3) if mini else (self.px(4), self.px(10)))
        if mini:
            self.restore.grid(row=0, column=1, padx=(self.px(4), 0))
        else:
            self.restore.grid_forget()

    # ----- 이동·크기 조절 -----

    def _draggable(self, widget):
        widget.bind("<ButtonPress-1>", self._drag_start, add="+")
        widget.bind("<B1-Motion>", self._drag_move, add="+")

    def _drag_start(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag_move(self, e):
        dx, dy = self._drag
        self.root.geometry(f"+{e.x_root - dx}+{e.y_root - dy}")

    def _resize_start(self, e):
        self._rs = (e.x_root, e.y_root, self.root.winfo_width(), self.root.winfo_height())
        return "break"

    def _resize_move(self, e):
        x0, y0, w0, h0 = self._rs
        min_w, min_h = (self.px(200), self.px(36)) if self.cfg["pip"]["mini"] else (self.px(220), self.px(80))
        self.root.geometry(f"{max(min_w, w0 + e.x_root - x0)}x{max(min_h, h0 + e.y_root - y0)}")
        return "break"

    # ----- 표시·모드 -----

    def is_shown(self):
        return self.root.state() != "withdrawn"

    def set_visible(self, visible):
        if visible:
            self.root.deiconify()
            self.root.attributes("-topmost", self.cfg["pip"]["topmost"])
        else:
            self.save_rect()
            self.root.withdraw()
            self.close_settings()
        self.cfg["pip"]["visible"] = visible
        uc.save_config(self.cfg)

    def save_rect(self):
        if not self.is_shown():
            return
        r = self.root
        rect = [r.winfo_x(), r.winfo_y(), r.winfo_width(), r.winfo_height()]
        self.cfg["pip"]["mini_rect" if self.cfg["pip"]["mini"] else "rect"] = rect
        uc.save_config(self.cfg)

    def schedule_save(self):
        """이동·크기 조절·투명도처럼 연달아 바뀌는 값은 마지막 변경 0.5초 뒤 한 번만 저장."""
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(500, self._flush_save)

    def _flush_save(self):
        self._save_job = None
        if self.is_shown():
            self.save_rect()
        else:
            uc.save_config(self.cfg)

    def toggle_mini(self):
        self.save_rect()
        self.cfg["pip"]["mini"] = not self.cfg["pip"]["mini"]
        uc.save_config(self.cfg)
        self.close_settings()
        self.build()
        self.apply_mode()
        if not self.is_shown():
            self.set_visible(True)

    def apply_mode(self, initial=False):
        p = self.cfg["pip"]
        mini = p["mini"]
        rect = p["mini_rect"] if mini else p["rect"]
        if not (rect and _on_screen(rect)):
            x, y = (100, 100) if initial else (self.root.winfo_x(), self.root.winfo_y())
            agents = max(1, sum(self.cfg["agents"].values()))
            # 미니 기본 높이: 작업 표시줄 높이(48), agent가 둘이면 행 수만큼 늘림
            h = self.px(48 + 36 * (agents - 1)) if mini else self.px(130 + 50 * (agents - 1))
            rect = [x, y, self.px(300), h]
        self.root.geometry(f"{rect[2]}x{rect[3]}+{rect[0]}+{rect[1]}")
        if self._last_update:
            self.update(*self._last_update)

    def apply_opacity(self):
        self.root.attributes("-alpha", self.cfg["pip"]["opacity"] / 100)

    # ----- 설정 팝업 -----

    def toggle_settings(self):
        if self._popup:
            self.close_settings()
            return
        p = self.cfg["pip"]
        pop = self._popup = tk.Toplevel(self.root, bg="#ffffff", padx=self.px(12), pady=self.px(10),
                                        highlightthickness=1, highlightbackground="#c8c8c8")
        pop.overrideredirect(True)
        pop.attributes("-topmost", True)
        f = tkfont.Font(family="Segoe UI", size=10)

        top = tk.BooleanVar(value=p["topmost"])

        def on_top():
            p["topmost"] = top.get()
            self.root.attributes("-topmost", p["topmost"])
            uc.save_config(self.cfg)
        tk.Checkbutton(pop, text="항상 위", variable=top, command=on_top, font=f, bg="#ffffff",
                       activebackground="#ffffff").pack(anchor="w")

        tk.Label(pop, text="창 색상", font=f, bg="#ffffff").pack(anchor="w", pady=(self.px(8), self.px(4)))
        sw = tk.Frame(pop, bg="#ffffff")
        sw.pack(anchor="w")
        d = self.px(24)
        for name, hex_color in PALETTE:
            c = tk.Canvas(sw, width=d + 4, height=d + 4, bg="#ffffff", highlightthickness=0, cursor="hand2")
            selected = hex_color == p["color"]
            c.create_oval(2, 2, d + 2, d + 2, fill=hex_color or "#f3f3f3",
                          outline="#0067c0" if selected else "#8a8a8a", width=3 if selected else 1)
            if hex_color is None:
                c.create_line(8, d - 4, d - 4, 8, fill="#8a8a8a")  # 기본(배경색 없음) 표시
            c.bind("<Button-1>", lambda e, h=hex_color: self._set_color(h))
            c.pack(side="left", padx=1)

        tk.Label(pop, text="투명도", font=f, bg="#ffffff").pack(anchor="w", pady=(self.px(8), 0))

        def on_opacity(v):
            p["opacity"] = int(float(v))
            self.apply_opacity()
            self.schedule_save()  # 드래그 중 매번 파일을 쓰지 않게
        s = tk.Scale(pop, from_=uc.MIN_OPACITY, to=100, resolution=5, orient="horizontal", length=self.px(200),
                     command=on_opacity, bg="#ffffff", highlightthickness=0, showvalue=True)
        s.set(p["opacity"])
        s.pack(anchor="w")

        pop.update_idletasks()
        x = self.gear.winfo_rootx()
        y = self.gear.winfo_rooty() + self.gear.winfo_height() + 2
        pop.geometry(f"+{x}+{y}")
        # 닫기: 톱니 다시 누르기 / Esc / 위젯의 다른 곳 클릭 / (포커스를 받은 적이 있으면) 다른 앱으로 포커스 이동.
        # 테두리 없는 창은 포커스를 못 받을 때가 있어, 받기 전의 FocusOut으로 바로 닫히지 않게 한다.
        pop.had_focus = False
        pop.bind("<FocusIn>", lambda e: setattr(pop, "had_focus", True))
        pop.bind("<FocusOut>", lambda e: pop.after(150, self._close_if_unfocused))
        pop.bind("<Escape>", lambda e: self.close_settings())
        pop.focus_force()

    def _close_if_unfocused(self):
        pop = self._popup
        if not pop or not pop.had_focus:
            return
        focus = self.root.focus_get()
        if focus is None or not str(focus).startswith(str(pop)):
            self.close_settings()

    def _click_outside_popup(self, e):
        if self._popup and e.widget is not self.gear and not str(e.widget).startswith(str(self._popup)):
            self.close_settings()

    def close_settings(self):
        if self._popup:
            self._popup.destroy()
            self._popup = None

    def _set_color(self, hex_color):
        self.cfg["pip"]["color"] = hex_color
        uc.save_config(self.cfg)
        self.close_settings()
        self.build()
        if self._last_update:
            self.update(*self._last_update)
        self.toggle_settings()  # 선택 표시가 바뀐 팝업을 다시 연다

    # ----- 내용 -----

    def update(self, results, last, updated_at):
        self._last_update = (results, last, updated_at)
        t, mini = self.theme, self.cfg["pip"]["mini"]
        for w in self.rows.winfo_children():
            w.destroy()
        self.rows.columnconfigure(1, weight=1)
        self.rows.columnconfigure(0, minsize=self.px(74 if mini else 84))
        self.rows.columnconfigure(2, minsize=self.px(34 if mini else 40))
        self.rows.columnconfigure(3, minsize=self.px(72 if mini else 80))
        r = 0
        for agent, name in (("claude", "Claude"), ("codex", "Codex")):
            if agent not in results:
                continue
            res = results[agent]
            usage = res.get("usage") or (last.get(agent) or {}).get("usage")
            stale = "usage" not in res
            for label, key in (("5h", "five_hour"), ("week", "weekly")):
                pct, reset = usage[key] if usage else (None, None)
                self._row(r, f"{name} {label}", pct, reset, stale, mini)
                r += 1
            if res.get("error") and not mini:  # 미니에서는 오류 문구 대신 회색 막대로만
                tk.Label(self.rows, text=f"{name}: {res['error']}", font=self.f_small, bg=t["bg"], fg=t["sub"],
                         anchor="w").grid(row=r, column=0, columnspan=4, sticky="w")
                r += 1
        if r == 0:
            tk.Label(self.rows, text="트레이 메뉴에서 agent를 선택하세요", font=self.f_text, bg=t["bg"],
                     fg=t["sub"]).grid(row=0, column=0, columnspan=4, sticky="w")
        if self.footer.winfo_exists():
            self.footer.configure(text=f"갱신 {updated_at:%H:%M:%S}" if updated_at else "조회 중…")

    def _row(self, r, label, pct, reset, stale, mini):
        t = self.theme
        color = uc.COLOR_UNKNOWN if stale else uc.color_for(pct)
        pady = 0 if mini else self.px(2)
        name = tk.Label(self.rows, text=label, font=self.f_text, bg=t["bg"], fg=t["fg"], anchor="w")
        name.grid(row=r, column=0, sticky="w", pady=pady)
        bar = tk.Canvas(self.rows, height=self.px(6), bg=t["bg"], highlightthickness=0)
        bar.grid(row=r, column=1, sticky="ew", padx=self.px(6), pady=pady)

        def draw(e, c=bar):
            c.delete("all")
            h, w = self.px(6), e.width
            mid, rad = e.height / 2, h / 2
            c.create_line(rad, mid, max(rad, w - rad), mid, width=h, fill=t["track"], capstyle="round")
            if pct:
                c.create_line(rad, mid, rad + (w - 2 * rad) * pct / 100, mid, width=h, fill=color, capstyle="round")
        bar.bind("<Configure>", draw)
        tk.Label(self.rows, text=uc.fmt_pct(pct), font=self.f_bold, bg=t["bg"], fg=color,
                 anchor="e").grid(row=r, column=2, sticky="e", pady=pady)
        tk.Label(self.rows, text=("↻" + uc.fmt_time(reset)) if reset else "", font=self.f_small, bg=t["bg"],
                 fg=t["sub"], anchor="w").grid(row=r, column=3, sticky="w", padx=(self.px(6), 0), pady=pady)
        for w in (name, bar):
            self._draggable(w)


# ---------- 앱 ----------

class App:
    def __init__(self):
        import pystray
        self.pystray = pystray
        self.cfg = uc.load_config()
        self.last = uc.load_last()
        self.claude = uc.ClaudeFetcher()
        self.results = {}
        self.updated_at = None
        self.ui = queue.Queue()  # 다른 스레드 → 메인(tkinter) 스레드 작업
        self.wake = threading.Event()
        self.stopped = False
        self.hotkey_tid = None

        self.root = tk.Tk()
        self.root.report_callback_exception = self._ui_error  # UI 예외로 앱이 죽지 않게
        self.icon = pystray.Icon(uc.APP_NAME, render_icon(None), "AI Usage Widget", menu=self._menu())
        self.pip = Pip(self, self.root)
        if not self.cfg["pip"]["visible"]:
            self.root.withdraw()

    def post(self, fn):
        self.ui.put(fn)

    def _pump(self):
        try:
            while True:
                self.ui.get_nowait()()
        except queue.Empty:
            pass
        except Exception as e:  # 한 작업이 실패해도 펌프는 계속
            self._ui_error(type(e), e, None)
        if not self.stopped:
            self.root.after(100, self._pump)

    def _ui_error(self, exc_type, exc, tb):
        self.icon.title = uc.build_tooltip([f"오류: {exc_type.__name__}"])

    # ----- 트레이 메뉴 (pystray 스레드에서 호출 → 큐로 넘김) -----

    def _menu(self):
        item, menu = self.pystray.MenuItem, self.pystray.Menu
        agents, pip = self.cfg["agents"], self.cfg["pip"]
        return menu(
            item("Claude", lambda: self.post(lambda: self._toggle("claude")), checked=lambda _: agents["claude"]),
            item("Codex", lambda: self.post(lambda: self._toggle("codex")), checked=lambda _: agents["codex"]),
            menu.SEPARATOR,
            # default=True → 아이콘 좌클릭 시 실행
            item("PiP 보기", lambda: self.post(lambda: self.pip.set_visible(not self.pip.is_shown())),
                 checked=lambda _: pip["visible"], default=True),
            item(lambda _: "아이콘: 주간 보기" if self.cfg["view"] == "five_hour" else "아이콘: 5시간 보기",
                 lambda: self.post(self._toggle_view)),
            item("지금 새로고침", lambda: self.refresh_now()),
            item("시작 시 실행", lambda: set_autostart(not autostart_enabled()), checked=lambda _: autostart_enabled()),
            item("종료", lambda: self.post(self.quit)),
        )

    def _toggle(self, agent):
        self.cfg["agents"][agent] = not self.cfg["agents"][agent]
        uc.save_config(self.cfg)
        self.refresh_now()

    def _toggle_view(self):
        self.cfg["view"] = "weekly" if self.cfg["view"] == "five_hour" else "five_hour"
        uc.save_config(self.cfg)
        self._draw()

    def refresh_now(self):
        self.wake.set()

    # ----- 조회 (작업 스레드) -----

    def _worker(self):
        while not self.stopped:
            try:
                agents = dict(self.cfg["agents"])
                results = {}
                if agents["claude"]:
                    results["claude"] = self.claude.get()
                if agents["codex"]:
                    results["codex"] = uc.read_codex()
                self.post(lambda r=results: self._apply(r))
            except Exception as e:  # 루프가 죽으면 값이 멈춘 채 남으므로 사유를 툴팁으로
                self.post(lambda n=type(e).__name__: setattr(self.icon, "title", uc.build_tooltip([f"오류: {n}"])))
            self.wake.wait(self.cfg["interval"])
            self.wake.clear()

    def _apply(self, results):
        lines = []
        for agent, name in (("claude", "Claude"), ("codex", "Codex")):
            if agent in results:
                lines.append(uc.format_line(name, results[agent], self.last.get(agent)))
                if "usage" in results[agent]:
                    self.last[agent] = results[agent]
        if any("usage" in r for r in results.values()):
            uc.save_last(self.last)
        self.results, self.updated_at = results, datetime.now()
        if lines:
            lines.append(f"갱신 {self.updated_at:%H:%M:%S}")
        self.icon.title = uc.build_tooltip(lines)
        self._draw()

    def _draw(self):
        pct, stale = uc.icon_state(self.results, self.last, self.cfg["view"])
        self.icon.icon = render_icon(pct, stale, VIEW_LABELS[self.cfg["view"]])
        self.pip.update(self.results, self.last, self.updated_at)

    # ----- 전역 단축키 Ctrl+Alt+U (자체 메시지 루프 스레드) -----

    def _hotkey(self):
        self.hotkey_tid = kernel32.GetCurrentThreadId()
        # 다른 앱이 이미 쓰는 조합이면 등록 실패 → 버튼으로만 전환
        if not user32.RegisterHotKey(None, 1, 0x2 | 0x1 | 0x4000, 0x55):  # CTRL|ALT|NOREPEAT, 'U'
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                self.post(self.pip.toggle_mini)
        user32.UnregisterHotKey(None, 1)

    # ----- 시작·종료 -----

    def run(self):
        self.results = {a: {"error": "조회 중"} for a, on in self.cfg["agents"].items() if on}
        self._draw()  # 첫 조회 전: 저장된 직전 값을 회색으로 먼저 표시
        self.icon.run_detached()
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._hotkey, daemon=True).start()
        self.root.after(100, self._pump)
        self.root.mainloop()

    def quit(self):
        self.stopped = True
        try:
            self.pip.save_rect()
            self.wake.set()
            if self.hotkey_tid:
                user32.PostThreadMessageW(self.hotkey_tid, 0x0012, 0, 0)  # WM_QUIT
            self.icon.stop()
        finally:
            self.root.destroy()


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 고해상도 화면에서 흐리지 않게 (Tk 생성 전에)
    except (AttributeError, OSError):
        pass
    if acquire_single_instance():
        App().run()
