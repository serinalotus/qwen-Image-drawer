"""千问图像工作台 —— 常量表（模型 / 尺寸 / 地域 / 协议 / 限制 / 默认值）。

所有元数据集中在此文件，UI 与请求构造都从这里取，避免硬编码散落各处。
数据来源：《千问-图像生成与编辑 API参考》。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 模型能力表

MODELS = [
    {
        "id": "qwen-image-3.0-pro",
        "name": "千问图像 3.0 Pro",
        "series": "3.0",
        "desc": "质量最高，文生图 + 图生图，支持反向提示词",
        "max_refs": 3,
        "supports_negative_prompt": True,
        "supports_thinking": True,
        "prompt_extend_modes": ["direct", "agent"],
    },
    {
        "id": "qwen-image-3.0",
        "name": "千问图像 3.0",
        "series": "3.0",
        "desc": "标准版，质量与速度兼顾，支持反向提示词",
        "max_refs": 3,
        "supports_negative_prompt": True,
        "supports_thinking": True,
        "prompt_extend_modes": ["direct", "agent"],
    },
    {
        "id": "qwen-image-2.1-pro",
        "name": "千问图像 2.1 Pro",
        "series": "2.1",
        "desc": "支持最多 10 张参考图，可输出透明通道",
        "max_refs": 10,
        "supports_negative_prompt": False,
        "supports_thinking": False,
        "prompt_extend_modes": ["direct"],
    },
    {
        "id": "qwen-image-2.1-turbo",
        "name": "千问图像 2.1 Turbo",
        "series": "2.1",
        "desc": "性价比最优，支持最多 10 张参考图",
        "max_refs": 10,
        "supports_negative_prompt": False,
        "supports_thinking": False,
        "prompt_extend_modes": ["direct"],
    },
]

# ---------------------------------------------------------------- 输出尺寸

# 全部满足 512*512 ≤ 面积 ≤ 2048*2048 且长宽比 ≤ 8:1（官方文档给的硬限制）
SIZE_PRESETS = [
    {"id": "auto", "label": "自动（由模型决定）", "group": "自动", "value": "auto"},
    {"id": "1:1-512", "label": "1:1 · 512（小图）", "group": "方形", "value": "512x512"},
    {"id": "1:1-768", "label": "1:1 · 768", "group": "方形", "value": "768x768"},
    {"id": "1:1-1024", "label": "1:1 · 1024（方形）", "group": "方形", "value": "1024x1024"},
    {"id": "1:1-1536", "label": "1:1 · 1536 高清", "group": "方形", "value": "1536x1536"},
    {"id": "1:1-2048", "label": "1:1 · 2048（最大）", "group": "方形", "value": "2048x2048"},
    {"id": "4:3-1152", "label": "4:3 · 1152×864（横图）", "group": "横图", "value": "1152x864"},
    {"id": "4:3-1536", "label": "4:3 · 1536×1152（横图）", "group": "横图", "value": "1536x1152"},
    {"id": "4:3-2048", "label": "4:3 · 2048×1536（横图大）", "group": "横图", "value": "2048x1536"},
    {"id": "3:2-1536", "label": "3:2 · 1536×1024（横图）", "group": "横图", "value": "1536x1024"},
    {"id": "3:2-2048", "label": "3:2 · 2048×1360（横图大）", "group": "横图", "value": "2048x1360"},
    {"id": "16:9-1536", "label": "16:9 · 1536×864（横图）", "group": "横图", "value": "1536x864"},
    {"id": "16:9-2048", "label": "16:9 · 2048×1152（横图大）", "group": "横图", "value": "2048x1152"},
    {"id": "2:1-1536", "label": "2:1 · 1536×768（宽幅）", "group": "横图", "value": "1536x768"},
    {"id": "3:4-1152", "label": "3:4 · 864×1152（竖图）", "group": "竖图", "value": "864x1152"},
    {"id": "3:4-1536", "label": "3:4 · 1152×1536（竖图）", "group": "竖图", "value": "1152x1536"},
    {"id": "3:4-2048", "label": "3:4 · 1536×2048（竖图大）", "group": "竖图", "value": "1536x2048"},
    {"id": "2:3-1536", "label": "2:3 · 1024×1536（竖图）", "group": "竖图", "value": "1024x1536"},
    {"id": "2:3-2048", "label": "2:3 · 1360×2048（竖图大）", "group": "竖图", "value": "1360x2048"},
    {"id": "9:16-1536", "label": "9:16 · 864×1536（竖图）", "group": "竖图", "value": "864x1536"},
    {"id": "9:16-2048", "label": "9:16 · 1152×2048（竖图大）", "group": "竖图", "value": "1152x2048"},
    {"id": "1:2-1536", "label": "1:2 · 768×1536（长竖）", "group": "竖图", "value": "768x1536"},
    {"id": "custom", "label": "自定义尺寸…（自己填宽高）", "group": "自定义", "value": "custom"},
]

# ---------------------------------------------------------------- 地域 / 域名

REGIONS = [
    {
        "id": "beijing-legacy",
        "label": "华北2（北京）· 通用域名",
        "base_url": "https://dashscope.aliyuncs.com",
        "needs_workspace": False,
    },
    {
        "id": "singapore-legacy",
        "label": "新加坡 · 通用域名",
        "base_url": "https://dashscope-intl.aliyuncs.com",
        "needs_workspace": False,
    },
    {
        "id": "beijing",
        "label": "华北2（北京）· 业务空间域名",
        "base_url": "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com",
        "needs_workspace": True,
    },
    {
        "id": "singapore",
        "label": "新加坡 · 业务空间域名",
        "base_url": "https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com",
        "needs_workspace": True,
    },
    {
        "id": "us-east-1",
        "label": "美国（弗吉尼亚）· 业务空间域名",
        "base_url": "https://{WorkspaceId}.us-east-1.maas.aliyuncs.com",
        "needs_workspace": True,
    },
    {
        "id": "eu-central-1",
        "label": "德国（法兰克福）· 业务空间域名",
        "base_url": "https://{WorkspaceId}.eu-central-1.maas.aliyuncs.com",
        "needs_workspace": True,
    },
    {
        "id": "ap-northeast-1",
        "label": "日本（东京）· 业务空间域名",
        "base_url": "https://{WorkspaceId}.ap-northeast-1.maas.aliyuncs.com",
        "needs_workspace": True,
    },
    {
        "id": "cn-hongkong",
        "label": "中国香港 · 业务空间域名",
        "base_url": "https://{WorkspaceId}.cn-hongkong.maas.aliyuncs.com",
        "needs_workspace": True,
    },
    {
        "id": "custom",
        "label": "自定义地址",
        "base_url": "",
        "needs_workspace": False,
    },
]

# ---------------------------------------------------------------- 协议

PROTOCOLS = [
    {
        "id": "dashscope",
        "label": "DashScope 原生（推荐）",
        "path": "/api/v1/services/aigc/multimodal-generation/generation",
        "hint": "与官方文档示例一致，参数最完整",
    },
    {
        "id": "openai",
        "label": "OpenAI 兼容",
        "path": "/compatible-mode/v1/images/generations",
        "hint": "参数平铺在顶层，便于复用 OpenAI SDK 代码",
    },
]

# ---------------------------------------------------------------- 硬性限制

LIMITS = {
    "prompt_max_tokens_hint": 4500,
    "n_min": 1,
    "n_max": 6,
    "seed_min": 0,
    "seed_max": 2147483647,
    "image_min_side": 1,
    "image_max_side": 8000,
    "image_max_bytes": 10 * 1024 * 1024,
    "image_max_aspect": 10,
    "output_min_area": 512 * 512,
    "output_max_area": 2048 * 2048,
    "output_max_aspect": 8,
    "request_timeout": 600,
}

DEFAULTS = {
    "protocol": "dashscope",
    "region": "beijing-legacy",
    "base_url": "https://dashscope.aliyuncs.com",
    "workspace_id": "",
    "model": "qwen-image-3.0-pro",
    "size": "1024x1024",
    "n": 1,
    "prompt_extend": True,
    "prompt_extend_mode": "direct",
    "enable_thinking": True,
    "watermark": False,
    "auto_save": True,
}


# 从服务端发现、但内置表里没有的模型（运行时用 set_discovered_models 填进来）
DISCOVERED_MODELS: list[dict] = []


def derive_model(model_id: str) -> dict:
    """按模型 id 推断能力，用于服务端新发现的模型（保守估计）。"""
    model_id = str(model_id or "").strip()
    series = "3.0" if "3.0" in model_id else ("2.1" if "2.1" in model_id else "2.0")
    caps = {
        "3.0": {"max_refs": 3, "negative": True, "thinking": True, "modes": ["direct", "agent"]},
        "2.1": {"max_refs": 10, "negative": False, "thinking": False, "modes": ["direct"]},
        "2.0": {"max_refs": 3, "negative": False, "thinking": False, "modes": ["direct"]},
    }[series]
    suffix = " Pro" if "-pro" in model_id else ""
    return {
        "id": model_id,
        "name": f"千问图像 {series}{suffix}（服务端）" if series != "2.0" else model_id,
        "series": series,
        "desc": f"服务端返回的模型：{model_id}",
        "max_refs": caps["max_refs"],
        "supports_negative_prompt": caps["negative"],
        "supports_thinking": caps["thinking"],
        "prompt_extend_modes": caps["modes"],
        "discovered": True,
    }


def set_discovered_models(model_ids) -> list[dict]:
    """把服务端返回的 id 注册成可用模型（去重、跳过内置已有的）。"""
    builtin = {item["id"] for item in MODELS}
    seen: set[str] = set()
    result: list[dict] = []
    for model_id in model_ids or []:
        model_id = str(model_id or "").strip()
        if not model_id or model_id in builtin or model_id in seen:
            continue
        seen.add(model_id)
        result.append(derive_model(model_id))
    DISCOVERED_MODELS[:] = result
    return list(DISCOVERED_MODELS)


def all_models() -> list[dict]:
    return list(MODELS) + list(DISCOVERED_MODELS)


def get_model(model_id: str) -> dict:
    for item in all_models():
        if item["id"] == model_id:
            return item
    return MODELS[0]


def get_region(region_id: str) -> dict:
    for item in REGIONS:
        if item["id"] == region_id:
            return item
    return REGIONS[0]


def get_protocol(protocol_id: str) -> dict:
    for item in PROTOCOLS:
        if item["id"] == protocol_id:
            return item
    return PROTOCOLS[0]


def resolve_base_url(region_id: str, base_url: str, workspace_id: str) -> str:
    """把地域预设 + 业务空间 ID 解析成真正的 Base URL。"""
    preset = get_region(region_id)
    url = (base_url or preset.get("base_url") or "").strip()
    if preset.get("needs_workspace") and workspace_id:
        url = url.replace("{WorkspaceId}", workspace_id.strip())
    return url.rstrip("/")
