"""Mock 数字人引擎（digital-human-livestream 管理后台 API 简化版）。

提供 /health、/admin/persona、/admin/wordlist，内存保存推送内容并打印请求日志，
用于 L3 无 GPU 环境下的「健康检查 + 配置导入」端到端验证。
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PERSONA = {}
WORDLIST_TEXT = ""
REQUIRED = ("name", "personality", "style", "knowledge_scope")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[mock-engine]", fmt % args, flush=True)

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        print(f"[mock-engine] GET {self.path} headers={dict(self.headers)}", flush=True)
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        elif self.path == "/admin/persona":
            self._send(200, {"code": 0, "data": PERSONA})
        elif self.path == "/admin/wordlist":
            # 真实 dhl：GET 返回 {"content": 文本, "path": ...}
            self._send(200, {"code": 0, "data": {"content": WORDLIST_TEXT, "path": "config/wordlist.txt"}})
        elif self.path == "/admin/status":
            self._send(200, {"code": 0, "data": {"livestream": "stopped", "llm": "ok"}})
        else:
            self._send(404, {"code": -1, "msg": "not found"})

    def do_POST(self):
        data = self._read_json()
        print(f"[mock-engine] POST {self.path} body={json.dumps(data, ensure_ascii=False)}", flush=True)
        if self.path == "/admin/persona":
            # 真实 dhl 校验四必填字段
            missing = [k for k in REQUIRED if not str((data or {}).get(k) or "").strip()]
            if missing:
                self._send(200, {"code": -1, "msg": f"配置缺少必需字段（{', '.join(missing)}）"})
                return
            PERSONA.clear()
            PERSONA.update(data or {})
            self._send(200, {"code": 0, "data": PERSONA})
        elif self.path == "/admin/wordlist":
            # 真实 dhl：POST body 为 {"content": "每行一词\n..."}
            content = (data or {}).get("content")
            if content is None:
                self._send(200, {"code": -1, "msg": "缺少 content 字段"})
                return
            global WORDLIST_TEXT
            WORDLIST_TEXT = str(content)
            self._send(200, {"code": 0, "data": {"msg": "敏感词词库已更新"}})
        else:
            self._send(404, {"code": -1, "msg": "not found"})


if __name__ == "__main__":
    port = 8010
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"[mock-engine] listening on :{port}", flush=True)
    server.serve_forever()
