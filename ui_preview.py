"""千问图像工作台 —— 右侧预览面板。

状态：空 / 生成中 / 出错 / 已出图。
功能：适应窗口、缩放、保存、另存全部、打开目录、复制图片、多图切换。
对外接口：
    panel.show_empty()
    panel.show_loading(stage)      stage 文本会实时更新
    panel.show_error(error: dict, on_retry)
    panel.show_result(result: dict)  result 来自 api.generate
    panel.set_status(text, kind)
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageTk

import storage
import ui_theme
from ui_theme import COLORS

ZOOM_STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]
THUMB = 64

ERROR_TITLES = {
    "NO_API_KEY": "未配置 API Key",
    "InvalidApiKey": "API Key 无效",
    "AccessDenied": "没有访问权限",
    "Throttling": "请求过于频繁",
    "InsufficientQuota": "配额不足",
    "Arrearage": "账户欠费",
    "TIMEOUT": "请求超时",
    "NETWORK": "网络错误",
    "CONFIG": "配置有误",
    "PARAM": "参数有误",
    "CANCELED": "已取消",
    "EMPTY_RESULT": "没有返回图片",
    "NOT_FOUND": "结果图下载失败",
    "ModelNotFound": "模型不可用",
    "ModelAccessDenied": "模型未开通",
    "DataInspectionFailed": "内容审核未通过",
    "UNEXPECTED": "发生意外错误",
}


def error_title(code: str, status=None) -> str:
    if code in ERROR_TITLES:
        return ERROR_TITLES[code]
    if isinstance(status, int):
        if status == 401:
            return "API Key 无效"
        if status == 403:
            return "没有访问权限"
        if status == 429:
            return "请求过于频繁"
        if status >= 500:
            return "服务端错误"
    return "生成失败"


def _round_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
              x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class PreviewPanel(tk.Frame):
    def __init__(self, master, theme: dict, *, on_retry: Callable[[], None],
                 on_open_settings: Callable[[], None], get_settings: Callable[[], dict]):
        self.theme = theme
        self.colors = theme["colors"]
        self.fonts = theme["fonts"]
        self.on_retry = on_retry
        self.on_open_settings = on_open_settings
        self.get_settings = get_settings

        super().__init__(master, bg=self.colors["bg"])
        self.state = "empty"          # empty | loading | error | result
        self.results: list[dict] = []  # 全部结果（历史）
        self.active = 0
        self.zoom_mode = "fit"        # fit | fixed
        self.zoom_value = 1.0
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._thumb_photos: list[ImageTk.PhotoImage] = []
        self._loading_dots = 0
        self._loading_job = None
        self._toast_job = None

        self._build_toolbar()
        self._build_stage()
        self._build_thumb_strip()
        self.show_empty()

    # ------------------------------------------------------------ 结构
    def _build_toolbar(self) -> None:
        c, f = self.colors, self.fonts
        bar = tk.Frame(self, bg=self.colors["bg"], height=44)
        bar.pack(fill="x", padx=(14, 14), pady=(8, 0))
        self.toolbar = bar

        self.btn_fit = ui_theme.flat_button(bar, self.theme, "适应", self._fit, bg=c["card"],
                                            fg=c["text_dim"], padx=10, pady=5)
        self.btn_fit.pack(side="left")
        self.btn_zoom_out = ui_theme.flat_button(bar, self.theme, "−", lambda: self._zoom(-1),
                                                 bg=c["card"], fg=c["text_dim"], padx=9, pady=5)
        self.btn_zoom_out.pack(side="left", padx=(6, 0))
        self.zoom_label = tk.Label(bar, text="100%", bg=self.colors["bg"], fg=c["muted"],
                                   font=f["small"], width=6)
        self.zoom_label.pack(side="left")
        self.btn_zoom_in = ui_theme.flat_button(bar, self.theme, "＋", lambda: self._zoom(1),
                                                bg=c["card"], fg=c["text_dim"], padx=9, pady=5)
        self.btn_zoom_in.pack(side="left")

        tk.Frame(bar, bg=c["border"], width=1, height=18).pack(side="left", padx=10)

        self.btn_save = ui_theme.flat_button(bar, self.theme, "保存", self._save_current, fg=c["text_dim"],
                                             padx=10, pady=5)
        self.btn_save.pack(side="left")
        self.btn_save_all = ui_theme.flat_button(bar, self.theme, "全部保存", self._save_all,
                                                 fg=c["text_dim"], padx=10, pady=5)
        self.btn_save_all.pack(side="left", padx=(4, 0))
        self.btn_open_dir = ui_theme.flat_button(bar, self.theme, "打开目录", self._open_dir,
                                                 fg=c["text_dim"], padx=10, pady=5)
        self.btn_open_dir.pack(side="left", padx=(4, 0))
        self.btn_copy = ui_theme.flat_button(bar, self.theme, "复制图片", self._copy_image,
                                             fg=c["text_dim"], padx=10, pady=5)
        self.btn_copy.pack(side="left", padx=(4, 0))

        self.meta_label = tk.Label(bar, text="", bg=self.colors["bg"], fg=c["muted"], font=f["small"])
        self.meta_label.pack(side="right")
        self._set_toolbar_enabled(False)

    def _build_stage(self) -> None:
        c = self.colors
        self.stage = tk.Frame(self, bg=c["canvas_bg"], highlightbackground=c["border"], highlightthickness=1)
        self.stage.pack(fill="both", expand=True, padx=14, pady=(10, 0))

        self.canvas = tk.Canvas(self.stage, bg=c["canvas_bg"], highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<MouseWheel>", self._on_wheel)

        # 空状态
        self.empty_frame = tk.Frame(self.canvas, bg=c["canvas_bg"])
        icon = tk.Canvas(self.empty_frame, width=86, height=70, bg=c["canvas_bg"], highlightthickness=0)
        icon.pack(pady=(0, 6))
        _round_rect(icon, 8, 6, 78, 64, 12, outline=c["accent"], width=2, fill="")
        icon.create_oval(22, 18, 34, 30, outline=c["accent"], width=2)
        icon.create_line(14, 60, 34, 40, 50, 52, 62, 36, 76, 60, fill=c["accent"], width=2, smooth=True)
        tk.Label(self.empty_frame, text="左侧填写提示词，点击「生成图像」", bg=c["canvas_bg"],
                 fg=c["text"], font=self.fonts["card_title"]).pack()
        tk.Label(self.empty_frame, text="加入 1~3 张参考图即为图生图；生成结果会自动保存",
                 bg=c["canvas_bg"], fg=c["muted"], font=self.fonts["small"]).pack(pady=(6, 0))
        for text in ("文生图 / 图生图双模式", "提示词改写与思考模式", "多图对比、保存与复制"):
            row = tk.Frame(self.empty_frame, bg=c["canvas_bg"])
            row.pack(pady=(6, 0))
            tk.Label(row, text="·", bg=c["canvas_bg"], fg=c["accent"], font=self.fonts["small"]).pack(side="left")
            tk.Label(row, text=text, bg=c["canvas_bg"], fg=c["muted"], font=self.fonts["small"]).pack(side="left", padx=(6, 0))

        # 生成中遮罩
        self.loading_frame = tk.Frame(self.canvas, bg=c["canvas_bg"])
        tk.Label(self.loading_frame, text="正在生成…", bg=c["canvas_bg"], fg=c["text"],
                 font=self.fonts["card_title"]).pack()
        self.loading_stage = tk.Label(self.loading_frame, text="正在请求模型…", bg=c["canvas_bg"],
                                      fg=c["muted"], font=self.fonts["small"])
        self.loading_stage.pack(pady=(8, 12))
        self.loading_bar = ttk.Progressbar(self.loading_frame, style="TProgressbar", mode="indeterminate",
                                           length=260)
        self.loading_bar.pack()
        self.loading_hint = tk.Label(self.loading_frame, text="出图通常需要 10~60 秒，可点「取消」中止",
                                      bg=c["canvas_bg"], fg=c["muted"], font=self.fonts["tiny"])
        self.loading_hint.pack(pady=(12, 0))

        # 错误卡片
        self.error_frame = tk.Frame(self.canvas, bg=c["err_bg"], highlightbackground="#4b2a30", highlightthickness=1)
        head = tk.Frame(self.error_frame, bg=c["err_bg"])
        head.pack(fill="x", padx=18, pady=(16, 0))
        tk.Label(head, text="⚠", bg=c["err_bg"], fg=c["err"], font=("Segoe UI Symbol", 12)).pack(side="left")
        self.error_title = tk.Label(head, text="生成失败", bg=c["err_bg"], fg=c["err"],
                                    font=self.fonts["card_title"])
        self.error_title.pack(side="left", padx=(8, 0))
        self.error_code = tk.Label(head, text="", bg=c["err_bg"], fg=c["err"], font=self.fonts["tiny"])
        self.error_code.pack(side="right")
        self.error_message = tk.Label(self.error_frame, text="", bg=c["err_bg"], fg=c["text"], font=self.fonts["small"],
                                      justify="left", wraplength=460, anchor="w")
        self.error_message.pack(fill="x", padx=44, pady=(8, 0))
        self.error_hint = tk.Label(self.error_frame, text="", bg=c["err_bg"], fg=c["text_dim"], font=self.fonts["small"],
                                   justify="left", wraplength=460, anchor="w")
        self.error_hint.pack(fill="x", padx=44, pady=(6, 0))
        foot = tk.Frame(self.error_frame, bg=c["err_bg"])
        foot.pack(fill="x", padx=18, pady=(10, 14))
        self.error_meta = tk.Label(foot, text="", bg=c["err_bg"], fg=c["muted"], font=self.fonts["tiny"])
        self.error_meta.pack(side="left")
        self.error_retry = tk.Button(foot, text="重试", command=lambda: self.on_retry(), bg=c["card"],
                                     fg=c["text"], font=self.fonts["small"], relief="flat", bd=0,
                                     padx=14, pady=4, cursor="hand2", activebackground=c["card_hover"],
                                     activeforeground=c["text"])
        self.error_retry.pack(side="right")

        self.toast = tk.Label(self.canvas, text="", bg="#2a2f3d", fg=c["text"], font=self.fonts["small"],
                              padx=14, pady=7, bd=0)

    def _build_thumb_strip(self) -> None:
        c = self.colors
        self.thumb_bar = tk.Frame(self, bg=self.colors["bg"], height=THUMB + 22)
        self.thumb_canvas = tk.Canvas(self.thumb_bar, bg=self.colors["bg"], highlightthickness=0, height=THUMB + 14)
        self.thumb_canvas.pack(fill="x", padx=14, pady=(8, 0))
        self.thumb_inner = tk.Frame(self.thumb_canvas, bg=self.colors["bg"])
        self._thumb_window = self.thumb_canvas.create_window((0, 0), window=self.thumb_inner, anchor="nw")
        self.thumb_inner.bind("<Configure>", lambda _e: self.thumb_canvas.configure(
            scrollregion=self.thumb_canvas.bbox("all")))
        self.thumb_canvas.bind("<MouseWheel>", lambda e: self.thumb_canvas.xview_scroll(
            int(-1 * (e.delta / 120)) or 1, "units"))

    # ------------------------------------------------------------ 状态切换
    def _hide_overlays(self) -> None:
        for frame in (self.empty_frame, self.loading_frame, self.error_frame):
            frame.place_forget()
        if self._loading_job:
            self.after_cancel(self._loading_job)
            self._loading_job = None

    def _center(self, frame: tk.Frame) -> None:
        frame.place(relx=0.5, rely=0.5, anchor="center")

    def show_empty(self) -> None:
        self.state = "empty"
        self._hide_overlays()
        self.canvas.delete("preview")
        self._center(self.empty_frame)
        self.empty_frame.lift()
        self.meta_label.configure(text="")
        self._set_toolbar_enabled(False)
        self.thumb_bar.pack_forget()

    def show_loading(self, stage: str = "正在请求模型…") -> None:
        self.state = "loading"
        self._hide_overlays()
        self.canvas.delete("preview")
        self.loading_stage.configure(text=stage)
        self.loading_bar.start(14)
        self._center(self.loading_frame)
        self.loading_frame.lift()
        self.meta_label.configure(text="生成中…")
        self._set_toolbar_enabled(False)
        self.thumb_bar.pack_forget()
        self._animate_loading()

    def _animate_loading(self) -> None:
        if self.state != "loading":
            return
        titles = ["正在生成…", "正在生成· ", "正在生成·· ", "正在生成···"]
        self._loading_dots = (self._loading_dots + 1) % len(titles)
        for child in self.loading_frame.winfo_children():
            if isinstance(child, tk.Label) and child.cget("font") == self.fonts["card_title"]:
                child.configure(text=titles[self._loading_dots])
                break
        self._loading_job = self.after(420, self._animate_loading)

    def update_stage(self, stage: str) -> None:
        if self.state == "loading":
            self.loading_stage.configure(text=stage)

    def show_error(self, error: dict, request_id: str = "") -> None:
        self.state = "error"
        self._hide_overlays()
        self.canvas.delete("preview")
        self.error_title.configure(text=error.get("title") or error_title(error.get("code") or "",
                                                                        error.get("status")))
        self.error_code.configure(text=error.get("code") or "")
        self.error_message.configure(text=error.get("message") or "未知错误")
        self.error_hint.configure(text=error.get("hint") or "")
        self.error_meta.configure(text=f"requestId：{request_id}" if request_id else "")
        self.error_frame.configure(width=560)
        self._center(self.error_frame)
        self.error_frame.lift()
        self.meta_label.configure(text="")
        self._set_toolbar_enabled(False)
        self.thumb_bar.pack_forget()

    def show_result(self, result: dict) -> None:
        """result: api.generate 的返回值。"""
        self.state = "result"
        self._hide_overlays()
        self.results = []
        urls = result.get("urls") or []
        for index, raw in enumerate(result.get("images") or []):
            try:
                image = Image.open(io.BytesIO(raw))
                image.load()
            except Exception:  # noqa: BLE001
                continue
            self.results.append({"png": raw, "image": image,
                                 "url": urls[index] if index < len(urls) else "",
                                 "saved_path": None})
        for image_info in result.get("saved") or []:
            if image_info.get("index", 0) < len(self.results):
                self.results[image_info["index"]]["saved_path"] = image_info.get("path")
        self.active = 0
        self._render_results()
        self.meta_label.configure(text=result.get("meta", ""))
        self._set_toolbar_enabled(True)
        self.zoom_mode = "fit"
        self._render_image()
        if len(self.results) > 1:
            self.thumb_bar.pack(fill="x")
            self._render_thumbs()
        else:
            self.thumb_bar.pack_forget()
        self._populate_timings(result)

    def append_results(self, result: dict) -> None:
        """在已有结果后追加一批（保留历史，最多 24 张）。"""
        start = len(self.results)
        for index, raw in enumerate(result.get("images") or []):
            try:
                image = Image.open(io.BytesIO(raw))
                image.load()
            except Exception:  # noqa: BLE001
                continue
            urls = result.get("urls") or []
            self.results.append({"png": raw, "image": image,
                                 "url": urls[index] if index < len(urls) else "", "saved_path": None})
        for saved in result.get("saved") or []:
            target = start + int(saved.get("index", 0))
            if target < len(self.results):
                self.results[target]["saved_path"] = saved.get("path")
        if len(self.results) > 24:
            self.results = self.results[-24:]
        self.state = "result"
        self._hide_overlays()
        self.active = min(start, len(self.results) - 1)
        self.zoom_mode = "fit"
        self._render_image()
        self._set_toolbar_enabled(True)
        if len(self.results) > 1:
            self.thumb_bar.pack(fill="x")
            self._render_thumbs()
        self._populate_timings(result)

    def _populate_timings(self, result: dict) -> None:
        parts = []
        if result.get("elapsed"):
            parts.append(f"耗时 {ui_theme.fmt_elapsed(result['elapsed'])}")
        if result.get("request_id"):
            parts.append(result["request_id"])
        # 由 app 侧写入状态栏，这里不覆盖 meta
        self.last_result_meta = " · ".join(parts)

    # ------------------------------------------------------------ 渲染图片
    def _current(self) -> Optional[dict]:
        if not self.results:
            return None
        return self.results[min(self.active, len(self.results) - 1)]

    def _render_results(self) -> None:
        self.active = min(self.active, max(0, len(self.results) - 1))

    def _render_image(self) -> None:
        current = self._current()
        if current is None:
            self.show_empty()
            return
        image: Image.Image = current["image"]
        canvas_w = max(self.canvas.winfo_width(), 100)
        canvas_h = max(self.canvas.winfo_height(), 100)
        if self.zoom_mode == "fit":
            scale = min((canvas_w - 32) / image.width, (canvas_h - 32) / image.height, 1.0)
        else:
            scale = self.zoom_value
        self.zoom_label.configure(text=f"{int(round(scale * 100))}%")
        target = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        display = image if target == image.size else image.resize(target, Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(display)
        self.canvas.delete("preview")
        self.canvas.create_image(canvas_w // 2, canvas_h // 2, image=self._photo, anchor="center", tags="preview")
        self._update_info(current)

    def _update_info(self, current: dict) -> None:
        image: Image.Image = current["image"]
        size_kb = len(current["png"]) / 1024
        save_hint = " · 已自动保存" if current.get("saved_path") else ""
        self.info_label = getattr(self, "info_label", None)
        text = f"{image.width} × {image.height} · {size_kb:.0f} KB{save_hint}"
        self.meta_label.configure(text=text)

    def _on_canvas_resize(self, _event=None) -> None:
        if self.state == "result":
            self._render_image()

    # ------------------------------------------------------------ 缩放
    def _fit(self) -> None:
        if self.state != "result":
            return
        self.zoom_mode = "fit"
        self._render_image()

    def _zoom(self, direction: int) -> None:
        if self.state != "result":
            return
        image: Image.Image = self._current()["image"]
        canvas_w, canvas_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        fit_scale = min((canvas_w - 32) / image.width, (canvas_h - 32) / image.height, 1.0)
        current = fit_scale if self.zoom_mode == "fit" else self.zoom_value
        candidates = [step for step in ZOOM_STEPS if (step > current + 1e-6) == (direction > 0)]
        if not candidates:
            candidates = ZOOM_STEPS
            pick = candidates[-1] if direction > 0 else candidates[0]
        else:
            pick = candidates[0] if direction > 0 else candidates[-1]
        self.zoom_mode = "fixed"
        self.zoom_value = pick
        self._render_image()

    def _on_wheel(self, event) -> None:
        if self.state != "result":
            return
        if event.state & 0x0004:  # Ctrl + 滚轮
            self._zoom(1 if event.delta > 0 else -1)

    # ------------------------------------------------------------ 缩略图
    def _render_thumbs(self) -> None:
        for child in self.thumb_inner.winfo_children():
            child.destroy()
        self._thumb_photos.clear()
        c = self.colors
        for index, item in enumerate(self.results):
            thumb = item["image"].copy()
            thumb.thumbnail((THUMB, THUMB), Image.LANCZOS)
            photo = ImageTk.PhotoImage(thumb)
            self._thumb_photos.append(photo)
            holder = tk.Frame(self.thumb_inner, bg=c["bg"])
            holder.pack(side="left", padx=(0, 8))
            border = c["accent"] if index == self.active else c["border"]
            frame = tk.Frame(holder, bg=border, padx=2, pady=2, cursor="hand2")
            frame.pack()
            label = tk.Label(frame, image=photo, bg=c["canvas_bg"], bd=0, cursor="hand2")
            label.pack()
            frame.bind("<Button-1>", lambda _e, i=index: self.select(i))
            label.bind("<Button-1>", lambda _e, i=index: self.select(i))
            badge = tk.Label(holder, text=str(index + 1), bg=border, fg="#14161b", font=self.fonts["tiny"],
                             padx=4)
            badge.pack(anchor="e", pady=(2, 0))
            badge.bind("<Button-1>", lambda _e, i=index: self.select(i))

    def select(self, index: int) -> None:
        if 0 <= index < len(self.results):
            self.active = index
            self.zoom_mode = "fit"
            self._render_image()
            self._render_thumbs()

    # ------------------------------------------------------------ 工具按钮
    def _set_toolbar_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        color = self.colors["text_dim"] if enabled else "#545a68"
        for widget in (self.btn_fit, self.btn_zoom_out, self.btn_zoom_in, self.btn_save,
                       self.btn_save_all, self.btn_open_dir, self.btn_copy):
            widget.configure(state=state, fg=color)

    def _save_current(self) -> None:
        current = self._current()
        if current is None:
            return
        settings = self.get_settings()
        folder = settings.get("save_dir") or storage.default_save_dir()
        path = filedialog.asksaveasfilename(
            title="保存图片", initialdir=folder, defaultextension=".png",
            initialfile=storage.suggest_name(1, prefix="qwen-image"),
            filetypes=[("PNG 图片", "*.png"), ("JPEG 图片", "*.jpg"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            storage.save_image(current["png"], path)
            current["saved_path"] = path
            self.set_status(f"已保存到 {path}", "ok")
            self._update_info(current)
        except OSError as exc:
            self.set_status(f"保存失败：{exc}", "err")

    def _save_all(self) -> None:
        if not self.results:
            return
        settings = self.get_settings()
        folder = filedialog.askdirectory(title="选择保存目录",
                                         initialdir=settings.get("save_dir") or storage.default_save_dir())
        if not folder:
            return
        saved = []
        for index, item in enumerate(self.results, start=1):
            path = os.path.join(folder, storage.suggest_name(index, prefix="qwen-image"))
            try:
                storage.save_image(item["png"], path)
                item["saved_path"] = path
                saved.append(path)
            except OSError as exc:
                self.set_status(f"保存失败：{exc}", "err")
                return
        self.set_status(f"已保存 {len(saved)} 张到 {folder}", "ok")

    def _open_dir(self) -> None:
        settings = self.get_settings()
        folder = settings.get("save_dir") or storage.default_save_dir()
        storage.ensure_dir(folder)
        try:
            os.startfile(folder)  # noqa: S606 - Windows 专用
        except OSError as exc:
            self.set_status(f"无法打开目录：{exc}", "err")

    def _copy_image(self) -> None:
        current = self._current()
        if current is None:
            return
        path = current.get("saved_path")
        if not path or not os.path.exists(path):
            folder = tempfile.mkdtemp(prefix="qwen-image-studio-")
            path = os.path.join(folder, storage.suggest_name(1, prefix="qwen-image"))
            storage.save_image(current["png"], path)
            current["saved_path"] = path
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"Set-Clipboard -Path '{path}'"], check=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.set_status("图片已复制到剪贴板，可直接粘贴到聊天窗口", "ok")
        except (OSError, subprocess.SubprocessError) as exc:
            self.set_status(f"复制失败：{exc}", "err")

    # ------------------------------------------------------------ 提示条
    def set_status(self, text: str, kind: str = "info") -> None:
        color = {"info": self.colors["text"], "ok": self.colors["ok"],
                 "warn": self.colors["warn"], "err": self.colors["err"]}.get(kind, self.colors["text"])
        self.toast.configure(text=text, fg=color)
        self.toast.place(relx=1.0, rely=0.0, x=-16, y=12, anchor="ne")
        self.toast.lift()
        if self._toast_job:
            self.after_cancel(self._toast_job)
        self._toast_job = self.after(2800, self._hide_toast)

    def clear_toast(self) -> None:
        """立即隐藏右上角提示条。"""
        if self._toast_job:
            try:
                self.after_cancel(self._toast_job)
            except tk.TclError:
                pass
            self._toast_job = None
        self.toast.place_forget()

    def _hide_toast(self) -> None:
        self._toast_job = None
        self.toast.place_forget()

    def toast_answer(self) -> None:  # pragma: no cover - 兼容旧调用
        pass
