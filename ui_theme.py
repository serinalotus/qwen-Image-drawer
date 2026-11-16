"""千问图像工作台 —— 主题与通用控件。

集中定义配色、字体与 ttk 样式，其他 UI 模块只引用这里，保证风格一致。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# ---------------------------------------------------------------- 配色

COLORS = {
    "bg": "#14161b",
    "panel": "#191c23",
    "card": "#1e222b",
    "card_hover": "#242936",
    "border": "#2b3040",
    "border_strong": "#3a4154",
    "text": "#e7e9ee",
    "text_dim": "#b9c0cd",
    "muted": "#8b93a3",
    "accent": "#6c5ce7",
    "accent_hover": "#7d6ff0",
    "accent_press": "#5a4bd4",
    "accent_soft": "#2a2450",
    "ok": "#37d67a",
    "warn": "#f5b74e",
    "err": "#ff6b6b",
    "err_bg": "#2b1b1f",
    "ok_bg": "#16281f",
    "input_bg": "#161922",
    "canvas_bg": "#101218",
    "thumb_border": "#3a4154",
}


def make_fonts(root: tk.Misc) -> dict:
    """按 DPI 生成字体表。"""
    family = "Microsoft YaHei UI"
    mono = "Consolas"
    return {
        "title": (family, 14, "bold"),
        "subtitle": (family, 9),
        "card_title": (family, 10, "bold"),
        "body": (family, 10),
        "small": (family, 9),
        "tiny": (family, 8),
        "button": (family, 10),
        "button_big": (family, 11, "bold"),
        "mono": (mono, 9),
        "mono_small": (mono, 8),
    }


# ---------------------------------------------------------------- ttk 样式

def setup_styles(root: tk.Misc) -> dict:
    fonts = make_fonts(root)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:  # pragma: no cover - 极少见
        pass

    c = COLORS
    style.configure(".", background=c["bg"], foreground=c["text"], font=fonts["body"], borderwidth=0)

    # 通用
    style.configure("TFrame", background=c["bg"])
    style.configure("Panel.TFrame", background=c["panel"])
    style.configure("Card.TFrame", background=c["card"])
    style.configure("TLabel", background=c["bg"], foreground=c["text"], font=fonts["body"])
    style.configure("Panel.TLabel", background=c["panel"], foreground=c["text"])
    style.configure("Card.TLabel", background=c["card"], foreground=c["text"])
    style.configure("CardDim.TLabel", background=c["card"], foreground=c["muted"], font=fonts["small"])
    style.configure("CardAccent.TLabel", background=c["card"], foreground=c["accent"], font=fonts["small"])
    style.configure("Dim.TLabel", background=c["bg"], foreground=c["muted"], font=fonts["small"])
    style.configure("Status.TLabel", background=c["panel"], foreground=c["muted"], font=fonts["small"])

    # 主按钮
    style.configure(
        "Accent.TButton",
        background=c["accent"],
        foreground="#ffffff",
        font=fonts["button_big"],
        padding=(16, 10),
        borderwidth=0,
        focusthickness=0,
        relief="flat",
    )
    style.map(
        "Accent.TButton",
        background=[("disabled", "#3c3a55"), ("pressed", c["accent_press"]), ("active", c["accent_hover"])],
        foreground=[("disabled", "#8d8aa8")],
    )

    # 次级按钮 / 工具栏按钮
    style.configure(
        "Ghost.TButton",
        background=c["card"],
        foreground=c["text_dim"],
        font=fonts["small"],
        padding=(10, 6),
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Ghost.TButton",
        background=[("disabled", c["card"]), ("pressed", c["border_strong"]), ("active", c["card_hover"])],
        foreground=[("disabled", c["muted"]), ("active", c["text"])],
    )
    style.configure("Toolbar.TButton", background=c["panel"], foreground=c["text_dim"],
                    font=fonts["small"], padding=(8, 5), borderwidth=0, relief="flat")
    style.map("Toolbar.TButton",
              background=[("disabled", c["panel"]), ("active", c["card_hover"]), ("pressed", c["border_strong"])],
              foreground=[("disabled", "#5d6373"), ("active", c["text"])])

    # 输入控件
    style.configure(
        "TEntry",
        fieldbackground=c["input_bg"],
        foreground=c["text"],
        insertcolor=c["text"],
        bordercolor=c["border"],
        lightcolor=c["border"],
        darkcolor=c["border"],
        padding=6,
        font=fonts["body"],
    )
    style.map("TEntry", bordercolor=[("focus", c["accent"])], fieldbackground=[("disabled", c["panel"])],
              foreground=[("disabled", c["muted"])])

    style.configure(
        "TCombobox",
        fieldbackground=c["input_bg"],
        background=c["card"],
        foreground=c["text"],
        arrowcolor=c["muted"],
        bordercolor=c["border"],
        lightcolor=c["border"],
        darkcolor=c["border"],
        padding=5,
        font=fonts["body"],
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", c["input_bg"]), ("disabled", c["panel"])],
        foreground=[("disabled", c["muted"])],
        bordercolor=[("focus", c["accent"])],
        arrowcolor=[("active", c["text"])],
    )
    root.option_add("*TCombobox*Listbox.background", c["card"])
    root.option_add("*TCombobox*Listbox.foreground", c["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    root.option_add("*TCombobox*Listbox.font", fonts["body"])

    # Checkbutton / Radiobutton
    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=c["card"], foreground=c["text_dim"], font=fonts["small"],
                        focusthickness=0, indicatorcolor=c["input_bg"], bordercolor=c["border"])
        style.map(
            name,
            background=[("active", c["card"])],
            foreground=[("disabled", c["muted"]), ("active", c["text"])],
            indicatorcolor=[("selected", c["accent"]), ("pressed", c["accent_hover"])],
        )

    style.configure("TSeparator", background=c["border"])

    style.configure(
        "TScrollbar",
        background=c["card"],
        troughcolor=c["bg"],
        bordercolor=c["bg"],
        arrowcolor=c["muted"],
        width=10,
    )
    style.map("TScrollbar", background=[("active", c["border_strong"])])

    style.configure(
        "TProgressbar",
        background=c["accent"],
        troughcolor=c["card"],
        bordercolor=c["card"],
        lightcolor=c["accent"],
        darkcolor=c["accent"],
        thickness=4,
    )

    style.configure("TSpinbox", fieldbackground=c["input_bg"], foreground=c["text"], arrowcolor=c["muted"],
                    bordercolor=c["border"], padding=5, font=fonts["body"])
    style.map("TSpinbox", fieldbackground=[("disabled", c["panel"])], bordercolor=[("focus", c["accent"])])

    return {"colors": COLORS, "fonts": fonts, "style": style}


# ---------------------------------------------------------------- 通用小控件

class Card(tk.Frame):
    """带 1px 描边的卡片容器；set_active 时整体描边变强调色。"""

    def __init__(self, master, theme: dict, **kwargs):
        c = theme["colors"]
        super().__init__(master, bg=c["card"], highlightbackground=c["border"],
                         highlightthickness=1, bd=0, **kwargs)
        self.theme = theme

    def set_active(self, active: bool) -> None:
        c = self.theme["colors"]
        try:
            self.configure(highlightbackground=c["accent"] if active else c["border"],
                           highlightthickness=1)
        except tk.TclError:
            pass

    def body(self) -> tk.Frame:
        """卡片内部留白区域。"""
        frame = tk.Frame(self, bg=self.theme["colors"]["card"])
        frame.pack(fill="both", expand=True, padx=12, pady=10)
        return frame


def card_header(parent: tk.Frame, theme: dict, index: int, title: str, extra: str = "") -> tk.Frame:
    """卡片标题行：序号徽标 + 标题 + 右侧小字。"""
    c = theme["colors"]
    fonts = theme["fonts"]
    row = tk.Frame(parent, bg=c["card"])
    row.pack(fill="x", pady=(0, 8))

    badge = tk.Label(row, text=str(index), bg=c["accent_soft"], fg=c["accent"],
                     font=fonts["tiny"], width=2, height=1)
    badge.pack(side="left", padx=(0, 7))
    title_label = tk.Label(row, text=title, bg=c["card"], fg=c["text"], font=fonts["card_title"])
    title_label.pack(side="left")
    row.badge = badge            # type: ignore[attr-defined]
    row.title_label = title_label  # type: ignore[attr-defined]
    if extra:
        tk.Label(row, text=extra, bg=c["card"], fg=c["muted"], font=fonts["tiny"]).pack(side="right")
    return row


def flat_button(parent: tk.Misc, theme: dict, text: str, command=None, bg=None, fg=None,
                font_key: str = "small", padx: int = 10, pady: int = 5, **kwargs) -> tk.Label:
    """自绘扁平按钮（tk.Label 实现），悬停变色，避免 ttk 主题差异。"""
    c = theme["colors"]
    normal_bg = bg or c["card"]
    hover_bg = c["card_hover"] if normal_bg == c["card"] else c["border_strong"]
    label = tk.Label(parent, text=text, bg=normal_bg, fg=fg or c["text_dim"],
                     font=theme["fonts"][font_key], padx=padx, pady=pady, cursor="hand2", **kwargs)
    label._normal_bg = normal_bg  # type: ignore[attr-defined]

    def on_enter(_event):
        if str(label.cget("state")) != "disabled":
            label.configure(bg=hover_bg)

    def on_leave(_event):
        label.configure(bg=label._normal_bg)  # type: ignore[attr-defined]

    def on_click(_event):
        if str(label.cget("state")) != "disabled" and command:
            command()

    label.bind("<Enter>", on_enter)
    label.bind("<Leave>", on_leave)
    label.bind("<Button-1>", on_click)
    return label


def set_enabled(widget: tk.Widget, enabled: bool, theme: dict) -> None:
    """统一切换启用状态与颜色。"""
    c = theme["colors"]
    try:
        if isinstance(widget, (tk.Entry, tk.Text)):
            widget.configure(state="normal" if enabled else "disabled",
                             fg=c["text"] if enabled else c["muted"])
        elif isinstance(widget, tk.Label) and hasattr(widget, "_normal_bg"):
            widget.configure(state="normal" if enabled else "disabled",
                             fg=c["text_dim"] if enabled else "#5d6373")
        else:
            widget.configure(state="normal" if enabled else "disabled")
    except tk.TclError:
        pass


# ---------------------------------------------------------------- 小工具

def fmt_elapsed(seconds) -> str:
    """秒数 → 人类可读耗时（不足 10 秒保留一位小数）。"""
    try:
        value = float(seconds or 0)
    except (TypeError, ValueError):
        return "—"
    if value < 0:
        return "—"
    if value < 10:
        return f"{value:.1f} 秒"
    if value < 60:
        return f"{value:.0f} 秒"
    minutes, secs = divmod(int(round(value)), 60)
    return f"{minutes} 分 {secs:02d} 秒"


def enable_dpi_awareness() -> None:
    """让进程按系统 DPI 渲染：字更清晰、窗口尺寸与截图坐标一致（失败静默）。"""
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001 - 老系统没有 shcore
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass


def enable_dark_titlebar(window: tk.Misc) -> None:
    """Windows 10/11 上把标题栏切成深色（失败静默忽略）。"""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = window.winfo_id()
        # Tk 的 winfo_id 有时是内部子窗口，标题栏属于 GA_ROOT 祖先窗口
        root_hwnd = user32.GetAncestor(hwnd, 2) or user32.GetParent(hwnd) or hwnd
        for target in {root_hwnd, hwnd}:
            for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE 的新旧编号
                flag = ctypes.c_int(1)
                try:
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        wintypes.HWND(target), attribute, ctypes.byref(flag),
                        ctypes.sizeof(flag))
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass


class SlimScrollbar(tk.Canvas):
    """自绘细滚动条：内容放得下时完全隐藏，溢出时才显示滑块。"""

    MIN_THUMB = 28

    def __init__(self, master, theme: dict, *, command=None, width: int = 12):
        c = theme["colors"]
        super().__init__(master, width=width, bg=c["bg"], highlightthickness=0, bd=0)
        self.colors = c
        self._command = command
        self._first = 0.0
        self._last = 1.0
        self._drag_dy = None
        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", lambda _e: self._redraw(True))
        self.bind("<Leave>", lambda _e: self._redraw(False))

    def set(self, first, last) -> None:  # noqa: A003 - 与 tk 滚动条协议同名
        self._first, self._last = float(first), float(last)
        self._redraw()

    def _thumb_span(self):
        height = self.winfo_height()
        span = self._last - self._first
        if height <= 1 or span >= 0.999:
            return None
        top = max(0, min(int(round(self._first * height)), height - self.MIN_THUMB))
        size = max(self.MIN_THUMB, int(round(span * height)))
        return top, min(height, top + size)

    def _redraw(self, hover=None) -> None:
        self.delete("thumb")
        span = self._thumb_span()
        if span is None:
            return
        top, bottom = span
        if self._drag_dy is not None or hover is True:
            color = self.colors["accent"]
        else:
            color = self.colors["border_strong"]
        self.create_rectangle(3, top + 1, self.winfo_width() - 3, bottom - 1,
                              fill=color, outline="", tags="thumb")

    def _on_press(self, event) -> None:
        span = self._thumb_span()
        if span is None or not self._command:
            return
        top, bottom = span
        if top <= event.y <= bottom:
            self._drag_dy = event.y - top
        else:
            height = max(1, self.winfo_height())
            self._command("moveto", max(0.0, min(1.0, (event.y - self.MIN_THUMB / 2) / height)))
            self._drag_dy = self.MIN_THUMB / 2
        self._redraw()

    def _on_drag(self, event) -> None:
        if self._drag_dy is None or not self._command:
            return
        height = max(1, self.winfo_height())
        self._command("moveto", max(0.0, min(1.0, (event.y - self._drag_dy) / height)))

    def _on_release(self, _event) -> None:
        self._drag_dy = None
        self._redraw()
