"""千问图像工作台 —— 接口层（参数校验 / 请求构造 / HTTP 调用 / 响应解析）。

对外只暴露少量函数：
    validate_payload(payload)        -> (value, error)        校验并规范化 UI 输入
    build_request(payload, protocol) -> (body, path)          构造请求体
    generate(settings, payload, ...)  -> result dict          同步生成（阻塞调用，需在后台线程执行）
    encode_reference(path)            -> dict                 读取本地图片并转成 data URL
    fetch_image(url)                  -> bytes                下载结果图

所有错误统一成 dict：{"code": str, "message": str, "hint": str, "status": int|None, "request_id": str}
"""

from __future__ import annotations

import base64
import io
import json
import time
from typing import Any, Optional
from urllib.parse import urlparse

import requests

import meta

# ---------------------------------------------------------------- 错误提示表

HINTS = {
    "InvalidApiKey": "请检查 API Key 是否填写正确，且与所选地域一致",
    "Unauthorized": "请检查 API Key 是否有效，且与所选地域一致",
    "AccessDenied": "访问被拒绝，请检查 API Key 权限、业务空间 ID 与地域配置",
    "Throttling": "请求过于频繁或超出配额，请稍后重试",
    "RateLimitExceeded": "请求过于频繁，请稍后重试",
    "InvalidParameter": "请检查请求参数（提示词、尺寸、参考图、种子）是否符合文档要求",
    "MissingParameter": "缺少必填参数，请检查提示词、模型与尺寸",
    "DataInspectionFailed": "内容审核未通过，请调整提示词后重试",
    "DataInspection": "内容审核未通过，请调整提示词后重试",
    "Arrearage": "账户余额不足或已欠费，请前往阿里云百炼控制台充值",
    "InsufficientQuota": "配额不足，请检查账户额度或稍后重试",
    "ModelNotFound": "模型不存在或未在该地域开通，请更换模型或地域",
    "ModelAccessDenied": "当前账号无权访问该模型，请到控制台开通",
    "CONFIG": "请检查服务地址、地域与业务空间 ID 配置",
    "PARAM": "请检查请求参数",
    "NETWORK": "网络连接失败，请检查网络、代理或服务地址",
    "TIMEOUT": "请求超时，请稍后重试或减少生成数量",
    "ABORTED": "请求已取消",
    "CANCELED": "操作已取消",
    "NO_API_KEY": "请先在「设置」中填写 API Key",
    "EMPTY_RESULT": "服务端未返回图片，请稍后重试",
    "NOT_FOUND": "图片不存在或已失效，请重新生成",
    "UNEXPECTED": "发生意外错误，请重试",
    "SAVE_FAILED": "保存失败，请检查目标目录是否可写",
}


def hint_for(code: str, status: Optional[int] = None) -> str:
    if code and code in HINTS:
        return HINTS[code]
    if isinstance(status, int):
        if status == 401:
            return HINTS["InvalidApiKey"]
        if status == 403:
            return HINTS["AccessDenied"]
        if status == 429:
            return HINTS["Throttling"]
        if status >= 500:
            return "服务端错误，请稍后重试"
        if status >= 400:
            return "请检查请求参数与账号权限"
    return ""


def make_error(code: str, message: str = "", status: Optional[int] = None,
               request_id: str = "") -> dict:
    return {
        "code": code or "UNEXPECTED",
        "message": message or "",
        "hint": hint_for(code, status),
        "status": status,
        "request_id": request_id or "",
    }


# ---------------------------------------------------------------- 参数校验

def normalize_size(raw: Any) -> tuple[bool, str, Optional[dict]]:
    value = str("" if raw is None else raw).strip().lower()
    if not value:
        return False, "", make_error("PARAM", "尺寸不能为空")
    if value == "auto":
        return True, "auto", None
    if "x" not in value and "*" not in value and "×" not in value:
        return False, "", make_error("PARAM", "尺寸格式无效，应为「宽x高」（例如 1024x1024）或 auto")
    for sep in ("×", "*"):
        value = value.replace(sep, "x")
    parts = value.split("x")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return False, "", make_error("PARAM", "尺寸格式无效，应为「宽x高」（例如 1024x1024）或 auto")
    width, height = int(parts[0]), int(parts[1])
    if width < 1 or height < 1:
        return False, "", make_error("PARAM", "尺寸的宽高必须为正整数")
    area = width * height
    limits = meta.LIMITS
    if area < limits["output_min_area"]:
        return False, "", make_error("PARAM", "输出尺寸过小：像素面积不能小于 512x512")
    if area > limits["output_max_area"]:
        return False, "", make_error("PARAM", "输出尺寸过大：像素面积不能超过 2048x2048")
    if max(width, height) / min(width, height) > limits["output_max_aspect"]:
        return False, "", make_error("PARAM", f"输出宽高比不能超过 {limits['output_max_aspect']}:1")
    return True, f"{width}x{height}", None


def validate_payload(payload: dict) -> tuple[Optional[dict], Optional[dict]]:
    """校验 UI 输入，返回 (规范化的值, 错误)。两者有且只有一个非 None。"""
    limits = meta.LIMITS

    model = meta.get_model(str(payload.get("model") or meta.DEFAULTS["model"]))
    if model["id"] != str(payload.get("model") or meta.DEFAULTS["model"]):
        return None, make_error("PARAM", f"不支持的模型：{payload.get('model')}")

    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        return None, make_error("PARAM", "提示词不能为空")

    try:
        n = int(payload.get("n", 1))
    except (TypeError, ValueError):
        return None, make_error("PARAM", f"生成数量需为 {limits['n_min']}~{limits['n_max']} 的整数")
    if n < limits["n_min"] or n > limits["n_max"]:
        return None, make_error("PARAM", f"生成数量需为 {limits['n_min']}~{limits['n_max']} 的整数")

    seed_raw = payload.get("seed", None)
    seed = None
    if seed_raw not in (None, ""):
        try:
            seed = int(seed_raw)
        except (TypeError, ValueError):
            return None, make_error("PARAM", f"随机种子需为 {limits['seed_min']}~{limits['seed_max']} 的整数")
        if seed < limits["seed_min"] or seed > limits["seed_max"]:
            return None, make_error("PARAM", f"随机种子需为 {limits['seed_min']}~{limits['seed_max']} 的整数")

    size_input = payload.get("size") or meta.DEFAULTS["size"]
    ok, size, error = normalize_size(size_input)
    if not ok:
        return None, error

    mode_requested = "agent" if payload.get("prompt_extend_mode") == "agent" else "direct"
    nowledge = model["prompt_extend_modes"]
    extend_mode = mode_requested if mode_requested in nowledge else "direct"

    refs = [item for item in (payload.get("images") or []) if item]
    if len(refs) > model["max_refs"]:
        return None, make_error("PARAM", f"{model['name']} 最多支持 {model['max_refs']} 张参考图")
    mode = "i2i" if refs else "t2i"
    if extend_mode == "agent" and mode == "i2i":
        return None, make_error("PARAM", "「智能改写」仅支持文生图，请先移除参考图或改用直接改写")

    images = []
    for index, item in enumerate(refs, start=1):
        data_url = str((item or {}).get("data_url") or "").strip()
        label = f"第 {index} 张参考图"
        if not data_url:
            return None, make_error("PARAM", f"{label}数据为空，请重新添加")
        if not data_url.startswith("data:image/"):
            return None, make_error("PARAM", f"{label}不是有效的图片数据（需为 PNG/JPG/WebP）")
        try:
            header, b64 = data_url.split(",", 1)
            raw = base64.b64decode(b64, validate=False)
        except (ValueError, IndexError):
            return None, make_error("PARAM", f"{label}不是有效的 Base64 图片数据")
        if len(raw) > limits["image_max_bytes"]:
            return None, make_error("PARAM", f"{label}超过 {limits['image_max_bytes'] // 1024 // 1024}MB 限制")
        images.append({
            "data_url": data_url,
            "name": str(item.get("name") or label),
            "width": int(item.get("width") or 0),
            "height": int(item.get("height") or 0),
            "bytes": len(raw),
        })

    negative = str(payload.get("negative_prompt") or "").strip()
    value = {
        "model": model,
        "model_id": model["id"],
        "prompt": prompt,
        "negative_prompt": negative,
        "n": n,
        "seed": seed,
        "size": size,
        "prompt_extend": bool(payload.get("prompt_extend", True)),
        "prompt_extend_mode": extend_mode,
        "enable_thinking": bool(payload.get("enable_thinking", True)) if model["supports_thinking"] else False,
        "watermark": bool(payload.get("watermark", False)),
        "mode": mode,
        "images": images,
    }
    return value, None


# ---------------------------------------------------------------- 请求构造

def _extra_props(value: dict) -> dict:
    props: dict = {}
    if value["model"]["supports_negative_prompt"] and value["negative_prompt"]:
        props["negative_prompt"] = value["negative_prompt"]
    if value["seed"] is not None:
        props["seed"] = value["seed"]
    return props


def build_body(value: dict, protocol: str) -> dict:
    if protocol == "openai":
        body: dict = {"model": value["model_id"], "prompt": value["prompt"]}
        if value["images"]:
            body["image"] = [item["data_url"] for item in value["images"]]
        body.update({
            "n": value["n"],
            "prompt_extend": value["prompt_extend"],
            "prompt_extend_mode": value["prompt_extend_mode"],
            "enable_thinking": value["enable_thinking"],
            "watermark": value["watermark"],
        })
        if value["size"] != "auto":
            body["size"] = value["size"]
        body.update(_extra_props(value))
        return body

    content = [{"image": item["data_url"]} for item in value["images"]]
    content.append({"text": value["prompt"]})
    parameters = {
        "prompt_extend": value["prompt_extend"],
        "prompt_extend_mode": value["prompt_extend_mode"],
        "enable_thinking": value["enable_thinking"],
        "n": value["n"],
        "watermark": value["watermark"],
    }
    if value["size"] != "auto":
        parameters["size"] = value["size"].replace("x", "*")
    parameters.update(_extra_props(value))
    return {
        "model": value["model_id"],
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": parameters,
    }


def build_request(payload: dict, protocol: str) -> tuple[dict, str]:
    value, error = validate_payload(payload)
    if error:
        raise ValueError(json.dumps(error, ensure_ascii=False))
    proto = meta.get_protocol(protocol)
    return build_body(value, proto["id"]), proto["path"]


# ---------------------------------------------------------------- 参考图编码

def encode_reference(path: str, max_side: int = 2048) -> dict:
    """读取本地图片 → base64 data URL；失败时抛出 ValueError（中文信息）。"""
    from PIL import Image

    limits = meta.LIMITS
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise ValueError(f"读取图片失败：{exc}") from exc
    if not raw:
        raise ValueError("图片文件为空")
    if len(raw) > limits["image_max_bytes"]:
        raise ValueError(f"图片超过 {limits['image_max_bytes'] // 1024 // 1024}MB 限制，请先压缩")

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as exc:  # noqa: BLE001 - Pillow 抛出的异常类型很杂
        raise ValueError("无法识别该图片格式（支持 PNG / JPG / WebP / BMP / GIF）") from exc

    width, height = image.size
    if width < limits["image_min_side"] or height < limits["image_min_side"]:
        raise ValueError(f"图片宽高需在 {limits['image_min_side']}~{limits['image_max_side']} 像素之间")
    if width > limits["image_max_side"] or height > limits["image_max_side"]:
        raise ValueError(f"图片宽高需在 {limits['image_min_side']}~{limits['image_max_side']} 像素之间")
    if max(width, height) / min(width, height) > limits["image_max_aspect"]:
        raise ValueError(f"图片长宽比不能超过 {limits['image_max_aspect']}:1")

    # 过大的图先等比缩小，避免请求体过大
    if max(width, height) > max_side:
        ratio = max_side / max(width, height)
        image = image.resize((max(1, int(width * ratio)), max(1, int(height * ratio))), Image.LANCZOS)
        width, height = image.size
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=92)
        raw = buffer.getvalue()
        mime = "image/jpeg"
    else:
        mime = (Image.MIME.get(image.format or "") or "image/png").lower()
        if mime not in ("image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp"):
            mime = "image/png"
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="PNG")
            raw = buffer.getvalue()

    data_url = "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))
    return {
        "path": path,
        "name": path.replace("\\", "/").rsplit("/", 1)[-1],
        "data_url": data_url,
        "width": width,
        "height": height,
        "bytes": len(raw),
        "mime": mime,
    }


# ---------------------------------------------------------------- 结果图下载

def fetch_image(url: str, timeout: int = 180) -> bytes:
    if not url:
        raise ValueError("图片地址为空")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不支持的图片地址：{url[:60]}")
    response = requests.get(url, timeout=timeout)
    if response.status_code != 200:
        raise ValueError(f"下载图片失败（HTTP {response.status_code}）")
    data = response.content
    if len(data) < 64:
        raise ValueError("下载到的图片数据为空")
    return data


# ---------------------------------------------------------------- 响应解析

def _collect_dashscope_images(body: dict) -> list:
    urls = []
    output = (body or {}).get("output") or {}
    for choice in output.get("choices") or []:
        message = (choice or {}).get("message") or {}
        for part in message.get("content") or []:
            if isinstance(part, dict) and isinstance(part.get("image"), str) and part["image"]:
                urls.append(part["image"])
    return urls


def _fallback_code(status: int) -> str:
    return {401: "InvalidApiKey", 403: "AccessDenied", 429: "Throttling", 400: "InvalidParameter"}.get(
        status, f"HTTP_{status}"
    )


def _map_http_error(protocol: str, status: int, body: Any, text: str, request_id: str) -> dict:
    code = ""
    message = ""
    if isinstance(body, dict):
        if protocol == "openai" and isinstance(body.get("error"), dict):
            error = body["error"]
            code = str(error.get("code") or "")
            message = str(error.get("message") or "")
            if not message and error.get("param"):
                message = f"{error.get('param')} 参数不合法"
        else:
            code = str(body.get("code") or "")
            message = str(body.get("message") or "")
    if not code:
        code = _fallback_code(status)
    if not message:
        snippet = (text or "").strip()
        message = snippet if snippet and len(snippet) <= 300 and not snippet.startswith("{") else f"请求失败（HTTP {status}）"
    return make_error(code, message, status, request_id)


def parse_response(protocol: str, status: int, headers: dict, text: str) -> dict:
    """把 HTTP 响应解析成 {ok, images, request_id, usage} 或 {ok: False, error}。"""
    try:
        body = json.loads(text) if text else None
    except json.JSONDecodeError:
        body = None

    header_request_id = ""
    for key, value in (headers or {}).items():
        if key.lower() == "x-request-id":
            header_request_id = str(value)
            break
    request_id = ""
    if isinstance(body, dict):
        request_id = str(body.get("request_id") or "") or header_request_id
    request_id = request_id or header_request_id

    if not (200 <= status < 300):
        return {"ok": False, "error": _map_http_error(protocol, status, body, text, request_id)}

    if protocol == "dashscope":
        images = _collect_dashscope_images(body)
        business_code = str((body or {}).get("code") or "")
        if not images:
            if business_code:
                return {"ok": False, "error": _map_http_error(protocol, status, body, text, request_id)}
            return {"ok": False, "error": make_error("EMPTY_RESULT", "服务端未返回图片", status, request_id)}
        return {
            "ok": True,
            "images": images,
            "request_id": request_id,
            "usage": (body or {}).get("usage") or {},
        }

    if isinstance(body, dict) and body.get("error"):
        return {"ok": False, "error": _map_http_error(protocol, status, body, text, request_id)}
    data = (body or {}).get("data") if isinstance(body, dict) else None
    images = [item["url"] for item in (data or []) if isinstance(item, dict) and isinstance(item.get("url"), str)]
    if not images:
        return {"ok": False, "error": make_error("EMPTY_RESULT", "服务端未返回图片", status, request_id)}
    return {
        "ok": True,
        "images": images,
        "request_id": request_id,
        "usage": (body or {}).get("usage") or {},
    }


# ---------------------------------------------------------------- 生成主流程

def list_models(settings: dict, timeout: int = 20) -> dict:
    """从 DashScope 的 OpenAI 兼容接口拉模型列表，只保留 qwen-image 系列。

    返回 {"ok": True, "models": [id...], "base": 实际请求的域名, "count": n} 或 {"ok": False, "error"}。
    永不抛异常。
    """
    api_key = str(settings.get("api_key") or "").strip()
    if not api_key:
        return {"ok": False, "error": make_error("NO_API_KEY", "请先在「设置」中填写 API Key")}

    base_url = meta.resolve_base_url(
        settings.get("region") or meta.DEFAULTS["region"],
        settings.get("base_url") or "",
        settings.get("workspace_id") or "",
    )
    candidates = []
    if base_url.startswith(("http://", "https://")) and "{workspaceid}" not in base_url.lower():
        candidates.append(base_url.rstrip("/"))
    # 业务空间域名没填 workspace id 时，退回通用域名
    for fallback in ("https://dashscope.aliyuncs.com",):
        if fallback not in candidates:
            candidates.append(fallback)

    headers = {"Authorization": f"Bearer {api_key}"}
    last_error = None
    for base in candidates:
        url = base + "/compatible-mode/v1/models"
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            last_error = make_error("NETWORK", f"连接模型列表接口失败：{exc.__class__.__name__}")
            continue
        if response.status_code != 200:
            last_error = _map_http_error("openai", response.status_code, None, response.text,
                                         response.headers.get("X-Request-Id", ""))
            if response.status_code in (401, 403):
                return {"ok": False, "error": last_error, "base": base}
            continue
        try:
            data = response.json()
        except ValueError:
            last_error = make_error("INVALID", "模型列表不是合法 JSON")
            continue
        items = data.get("data") or data.get("models") or []
        ids = []
        for item in items:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or item.get("model") or "").strip()
            if model_id.startswith("qwen-image"):
                ids.append(model_id)
        ids = sorted(set(ids), key=lambda value: (not value.startswith("qwen-image-3"), value))
        if ids:
            return {"ok": True, "models": ids, "base": base, "count": len(ids)}
        last_error = make_error("NOT_FOUND", "服务端没有返回 qwen-image 系列模型")
    return {"ok": False, "error": last_error or make_error("UNKNOWN", "获取模型列表失败")}


def generate(settings: dict, payload: dict, cancel_event=None, on_stage=None) -> dict:
    """同步执行一次生成，永不抛异常。

    settings: {"protocol", "base_url", "region", "workspace_id", "api_key"}
    payload : UI 表单值（见 validate_payload）
    返回 {"ok": True, "images": [PNG bytes], "urls": [...], "request_id", "usage", "elapsed"} 或 {"ok": False, "error"}
    """
    started = time.time()

    def stage(text: str) -> None:
        if on_stage:
            try:
                on_stage(text)
            except Exception:  # noqa: BLE001 - 进度回调不应影响主流程
                pass

    api_key = str(settings.get("api_key") or "").strip()
    if not api_key:
        return {"ok": False, "error": make_error("NO_API_KEY", "请先在「设置」中填写 API Key")}

    value, error = validate_payload(payload)
    if error:
        return {"ok": False, "error": error}

    protocol = str(settings.get("protocol") or meta.DEFAULTS["protocol"])
    base_url = meta.resolve_base_url(
        settings.get("region") or meta.DEFAULTS["region"],
        settings.get("base_url") or "",
        settings.get("workspace_id") or "",
    )
    if not base_url.startswith(("http://", "https://")):
        return {"ok": False, "error": make_error("CONFIG", "服务地址无效，请填写以 http(s):// 开头的 Base URL")}

    proto = meta.get_protocol(protocol)
    url = base_url + proto["path"]
    body = build_body(value, proto["id"])
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    stage("正在请求模型…")
    timeout = meta.LIMITS["request_timeout"]
    try:
        response = requests.post(url, headers=headers, json=body, timeout=(15, timeout))
    except requests.exceptions.Timeout:
        return {"ok": False, "error": make_error("TIMEOUT", "请求超时，请稍后重试或减少生成数量")}
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "error": make_error("NETWORK", f"网络请求失败：{exc}")}

    if cancel_event is not None and cancel_event.is_set():
        return {"ok": False, "error": make_error("CANCELED", "操作已取消")}

    parsed = parse_response(proto["id"], response.status_code, dict(response.headers), response.text)
    if not parsed["ok"]:
        return parsed

    urls = parsed["images"]
    images: list[bytes] = []
    for index, image_url in enumerate(urls, start=1):
        stage(f"正在下载第 {index}/{len(urls)} 张…")
        if cancel_event is not None and cancel_event.is_set():
            return {"ok": False, "error": make_error("CANCELED", "操作已取消")}
        try:
            if image_url.startswith("data:"):
                images.append(base64.b64decode(image_url.split(",", 1)[1]))
            else:
                images.append(fetch_image(image_url))
        except (ValueError, OSError) as exc:
            return {"ok": False, "error": make_error("NOT_FOUND", f"下载结果图失败：{exc}")}

    return {
        "ok": True,
        "images": images,
        "urls": urls,
        "request_id": parsed.get("request_id") or "",
        "usage": parsed.get("usage") or {},
        "elapsed": round(time.time() - started, 1),
    }
