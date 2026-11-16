"""探测：用本机已保存的 Key 请求模型列表，看看服务端回来什么。"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

import settings as settings_store  # noqa: E402

st = settings_store.load()
base = st.get("base_url", "")
key = st.get("api_key", "")
print("base:", base)
print("key set:", bool(key), "len:", len(key))
print("protocol:", st.get("protocol"), "region:", st.get("region"))

bases = [b for b in (base,) if "{" not in b]
bases += ["https://dashscope.aliyuncs.com", "https://dashscope-intl.aliyuncs.com"]
for base in bases:
  for path in ("/compatible-mode/v1/models", "/api/v1/models"):
    url = base.rstrip("/") + path
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=20)
        print("\n==", url, "->", r.status_code)
        text = r.text
        print(text[:600])
        if r.status_code == 200:
            try:
                data = r.json()
            except Exception:
                continue
            items = data.get("data") or data.get("models") or []
            ids = [item.get("id") or item.get("model") for item in items if isinstance(item, dict)]
            print("count:", len(ids))
            print("qwen-image:", [i for i in ids if i and "image" in i])
    except Exception as exc:  # noqa: BLE001
        print("ERR", type(exc).__name__, exc)
