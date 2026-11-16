"""千问图像工作台 —— 左侧表单面板。

包含：提示词、反向提示词、参考图、输出设置、生成/取消按钮。
对外接口：
    panel.get_payload()        -> dict        读取当前表单值
    panel.set_busy(True/False)                 生成中禁用交互
    panel.apply_settings(settings)             地域/协议等设置变化后刷新提示
    panel.set_status(text, kind)               底部提示
"""

from __future__ import annotations

import os
import random
import tkinter as tk
from tkinter import filedialog
from typing import Callable, Optional

from PIL import Image, ImageTk

import api
import meta
import ui_theme
from ui_theme import COLORS, card_header, flat_button

REF_THUMB = 74          # 参考图缩略图边长（逻辑像素）
REF_COLS = 4


# ---------------------------------------------------------------- 主按钮

class PrimaryButton(tk.Frame):
    """主操作按钮：纯 tk 绘制，悬停/按下/禁用三态。"""

    def __init__(self, master, theme: dict, text: str, command: Callable[[], None],
                 bg: Optional[str] = None, font_key: str = "button_big", height: int = 40,
                 width: int = 0):
        self.theme = theme
        self.colors = theme["colors"]
        self._bg = bg or self.colors["accent"]
        self._command = command
        self._enabled = True
        super().__init__(master, bg=self._bg, height=height, width=width, bd=0,
                         highlightthickness=0, cursor="hand2")
        self.pack_propagate(False)
        self.label = tk.Label(self, text=text, bg=self._bg, fg="#ffffff",
                              font=theme["fonts"][font_key], cursor="hand2")
        self.label.pack(expand=True, fill="both")
        for widget in (self, self.label):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<Button-1>", self._on_press)
            widget.bind("<ButtonRelease-1>", self._on_release)

    # -- 交互
    def _on_enter(self, _e=None):
        if self._enabled:
            self._paint(self._hover_color())

    def _on_leave(self, _e=None):
        if self._enabled:
            self._paint(self._bg)

    def _on_press(self, _e=None):
        if self._enabled:
            self._paint(self._press_color())

    def _on_release(self, _e=None):
        if not self._enabled:
            return
        self._paint(self._hover_color())
        if self._command:
            self._command()

    def _hover_color(self) -> str:
        if self._bg == self.colors["accent"]:
            return self.colors["accent_hover"]
        return self.colors["card_hover"]

    def _press_color(self) -> str:
        if self._bg == self.colors["accent"]:
            return self.colors["accent_press"]
        return self.colors["border_strong"]

    def _paint(self, color: str) -> None:
        self.configure(bg=color)
        self.label.configure(bg=color)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        color = self._bg if enabled else "#3c3a55"
        self._paint(color)
        self.configure(cursor="hand2" if enabled else "arrow")
        self.label.configure(cursor="hand2" if enabled else "arrow",
                             fg="#ffffff" if enabled else "#8d8aa8")

    def set_text(self, text: str) -> None:
        self.label.configure(text=text)


# ---------------------------------------------------------------- 可滚动容器

class ScrollArea(tk.Frame):
    """竖向滚动区域：Canvas + 内部 Frame + 滚轮绑定。"""

    def __init__(self, master, theme: dict, width: int):
        self.theme = theme
        c = theme["colors"]
        super().__init__(master, bg=c["bg"], width=width)
        self.canvas = tk.Canvas(self, bg=c["bg"], highlightthickness=0, bd=0, width=width)
        self.scrollbar = ui_theme.SlimScrollbar(self, theme, command=self.canvas.yview, width=12)
        self.inner = tk.Frame(self.canvas, bg=c["bg"])
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._on_wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._fit_width()

    def _on_canvas_configure(self, _event=None):
        self._fit_width()

    def _fit_width(self):
        width = self.canvas.winfo_width()
        if width > 1:
            self.canvas.itemconfigure(self._window, width=width)

    def _on_wheel(self, event):
        if self.inner.winfo_height() <= self.canvas.winfo_height():
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)) or (-1 if event.delta > 0 else 1), "units")

    def scroll_to_top(self):
        self.canvas.yview_moveto(0)


# ---------------------------------------------------------------- 表单面板

class FormPanel(tk.Frame):
    def __init__(self, master, theme: dict, *, on_generate: Callable[[], None],
                 on_cancel: Callable[[], None], settings: dict, on_open_settings: Callable[[], None],
                 on_refresh_models: Optional[Callable[[], None]] = None,
                 on_save_prompt: Optional[Callable[[], None]] = None,
                 on_open_prompt_library: Optional[Callable[[], None]] = None):
        self.theme = theme
        self.colors = theme["colors"]
        self.fonts = theme["fonts"]
        self.settings = settings
        self.on_generate = on_generate
        self.on_cancel = on_cancel
        self.on_open_settings = on_open_settings
        self.on_refresh_models = on_refresh_models
        self.on_save_prompt = on_save_prompt
        self.on_open_prompt_library = on_open_prompt_library

        super().__init__(master, bg=self.colors["panel"], width=452)
        self.pack_propagate(False)

        self.references: list[dict] = []
        self._ref_photos: list[ImageTk.PhotoImage] = []
        self._busy = False

        # 底部固定操作区（先占位，滚动区再吃掉剩余高度）
        self._build_action_bar()

        # 顶部滚动区
        self.scroll = ScrollArea(self, theme, width=440)
        self.scroll.pack(fill="both", expand=True, padx=(8, 2), pady=(12, 6))
        body = self.scroll.inner

        self._build_prompt_card(body)
        self._build_negative_card(body)
        self._build_reference_card(body)
        self._build_output_card(body)
        tk.Frame(body, bg=self.colors["bg"], height=6).pack(fill="x")

        self._register_focus_rings()
        self._bind_shortcuts()

    # ------------------------------------------------------------ 卡片 1：提示词
    def _build_prompt_card(self, parent: tk.Frame) -> None:
        c, f = self.colors, self.fonts
        card = ui_theme.Card(parent, self.theme)
        card.pack(fill="x", pady=(0, 10))
        inner = card.body()

        header = card_header(inner, self.theme, 1, "提示词")
        self.prompt_count = tk.Label(header, text="0 字符", bg=c["card"], fg=c["muted"], font=f["tiny"])
        self.prompt_count.pack(side="right")

        self.prompt_wrap = wrap = tk.Frame(inner, bg=c["card"], highlightbackground=c["border"],
                                           highlightthickness=1)
        wrap.pack(fill="x")
        self.prompt_text = tk.Text(wrap, height=6, bg=c["input_bg"], fg=c["text"], insertbackground=c["text"],
                                   font=f["body"], bd=0, highlightthickness=0, wrap="word", padx=10, pady=8,
                                   selectbackground=c["accent"], selectforeground="#ffffff", relief="flat")
        self.prompt_text.pack(fill="both", expand=True)
        self.prompt_text.insert("1.0", "描述你想生成的画面，例如：清晨的江南水乡，薄雾漫过石桥，乌篷船缓缓划过，柔和的侧逆光，电影质感……")
        self.prompt_text.configure(fg=c["muted"])
        self._prompt_placeholder = True
        self.prompt_text.bind("<FocusIn>", self._clear_placeholder)
        self.prompt_text.bind("<KeyRelease>", lambda _e: self._update_prompt_count())
        self.prompt_text.bind("<Button-1>", self._clear_placeholder)
        self.prompt_card = card
        self.prompt_header = header

        foot = tk.Frame(inner, bg=c["card"])
        foot.pack(fill="x", pady=(6, 0))
        self.prompt_hint = tk.Label(foot, text=f"建议 ≤ {meta.LIMITS['prompt_max_tokens_hint']} token",
                                    bg=c["card"], fg=c["muted"], font=f["tiny"])
        self.prompt_hint.pack(side="left")
        flat_button(foot, self.theme, "清空", self._clear_prompt, fg=c["muted"], pady=2, padx=6).pack(side="right")
        self.prompt_save_btn = flat_button(foot, self.theme, "保存提示词", self._save_prompt,
                                           fg=c["accent"], pady=2, padx=6)
        self.prompt_save_btn.pack(side="right")
        self.prompt_lib_btn = flat_button(foot, self.theme, "提示词库", self._open_prompt_library,
                                          fg=c["muted"], pady=2, padx=6)
        self.prompt_lib_btn.pack(side="right")

    def _save_prompt(self) -> None:
        if self.on_save_prompt:
            self.on_save_prompt()

    def _open_prompt_library(self) -> None:
        if self.on_open_prompt_library:
            self.on_open_prompt_library()

    def set_negative(self, text: str) -> None:
        self.negative_text.configure(state="normal")
        self.negative_text.delete("1.0", "end")
        self.negative_text.insert("1.0", text)

    def get_negative(self) -> str:
        return self.negative_text.get("1.0", "end").strip()

    def _bind_focus_ring(self, container: tk.Frame, widget: tk.Widget,
                         card=None, header=None) -> None:
        """输入框获得焦点时：输入框描边 + 整张卡片描边 + 序号徽标 一起变强调色。"""
        c = self.colors

        def on_focus(_event=None):
            try:
                container.configure(highlightbackground=c["accent"],
                                    highlightcolor=c["accent"], highlightthickness=2)
            except tk.TclError:
                pass
            if card is not None:
                card.set_active(True)
            if header is not None:
                try:
                    header.badge.configure(bg=c["accent"], fg="#ffffff")
                except tk.TclError:
                    pass

        def on_blur(_event=None):
            try:
                container.configure(highlightbackground=c["border"], highlightthickness=1)
            except tk.TclError:
                pass
            if card is not None:
                card.set_active(False)
            if header is not None:
                try:
                    header.badge.configure(bg=c["accent_soft"], fg=c["accent"])
                except tk.TclError:
                    pass

        widget.bind("<FocusIn>", on_focus, add="+")
        widget.bind("<FocusOut>", on_blur, add="+")
        return on_focus

    def _clear_placeholder(self, _event=None):
        if getattr(self, "_prompt_placeholder", False):
            self._prompt_placeholder = False
            self.prompt_text.delete("1.0", "end")
            self.prompt_text.configure(fg=self.colors["text"])

    def _prompt_value(self) -> str:
        if getattr(self, "_prompt_placeholder", False):
            return ""
        return self.prompt_text.get("1.0", "end").strip()

    def _update_prompt_count(self) -> None:
        text = self._prompt_value()
        count = len(text)
        hint = f"{count} 字符"
        if count:
            estimate = int(count * 1.6)
            hint += f" · 约 {estimate} token"
            limit = meta.LIMITS["prompt_max_tokens_hint"]
            self.prompt_count.configure(fg=self.colors["warn"] if estimate > limit else self.colors["muted"])
        else:
            self.prompt_count.configure(fg=self.colors["muted"])
        self.prompt_count.configure(text=hint)

    def _clear_prompt(self) -> None:
        self._prompt_placeholder = False
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.configure(fg=self.colors["text"])
        self._update_prompt_count()
        self.prompt_text.focus_set()

    # ------------------------------------------------------------ 卡片 2：反向提示词
    def _build_negative_card(self, parent: tk.Frame) -> None:
        c, f = self.colors, self.fonts
        card = ui_theme.Card(parent, self.theme)
        card.pack(fill="x", pady=(0, 10))
        inner = card.body()

        header = card_header(inner, self.theme, 2, "反向提示词")
        self.negative_badge = tk.Label(header, text="3.0 系列支持", bg=c["card"], fg=c["muted"], font=f["tiny"])
        self.negative_badge.pack(side="right")

        self.negative_wrap = wrap = tk.Frame(inner, bg=c["card"], highlightbackground=c["border"],
                                             highlightthickness=1)
        wrap.pack(fill="x")
        self.negative_text = tk.Text(wrap, height=3, bg=c["input_bg"], fg=c["text"], insertbackground=c["text"],
                                     font=f["body"], bd=0, highlightthickness=0, wrap="word", padx=10, pady=8,
                                     selectbackground=c["accent"], selectforeground="#ffffff", relief="flat")
        self.negative_text.pack(fill="both", expand=True)
        self.negative_card = card
        self.negative_header = header

        foot = tk.Frame(inner, bg=c["card"])
        foot.pack(fill="x", pady=(6, 0))
        self.negative_hint = tk.Label(foot, text="不希望出现的内容，例如：模糊、畸变、多余手指、水印、低分辨率",
                                      bg=c["card"], fg=c["muted"], font=f["tiny"])
        self.negative_hint.pack(side="left")

    def _negative_value(self) -> str:
        if str(self.negative_text.cget("state")) == "disabled":
            return ""
        return self.negative_text.get("1.0", "end").strip()

    # ------------------------------------------------------------ 卡片 3：参考图
    def _build_reference_card(self, parent: tk.Frame) -> None:
        c, f = self.colors, self.fonts
        card = ui_theme.Card(parent, self.theme)
        card.pack(fill="x", pady=(0, 10))
        inner = card.body()

        header = card_header(inner, self.theme, 3, "参考图")
        self.ref_count = tk.Label(header, text="0 / 3", bg=c["card"], fg=c["muted"], font=f["tiny"])
        self.ref_count.pack(side="right")
        self.ref_card = card
        self.ref_header = header

        self.ref_area = tk.Frame(inner, bg=c["card"])
        self.ref_area.pack(fill="x")

        self.ref_grid = tk.Frame(self.ref_area, bg=c["card"])
        self.ref_grid.pack(fill="x")

        self.drop_zone = tk.Frame(self.ref_area, bg=c["input_bg"], highlightbackground=c["border"],
                                  highlightthickness=1, cursor="hand2", takefocus=1)
        self.drop_zone.pack(fill="x", pady=(0, 6), before=self.ref_grid)
        self.drop_icon = tk.Label(self.drop_zone, text="＋", bg=c["input_bg"], fg=c["accent"], font=(f["body"][0], 18))
        self.drop_icon.pack(pady=(10, 0))
        self.drop_main = tk.Label(self.drop_zone, text="拖拽图片到窗口任意位置，或点击选择",
                                  bg=c["input_bg"], fg=c["text_dim"], font=f["small"],
                                  wraplength=372, justify="center")
        self.drop_main.pack(pady=(2, 0))
        self.drop_sub = tk.Label(self.drop_zone,
                                 text="也可以在提示词框外按 Ctrl+V 粘贴\nPNG / JPG / WebP / BMP · 单张 ≤ 10MB",
                                 bg=c["input_bg"], fg=c["muted"], font=f["tiny"],
                                 wraplength=372, justify="center")
        self.drop_sub.pack(pady=(2, 10))
        def _on_drop_click(_event=None):
            try:
                self.drop_zone.focus_set()
            except tk.TclError:
                pass
            self.choose_references()

        for widget in (self.drop_zone, self.drop_icon, self.drop_main, self.drop_sub):
            widget.bind("<Button-1>", _on_drop_click)
        self._bind_focus_ring(self.drop_zone, self.drop_zone)

        self.mode_hint = tk.Label(inner, text="文生图｜加入 1~3 张参考图即为图生图",
                                  bg=c["card"], fg=c["muted"], font=f["tiny"], anchor="w")
        self.mode_hint.pack(fill="x", pady=(6, 0))

    def _register_focus_rings(self) -> None:
        self._bind_focus_ring(self.prompt_wrap, self.prompt_text,
                              card=getattr(self, "prompt_card", None),
                              header=getattr(self, "prompt_header", None))
        self._bind_focus_ring(self.negative_wrap, self.negative_text,
                              card=getattr(self, "negative_card", None),
                              header=getattr(self, "negative_header", None))
        self._bind_focus_ring(self.drop_zone, self.drop_zone,
                              card=getattr(self, "ref_card", None),
                              header=getattr(self, "ref_header", None))

    def choose_references(self) -> None:
        if self._busy:
            return
        max_refs = meta.get_model(self.current_model_id())["max_refs"]
        remaining = max_refs - len(self.references)
        if remaining <= 0:
            self.set_status(f"{meta.get_model(self.current_model_id())['name']} 最多 {max_refs} 张参考图", "warn")
            return
        paths = filedialog.askopenfilenames(
            title="选择参考图",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"), ("所有文件", "*.*")],
        )
        if not paths:
            return
        for path in list(paths)[:remaining]:
            self.add_reference(path)
        if len(paths) > remaining:
            self.set_status(f"只添加了前 {remaining} 张，已达上限", "warn")

    def add_reference(self, path: str) -> bool:
        try:
            item = api.encode_reference(path)
        except ValueError as exc:
            self.set_status(str(exc), "err")
            return False
        item["thumb"] = self._make_thumb(item["path"])
        self.references.append(item)
        self._refresh_refs()
        self.set_status(f"已添加参考图：{item['name']}", "ok")
        return True

    def _make_thumb(self, path: str) -> Image.Image:
        try:
            image = Image.open(path)
            image.load()
            return image.convert("RGB")
        except Exception:  # noqa: BLE001
            return Image.new("RGB", (REF_THUMB, REF_THUMB), self.colors["card"])

    def remove_reference(self, index: int) -> None:
        if 0 <= index < len(self.references):
            removed = self.references.pop(index)
            self._refresh_refs()
            self.set_status(f"已移除：{removed.get('name', '参考图')}", "info")

    def _refresh_refs(self) -> None:
        c, f = self.colors, self.fonts
        for child in self.ref_grid.winfo_children():
            child.destroy()
        self._ref_photos.clear()

        model = meta.get_model(self.current_model_id())
        max_refs = model["max_refs"]
        self.ref_count.configure(text=f"{len(self.references)} / {max_refs}")
        self.mode_hint.configure(text=("图生图 · 将基于参考图生成" if self.references
                                       else "文生图｜加入参考图即为图生图"))

        for index, item in enumerate(self.references):
            row, col = divmod(index, REF_COLS)
            tile = tk.Frame(self.ref_grid, bg=c["input_bg"], highlightbackground=c["border"],
                            highlightthickness=1, width=REF_THUMB, height=REF_THUMB)
            tile.grid(row=row, column=col, padx=(0, 6), pady=(0, 6))
            tile.grid_propagate(False)

            thumb = item["thumb"].copy()
            thumb.thumbnail((REF_THUMB, REF_THUMB), Image.LANCZOS)
            photo = ImageTk.PhotoImage(thumb)
            self._ref_photos.append(photo)
            label = tk.Label(tile, image=photo, bg=c["input_bg"], bd=0)
            label.place(relx=0.5, rely=0.5, anchor="center")

            remove = tk.Label(tile, text="×", bg="#000000", fg="#ffffff", font=f["tiny"],
                              width=2, cursor="hand2")
            remove.place(relx=1.0, rely=0.0, anchor="ne")
            remove.bind("<Button-1>", lambda _e, i=index: self.remove_reference(i))

            tip = f"{item['name']} · {item['width']}×{item['height']} · {item['bytes'] / 1024:.0f}KB"
            label.bind("<Enter>", lambda _e, t=tip: self.set_status(t, "info"))

        self.drop_zone.pack_forget()
        if len(self.references) < max_refs:
            self.drop_zone.pack(fill="x", pady=(0, 6), before=self.ref_grid)

    # ------------------------------------------------------------ 卡片 4：输出设置
    def _build_output_card(self, parent: tk.Frame) -> None:
        c, f = self.colors, self.fonts
        card = ui_theme.Card(parent, self.theme)
        card.pack(fill="x", pady=(0, 12))
        inner = card.body()

        header = card_header(inner, self.theme, 4, "输出设置")
        self.settings_hint = tk.Label(header, text="", bg=c["card"], fg=c["accent"], font=f["tiny"])
        self.settings_hint.pack(side="right")

        # 模型
        model_row = tk.Frame(inner, bg=c["card"])
        model_row.pack(fill="x")
        tk.Label(model_row, text="模型", bg=c["card"], fg=c["muted"], font=f["tiny"], anchor="w").pack(side="left")
        self.refresh_models_btn = flat_button(model_row, self.theme, "刷新可用模型", self._refresh_models,
                                              fg=c["accent"], pady=1, padx=6)
        self.refresh_models_btn.pack(side="right")
        self.model_var = tk.StringVar()
        self.model_combo = ui_theme.ttk.Combobox(inner, textvariable=self.model_var, state="readonly",
                                                 values=[m["name"] for m in meta.all_models()], font=f["body"])
        self.model_combo.pack(fill="x", pady=(3, 2))
        self.model_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_model_change())
        self.model_desc = tk.Label(inner, text="", bg=c["card"], fg=c["muted"], font=f["tiny"], anchor="w")
        self.model_desc.pack(fill="x", pady=(0, 8))

        # 尺寸
        size_row = tk.Frame(inner, bg=c["card"])
        size_row.pack(fill="x")
        tk.Label(size_row, text="尺寸", bg=c["card"], fg=c["muted"], font=f["tiny"], anchor="w").pack(side="left")
        self.size_hint = tk.Label(size_row, text="", bg=c["card"], fg=c["muted"], font=f["tiny"])
        self.size_hint.pack(side="right")
        self.size_var = tk.StringVar()
        self.size_labels = [f"{p['label']}" for p in meta.SIZE_PRESETS]
        self.size_combo = ui_theme.ttk.Combobox(inner, textvariable=self.size_var, state="readonly",
                                                values=self.size_labels, font=f["body"])
        self.size_combo.pack(fill="x", pady=(3, 4))
        self.size_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_size_change())

        # 自定义尺寸（选「自定义尺寸…」时才出现）
        self.custom_size_row = tk.Frame(inner, bg=c["card"])
        self.custom_w_var = tk.StringVar(value="1024")
        self.custom_h_var = tk.StringVar(value="1024")
        tk.Label(self.custom_size_row, text="宽", bg=c["card"], fg=c["muted"], font=f["tiny"]).pack(side="left")
        self.custom_w_entry = ui_theme.ttk.Entry(self.custom_size_row, textvariable=self.custom_w_var, width=7,
                                                 font=f["body"])
        self.custom_w_entry.pack(side="left", padx=(4, 2))
        tk.Label(self.custom_size_row, text="×", bg=c["card"], fg=c["muted"], font=f["tiny"]).pack(side="left")
        tk.Label(self.custom_size_row, text="高", bg=c["card"], fg=c["muted"], font=f["tiny"]).pack(side="left",
                                                                                                  padx=(4, 0))
        self.custom_h_entry = ui_theme.ttk.Entry(self.custom_size_row, textvariable=self.custom_h_var, width=7,
                                                 font=f["body"])
        self.custom_h_entry.pack(side="left", padx=(4, 6))
        self.custom_apply = flat_button(self.custom_size_row, self.theme, "应用", self._apply_custom_size,
                                        fg=c["accent"], pady=1, padx=8)
        self.custom_apply.pack(side="left")
        self.custom_size_error = tk.Label(inner, text="", bg=c["card"], fg=c["warn"], font=f["tiny"],
                                          anchor="w", justify="left", wraplength=380)
        for var in (self.custom_w_var, self.custom_h_var):
            var.trace_add("write", lambda *_a: self._validate_custom_size())

        # 张数 + 种子 一行
        row = tk.Frame(inner, bg=c["card"])
        row.pack(fill="x", pady=(0, 8))
        left = tk.Frame(row, bg=c["card"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="张数", bg=c["card"], fg=c["muted"], font=f["tiny"], anchor="w").pack(fill="x")
        self.n_var = tk.StringVar()
        self.n_combo = ui_theme.ttk.Combobox(left, textvariable=self.n_var, state="readonly", width=6,
                                             values=[str(i) for i in range(meta.LIMITS["n_min"], meta.LIMITS["n_max"] + 1)],
                                             font=f["body"])
        self.n_combo.pack(anchor="w", pady=(3, 0), fill="x")

        right = tk.Frame(row, bg=c["card"])
        right.pack(side="left", fill="x", expand=True, padx=(10, 0))
        tk.Label(right, text="随机种子（留空随机）", bg=c["card"], fg=c["muted"], font=f["tiny"], anchor="w").pack(fill="x")
        seed_row = tk.Frame(right, bg=c["card"])
        seed_row.pack(fill="x", pady=(3, 0))
        self.seed_var = tk.StringVar()
        self.seed_entry = ui_theme.ttk.Entry(seed_row, textvariable=self.seed_var, font=f["body"])
        self.seed_entry.pack(side="left", fill="x", expand=True)
        flat_button(seed_row, self.theme, "随机", self._random_seed, fg=c["muted"], pady=2, padx=6).pack(side="left", padx=(4, 0))

        # 选项
        opts = tk.Frame(inner, bg=c["card"])
        opts.pack(fill="x", pady=(2, 0))
        self.extend_var = tk.BooleanVar(value=True)
        self.extend_check = ui_theme.ttk.Checkbutton(opts, text="提示词改写", variable=self.extend_var,
                                                     command=self._on_extend_toggle)
        self.extend_check.pack(side="left")
        self.extend_mode_var = tk.StringVar(value="direct")
        self.mode_direct = ui_theme.ttk.Radiobutton(opts, text="直接", value="direct", variable=self.extend_mode_var)
        self.mode_direct.pack(side="left", padx=(12, 2))
        self.mode_agent = ui_theme.ttk.Radiobutton(opts, text="智能", value="agent", variable=self.extend_mode_var)
        self.mode_agent.pack(side="left")

        opts2 = tk.Frame(inner, bg=c["card"])
        opts2.pack(fill="x", pady=(6, 0))
        self.thinking_var = tk.BooleanVar(value=True)
        self.thinking_check = ui_theme.ttk.Checkbutton(opts2, text="思考模式", variable=self.thinking_var)
        self.thinking_check.pack(side="left")
        self.watermark_var = tk.BooleanVar(value=False)
        self.watermark_check = ui_theme.ttk.Checkbutton(opts2, text="添加水印", variable=self.watermark_var)
        self.watermark_check.pack(side="left", padx=(16, 0))

    # ------------------------------------------------------------ 底部操作区
    def _build_action_bar(self) -> None:
        c, f = self.colors, self.fonts
        bar = tk.Frame(self, bg=c["panel"])
        bar.pack(fill="x", side="bottom", padx=12, pady=(8, 12))

        self.status_row = tk.Frame(bar, bg=c["panel"])
        self.status_row.pack(fill="x", pady=(0, 6))
        self.status_label = tk.Label(self.status_row, text="填写提示词后点击生成", bg=c["panel"],
                                     fg=c["muted"], font=f["tiny"], anchor="w")
        self.status_label.pack(side="left")

        buttons = tk.Frame(bar, bg=c["panel"])
        buttons.pack(fill="x")
        self.generate_btn = PrimaryButton(buttons, self.theme, "生成图像", self.on_generate)
        self.generate_btn.pack(side="left", fill="x", expand=True)
        self.cancel_btn = flat_button(buttons, self.theme, "取消", self.on_cancel, fg=c["muted"],
                                      padx=16, pady=11, bg=c["card"])
        self.cancel_btn.pack(side="left", padx=(8, 0))
        self.cancel_btn.pack_forget()

        hint = tk.Frame(bar, bg=c["panel"])
        hint.pack(fill="x", pady=(6, 0))
        tk.Label(hint, text="Ctrl + Enter 快速生成", bg=c["panel"], fg=c["muted"], font=f["tiny"]).pack(side="left")
        flat_button(hint, self.theme, "设置", self.on_open_settings, fg=c["muted"], pady=1, padx=6,
                    bg=c["panel"]).pack(side="right")

    def _bind_shortcuts(self) -> None:
        for widget in (self.prompt_text, self.negative_text, self.seed_entry):
            widget.bind("<Control-Return>", lambda _e: self._shortcut_generate())
        self.bind_all("<Control-Return>", lambda _e: self._shortcut_generate())

    def _shortcut_generate(self) -> str:
        if not self._busy:
            self.on_generate()
        return "break"

    # ------------------------------------------------------------ 状态与联动
    def set_status(self, text: str, kind: str = "info") -> None:
        color = {"info": self.colors["muted"], "ok": self.colors["ok"],
                 "warn": self.colors["warn"], "err": self.colors["err"]}.get(kind, self.colors["muted"])
        self.status_label.configure(text=text, fg=color)

    def set_busy(self, busy: bool, canceling: bool = False) -> None:
        self._busy = busy
        if busy:
            self.generate_btn.set_enabled(False)
            self.generate_btn.set_text("生成中…")
            if not self.cancel_btn.winfo_ismapped():
                self.cancel_btn.pack(side="left", padx=(8, 0))
            self.cancel_btn.configure(text="取消")
            self.cancel_btn.configure(fg=self.colors["muted"])
        else:
            self.generate_btn.set_enabled(True)
            self.generate_btn.set_text("生成图像")
            self.cancel_btn.pack_forget()
        for widget in (self.model_combo, self.size_combo, self.n_combo, self.seed_entry,
                       self.extend_check, self.mode_direct, self.mode_agent,
                       self.thinking_check, self.watermark_check):
            try:
                if widget is self.model_combo or widget is self.size_combo or widget is self.n_combo:
                    widget.configure(state="disabled" if busy else "readonly")
                else:
                    widget.configure(state="disabled" if busy else "normal")
            except tk.TclError:
                pass
        if canceling:
            self.cancel_btn.configure(text="正在取消…", fg=self.colors["warn"])

    def current_model_id(self) -> str:
        name = self.model_var.get()
        for model in meta.all_models():
            if model["name"] == name:
                return model["id"]
        return meta.DEFAULTS["model"]

    # ------------------------------------------------------------ 模型列表刷新
    def _refresh_models(self) -> None:
        if self.on_refresh_models:
            self.on_refresh_models()

    def set_models(self, models: list[dict], note: str = "") -> None:
        """服务端拉回新模型后刷新下拉框（保留当前选择）。"""
        names = [m["name"] for m in models]
        if not names:
            return
        current = self.model_var.get()
        self.model_combo.configure(values=names)
        if current in names:
            self.model_var.set(current)
        else:
            self.model_var.set(names[0])
        self._on_model_change()
        if note:
            self.model_desc.configure(text=note)

    # ------------------------------------------------------------ 尺寸（预设 + 自定义）
    def _size_preset(self) -> dict:
        label = self.size_var.get()
        for preset in meta.SIZE_PRESETS:
            if preset["label"] == label:
                return preset
        return meta.SIZE_PRESETS[0]

    def _on_size_change(self) -> None:
        preset = self._size_preset()
        is_custom = preset["value"] == "custom"
        if is_custom:
            self.custom_size_row.pack(fill="x", pady=(0, 4), after=self.size_combo)
            self.custom_size_error.pack(fill="x", pady=(0, 6), after=self.custom_size_row)
            self.size_hint.configure(text="")
            self.custom_w_entry.focus_set()
            self._validate_custom_size()
            # 输入行在页面下半段，自动滚到底，免得用户以为没反应
            try:
                self.scroll.canvas.update_idletasks()
                self.scroll.canvas.yview_moveto(1.0)
            except Exception:  # noqa: BLE001
                pass
        else:
            self.custom_size_row.pack_forget()
            self.custom_size_error.pack_forget()
            if preset["value"] == "auto":
                self.size_hint.configure(text="不指定尺寸，由模型推荐")
            else:
                w, h = preset["value"].split("x")
                self.size_hint.configure(text=f"{w} × {h}")

    def _custom_size_value(self) -> str:
        return f"{self.custom_w_var.get().strip()}x{self.custom_h_var.get().strip()}"

    def _validate_custom_size(self) -> bool:
        """校验自定义宽高；返回是否可用，并把提示写进标签。"""
        if not hasattr(self, "custom_size_error"):
            return True
        if self._size_preset()["value"] != "custom":
            return True
        ok, value, error = api.normalize_size(self._custom_size_value())
        if ok:
            w, h = value.split("x")
            self.custom_size_error.configure(text=f"将输出 {w} × {h} 像素", fg=self.colors["ok"])
            self.size_hint.configure(text=f"{w} × {h}")
            return True
        message = (error or {}).get("message") or "尺寸无效"
        self.custom_size_error.configure(text=message, fg=self.colors["warn"])
        self.size_hint.configure(text="待修正")
        return False

    def _apply_custom_size(self) -> None:
        if self._validate_custom_size():
            self.custom_apply.configure(fg=self.colors["accent"])
            self.set_status("已应用自定义尺寸 " + self._custom_size_value().replace("x", " × "), "ok")

    def _on_model_change(self) -> None:
        model = meta.get_model(self.current_model_id())
        self.model_desc.configure(text=model["desc"])
        max_refs = model["max_refs"]

        # 反向提示词
        if model["supports_negative_prompt"]:
            self.negative_text.configure(state="normal")
            self.negative_badge.configure(text="3.0 系列支持", fg=self.colors["muted"])
            self.negative_hint.configure(text="不希望出现的内容，例如：模糊、畸变、多余手指、水印、低分辨率")
        else:
            self.negative_text.configure(state="disabled")
            self.negative_badge.configure(text="该模型不支持", fg=self.colors["warn"])
            self.negative_hint.configure(text="2.1 系列不支持反向提示词，切到 3.0 系列可用")

        # 思考模式
        if model["supports_thinking"]:
            self.thinking_check.configure(state="normal")
        else:
            self.thinking_var.set(False)
            self.thinking_check.configure(state="disabled")

        # 改写方式
        if "agent" in model["prompt_extend_modes"]:
            self.mode_agent.configure(state="normal")
        else:
            if self.extend_mode_var.get() == "agent":
                self.extend_mode_var.set("direct")
            self.mode_agent.configure(state="disabled")

        # 参考图上限
        if len(self.references) > max_refs:
            self.references = self.references[:max_refs]
        self._refresh_refs()
        self.settings_hint.configure(text=f"最多 {max_refs} 张参考图")

    def _on_extend_toggle(self) -> None:
        enabled = self.extend_var.get()
        state = "normal" if enabled else "disabled"
        if "agent" not in meta.get_model(self.current_model_id())["prompt_extend_modes"]:
            self.mode_agent.configure(state="disabled")
        else:
            self.mode_agent.configure(state=state)
        self.mode_direct.configure(state=state)

    def _random_seed(self) -> None:
        self.seed_var.set(str(random.randint(meta.LIMITS["seed_min"], meta.LIMITS["seed_max"])))

    # ------------------------------------------------------------ 读写表单
    def get_payload(self) -> dict:
        preset = self._size_preset()
        size_value = preset["value"]
        if size_value == "custom":
            size_value = self._custom_size_value()
        return {
            "model": self.current_model_id(),
            "prompt": self._prompt_value(),
            "negative_prompt": self._negative_value(),
            "size": size_value,
            "n": int(self.n_var.get() or 1),
            "seed": self.seed_var.get().strip() or None,
            "prompt_extend": self.extend_var.get(),
            "prompt_extend_mode": self.extend_mode_var.get(),
            "enable_thinking": self.thinking_var.get(),
            "watermark": self.watermark_var.get(),
            "images": [{"name": item["name"], "data_url": item["data_url"],
                        "width": item["width"], "height": item["height"]} for item in self.references],
        }

    def set_prompt(self, text: str) -> None:
        self._prompt_placeholder = False
        self.prompt_text.configure(fg=self.colors["text"])
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", text)
        self._update_prompt_count()

    def apply_defaults(self, settings: dict) -> None:
        self.model_var.set(meta.get_model(settings.get("model") or meta.DEFAULTS["model"])["name"])
        saved_size = str(settings.get("size") or meta.DEFAULTS["size"])
        for preset in meta.SIZE_PRESETS:
            if preset["value"] == saved_size:
                self.size_var.set(preset["label"])
                break
        else:
            if "x" in saved_size:
                width, height = saved_size.split("x", 1)
                self.custom_w_var.set(width)
                self.custom_h_var.set(height)
                self.size_var.set(next(p["label"] for p in meta.SIZE_PRESETS if p["value"] == "custom"))
            else:
                self.size_var.set(self.size_labels[1])
        self._on_size_change()
        self.n_var.set(str(settings.get("n") or 1))
        self.extend_var.set(bool(settings.get("prompt_extend", True)))
        self.extend_mode_var.set(settings.get("prompt_extend_mode") or "direct")
        self.thinking_var.set(bool(settings.get("enable_thinking", True)))
        self.watermark_var.set(bool(settings.get("watermark", False)))
        self._on_model_change()
        self._on_extend_toggle()

    def apply_settings(self, settings: dict) -> None:
        """设置变化后刷新与地域/协议相关的小字。"""
        self.settings = settings
        if not self.model_desc.cget("text"):
            self._on_model_change()

    def focus_prompt(self) -> None:
        self.prompt_text.focus_set()
