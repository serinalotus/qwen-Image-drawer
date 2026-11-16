"""千问图像工作台 —— 配置读写（%APPDATA%\\QwenImageStudio\\settings.json）。"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

import meta

APP_FOLDER = "QwenImageStudio"


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_FOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    return os.path.join(config_dir(), "settings.json")


def defaults() -> dict:
    value = dict(meta.DEFAULTS)
    value.update({"api_key": "", "save_dir": "", "window": "1440x900", "models_discovered": []})
    return value


def load() -> dict:
    value = defaults()
    path = config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if isinstance(stored, dict):
                value.update({k: v for k, v in stored.items() if k in value or k == "api_key"})
        except (OSError, json.JSONDecodeError):
            pass  # 配置损坏时用默认值，不阻塞启动
    value["api_key"] = str(value.get("api_key") or "").strip()
    return value


def save(value: dict) -> None:
    payload = {k: value[k] for k in defaults() if k in value}
    payload["api_key"] = str(value.get("api_key") or "")
    path = config_path()
    fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=config_dir())
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def mask_key(api_key: str) -> str:
    key = (api_key or "").strip()
    if not key:
        return ""
    if len(key) <= 10:
        return key[:3] + "····"
    return f"{key[:6]}····{key[-4:]}"


def apply_to(value: dict) -> dict[str, Any]:
    """给 API 层用的运行时设置（把地域/业务空间解析成 base_url）。"""
    return {
        "protocol": value.get("protocol") or meta.DEFAULTS["protocol"],
        "region": value.get("region") or meta.DEFAULTS["region"],
        "base_url": value.get("base_url") or "",
        "workspace_id": value.get("workspace_id") or "",
        "api_key": value.get("api_key") or "",
        "auto_save": bool(value.get("auto_save", True)),
        "save_dir": value.get("save_dir") or "",
    }


def effective_base_url(value: dict) -> str:
    url = meta.resolve_base_url(value.get("region") or meta.DEFAULTS["region"],
                                value.get("base_url") or "",
                                value.get("workspace_id") or "")
    return url or "（未设置）"
