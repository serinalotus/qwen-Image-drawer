"""把文件拖进窗口（Windows 原生 WM_DROPFILES），零第三方依赖。

用法：
    target = FileDropTarget(root, on_paths)      # on_paths(list[str]) 在 Tk 线程里被调用
    target.install()
    ...
    target.uninstall()

实现要点：
- Tk 在 Windows 上顶层窗口有一个真正的 HWND（winfo_id() 是它的子窗口，用 GetAncestor 取根）。
- DragAcceptFiles 让窗口接收 WM_DROPFILES；再子类化窗口过程，只在这条消息里取文件列表，
  立刻把结果塞进 Queue，真正的 UI 处理交给 Tk 的 after 轮询（绝不在窗口过程里碰 Tcl）。
- 任何一步失败都静默降级：应用照常可用，只是拖放无效。
"""

from __future__ import annotations

import ctypes
import queue
import traceback
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

WM_DROPFILES = 0x0233
GA_ROOT = 2
GWLP_WNDPROC = -4

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
shell32.DragAcceptFiles.restype = None
shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
shell32.DragQueryFileW.restype = wintypes.UINT
shell32.DragFinish.argtypes = [wintypes.HANDLE]
shell32.DragFinish.restype = None

if hasattr(user32, "SetWindowLongPtrW"):
    _set_wndproc = user32.SetWindowLongPtrW
    _set_wndproc.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    _set_wndproc.restype = ctypes.c_void_p
    _call_wndproc = user32.CallWindowProcW
    _call_wndproc.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                              wintypes.WPARAM, wintypes.LPARAM]
    _call_wndproc.restype = LRESULT
else:  # 32 位 Python
    _set_wndproc = user32.SetWindowLongW
    _set_wndproc.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    _set_wndproc.restype = ctypes.c_void_p
    _call_wndproc = user32.CallWindowProcW
    _call_wndproc.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                              wintypes.WPARAM, wintypes.LPARAM]
    _call_wndproc.restype = LRESULT


def _hwnd_of(root) -> int:
    hwnd = int(root.winfo_id())
    try:
        root_hwnd = user32.GetAncestor(wintypes.HWND(hwnd), GA_ROOT)
        if root_hwnd:
            return int(root_hwnd)
    except Exception:  # noqa: BLE001
        pass
    return hwnd


def _read_paths(hdrop) -> list[str]:
    count = int(shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0))
    paths: list[str] = []
    for index in range(count):
        length = int(shell32.DragQueryFileW(hdrop, index, None, 0))
        if length <= 0:
            continue
        buffer = ctypes.create_unicode_buffer(length + 2)
        shell32.DragQueryFileW(hdrop, index, buffer, length + 2)
        if buffer.value:
            paths.append(buffer.value)
    return paths


class FileDropTarget:
    """在 Tk 顶层窗口上启用「拖文件进来」。"""

    def __init__(self, root, on_paths):
        self.root = root
        self.on_paths = on_paths
        self.hwnd = 0
        self._old_proc: int | None = None
        self._proc = None
        self.pending: queue.Queue[list[str]] = queue.Queue()
        self._job = None
        self.installed = False

    # ---------------------------------------------------------- 安装
    def install(self) -> bool:
        try:
            self.hwnd = _hwnd_of(self.root)
            if not self.hwnd:
                return False
            self._proc = WNDPROC(self._wndproc)  # 必须持有引用，否则回调会被回收
            previous = _set_wndproc(wintypes.HWND(self.hwnd), GWLP_WNDPROC,
                                    ctypes.cast(self._proc, ctypes.c_void_p))
            self._old_proc = int(previous) if previous else None
            if not self._old_proc:
                return False
            shell32.DragAcceptFiles(wintypes.HWND(self.hwnd), True)
            self._job = self.root.after(120, self._drain)
            self.installed = True
            return True
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self.installed = False
            return False

    def uninstall(self) -> None:
        if self._job is not None:
            try:
                self.root.after_cancel(self._job)
            except Exception:  # noqa: BLE001
                pass
            self._job = None
        if self.installed and self.hwnd:
            try:
                shell32.DragAcceptFiles(wintypes.HWND(self.hwnd), False)
                if self._old_proc:
                    _set_wndproc(wintypes.HWND(self.hwnd), GWLP_WNDPROC,
                                 ctypes.cast(self._old_proc, ctypes.c_void_p))
            except Exception:  # noqa: BLE001
                pass
        self.installed = False

    # ---------------------------------------------------------- 窗口过程
    def _wndproc(self, hwnd, message, wparam, lparam):
        if message == WM_DROPFILES:
            try:
                paths = _read_paths(wparam)
                if paths:
                    self.pending.put(paths)
            except Exception:  # noqa: BLE001
                pass
            finally:
                try:
                    shell32.DragFinish(wparam)
                except Exception:  # noqa: BLE001
                    pass
            return 0
        if self._old_proc:
            return _call_wndproc(ctypes.c_void_p(self._old_proc), hwnd, message, wparam, lparam)
        return 0

    # ---------------------------------------------------------- 交给 Tk 线程
    def _drain(self) -> None:
        try:
            while True:
                paths = self.pending.get_nowait()
                try:
                    self.on_paths(paths)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
        except queue.Empty:
            pass
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        finally:
            try:
                self._job = self.root.after(120, self._drain)
            except Exception:  # noqa: BLE001
                self._job = None
