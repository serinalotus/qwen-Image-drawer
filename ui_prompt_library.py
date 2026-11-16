"""千问图像工作台 —— 提示词库对话框（保存 / 载入 / 重命名 / 删除）。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Callable

import prompt_store
import ui_theme
from ui_form import PrimaryButton, ScrollArea


class PromptLibraryDialog(tk.Toplevel):
    """看一眼所有收藏，双击或用按钮载入；也可以顺手删掉/改名。"""

    def __init__(self, master, theme: dict, on_pick: Callable[[dict], None]):
        super().__init__(master)
        self.theme = theme
        self.colors = theme["colors"]
        self.fonts = theme["fonts"]
        self.on_pick = on_pick
        self.items: list[dict] = prompt_store.load()
        self._selected: str = ""

        self.title("提示词库")
        self.configure(bg=self.colors["panel"])
        self.resizable(False, False)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())
        self.bind("<Return>", lambda _e: self._load())

        self._build()
        self._fit_geometry(master)
        self._refresh_list()
        self.grab_set()
        self.focus_force()

    # ------------------------------------------------------------ 布局
    def _fit_geometry(self, master) -> None:
        self.update_idletasks()
        width, height = 660, 560
        master.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + (master.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{max(30, x)}+{max(30, y)}")
        self.update_idletasks()
        ui_theme.enable_dark_titlebar(self)

    def _build(self) -> None:
        c, f = self.colors, self.fonts
        wrap = tk.Frame(self, bg=c["panel"])
        wrap.pack(fill="both", expand=True, padx=18, pady=14)

        foot = tk.Frame(wrap, bg=c["panel"])
        foot.pack(fill="x", side="bottom", pady=(12, 0))
        PrimaryButton(foot, self.theme, "载入到表单", self._load, height=38, width=132).pack(side="right")
        ui_theme.flat_button(foot, self.theme, "关闭", self._close, fg=c["muted"], padx=18, pady=9,
                             bg=c["card"]).pack(side="right", padx=(0, 8))
        self.delete_btn = ui_theme.flat_button(foot, self.theme, "删除", self._delete, fg=c["warn"],
                                               padx=14, pady=9, bg=c["card"])
        self.delete_btn.pack(side="left")
        self.rename_btn = ui_theme.flat_button(foot, self.theme, "重命名", self._rename, fg=c["muted"],
                                               padx=14, pady=9, bg=c["card"])
        self.rename_btn.pack(side="left", padx=(8, 0))

        head = tk.Frame(wrap, bg=c["panel"])
        head.pack(fill="x", pady=(0, 10))
        tk.Label(head, text="提示词库", bg=c["panel"], fg=c["text"], font=f["title"]).pack(side="left")
        self.count_label = tk.Label(head, text="", bg=c["panel"], fg=c["muted"], font=f["tiny"])
        self.count_label.pack(side="right")

        body = tk.Frame(wrap, bg=c["panel"])
        body.pack(fill="both", expand=True)

        # 左侧列表
        left = tk.Frame(body, bg=c["card"], highlightthickness=1, highlightbackground=c["border"])
        left.pack(side="left", fill="both", expand=False)

        self.listbox_frame = tk.Frame(left, bg=c["card"])
        self.listbox_frame.pack(fill="both", expand=True, padx=1, pady=1)
        self.scroll = ScrollArea(self.listbox_frame, self.theme, width=250)
        self.scroll.pack(fill="both", expand=True)
        self.rows_frame = self.scroll.inner

        self._rows: list[dict] = []

        # 右侧预览
        right = tk.Frame(body, bg=c["card"], highlightthickness=1, highlightbackground=c["border"])
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        preview = tk.Frame(right, bg=c["card"])
        preview.pack(fill="both", expand=True, padx=14, pady=12)
        self.preview_title = tk.Label(preview, text="从左边选一条", bg=c["card"], fg=c["text"],
                                      font=f["button"], anchor="w")
        self.preview_title.pack(fill="x")
        self.preview_meta = tk.Label(preview, text="", bg=c["card"], fg=c["muted"], font=f["tiny"], anchor="w")
        self.preview_meta.pack(fill="x", pady=(2, 8))

        self.preview_text = tk.Text(preview, bg=c["card"], fg=c["text"], font=f["body"], bd=0,
                                    highlightthickness=0, wrap="word", height=10, cursor="arrow")
        self.preview_text.pack(fill="both", expand=True)
        self.preview_text.configure(state="disabled")

    # ------------------------------------------------------------ 数据刷新
    def _refresh_list(self) -> None:
        c, f = self.colors, self.fonts
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._rows = []
        self.count_label.configure(text=f"共 {len(self.items)} 条")

        if not self.items:
            empty = tk.Frame(self.rows_frame, bg=c["card"])
            empty.pack(fill="both", expand=True, pady=40)
            tk.Label(empty, text="还没有收藏", bg=c["card"], fg=c["text"], font=f["button"]).pack()
            tk.Label(empty, text="回到主窗口写一段提示词，\n点「保存提示词」就会出现在这里。",
                     bg=c["card"], fg=c["muted"], font=f["tiny"], justify="center").pack(pady=(6, 0))
            self.preview_title.configure(text="还没有收藏")
            self.preview_meta.configure(text="")
            self._set_preview("")
            return

        for index, item in enumerate(self.items):
            row = tk.Frame(self.rows_frame, bg=c["card"], cursor="hand2")
            row.pack(fill="x", padx=8, pady=(2, 0))
            name_label = tk.Label(row, text=item["name"], bg=c["card"], fg=c["text"], font=f["body"],
                                  anchor="w", justify="left", wraplength=200)
            name_label.pack(fill="x", pady=(6, 0))
            meta_label = tk.Label(row, text=prompt_store.describe(item), bg=c["card"], fg=c["muted"],
                                  font=f["tiny"], anchor="w")
            meta_label.pack(fill="x", pady=(0, 6))
            for widget in (row, name_label, meta_label):
                widget.bind("<Button-1>", lambda _e, i=index: self._select(i))
                widget.bind("<Double-Button-1>", lambda _e, i=index: self._select(i, load=True))
            self._rows.append({"frame": row, "name": name_label, "meta": meta_label, "item": item})

        target = 0
        for index, row in enumerate(self._rows):
            if row["item"]["name"] == self._selected:
                target = index
                break
        self._select(target)

    def _select(self, index: int, load: bool = False) -> None:
        if not self._rows:
            return
        index = max(0, min(index, len(self._rows) - 1))
        c = self.colors
        for position, row in enumerate(self._rows):
            selected = position == index
            bg = c["input_bg"] if selected else c["card"]
            for widget in (row["frame"], row["name"], row["meta"]):
                widget.configure(bg=bg)
            row["name"].configure(fg=c["accent"] if selected else c["text"])
        item = self._rows[index]["item"]
        self._selected = item["name"]
        self.preview_title.configure(text=item["name"])
        self.preview_meta.configure(text=prompt_store.describe(item))
        self._set_preview(item["prompt"] + (f"\n\n[反向提示词]\n{item['negative']}" if item.get("negative") else ""))
        if load:
            self._load()

    def _set_preview(self, text: str) -> None:
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.configure(state="disabled")

    def _current_item(self) -> dict | None:
        return prompt_store.find(self.items, self._selected)

    # ------------------------------------------------------------ 动作
    def _load(self) -> None:
        item = self._current_item()
        if not item:
            messagebox.showinfo("提示词库", "先在左边选一条提示词。", parent=self)
            return
        self.on_pick(dict(item))
        self._close()

    def _delete(self) -> None:
        item = self._current_item()
        if not item:
            messagebox.showinfo("提示词库", "先在左边选一条提示词。", parent=self)
            return
        if not messagebox.askyesno("删除提示词", f"确定删除「{item['name']}」吗？", parent=self):
            return
        try:
            self.items = prompt_store.remove(item["name"])
        except OSError as exc:
            messagebox.showerror("删除失败", f"写文件失败：{exc}", parent=self)
            return
        self._selected = ""
        self._refresh_list()

    def _rename(self) -> None:
        item = self._current_item()
        if not item:
            messagebox.showinfo("提示词库", "先在左边选一条提示词。", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("重命名")
        dialog.configure(bg=self.colors["panel"])
        dialog.transient(self)
        dialog.resizable(False, False)
        tk.Label(dialog, text="新名称", bg=self.colors["panel"], fg=self.colors["muted"],
                 font=self.fonts["tiny"]).pack(anchor="w", padx=16, pady=(14, 4))
        var = tk.StringVar(value=item["name"])
        entry = ui_theme.ttk.Entry(dialog, textvariable=var, width=32, font=self.fonts["body"])
        entry.pack(padx=16, fill="x")
        entry.focus_set()
        entry.select_range(0, "end")

        def apply_rename() -> None:
            try:
                self.items = prompt_store.rename(item["name"], var.get())
            except (ValueError, OSError) as exc:
                messagebox.showerror("重命名失败", str(exc), parent=dialog)
                return
            self._selected = var.get().strip()
            dialog.destroy()
            self._refresh_list()

        buttons = tk.Frame(dialog, bg=self.colors["panel"])
        buttons.pack(fill="x", padx=16, pady=12)
        PrimaryButton(buttons, self.theme, "确定", apply_rename, height=34, width=96).pack(side="right")
        ui_theme.flat_button(buttons, self.theme, "取消", dialog.destroy, fg=self.colors["muted"],
                             padx=14, pady=6, bg=self.colors["card"]).pack(side="right", padx=(0, 8))
        entry.bind("<Return>", lambda _e: apply_rename())
        dialog.update_idletasks()
        dialog.geometry(f"+{self.winfo_rootx() + 120}+{self.winfo_rooty() + 160}")
        dialog.grab_set()
        ui_theme.enable_dark_titlebar(dialog)

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


class NameDialog(tk.Toplevel):
    """给提示词起名字的小对话框（深色，和主界面一致）。"""

    def __init__(self, master, theme: dict, title: str, default: str,
                 on_ok: Callable[[str], None], hint: str = ""):
        super().__init__(master)
        self.theme = theme
        self.colors = theme["colors"]
        self.fonts = theme["fonts"]
        self.on_ok = on_ok
        self.result = ""

        self.title(title)
        self.configure(bg=self.colors["panel"])
        self.resizable(False, False)
        self.transient(master)

        wrap = tk.Frame(self, bg=self.colors["panel"])
        wrap.pack(fill="both", expand=True, padx=18, pady=14)
        tk.Label(wrap, text=title, bg=self.colors["panel"], fg=self.colors["text"],
                 font=self.fonts["card_title"], anchor="w").pack(fill="x")
        if hint:
            tk.Label(wrap, text=hint, bg=self.colors["panel"], fg=self.colors["muted"],
                     font=self.fonts["tiny"], anchor="w").pack(fill="x", pady=(2, 8))

        self.var = tk.StringVar(value=default)
        entry = ui_theme.ttk.Entry(wrap, textvariable=self.var, width=34, font=self.fonts["body"])
        entry.pack(fill="x", pady=(8, 12))
        entry.focus_set()
        entry.select_range(0, "end")
        entry.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())

        buttons = tk.Frame(wrap, bg=self.colors["panel"])
        buttons.pack(fill="x")
        PrimaryButton(buttons, self.theme, "确定", self._ok, height=34, width=96).pack(side="right")
        ui_theme.flat_button(buttons, self.theme, "取消", self.destroy, fg=self.colors["muted"],
                             padx=14, pady=6, bg=self.colors["card"]).pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.update_idletasks()
        width, height = 380, self.winfo_reqheight()
        master.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + 160
        self.geometry(f"{width}x{height}+{max(30, x)}+{max(30, y)}")
        self.update_idletasks()
        ui_theme.enable_dark_titlebar(self)
        self.grab_set()
        self.focus_force()

    def _ok(self) -> None:
        name = self.var.get().strip()
        if not name:
            return
        self.result = name
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        self.on_ok(name)
