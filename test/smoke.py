"""端到端冒烟：真实 tkinter 窗口 + 本地假服务，验证表单 → 请求 → 出图 → 保存 → 错误态。

运行：python test/smoke.py
输出：test/out/smoke-result.png、test/out/smoke-error.png、test/out/smoke-report.json
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = Path(__file__).resolve().parent
OUT_DIR = TEST_DIR / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TEST_DIR))

TMP = tempfile.mkdtemp(prefix="qis-smoke-")
os.environ["APPDATA"] = os.path.join(TMP, "appdata")
os.makedirs(os.environ["APPDATA"], exist_ok=True)

import tkinter as tk  # noqa: E402

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

import api  # noqa: E402
import settings as settings_store  # noqa: E402
import ui_theme  # noqa: E402
from mock_server import MockServer, STATE  # noqa: E402

RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})
    print(("  PASS " if ok else "  FAIL ") + name + (f" — {detail}" if detail and not ok else ""))
    return ok


def pump(root: tk.Tk, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def wait_idle(root: tk.Tk, application, timeout: float = 90.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        root.update()
        if not application.busy:
            pump(root, 0.4)
            return True
        time.sleep(0.03)
    return False


def _print_window_image(hwnd: int, width: int = 0, height: int = 0):
    """用 PrintWindow 直接把窗口画到内存 DC，被其它窗口挡着也能截到。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32.GetWindowDC.restype = wintypes.HDC
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.PrintWindow.restype = wintypes.BOOL
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL

    if not width or not height:
        rect = wintypes.RECT()
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None

    hdc = user32.GetWindowDC(wintypes.HWND(hwnd))
    if not hdc:
        return None
    mem = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(mem, bitmap)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    header = BITMAPINFOHEADER()
    header.biSize = 40
    header.biWidth = width
    header.biHeight = -height
    header.biPlanes = 1
    header.biBitCount = 32
    buffer = ctypes.create_string_buffer(width * height * 4)
    try:
        user32.PrintWindow(wintypes.HWND(hwnd), mem, 2)  # PW_RENDERFULLCONTENT
        copied = gdi32.GetDIBits(mem, bitmap, 0, height, buffer,
                                 ctypes.byref(header), 0)  # DIB_RGB_COLORS
        if copied != height:
            return None
        return Image.frombuffer("RGB", (width, height), buffer, "raw", "BGRX", 0, 1).copy()
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(wintypes.HWND(hwnd), hdc)


def screenshot(root: tk.Tk, name: str, window: tk.Misc | None = None) -> str:
    """优先 PrintWindow（被遮挡也能截到），失败再退回抓屏。"""
    root.lift()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    target = window if window is not None else root
    root.update()
    if window is not None:
        window.update_idletasks()
    pump(root, 0.35)
    path = OUT_DIR / name
    hwnd = 0
    try:
        import dnd_win

        hwnd = dnd_win._hwnd_of(target)
    except Exception:  # noqa: BLE001
        hwnd = 0
    image = None
    if hwnd:
        image = _print_window_image(hwnd)
        if image is not None and image.getextrema()[0][1] < 8:
            image = None  # 全黑视为失败
    if image is None:
        bbox = (target.winfo_rootx(), target.winfo_rooty(),
                target.winfo_rootx() + target.winfo_width(),
                target.winfo_rooty() + target.winfo_height())
        image = ImageGrab.grab(bbox=bbox)
    image.save(path)
    try:
        root.attributes("-topmost", False)
    except tk.TclError:
        pass
    root.update()
    return str(path)


def make_reference(path: str) -> str:
    image = Image.new("RGB", (768, 768), (30, 40, 70))
    draw = ImageDraw.Draw(image)
    draw.ellipse([180, 180, 588, 588], fill=(220, 140, 70), outline=(255, 220, 160), width=6)
    draw.rectangle([330, 330, 438, 438], fill=(60, 30, 20))
    image.save(path, format="PNG")
    return path



# ---------------------------------------------------------------- 剪贴板/拖放测试辅助
def _win32():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    return ctypes, wintypes, user32, kernel32


def _set_clipboard_text(text: str) -> None:
    ctypes, wintypes, user32, kernel32 = _win32()
    user32.OpenClipboard(None)
    try:
        user32.EmptyClipboard()
        data = text.encode("utf-16-le") + bytes([0, 0])
        handle = kernel32.GlobalAlloc(2, len(data))   # GMEM_MOVEABLE
        pointer = kernel32.GlobalLock(handle)
        assert pointer, "GlobalLock failed"
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        assert user32.SetClipboardData(13, handle), "SetClipboardData(CF_UNICODETEXT) failed"
    finally:
        user32.CloseClipboard()


def _set_clipboard_image(path: str) -> None:
    """把一张图放进剪贴板（CF_DIB，32 位、自上而下），验证粘贴图片链路。"""
    ctypes, wintypes, user32, kernel32 = _win32()
    image = Image.open(path).convert("RGB")
    width, height = image.size
    stride = width * 4
    import struct

    header = bytearray(40)
    struct.pack_into("<IiiHHIIiiII", header, 0,
                     40, width, -height, 1, 32, 0, stride * height, 0, 0, 0, 0)
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            r, g, b = image.getpixel((x, y))
            pixels += bytes((b, g, r, 255))
    payload = bytes(header) + bytes(pixels)
    user32.OpenClipboard(None)
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(2, len(payload))
        pointer = kernel32.GlobalLock(handle)
        assert pointer, "GlobalLock failed"
        ctypes.memmove(pointer, payload, len(payload))
        kernel32.GlobalUnlock(handle)
        assert user32.SetClipboardData(8, handle), "SetClipboardData(CF_DIB) failed"  # CF_DIB
    finally:
        user32.CloseClipboard()


def _send_fake_drop(hwnd: int, path: str) -> bool:
    """给窗口发一条真正的 WM_DROPFILES，模拟「把文件拖进来」。"""
    ctypes, wintypes, user32, kernel32 = _win32()

    class DROPFILES(ctypes.Structure):
        _fields_ = [("pFiles", wintypes.DWORD), ("pt", wintypes.POINT),
                    ("fNC", wintypes.BOOL), ("fWide", wintypes.BOOL)]

    header_size = ctypes.sizeof(DROPFILES)
    payload = path.encode("utf-16-le") + bytes([0, 0]) + bytes([0, 0])
    total = header_size + len(payload)
    handle = kernel32.GlobalAlloc(2, total)
    pointer = kernel32.GlobalLock(handle)
    assert pointer, "GlobalLock failed"
    drop = DROPFILES(pFiles=header_size, fNC=0, fWide=1)
    ctypes.memmove(pointer, ctypes.byref(drop), header_size)
    ctypes.memmove(pointer + header_size, payload, len(payload))
    kernel32.GlobalUnlock(handle)
    user32.SendMessageW(wintypes.HWND(hwnd), 0x0233, handle, 0)  # WM_DROPFILES
    return True


def main() -> int:
    save_dir = os.path.join(TMP, "pictures")
    server = MockServer().start()
    print(f"══ Python 桌面版冒烟 ══  mock={server.base_url}")

    config = settings_store.defaults()
    config.update({
        "protocol": "dashscope", "region": "custom", "base_url": server.base_url,
        "api_key": "sk-test", "auto_save": True, "save_dir": save_dir,
    })
    settings_store.save(config)
    check("配置已隔离写入临时 APPDATA", os.path.exists(settings_store.config_path()))

    import app as app_module

    app_module.enable_dpi_awareness()
    ui_theme.enable_dpi_awareness()
    root = tk.Tk()
    application = app_module.App(root)
    pump(root, 0.8)

    check("主窗口创建成功", root.winfo_exists() == 1, root.title())
    check("左表单右预览布局", application.form.winfo_width() > 300 and application.preview.winfo_width() > 400,
          f"{application.form.winfo_width()}x{application.preview.winfo_width()}")
    check("启动时有提示词占位与空预览", application.preview.state == "empty")
    check("状态栏展示配置摘要", "DashScope" in application.config_label.cget("text"),
          application.config_label.cget("text"))
    first_shot = screenshot(root, "smoke-initial.png")
    check("首屏截图已生成", os.path.exists(first_shot), first_shot)

    # ---------------- 尺寸：自动 = 不下发；自定义 = 自由宽高
    import meta as meta_module

    probe = dict(application.form.get_payload(), size="auto", prompt="尺寸测试")
    value, error = api.validate_payload(probe)
    check("自动尺寸能通过校验", error is None, error)
    parameters = api.build_body(value, "dashscope").get("parameters") or {}
    check("自动尺寸不下发 size（原生）", "size" not in parameters, parameters)
    check("自动尺寸不下发 size（OpenAI）", "size" not in api.build_body(value, "openai"))

    probe["size"] = "1000x1500"
    value, error = api.validate_payload(probe)
    check("自定义尺寸通过校验", error is None, error)
    check("原生协议用 宽*高", (api.build_body(value, "dashscope").get("parameters") or {}).get("size") == "1000*1500")
    check("OpenAI 协议用 宽x高", api.build_body(value, "openai").get("size") == "1000x1500")
    check("最大 2048×2048 可用", api.validate_payload(dict(probe, size="2048x2048"))[1] is None)
    check("超小尺寸被拦截", "过小" in ((api.validate_payload(dict(probe, size="100x100"))[1] or {}).get("message") or ""))
    check("超长宽比被拦截", "宽高比" in ((api.validate_payload(dict(probe, size="4000x400"))[1] or {}).get("message") or ""))
    check("预设数量扩充（≥20 项）", len(meta_module.SIZE_PRESETS) >= 20, len(meta_module.SIZE_PRESETS))

    form = application.form
    custom_label = next(p["label"] for p in meta_module.SIZE_PRESETS if p["value"] == "custom")
    form.size_var.set(custom_label)
    form._on_size_change()
    pump(root, 0.15)
    check("选自定义后出现宽高输入", bool(form.custom_size_row.winfo_ismapped()))
    form.scroll.canvas.yview_moveto(1.0)
    form.custom_w_var.set("1000")
    form.custom_h_var.set("1500")
    pump(root, 0.3)
    check("自定义尺寸写进 payload", form.get_payload()["size"] == "1000x1500", form.get_payload()["size"])
    check("自定义尺寸提示为有效", "像素" in form.custom_size_error.cget("text"), form.custom_size_error.cget("text"))
    check("自定义尺寸截图已生成", os.path.exists(screenshot(root, "smoke-custom-size.png")))
    form.custom_w_var.set("100")
    pump(root, 0.15)
    check("自定义尺寸过小时给出错误", "过小" in form.custom_size_error.cget("text"),
          form.custom_size_error.cget("text"))
    form.custom_w_var.set("1000")
    pump(root, 0.15)
    form.size_var.set("1:1 · 1024（方形）")
    form._on_size_change()
    pump(root, 0.15)
    check("切回预设后自定义行隐藏", not form.custom_size_row.winfo_ismapped())

    # ---------------- 模型列表：从服务端拉取并合并
    collected = api.list_models({"api_key": "sk-test", "region": "custom", "base_url": server.base_url,
                                 "workspace_id": ""})
    check("模型列表接口成功", bool(collected.get("ok")), collected.get("error"))
    ids = collected.get("models") or []
    check("只保留 qwen-image 系列", bool(ids) and all(i.startswith("qwen-image") for i in ids), ids)
    check("发现内置列表之外的新模型", "qwen-image-2.0-pro-2099-01-01" in ids, ids)
    form.scroll.canvas.yview_moveto(1.0)
    application._apply_models(collected)
    pump(root, 0.3)
    names = list(application.form.model_combo.cget("values"))
    check("刷新后下拉包含新模型", any("2099" in name for name in names), names)
    check("刷新结果写入配置", "qwen-image-2.0-pro-2099-01-01" in (settings_store.load().get("models_discovered") or []))
    check("新模型能力按 id 推断", meta_module.get_model("qwen-image-2.0-pro-2099-01-01")["max_refs"] >= 1)
    check("模型刷新截图已生成", os.path.exists(screenshot(root, "smoke-models.png")))

    # ---------------- 提示词库：保存 → 打开库 → 载入回表单
    import prompt_store

    application.form.set_prompt("雾中古镇的清晨，青石板路反光，柔和的侧逆光")
    application.form.set_negative("模糊、水印")
    pump(root, 0.15)
    application.save_prompt()
    pump(root, 0.3)
    name_dialog = getattr(application, "_name_dialog", None)
    check("保存提示词弹出命名对话框", bool(name_dialog) and name_dialog.winfo_exists())
    name_dialog.var.set("冒烟收藏")
    name_dialog._ok()
    pump(root, 0.3)
    saved = prompt_store.load()
    check("提示词已写入 prompts.json", any(i["name"] == "冒烟收藏" for i in saved), saved)
    check("保存后状态栏给出提示", "已保存提示词" in application.form.status_label.cget("text"),
          application.form.status_label.cget("text"))

    application.open_prompt_library()
    pump(root, 0.35)
    library = getattr(application, "_prompt_dialog", None)
    check("提示词库对话框打开", bool(library) and library.winfo_exists())
    items = library.items
    check("提示词库列出了收藏", any(i["name"] == "冒烟收藏" for i in items), items)
    check("提示词库截图已生成", os.path.exists(screenshot(root, "smoke-prompts.png", window=library)))
    application.form.set_prompt("先清掉再载入")
    library._select(0)
    library._load()
    pump(root, 0.3)
    check("载入后提示词回到表单", application.form._prompt_value().startswith("雾中古镇"),
          application.form._prompt_value()[:20])
    check("载入后反向提示词也恢复", application.form.get_negative() == "模糊、水印",
          application.form.get_negative())
    library.destroy()
    pump(root, 0.2)

    # ---------------- 文生图
    application.form.set_prompt("一只戴宇航头盔的橘猫，赛博朋克霓虹街道，电影感光线")
    application.form.model_var.set("千问图像 3.0 Pro")
    application.form._on_model_change()
    application.form.size_var.set("1:1 · 1024（方形）")
    application.form.n_var.set("2")
    application.start_generation()
    check("点击生成后进入生成中状态", application.busy or application.preview.state in ("loading", "result"),
          application.preview.state)
    finished = wait_idle(root, application)
    check("文生图流程结束（未超时）", finished)

    last = STATE["last"] or {}
    body = last.get("body") or {}
    content = (((body.get("input") or {}).get("messages") or [{}])[0].get("content")) or []
    text_parts = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    check("请求打到 DashScope 原生接口", str(last.get("path", "")).endswith(
        "/api/v1/services/aigc/multimodal-generation/generation"), last.get("path"))
    check("请求带 Bearer Key", "sk-test" in str(last.get("auth")), str(last.get("auth")))
    check("请求包含提示词", "宇航头盔" in text_parts, text_parts[:60])
    parameters = body.get("parameters") or {}
    check("请求张数为 2", str(parameters.get("n")) == "2", str(parameters.get("n")))
    check("请求尺寸为 1024x1024", "1024" in str(parameters.get("size")), str(parameters.get("size")))

    check("预览进入结果态", application.preview.state == "result", application.preview.state)
    check("出图 2 张", len(application.preview.results) == 2, str(len(application.preview.results)))
    png_files = sorted(Path(save_dir).rglob("*.png"))
    check("自动保存 2 个文件", len(png_files) == 2, str([p.name for p in png_files]))
    generated_shot = screenshot(root, "smoke-result.png")
    check("出图截图已生成", os.path.exists(generated_shot), generated_shot)
    check("状态栏显示完成", "已完成" in application.state_label.cget("text"),
          application.state_label.cget("text"))

    # ---------------- 图生图（带参考图）
    ref_path = make_reference(os.path.join(TMP, "ref.png"))
    check("参考图可加入表单", application.form.add_reference(ref_path))
    check("参考图数量正确", len(application.form.references) == 1)
    application.form.n_var.set("1")
    application.start_generation()
    finished = wait_idle(root, application)
    check("图生图流程结束", finished)
    last = STATE["last"] or {}
    body = last.get("body") or {}
    content = (((body.get("input") or {}).get("messages") or [{}])[0].get("content")) or []
    image_parts = [part for part in content if isinstance(part, dict) and part.get("image")]
    check("图生图请求带参考图 data URL", len(image_parts) == 1 and
          str(image_parts[0]["image"]).startswith("data:image/"))
    check("图生图出图成功", application.preview.state == "result" and len(application.preview.results) == 1,
          application.preview.state)
    i2i_shot = screenshot(root, "smoke-i2i.png")
    check("图生图截图已生成", os.path.exists(i2i_shot), i2i_shot)

    # ---------------- 错误态
    application.settings["api_key"] = "badkey"
    application.form.add_reference(ref_path)
    application.start_generation()
    wait_idle(root, application)
    check("错误态进入 error", application.preview.state == "error", application.preview.state)
    check("错误标题为 API Key 无效", "API Key 无效" in application.preview.error_title.cget("text"),
          application.preview.error_title.cget("text"))
    error_shot = screenshot(root, "smoke-error.png")
    check("错误态截图已生成", os.path.exists(error_shot), error_shot)

    # ---------------- 设置对话框
    try:
        from ui_settings import SettingsDialog

        demo_settings = dict(application.settings)
        demo_settings.update({"protocol": "dashscope", "region": "beijing-legacy",
                             "base_url": "", "workspace_id": "",
                             "api_key": "sk-abcdefghijkLMNOP7890", "models_discovered": []})
        dialog = SettingsDialog(root, application.theme, demo_settings, on_saved=lambda _v: None)
        pump(root, 0.4)
        check("设置对话框可打开", dialog.winfo_exists() == 1)
        # 截图用中性保存目录，避免把本机用户名带进文档图片
        dialog.dir_var.set("C:" + chr(92) + "Users" + chr(92) + "Public" + chr(92)
                           + "Pictures" + chr(92) + "QwenImageStudio")
        pump(root, 0.2)
        settings_shot = screenshot(root, "smoke-settings.png", window=dialog)
        check("设置截图已生成", os.path.exists(settings_shot), settings_shot)
        dialog._cancel()
        pump(root, 0.2)
        check("设置对话框可关闭", not dialog.winfo_exists())
    except Exception as exc:  # noqa: BLE001
        check("设置对话框可打开", False, f"{type(exc).__name__}: {exc}")

    # ---------------- 杂项：图标 / 快捷键 / 尺寸记忆 / 耗时格式
    check("应用图标存在", os.path.exists(os.path.join(ROOT, "assets", "app.ico")))
    check("Esc 已绑定取消生成", bool(root.bind("<Escape>")))
    application.settings["window"] = "1600x1000"
    check("窗口尺寸可恢复", application._initial_size() == (1600, 1000), str(application._initial_size()))
    application.settings["window"] = "坏值"
    check("尺寸异常时回落到默认", application._initial_size() == (1440, 900),
          str(application._initial_size()))
    check("耗时格式（秒）", ui_theme.fmt_elapsed(0.42) == "0.4 秒", ui_theme.fmt_elapsed(0.42))
    check("耗时格式（分）", ui_theme.fmt_elapsed(75) == "1 分 15 秒", ui_theme.fmt_elapsed(75))


    # ---------------- 交互体验：焦点提示 / 粘贴速度 / 粘贴图片 / 拖放
    base_refs = len(application.form.references)

    application.form.prompt_text.focus_set()
    root.update()
    application._refresh_focus_hint()
    check("焦点提示：提示词框", "提示词" in application.focus_label.cget("text"),
          application.focus_label.cget("text"))

    application.preview.canvas.focus_set()
    root.update()
    application._refresh_focus_hint()
    check("焦点提示：窗口/预览", "窗口" in application.focus_label.cget("text"),
          application.focus_label.cget("text"))

    application.form.prompt_text.focus_set()
    root.update()
    ring_on = str(application.form.prompt_wrap.cget("highlightbackground"))
    check("提示词框聚焦时有强调描边", ring_on == application.colors["accent"], ring_on)
    card_on = str(application.form.prompt_card.cget("highlightbackground"))
    check("聚焦时整张卡片一起高亮", card_on == application.colors["accent"], card_on)
    focus_shot = screenshot(root, "smoke-focus-active.png")
    check("聚焦态截图已生成", os.path.exists(focus_shot), focus_shot)

    application.preview.canvas.focus_set()
    root.update()
    ring_off = str(application.form.prompt_wrap.cget("highlightbackground"))
    check("失焦后描边复原", ring_off == application.colors["border"], ring_off)
    card_off = str(application.form.prompt_card.cget("highlightbackground"))
    check("失焦后卡片描边复原", card_off == application.colors["border"], card_off)

    check("拖放区文案提到拖拽", "拖拽" in application.form.drop_main.cget("text"),
          application.form.drop_main.cget("text"))

    # 粘贴文字：必须走控件原生路径，不能因为读图片而变慢
    _set_clipboard_text("测试粘贴的提示词")
    application.form.prompt_text.delete("1.0", "end")
    application.form._prompt_placeholder = False
    application.form.prompt_text.focus_set()
    root.update()
    first_cost = None
    steady_cost = None
    for round_index in range(2):
        application.form.prompt_text.delete("1.0", "end")
        root.update()
        started = time.time()
        application.form.prompt_text.event_generate("<Control-v>")
        root.update()
        cost = time.time() - started
        if round_index == 0:
            first_cost = cost
        else:
            steady_cost = cost
    pasted = application.form.prompt_text.get("1.0", "end").strip()
    check("粘贴文字：内容进入提示词框", pasted == "测试粘贴的提示词", pasted[:40])
    check("粘贴文字：首次耗时小于 1.2 秒（含 Tk 剪贴板初始化）", first_cost < 1.2, f"{first_cost:.3f}s")
    check("粘贴文字：稳态耗时小于 0.1 秒", steady_cost < 0.1, f"{steady_cost:.3f}s")
    check("粘贴文字：没有被当成图片", len(application.form.references) == base_refs)

    # 粘贴图片：焦点不在输入框时，Ctrl+V 应当加参考图
    _set_clipboard_image(ref_path)
    application.preview.canvas.focus_set()
    root.update()
    started = time.time()
    application._on_paste()
    for _ in range(60):
        pump(root, 0.05)
        if len(application.form.references) > base_refs:
            break
    cost = time.time() - started
    check("粘贴图片：参考图 +1", len(application.form.references) == base_refs + 1,
          str(len(application.form.references)))
    check("粘贴图片：耗时小于 2 秒", cost < 2.0, f"{cost:.2f}s")
    check("粘贴参考图截图已生成", os.path.exists(screenshot(root, "smoke-paste.png")))

    # 拖放：给窗口发一条真实的 WM_DROPFILES
    check("拖放已安装", bool(getattr(application, "_dnd", None) and application._dnd.installed))
    if getattr(application, "_dnd", None):
        while application.form.references:
            application.form.remove_reference(0)
        pump(root, 0.15)
        before = len(application.form.references)
        _send_fake_drop(application._dnd.hwnd, ref_path)
        for _ in range(40):
            pump(root, 0.05)
            if len(application.form.references) > before:
                break
        check("拖放：参考图 +1", len(application.form.references) == before + 1,
              str(len(application.form.references)))

    experience_shot = screenshot(root, "smoke-focus.png")
    check("焦点/交互截图已生成", os.path.exists(experience_shot), experience_shot)

    # ---------------- 关闭
    try:
        application.on_close()
    except tk.TclError:
        pass

    server.stop()
    passed = sum(1 for item in RESULTS if item["ok"])
    failed = len(RESULTS) - passed
    report = {"passed": passed, "failed": failed, "results": RESULTS, "mock_url": server.base_url,
              "saved_dir": save_dir, "tmp": TMP}
    (OUT_DIR / "smoke-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果：{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
