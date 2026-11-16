"""千问图像工作台 —— 设置对话框（协议 / 地域 / Base URL / API Key / 自动保存）。"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable

import meta
import settings as settings_store
import storage
import ui_theme
from ui_form import PrimaryButton


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, theme: dict, current: dict, on_saved: Callable[[dict], None]):
        super().__init__(master)
        self.theme = theme
        self.colors = theme["colors"]
        self.fonts = theme["fonts"]
        self.on_saved = on_saved
        self.current = dict(current)
        self.result: dict | None = None

        self.title("设置")
        self.configure(bg=self.colors["panel"])
        self.resizable(False, False)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _e: self._cancel())

        self._build()
        self._fit_geometry(master)
        self.grab_set()
        self.focus_force()

    def _fit_geometry(self, master) -> None:
        """按内容实际高度决定对话框尺寸，避免底部被裁切。"""
        self.update_idletasks()
        wrap = self.winfo_children()[0]
        width = 680
        needed = wrap.winfo_reqheight() + 34
        height = min(max(560, needed), self.winfo_screenheight() - 120)
        self.geometry(self._center_geometry(master, width, height))
        self.update_idletasks()
        ui_theme.enable_dark_titlebar(self)

    def _center_geometry(self, master, width: int, height: int) -> str:
        master.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + (master.winfo_height() - height) // 2
        return f"{width}x{height}+{max(30, x)}+{max(30, y)}"

    # ------------------------------------------------------------ UI
    def _build(self) -> None:
        c, f = self.colors, self.fonts
        wrap = tk.Frame(self, bg=c["panel"])
        wrap.pack(fill="both", expand=True, padx=18, pady=14)

        # 底部按钮先占位，避免内容把按钮挤出窗口
        foot = tk.Frame(wrap, bg=c["panel"])
        foot.pack(fill="x", side="bottom", pady=(14, 0))
        PrimaryButton(foot, self.theme, "保存设置", self._save, height=38, width=132).pack(side="right")
        ui_theme.flat_button(foot, self.theme, "取消", self._cancel, fg=c["muted"], padx=18, pady=9,
                             bg=c["card"]).pack(side="right", padx=(0, 8))

        title_row = tk.Frame(wrap, bg=c["panel"])
        title_row.pack(fill="x", pady=(0, 10))
        tk.Label(title_row, text="设置", bg=c["panel"], fg=c["text"], font=f["title"]).pack(side="left")
        tk.Label(title_row, text="Key 只保存在本机，不会上传", bg=c["panel"], fg=c["muted"],
                 font=f["tiny"]).pack(side="right")

        # 缺少 Key 提示
        self.key_banner = tk.Label(wrap, text="", bg="#332a18", fg=c["warn"], font=f["small"],
                                   anchor="w", padx=10, pady=7)
        if not self.current.get("api_key"):
            self.key_banner.configure(text="还没有配置 API Key，请填写后保存再生成。")
            self.key_banner.pack(fill="x", pady=(0, 10))

        # 协议
        self._label(wrap, "协议")
        self.protocol_var = tk.StringVar()
        labels = [f'{item["label"]}' for item in meta.PROTOCOLS]
        self.protocol_combo = ttk.Combobox(wrap, textvariable=self.protocol_var, state="readonly",
                                           values=labels, font=f["body"])
        self.protocol_combo.pack(fill="x", pady=(3, 2))
        self.protocol_hint = tk.Label(wrap, text="", bg=c["panel"], fg=c["muted"], font=f["tiny"],
                                      anchor="w", justify="left", wraplength=600)
        self.protocol_hint.pack(fill="x", pady=(0, 8))
        self.protocol_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_protocol_change())

        # 地域
        self._label(wrap, "地域")
        self.region_var = tk.StringVar()
        self.region_combo = ttk.Combobox(wrap, textvariable=self.region_var, state="readonly",
                                         values=[item["label"] for item in meta.REGIONS], font=f["body"])
        self.region_combo.pack(fill="x", pady=(3, 2))
        self.region_hint = tk.Label(wrap, text="", bg=c["panel"], fg=c["muted"], font=f["tiny"], anchor="w")
        self.region_hint.pack(fill="x", pady=(0, 8))
        self.region_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_region_change())

        # Base URL
        self._label(wrap, "Base URL")
        self.base_var = tk.StringVar()
        self.base_entry = ttk.Entry(wrap, textvariable=self.base_var, font=f["body"])
        self.base_entry.pack(fill="x", pady=(3, 2))
        self.base_hint = tk.Label(wrap, text="", bg=c["panel"], fg=c["muted"], font=f["tiny"],
                                  anchor="w", justify="left", wraplength=600)
        self.base_hint.pack(fill="x", pady=(0, 8))
        self.base_var.trace_add("write", lambda *_: self._update_base_hint())

        # 业务空间 ID
        self._label(wrap, "业务空间 ID（使用业务空间域名时必填）")
        self.workspace_var = tk.StringVar()
        self.workspace_entry = ttk.Entry(wrap, textvariable=self.workspace_var, font=f["body"])
        self.workspace_entry.pack(fill="x", pady=(3, 8))

        # API Key
        self._label(wrap, "API Key（DashScope 控制台获取，形如 sk-...）")
        key_row = tk.Frame(wrap, bg=c["panel"])
        key_row.pack(fill="x", pady=(3, 2))
        self.key_var = tk.StringVar()
        self.key_entry = ttk.Entry(key_row, textvariable=self.key_var, font=f["body"], show="•")
        self.key_entry.pack(side="left", fill="x", expand=True)
        ui_theme.flat_button(key_row, self.theme, "清除", self._clear_key, fg=c["muted"], padx=8,
                             pady=4, bg=c["card"]).pack(side="left", padx=(6, 0))
        self.key_hint = tk.Label(wrap, text="", bg=c["panel"], fg=c["muted"], font=f["tiny"], anchor="w")
        self.key_hint.pack(fill="x", pady=(0, 10))

        # 自动保存
        row = tk.Frame(wrap, bg=c["panel"])
        row.pack(fill="x", pady=(2, 6))
        left = tk.Frame(row, bg=c["panel"])
        left.pack(side="left")
        self.auto_save_var = tk.BooleanVar(value=bool(self.current.get("auto_save", True)))
        ttk.Checkbutton(left, text="自动保存结果", variable=self.auto_save_var).pack(anchor="w")
        tk.Label(left, text="生成完成后自动保存到下方目录", bg=c["panel"], fg=c["muted"],
                 font=f["tiny"]).pack(anchor="w")

        dir_row = tk.Frame(wrap, bg=c["panel"])
        dir_row.pack(fill="x", pady=(0, 4))
        self.dir_var = tk.StringVar(value=self.current.get("save_dir") or storage.default_save_dir())
        ttk.Entry(dir_row, textvariable=self.dir_var, font=f["small"]).pack(side="left", fill="x", expand=True)
        ui_theme.flat_button(dir_row, self.theme, "浏览…", self._choose_dir, fg=c["text_dim"], padx=10,
                             pady=4, bg=c["card"]).pack(side="left", padx=(6, 0))

        self._load_values()

    def _label(self, parent, text: str) -> None:
        tk.Label(parent, text=text, bg=self.colors["panel"], fg=self.colors["muted"],
                 font=self.fonts["tiny"], anchor="w").pack(fill="x")

    # ------------------------------------------------------------ 数据 <-> 控件
    def _load_values(self) -> None:
        protocol = self.current.get("protocol") or meta.DEFAULTS["protocol"]
        proto = meta.get_protocol(protocol)
        self.protocol_var.set(proto["label"])

        region = self.current.get("region") or meta.DEFAULTS["region"]
        preset = meta.get_region(region)
        self.region_var.set(preset["label"])

        self.base_var.set(self.current.get("base_url") or preset.get("base_url") or "")
        self.workspace_var.set(self.current.get("workspace_id") or "")

        key = self.current.get("api_key") or ""
        if key:
            self.key_hint.configure(text=f"已保存 {settings_store.mask_key(key)}，留空表示不修改")
        else:
            self.key_hint.configure(text="Key 仅保存在本机；没有 Key 时无法生成")

        self._on_protocol_change()
        self._on_region_change()

    def _selected_protocol(self) -> dict:
        label = self.protocol_var.get()
        for item in meta.PROTOCOLS:
            if item["label"] == label:
                return item
        return meta.PROTOCOLS[0]

    def _selected_region(self) -> dict:
        label = self.region_var.get()
        for item in meta.REGIONS:
            if item["label"] == label:
                return item
        return meta.REGIONS[0]

    def _on_protocol_change(self) -> None:
        proto = self._selected_protocol()
        self.protocol_hint.configure(text=f'请求路径：{proto["path"]} · {proto["hint"]}')

    def _on_region_change(self) -> None:
        preset = self._selected_region()
        self.region_hint.configure(text=f'域名：{preset["base_url"] or "（下方手工填写）"}')
        self.base_var.set(preset.get("base_url") or "")
        state = "normal" if preset.get("needs_workspace") else "disabled"
        self.workspace_entry.configure(state=state)
        if preset.get("needs_workspace") and not self.workspace_var.get():
            self.workspace_var.set(self.current.get("workspace_id") or "")
        self._update_base_hint()

    def _update_base_hint(self) -> None:
        preset = self._selected_region()
        hint = meta.resolve_base_url(preset["id"], self.base_var.get(), self.workspace_var.get())
        if preset.get("needs_workspace") and not self.workspace_var.get().strip():
            self.base_hint.configure(text="还需要填写业务空间 ID 才能拼出完整地址", fg=self.colors["warn"])
        elif not hint.startswith(("http://", "https://")):
            self.base_hint.configure(text="Base URL 需以 http(s):// 开头", fg=self.colors["warn"])
        else:
            self.base_hint.configure(text=f"实际请求：{hint}", fg=self.colors["muted"])

    def _clear_key(self) -> None:
        self.key_var.set("")
        self.current["api_key"] = ""
        self.key_hint.configure(text="已清空 Key，保存后生效", fg=self.colors["warn"])
        if not self.key_banner.winfo_ismapped():
            self.key_banner.configure(text="还没有配置 API Key，请填写后保存再生成。")
            self.key_banner.pack(fill="x", pady=(0, 10), before=self.protocol_combo)

    def _choose_dir(self) -> None:
        folder = filedialog.askdirectory(title="选择自动保存目录",
                                         initialdir=self.dir_var.get() or storage.default_save_dir())
        if folder:
            self.dir_var.set(folder)

    # ------------------------------------------------------------ 保存
    def _collect(self) -> dict:
        value = dict(self.current)
        proto = self._selected_protocol()
        preset = self._selected_region()
        typed_key = self.key_var.get().strip()
        value.update({
            "protocol": proto["id"],
            "region": preset["id"],
            "base_url": self.base_var.get().strip(),
            "workspace_id": self.workspace_var.get().strip(),
            "auto_save": bool(self.auto_save_var.get()),
            "save_dir": self.dir_var.get().strip(),
        })
        if typed_key:
            value["api_key"] = typed_key
        elif not self.current.get("api_key"):
            value["api_key"] = ""
        return value

    def _save(self) -> None:
        value = self._collect()
        base = meta.resolve_base_url(value["region"], value["base_url"], value["workspace_id"])
        if not base.startswith(("http://", "https://")):
            self.base_hint.configure(text="Base URL 无效，请检查后重试", fg=self.colors["err"])
            self.base_entry.focus_set()
            return
        try:
            settings_store.save(value)
        except OSError as exc:
            self.base_hint.configure(text=f"保存失败：{exc}", fg=self.colors["err"])
            return
        self.current = value
        if self.on_saved:
            self.on_saved(value)
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        self.grab_release()
        self.destroy()
