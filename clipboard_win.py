"""剪贴板读取（Windows）：纯 ctypes 实现，不启动任何子进程。

三个能力：
    probe()            -> {"files": bool, "image": bool, "text": bool}   几十微秒，不打开剪贴板数据
    get_image_paths()  -> list[str]    剪贴板里「复制的文件」中的图片路径
    grab_image()       -> PIL.Image|None   剪贴板里的位图（PNG / DIB / DIBV5 都能解）

失败一律返回空值，绝不抛异常（界面线程安全）。
"""

from __future__ import annotations

import ctypes
import io
import os
from ctypes import wintypes

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

CF_TEXT = 1
CF_BITMAP = 2
CF_DIB = 8
CF_UNICODETEXT = 13
CF_HDROP = 15
CF_DIBV5 = 17

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT

shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
shell32.DragQueryFileW.restype = wintypes.UINT

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


_PNG_FORMAT = 0


def _png_clipboard_format() -> int:
    global _PNG_FORMAT
    if not _PNG_FORMAT:
        try:
            _PNG_FORMAT = int(user32.RegisterClipboardFormatW("PNG"))
        except Exception:  # noqa: BLE001
            _PNG_FORMAT = -1
    return _PNG_FORMAT


def probe() -> dict:
    """不读数据，只问 Windows 有哪些格式可用（很快）。"""
    result = {"files": False, "image": False, "text": False}
    try:
        if user32.OpenClipboard(None):
            try:
                result["files"] = bool(user32.IsClipboardFormatAvailable(CF_HDROP))
                result["text"] = bool(user32.IsClipboardFormatAvailable(CF_UNICODETEXT)
                                      or user32.IsClipboardFormatAvailable(CF_TEXT))
                result["image"] = bool(user32.IsClipboardFormatAvailable(CF_DIBV5)
                                       or user32.IsClipboardFormatAvailable(CF_DIB)
                                       or user32.IsClipboardFormatAvailable(CF_BITMAP)
                                       or (_png_clipboard_format() > 0
                                           and user32.IsClipboardFormatAvailable(_png_clipboard_format())))
            finally:
                user32.CloseClipboard()
    except Exception:  # noqa: BLE001
        pass
    return result


def _global_bytes(handle) -> bytes | None:
    """GetClipboardData 返回的 HGLOBAL（剪贴板在打开状态下有效）。"""
    if not handle:
        return None
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        return None
    try:
        size = int(kernel32.GlobalSize(handle))
        if size <= 0:
            return None
        return ctypes.string_at(pointer, size)
    finally:
        kernel32.GlobalUnlock(handle)


def get_image_paths() -> list[str]:
    """剪贴板里如果是「复制的文件」，返回其中的图片路径。"""
    paths: list[str] = []
    try:
        if not user32.OpenClipboard(None):
            return []
        try:
            handle = user32.GetClipboardData(CF_HDROP)
            if not handle:
                return []
            count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
            for index in range(int(count)):
                length = shell32.DragQueryFileW(handle, index, None, 0)
                if length <= 0:
                    continue
                buffer = ctypes.create_unicode_buffer(length + 1)
                shell32.DragQueryFileW(handle, index, buffer, length + 1)
                if buffer.value:
                    paths.append(buffer.value)
        finally:
            user32.CloseClipboard()
    except Exception:  # noqa: BLE001
        return []
    return [p for p in paths
            if p.lower().endswith(IMAGE_EXTS) and os.path.isfile(p)]


def _dib_to_image(data: bytes):
    """把 CF_DIB / CF_DIBV5 的字节流还原成 PIL.Image。"""
    from PIL import Image  # 局部导入，模块被 import 时不强依赖

    if len(data) < 40:
        return None
    header = _BitmapInfoHeader.from_buffer_copy(data[:ctypes.sizeof(_BitmapInfoHeader)])
    width, height = int(header.biWidth), int(header.biHeight)
    if width <= 0 or height == 0:
        return None
    top_down = height < 0
    height = abs(height)
    bpp = int(header.biBitCount)
    compression = int(header.biCompression)

    header_size = int(header.biSize) or 40
    if header_size < 40 or header_size > len(data):
        header_size = 40
    palette_entries = 0
    if bpp <= 8:
        palette_entries = int(header.biClrUsed) or (1 << bpp)
    offset = header_size + palette_entries * 4
    if offset >= len(data):
        return None

    if bpp == 32:
        stride = width * 4
        pixels = data[offset:offset + stride * height]
        if len(pixels) < stride * height:
            return None
        raw = "BGRX" if compression in (0, 3, 6) else "BGRX"
        image = Image.frombuffer("RGB", (width, height), pixels, "raw", raw, stride, 1)
    elif bpp == 24:
        stride = ((width * 3 + 3) // 4) * 4
        pixels = data[offset:offset + stride * height]
        if len(pixels) < stride * height:
            return None
        image = Image.frombuffer("RGB", (width, height), pixels, "raw", "BGR", stride, 1)
    elif bpp == 8:
        stride = ((width + 3) // 4) * 4
        pixels = data[offset:offset + stride * height]
        if len(pixels) < stride * height:
            return None
        gray = Image.frombuffer("L", (width, height), pixels, "raw", "L", stride, 1)
        palette = data[header_size:header_size + palette_entries * 4]
        image = gray.convert("RGB")
        if len(palette) >= palette_entries * 4:
            rgb = []
            for i in range(palette_entries):
                b, g, r = palette[i * 4], palette[i * 4 + 1], palette[i * 4 + 2]
                rgb.extend((r, g, b))
            image.putpalette(rgb + [0] * (768 - len(rgb)))
            image = image.convert("RGB")
    else:
        return None

    if not top_down:
        image = image.transpose(Image.FLIP_TOP_BOTTOM)
    return image.convert("RGB")


def grab_image():
    """把剪贴板里的图片读成 PIL.Image；没有就返回 None。"""
    try:
        from PIL import Image
    except ModuleNotFoundError:
        return None

    try:
        if not user32.OpenClipboard(None):
            return None
        try:
            png_format = _png_clipboard_format()
            if png_format > 0 and user32.IsClipboardFormatAvailable(png_format):
                raw = _global_bytes(user32.GetClipboardData(png_format))
                if raw:
                    image = Image.open(io.BytesIO(raw))
                    image.load()
                    return image.convert("RGB")
            for fmt in (CF_DIBV5, CF_DIB):
                if user32.IsClipboardFormatAvailable(fmt):
                    raw = _global_bytes(user32.GetClipboardData(fmt))
                    if raw:
                        image = _dib_to_image(raw)
                        if image is not None:
                            return image
            return None
        finally:
            user32.CloseClipboard()
    except Exception:  # noqa: BLE001
        return None


def save_image_to_temp(image) -> str:
    """把 PIL.Image 存成临时 PNG（供表单复用已有的 add_reference 流程）。"""
    import tempfile

    handle, path = tempfile.mkstemp(prefix="qis-paste-", suffix=".png")
    os.close(handle)
    try:
        image.save(path, "PNG")
    except OSError:
        return ""
    return path
