"""本地假服务：模拟 DashScope 原生协议与 OpenAI 兼容协议，供冒烟测试使用。"""

from __future__ import annotations

import base64
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageDraw

STATE = {"last": None, "calls": 0, "fail_mode": ""}


def make_png(seed: int = 0, width: int = 512, height: int = 512) -> bytes:
    image = Image.new("RGB", (width, height), (16, 18, 24))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        base = (int(40 + 60 * ratio), int(60 + 120 * ratio), int(140 + 80 * ratio))
        draw.line([(0, y), (width, y)], fill=base)
    draw.ellipse([width * 0.25 + seed * 20, height * 0.3, width * 0.75 + seed * 20, height * 0.8],
                 fill=(240 - seed * 30, 120 + seed * 20, 90))
    draw.text((20, 20), f"MOCK seed={seed}", fill=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _data_url(seed: int, width: int = 512, height: int = 512) -> str:
    return "data:image/png;base64," + base64.b64encode(make_png(seed, width, height)).decode("ascii")


def _count_images(handler_body: dict, protocol: str) -> int:
    try:
        if protocol == "openai":
            return max(1, int(handler_body.get("n") or 1))
        parameters = handler_body.get("parameters") or {}
        return max(1, int(parameters.get("n") or 1))
    except (TypeError, ValueError):
        return 1


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):  # 静音
        pass

    def _send_json(self, status: int, payload: dict, request_id: str = "mock-req") -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Request-Id", request_id)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/__last"):
            self._send_json(200, {"last": STATE["last"], "calls": STATE["calls"]})
            return
        if self.path.startswith("/__reset"):
            STATE.update({"last": None, "calls": 0, "fail_mode": ""})
            self._send_json(200, {"ok": True})
            return
        if self.path.startswith("/compatible-mode/v1/models"):
            self._send_json(200, {"object": "list", "data": [
                {"id": "qwen-image-3.0-pro", "object": "model"},
                {"id": "qwen-image-3.0", "object": "model"},
                {"id": "qwen-image-2.1-pro", "object": "model"},
                {"id": "qwen-image-2.0-pro-2099-01-01", "object": "model"},
                {"id": "qwen-max", "object": "model"},
            ]})
            return
        if self.path.startswith("/image/"):
            raw = make_png(1)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"code": "InvalidParameter", "message": "bad json"})
            return

        STATE["calls"] += 1
        STATE["last"] = {"path": self.path, "auth": self.headers.get("Authorization"),
                         "body": body, "headers": dict(self.headers)}
        auth = self.headers.get("Authorization") or ""

        if STATE["fail_mode"] == "401" or "badkey" in auth:
            self._send_json(401, {"code": "InvalidApiKey",
                                  "message": "Invalid API-key provided.",
                                  "request_id": "mock-err-401"}, "mock-err-401")
            return
        if STATE["fail_mode"] == "429":
            self._send_json(429, {"code": "Throttling", "message": "Requests rate limit exceeded",
                                  "request_id": "mock-err-429"}, "mock-err-429")
            return

        if self.path.startswith("/compatible-mode/"):
            count = _count_images(body, "openai")
            data = [{"url": _data_url(i)} for i in range(count)]
            self._send_json(200, {"created": 1, "data": data,
                                  "usage": {"total_tokens": 100, "image_count": count},
                                  "id": "mock-openai-1"}, "mock-openai-1")
            return

        count = _count_images(body, "dashscope")
        content = [{"image": _data_url(i)} for i in range(count)]
        self._send_json(200, {
            "output": {"choices": [{"finish_reason": "stop",
                                    "message": {"role": "assistant", "content": content}}]},
            "usage": {"image_count": count, "width": 512, "height": 512},
            "request_id": "mock-dashscope-1",
        }, "mock-dashscope-1")


class MockServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.httpd = ThreadingHTTPServer((host, port), Handler)
        self.httpd.daemon_threads = True
        self.thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> "MockServer":
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


if __name__ == "__main__":
    server = MockServer(port=18799).start()
    print("mock server on", server.base_url)
    threading.Event().wait()
