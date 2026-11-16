"""千问图像工作台 —— 主窗口：左侧表单 + 右侧预览，生成在后台线程执行。

启动方式：
    双击 run.bat            （无控制台窗口）
    python app.py           （带控制台，便于排查）
    python app.py --smoke   （自动化冒烟，不进入主循环）
"""

from __future__ import annotations

import ctypes
import os
import queue
import re
import sys
import threading
import tkinter as tk
from tkinter import messagebox

# 第三方依赖：缺了就别静默闪退，main() 里会弹窗告诉用户装什么
_MISSING_DEPS = ""
try:
    import PIL  # noqa: F401
    import requests  # noqa: F401
except ModuleNotFoundError as _exc:  # pragma: no cover - 环境问题
    _MISSING_DEPS = _exc.name or "PIL / requests"

if not _MISSING_DEPS:
    import api
    import meta
    import prompt_store
    import settings as settings_store
    import storage
    import ui_theme
    from ui_form import FormPanel
    from ui_preview import PreviewPanel
    from ui_prompt_library import NameDialog, PromptLibraryDialog
    from ui_settings import SettingsDialog

OS_DIR = os.path.dirname(os.path.abspath(__file__))
WINDOW_TITLE = "千问图像工作台 · Qwen Image Studio"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.theme = ui_theme.setup_styles(root)
        self.colors = self.theme["colors"]
        self.fonts = self.theme["fonts"]
        self.settings = settings_store.load()
        stored_models = self.settings.get("models_discovered") or []
        if stored_models:
            meta.set_discovered_models(stored_models)
        self.busy = False
        self.last_payload: dict | None = None
        self.cancel_event = threading.Event()
        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self._poll_job = None

        root.title(WINDOW_TITLE)
        root.configure(bg=self.colors["bg"])
        self._apply_icon()
        self._center_window(*self._initial_size())
        self.root.update_idletasks()
        ui_theme.enable_dark_titlebar(self.root)
        root.minsize(1120, 720)

        self._build_layout()
        self.form.apply_defaults(self.settings)   # 恢复上次的模型 / 尺寸 / 张数等
        self._bind_shortcuts()
        self._refresh_status_bar()

        # 拖放（Windows 原生 WM_DROPFILES）。失败也不影响其它功能。
        self._dnd = None
        try:
            import dnd_win

            self._dnd = dnd_win.FileDropTarget(root, self._on_files_dropped)
            self._dnd.install()
        except Exception:  # noqa: BLE001
            self._dnd = None

        self.root.bind_all("<FocusIn>", self._on_focus_change, add="+")
        self.root.after(120, self._refresh_focus_hint)

        self._poll_job = root.after(80, self._poll_queue)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        root.after(500, self._check_first_run)

    # ------------------------------------------------------------ 布局
    def _apply_icon(self) -> None:
        icon = os.path.join(OS_DIR, "assets", "app.ico")
        if os.path.exists(icon):
            try:
                self.root.iconbitmap(default=icon)
            except tk.TclError:
                pass

    def _initial_size(self) -> tuple[int, int]:
        match = re.match(r"^(\d{3,5})x(\d{3,5})$", str(self.settings.get("window") or ""))
        if not match:
            return 1440, 900
        width, height = int(match.group(1)), int(match.group(2))
        return max(1120, width), max(720, height)

    def _center_window(self, width: int, height: int) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(width, screen_w - 60)
        height = min(height, screen_h - 90)
        x = max(20, (screen_w - width) // 2)
        y = max(10, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _build_layout(self) -> None:
        c = self.colors
        body = tk.Frame(self.root, bg=c["bg"])
        body.pack(fill="both", expand=True)

        self.form = FormPanel(body, self.theme, on_generate=self.start_generation,
                              on_cancel=self.cancel_generation, settings=self.settings,
                              on_open_settings=self.open_settings,
                              on_refresh_models=self.refresh_models,
                              on_save_prompt=self.save_prompt,
                              on_open_prompt_library=self.open_prompt_library)
        self.form.pack(side="left", fill="y")

        tk.Frame(body, bg=c["border"], width=1).pack(side="left", fill="y")

        self.preview = PreviewPanel(body, self.theme, on_retry=self.start_generation,
                                    on_open_settings=self.open_settings,
                                    get_settings=lambda: self.settings)
        self.preview.pack(side="left", fill="both", expand=True)

        self._build_status_bar()

    def _build_status_bar(self) -> None:
        c, f = self.colors, self.fonts
        bar = tk.Frame(self.root, bg=c["panel"], height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self.state_label = tk.Label(bar, text="就绪", bg=c["panel"], fg=c["muted"], font=f["tiny"])
        self.state_label.pack(side="left", padx=(14, 0))

        tk.Frame(bar, bg=c["border"], width=1, height=12).pack(side="left", padx=10, pady=8)
        self.focus_label = tk.Label(bar, text="焦点：窗口", bg=c["panel"], fg=c["muted"], font=f["tiny"])
        self.focus_label.pack(side="left")

        self.config_label = tk.Label(bar, text="", bg=c["panel"], fg=c["muted"], font=f["tiny"])
        self.config_label.pack(side="right", padx=(0, 14))

    # ------------------------------------------------------------ 快捷键
    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-comma>", lambda _e: self.open_settings())
        self.root.bind("<Control-s>", lambda _e: self.preview._save_current())
        self.root.bind("<F5>", lambda _e: self.start_generation())
        self.root.bind("<Control-v>", self._on_paste)
        self.root.bind("<Escape>", lambda _e: self.cancel_generation())

    # ------------------------------------------------------------ 设置
    def _check_first_run(self) -> None:
        if not self.settings.get("api_key"):
            self.form.set_status("还没有配置 API Key，先填一个再生成", "warn")
            self.open_settings()

    def open_settings(self) -> None:
        if getattr(self, "_settings_dialog", None) is not None and self._settings_dialog.winfo_exists():
            self._settings_dialog.lift()
            self._settings_dialog.focus_force()
            return
        self._settings_dialog = SettingsDialog(self.root, self.theme, self.settings,
                                               on_saved=self._on_settings_saved)

    # ------------------------------------------------------------ 提示词库
    def save_prompt(self) -> None:
        payload = self.form.get_payload()
        prompt = payload.get("prompt") or ""
        if not prompt:
            self.form.set_status("提示词是空的，先写点内容再保存", "warn")
            return
        existing = [item["name"] for item in prompt_store.load()]
        default = prompt_store.suggest_name(prompt)

        def on_ok(name: str) -> None:
            overwrite = name in existing
            if overwrite and not messagebox.askyesno(
                    "覆盖提示词", f"「{name}」已经存在，要覆盖吗？", parent=self.root):
                return
            try:
                items = prompt_store.upsert(name, prompt, self.form.get_negative())
            except (ValueError, OSError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=self.root)
                return
            self.form.set_status(f"已保存提示词「{name}」，当前共 {len(items)} 条", "ok")

        self._name_dialog = NameDialog(self.root, self.theme, "保存提示词", default, on_ok,
                                       hint="起个好记的名字，之后可以在「提示词库」里一键载入")

    def open_prompt_library(self) -> None:
        if getattr(self, "_prompt_dialog", None) is not None and self._prompt_dialog.winfo_exists():
            self._prompt_dialog.lift()
            self._prompt_dialog.focus_force()
            return
        self._prompt_dialog = PromptLibraryDialog(self.root, self.theme, on_pick=self._load_prompt_item)

    def _load_prompt_item(self, item: dict) -> None:
        self.form.set_prompt(item.get("prompt") or "")
        self.form.set_negative(item.get("negative") or "")
        self.form.prompt_text.focus_set()
        self.form.set_status(f"已载入提示词「{item.get('name')}」", "ok")

    def refresh_models(self) -> None:
        """向服务端请求最新的 qwen-image 模型列表，并更新下拉框。"""
        if not self.settings.get("api_key"):
            self.form.set_status("还没有 API Key，先填一个再刷新模型", "warn")
            self.open_settings()
            return
        if getattr(self, "_refreshing_models", False):
            return
        self._refreshing_models = True
        self.form.refresh_models_btn.configure(fg=self.colors["muted"])
        self.form.set_status("正在向服务端查询可用模型…", "info")
        self.preview.set_status("正在查询可用模型…", "info")

        def worker():
            result = api.list_models(self.settings)
            try:
                self.queue.put(("models", result))
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _apply_models(self, result: dict) -> None:
        self._refreshing_models = False
        self.form.refresh_models_btn.configure(fg=self.colors["accent"])
        if not result.get("ok"):
            error = result.get("error") or {}
            message = error.get("message") or "获取模型列表失败"
            self.form.set_status(message, "err")
            self.preview.set_status(message, "err")
            return
        models = result.get("models") or []
        meta.set_discovered_models(models)
        note = f"已从服务端同步 {len(models)} 个模型（{result.get('base', '')}）"
        self.form.set_models(meta.all_models(), note)
        self.settings["models_discovered"] = models
        try:
            settings_store.save(self.settings)
        except Exception as exc:  # noqa: BLE001
            note += f"，但保存失败：{exc.__class__.__name__}"
        self._refresh_status_bar()
        self.form.set_status(note, "ok")
        self.preview.set_status(f"可用模型已更新：{len(models)} 个", "ok")

    def _on_settings_saved(self, value: dict) -> None:
        self.settings = value
        self.form.apply_settings(value)
        self._refresh_status_bar()
        if value.get("api_key"):
            self.form.set_status("设置已保存，可以开始生成", "ok")
            self.preview.set_status("设置已保存", "ok")
        else:
            self.form.set_status("还没有 API Key，无法生成", "warn")

    def _refresh_status_bar(self) -> None:
        proto = meta.get_protocol(self.settings.get("protocol") or meta.DEFAULTS["protocol"])
        region = meta.get_region(self.settings.get("region") or meta.DEFAULTS["region"])
        model = meta.get_model(self.settings.get("model") or meta.DEFAULTS["model"])
        folder = self.settings.get("save_dir") or ""
        folder = storage.display_path(folder) if folder else "默认图片目录"
        self.config_label.configure(
            text=f'{proto["label"].split("（")[0]} · {region["label"]} · {model["name"]} · 自动保存：{folder}')

    def _set_state(self, text: str, kind: str = "info") -> None:
        color = {"info": self.colors["muted"], "ok": self.colors["ok"],
                 "warn": self.colors["warn"], "err": self.colors["err"]}.get(kind, self.colors["muted"])
        self.state_label.configure(text=text, fg=color)

    # ------------------------------------------------------------ 生成
    def start_generation(self, payload: dict | None = None) -> None:
        if self.busy:
            return
        payload = payload or self.form.get_payload()
        self.last_payload = payload

        if not payload.get("prompt"):
            self.form.set_status("请先填写提示词", "warn")
            self.form.focus_prompt()
            return

        value, error = api.validate_payload(payload)
        if error:
            self.form.set_status(error.get("message") or "参数有误", "err")
            return

        if not self.settings.get("api_key"):
            self.form.set_status("还没有配置 API Key，正在打开设置…", "warn")
            self.open_settings()
            return

        self.busy = True
        self.cancel_event.clear()
        self.form.set_busy(True)
        self.preview.clear_toast()
        self.preview.show_loading("正在请求模型…")
        self._set_state("生成中…", "info")
        self.form.set_status("正在请求模型…")

        worker = threading.Thread(target=self._run_generate, args=(payload,), daemon=True)
        worker.start()

    def _run_generate(self, payload: dict) -> None:
        runtime = settings_store.apply_to(self.settings)
        try:
            result = api.generate(
                runtime, payload, cancel_event=self.cancel_event,
                on_stage=lambda text: self.queue.put(("stage", text)),
            )
        except Exception as exc:  # noqa: BLE001 - 线程内兜底，避免静默退出
            result = {"ok": False, "error": api.make_error("UNEXPECTED", f"{type(exc).__name__}: {exc}")}
        self.queue.put(("done", (result, payload)))

    def cancel_generation(self) -> None:
        if not self.busy:
            return
        self.cancel_event.set()
        self.form.set_busy(True, canceling=True)
        self._set_state("正在取消…", "warn")
        self.form.set_status("已发出取消请求，正在等待网络返回…", "warn")

    # ------------------------------------------------------------ 队列
    def _poll_queue(self) -> None:
        try:
            for _ in range(12):
                kind, payload = self.queue.get_nowait()
                if kind == "stage":
                    self.preview.update_stage(payload)
                    self.form.set_status(payload)
                elif kind == "done":
                    self._finish(*payload)
                elif kind == "paste_image":
                    self._apply_pasted_image(payload)
                elif kind == "paste_fail":
                    self.form.set_status(payload, "warn")
                elif kind == "models":
                    self._apply_models(payload)
        except queue.Empty:
            pass
        self._poll_job = self.root.after(80, self._poll_queue)

    def _finish(self, result: dict, payload: dict) -> None:
        self.busy = False
        self.form.set_busy(False)

        if not result.get("ok"):
            error = result.get("error") or api.make_error("UNEXPECTED")
            code = error.get("code") or ""
            if code == "CANCELED":
                self.preview.show_empty()
                self.preview.set_status("已取消本次生成", "warn")
                self.form.set_status("已取消", "warn")
                self._set_state("已取消", "warn")
                return
            self.preview.show_error(error, request_id=error.get("request_id") or "")
            hint = error.get("hint") or ""
            self.form.set_status(hint or (error.get("message") or "生成失败"), "err")
            self._set_state(f'失败：{code or "未知错误"}', "err")
            return

        # 自动保存
        saved: list[dict] = []
        if self.settings.get("auto_save", True) and result.get("images"):
            try:
                saved = storage.save_batch(
                    result["images"],
                    base_dir=self.settings.get("save_dir") or "",
                    prompt=(payload.get("prompt") or "")[:20],
                )
            except OSError as exc:
                self.preview.set_status(f"自动保存失败：{exc}", "err")
        result["saved"] = saved

        count = len(result.get("images") or [])
        self.preview.show_result(result)
        elapsed = result.get("elapsed") or 0
        if saved:
            self.preview.set_status(f"已生成 {count} 张，自动保存 {len(saved)} 张", "ok")
        else:
            self.preview.set_status(f"已生成 {count} 张", "ok")
        self.form.set_status(f"已生成 {count} 张 · 耗时 {ui_theme.fmt_elapsed(elapsed)}", "ok")
        request_id = result.get("request_id") or ""
        self._set_state("已完成 · 耗时 " + ui_theme.fmt_elapsed(elapsed) + (f" · {request_id}" if request_id else ""), "ok")

    # ------------------------------------------------------------ 拖拽 / 粘贴
    def _on_files_dropped(self, paths: list[str]) -> None:
        images = [p for p in paths if p.lower().endswith(IMAGE_EXTS)]
        if not images:
            self.form.set_status("只支持拖入图片文件（PNG / JPG / WebP / BMP）", "warn")
            return
        added = 0
        skipped = 0
        for path in images:
            if self.form.add_reference(path):
                added += 1
            else:
                skipped += 1
        if added:
            self.form.set_status(f"已拖入 {added} 张参考图" + (f"，{skipped} 张被跳过" if skipped else ""), "ok")

    # ------------------------------------------------------------ 焦点提示
    def _focus_name(self) -> str:
        try:
            widget = self.root.focus_get()
        except (tk.TclError, KeyError):
            widget = None
        if widget is None:
            return "窗口"
        names = {
            str(self.form.prompt_text): "提示词框（Ctrl+V 粘贴文字）",
            str(self.form.negative_text): "反向提示词框（Ctrl+V 粘贴文字）",
            str(self.form.seed_entry): "种子输入框",
        }
        key = str(widget)
        if key in names:
            return names[key]
        try:
            parent = widget.master
            while parent is not None:
                if parent is self.form.ref_area:
                    return "参考图区"
                if parent is self.root:
                    break
                parent = parent.master
        except (tk.TclError, AttributeError):
            pass
        return "窗口（Ctrl+V 当作图片粘贴）"

    def _on_focus_change(self, _event=None) -> None:
        self._refresh_focus_hint()

    def _refresh_focus_hint(self) -> None:
        if not hasattr(self, "focus_label"):
            return
        try:
            self.focus_label.configure(text=f"焦点：{self._focus_name()}")
        except tk.TclError:
            pass

    def _warm_clipboard(self) -> None:
        """预热 Tk 的剪贴板通道：首次 Ctrl+V 要初始化一次，先在本进程里试读一次。"""
        try:
            self.root.clipboard_get(type="UTF8_STRING")
        except tk.TclError:
            pass
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 粘贴
    def _on_paste(self, _event=None):
        """Ctrl+V 的规则（可预测，不用猜）：

        - 焦点在提示词/反向提示词/种子框里：当作「粘贴文字」，完全交给控件自己处理；
        - 焦点在别处（预览、参考图区、窗口空白）：当作「粘贴图片/文件」，加为参考图。
        """
        try:
            import clipboard_win
        except Exception:  # noqa: BLE001
            return None

        focus = self.root.focus_get()
        text_like = isinstance(focus, (tk.Text, tk.Entry)) or type(focus).__name__ in (
            "Entry", "Text", "TCombobox", "Spinbox")

        try:
            info = clipboard_win.probe()
        except Exception:  # noqa: BLE001
            info = {"files": False, "image": False, "text": False}

        if text_like:
            # 输入框里永远优先粘文字；只有当剪贴板里没有文字、却有图片时才改成加参考图
            if info["text"] or not info["image"]:
                return None
            self._paste_image_async()
            return "break"

        paths = clipboard_win.get_image_paths() if info["files"] else []
        if paths:
            self._on_files_dropped(paths)
            return "break"
        if info["image"]:
            self._paste_image_async()
            return "break"

        if info["text"]:
            self.form.set_status("剪贴板里是文字；把光标点进提示词框再 Ctrl+V 就能粘贴", "warn")
        else:
            self.form.set_status("剪贴板里没有图片或文字", "warn")
        return "break"

    def _paste_image_async(self) -> None:
        """读剪贴板图片可能在几十毫秒以上，放到后台线程，完成后走队列回 UI。"""
        self.form.set_status("正在读取剪贴板图片…", "info")

        def worker() -> None:
            try:
                import clipboard_win

                image = clipboard_win.grab_image()
                if image is None:
                    self.queue.put(("paste_fail", "剪贴板里没有可用的图片"))
                    return
                path = clipboard_win.save_image_to_temp(image)
                if not path:
                    self.queue.put(("paste_fail", "剪贴板图片保存失败"))
                    return
                self.queue.put(("paste_image", path))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("paste_fail", f"读取剪贴板失败：{type(exc).__name__}"))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_pasted_image(self, path: str) -> None:
        added = self.form.add_reference(path)
        if added:
            self.form.set_status("已从剪贴板加入 1 张参考图", "ok")
        else:
            self.form.set_status("剪贴板图片没有加入（可能已达上限或格式不支持）", "warn")

    # ------------------------------------------------------------ 关闭
    def on_close(self) -> None:
        if self.busy:
            self.cancel_event.set()
        if getattr(self, "_dnd", None) is not None:
            try:
                self._dnd.uninstall()
            except Exception:  # noqa: BLE001
                pass
        if self._poll_job:
            try:
                self.root.after_cancel(self._poll_job)
            except tk.TclError:
                pass
        try:
            self.settings["window"] = f"{self.root.winfo_width()}x{self.root.winfo_height()}"
            try:
                payload = self.form.get_payload()
                self.settings["model"] = payload.get("model") or self.settings.get("model")
                self.settings["size"] = payload.get("size") or self.settings.get("size")
                self.settings["n"] = payload.get("n") or self.settings.get("n")
            except Exception:  # noqa: BLE001
                pass
            settings_store.save(self.settings)
        except OSError:
            pass
        self.root.destroy()


def _show_missing_deps() -> None:
    """依赖缺失时给出可操作提示（pythonw 没有控制台，必须弹窗）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    message = (
        f"缺少 Python 依赖：{_MISSING_DEPS}\n\n"
        "请打开命令行运行下面这行，装好后再双击启动：\n\n"
        f'    "{sys.executable}" -m pip install -r "{os.path.join(here, "requirements.txt")}"\n\n'
        "（如果提示找不到 pip，先运行 python -m ensurepip）"
    )
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("缺少依赖 · 千问图像工作台", message)
        root.destroy()
    except Exception:  # noqa: BLE001 - 连 tkinter 都起不来时退化到 stderr
        print(message, file=sys.stderr)


def main() -> int:
    if _MISSING_DEPS:
        _show_missing_deps()
        return 1
    enable_dpi_awareness()
    root = tk.Tk()
    App(root)
    if "--smoke" in sys.argv:
        return 0
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
