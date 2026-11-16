"""千问图像工作台 —— 图片落盘与目录工具。"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime
from typing import Iterable


def default_save_dir() -> str:
    """默认保存目录：系统「图片」目录下的 QwenImageStudio。"""
    home = os.path.expanduser("~")
    pictures = os.path.join(home, "Pictures")
    if not os.path.isdir(pictures):
        pictures = home
    return os.path.join(pictures, "QwenImageStudio")


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def display_path(path: str, limit: int = 64) -> str:
    """把用户目录缩成 ~，太长时保留头尾，方便在状态栏里看。"""
    if not path:
        return ""
    text = str(path)
    try:
        home = os.path.expanduser("~")
        if home and home != "~" and text.lower().startswith(home.lower()):
            text = "~" + text[len(home):]
    except Exception:  # noqa: BLE001
        pass
    if len(text) > limit:
        head = text[: max(8, limit // 2 - 4)]
        tail = text[-(limit // 2 - 3):]
        text = f"{head}…{tail}"
    return text


def _sanitize(text: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "-", text).strip("-")
    return cleaned[:24] or "image"


def suggest_name(index: int, prefix: str = "qwen-image", prompt: str = "") -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tail = f"-{_sanitize(prompt)}" if prompt else ""
    return f"{prefix}-{stamp}-{index}{tail}.png"


def save_image(raw: bytes, path: str) -> str:
    """把 PNG 字节写到 path（自动建目录，JPEG 后缀会转换）。"""
    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        ensure_dir(folder)
    if path.lower().endswith((".jpg", ".jpeg")):
        from io import BytesIO

        from PIL import Image

        image = Image.open(BytesIO(raw)).convert("RGB")
        image.save(path, format="JPEG", quality=94)
    else:
        with open(path, "wb") as handle:
            handle.write(raw)
    return path


def save_batch(images: Iterable[bytes], *, base_dir: str = "", prompt: str = "",
               prefix: str = "qwen-image") -> list[dict]:
    """自动保存一批图片，返回 [{"index":0,"path":...}]。"""
    folder = ensure_dir(base_dir or default_save_dir())
    stamp = time.strftime("%Y%m%d")
    day_dir = ensure_dir(os.path.join(folder, stamp))
    saved = []
    for index, raw in enumerate(images):
        path = os.path.join(day_dir, suggest_name(index + 1, prefix=prefix, prompt=prompt))
        save_image(raw, path)
        saved.append({"index": index, "path": path})
    return saved
