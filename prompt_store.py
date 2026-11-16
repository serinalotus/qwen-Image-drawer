"""提示词收藏夹 —— 把常用的提示词（含反向提示词）存在本机，随时取用。

存储位置：%APPDATA%\\QwenImageStudio\\prompts.json
结构：{"version": 1, "items": [{"name", "prompt", "negative", "updated"}]}
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Any

import settings as settings_store


def _path() -> str:
    return os.path.join(settings_store.config_dir(), "prompts.json")


def load() -> list[dict]:
    """读取全部收藏；文件损坏时返回空列表，不阻塞启动。"""
    path = _path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items") if isinstance(data, dict) else data
    result = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        prompt = str(item.get("prompt") or "")
        if not name or not prompt:
            continue
        result.append({
            "name": name,
            "prompt": prompt,
            "negative": str(item.get("negative") or ""),
            "updated": float(item.get("updated") or 0),
        })
    result.sort(key=lambda entry: entry["updated"], reverse=True)
    return result


def save(items: list[dict]) -> None:
    """原子写入；写失败抛 OSError 交给上层提示。"""
    path = _path()
    payload = {"version": 1, "items": [
        {"name": item["name"], "prompt": item["prompt"], "negative": item.get("negative", ""),
         "updated": float(item.get("updated") or 0)}
        for item in items
    ]}
    fd, tmp = tempfile.mkstemp(prefix=".prompts-", suffix=".json", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def upsert(name: str, prompt: str, negative: str = "") -> list[dict]:
    """同名覆盖、否则新增；返回最新列表。"""
    name = str(name or "").strip()
    prompt = str(prompt or "")
    if not name or not prompt:
        raise ValueError("名称和提示词都不能为空")
    items = load()
    for item in items:
        if item["name"] == name:
            item.update({"prompt": prompt, "negative": str(negative or ""), "updated": time.time()})
            break
    else:
        items.append({"name": name, "prompt": prompt, "negative": str(negative or ""),
                      "updated": time.time()})
    save(items)
    return load()


def remove(name: str) -> list[dict]:
    items = [item for item in load() if item["name"] != name]
    save(items)
    return load()


def rename(old: str, new: str) -> list[dict]:
    new = str(new or "").strip()
    if not new:
        raise ValueError("名称不能为空")
    items = load()
    if any(item["name"] == new and item["name"] != old for item in items):
        raise ValueError("已经有同名提示词了")
    for item in items:
        if item["name"] == old:
            item["name"] = new
            item["updated"] = time.time()
    save(items)
    return load()


def suggest_name(prompt: str, limit: int = 18) -> str:
    """没填名字时，用提示词开头当默认名称。"""
    text = " ".join(str(prompt or "").split())
    return text[:limit] or "未命名提示词"


def find(items: list[dict], name: str) -> dict | None:
    for item in items:
        if item["name"] == name:
            return item
    return None


def describe(item: dict) -> str:
    stamp = ""
    if item.get("updated"):
        stamp = time.strftime("%m-%d %H:%M", time.localtime(item["updated"]))
    count = len(item.get("prompt") or "")
    negative = " · 带反向词" if item.get("negative") else ""
    return f"{stamp} · {count} 字{negative}"


def as_choice(item: dict) -> str:
    return f"{item['name']}　　{describe(item)}"


def any_items(items: list[dict]) -> bool:
    return bool(items)


def export_text(items: list[dict]) -> str:
    blocks: list[str] = []
    for item in items:
        block = f"### {item['name']}\n{item['prompt']}"
        if item.get("negative"):
            block += f"\n\n[反向提示词]\n{item['negative']}"
        blocks.append(block)
    return "\n\n".join(blocks)


def coerce(value: Any) -> list[dict]:
    return value if isinstance(value, list) else []
