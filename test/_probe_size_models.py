"""本地验证：size 省略逻辑 + 真实模型列表拉取。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import api  # noqa: E402
import meta  # noqa: E402

base_payload = {
    "prompt": "测试",
    "size": "auto",
    "n": 1,
    "model": "qwen-image-3.0-pro",
}

for protocol in ("dashscope", "openai"):
    body = api.build_body(api.validate_payload(base_payload)[0], protocol)
    if protocol == "dashscope":
        size = body["parameters"].get("size", "<absent>")
    else:
        size = body.get("size", "<absent>")
    print(f"{protocol} auto -> size={size!r}")

custom = dict(base_payload, size="1024x1536")
for protocol in ("dashscope", "openai"):
    body = api.build_body(api.validate_payload(custom)[0], protocol)
    size = body["parameters"].get("size") if protocol == "dashscope" else body.get("size")
    print(f"{protocol} 1024x1536 -> size={size!r}")

for raw in ("auto", "1024x1024", "2048x2048", "512x4096", "100x100", "abc"):
    ok, value, error = api.normalize_size(raw)
    print("normalize", raw, "->", ok, value, (error or {}).get("message"))

import settings as settings_store  # noqa: E402

st = settings_store.load()
result = api.list_models(st)
print("list_models ok:", result.get("ok"), "count:", result.get("count"), "base:", result.get("base"))
print("models:", result.get("models"))
print("error:", result.get("error"))
