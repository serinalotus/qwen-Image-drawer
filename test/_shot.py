"""按窗口标题截图；--close 时截完关闭窗口。用于人工验收当前运行中的实例。"""

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:  # noqa: BLE001
    ctypes.windll.user32.SetProcessDPIAware()

from PIL import ImageGrab  # noqa: E402

TITLE = "千问图像工作台 · Qwen Image Studio"
OUT = Path(__file__).resolve().parent / "out" / "live-python315.png"

user32 = ctypes.windll.user32
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]

hwnd = user32.FindWindowW(None, TITLE)
if not hwnd:
    raise SystemExit("window not found")
user32.ShowWindow(hwnd, 9)          # SW_RESTORE
user32.SetForegroundWindow(hwnd)
time.sleep(1.8)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke import _print_window_image  # noqa: E402

img = _print_window_image(hwnd)
if img is None:
    rect = wintypes.RECT()
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
img.save(OUT)
print("saved", OUT, img.size)
if "--close" in sys.argv:
    user32.PostMessageW(hwnd, 0x0010, 0, 0)
    time.sleep(2)
    print("closed:", not user32.FindWindowW(None, TITLE))
