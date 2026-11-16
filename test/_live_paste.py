"""真实窗口交互验证：把图片放进系统剪贴板 → 向应用窗口发 Ctrl+V → 确认参考图 +1。"""

import ctypes
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "test"))

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

from PIL import Image, ImageGrab  # noqa: E402

TITLE = "千问图像工作台 · Qwen Image Studio"
user32 = ctypes.windll.user32
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
VK_CONTROL, VK_V = 0x11, 0x56
KEYEVENTF_KEYUP = 0x0002

proc = subprocess.Popen([sys.executable, str(ROOT / "app.py")])
hwnd = 0
for _ in range(60):
    time.sleep(0.5)
    hwnd = user32.FindWindowW(None, TITLE)
    if hwnd:
        break
if not hwnd:
    proc.terminate()
    raise SystemExit("window not found")

time.sleep(2.0)

# 1) 生成一张图并写进系统剪贴板（模拟「从浏览器复制图片」）
sample = Path(tempfile.mkdtemp()) / "clip.png"
image = Image.new("RGB", (256, 256), (30, 120, 210))
for x in range(256):
    for y in range(256):
        if (x - 128) ** 2 + (y - 128) ** 2 < 60 ** 2:
            image.putpixel((x, y), (240, 120, 60))
image.save(sample)
sys.argv = [sys.argv[0], str(sample)]
from smoke import _set_clipboard_image  # noqa: E402

_set_clipboard_image(str(sample))
print("clipboard image set")

# 2) 激活窗口（点一下预览空白处，确保焦点不在输入框）
HWND_TOPMOST, SWP_NOMOVE, SWP_NOSIZE = -1, 0x0002, 0x0001
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.ShowWindow(wintypes.HWND(hwnd), 9)
user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE)
user32.SetForegroundWindow(wintypes.HWND(hwnd))
time.sleep(1.0)
print("foreground:", hex(user32.GetForegroundWindow() or 0))

rect = wintypes.RECT()
user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
click_x = rect.left + int((rect.right - rect.left) * 0.72)
click_y = rect.top + int((rect.bottom - rect.top) * 0.45)
user32.SetCursorPos(click_x, click_y)
time.sleep(0.2)
user32.mouse_event(0x0002, 0, 0, 0, 0)  # left down
user32.mouse_event(0x0004, 0, 0, 0, 0)  # left up
time.sleep(0.5)

# 3) 发 Ctrl+V
user32.keybd_event(VK_CONTROL, 0, 0, 0)
user32.keybd_event(VK_V, 0, 0, 0)
time.sleep(0.05)
user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
time.sleep(2.0)

from smoke import _print_window_image  # noqa: E402
from PIL import Image as _Image  # noqa: E402

client_w, client_h = 1440, 900
shot = _print_window_image(hwnd, client_w, client_h)
if shot is None:
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
    shot = ImageGrab.grab(bbox=(rect.left - 1, rect.top - 1, rect.right + 1, rect.bottom + 1))
out = ROOT / "test" / "out" / "live-paste.png"
shot.save(out)
print("saved", out, shot.size)
proc.terminate()
