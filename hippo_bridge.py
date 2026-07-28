"""
hippo_bridge.py
───────────────
Kassir kompyuterida ishlaydigan kichik CORS proxy.
Hippo Communicator (localhost:8081) ga brauzerdan murojaat qilish imkonini beradi.

Ishlatish:
    python hippo_bridge.py

Keyin brauzer http://127.0.0.1:8082 orqali Hippo ga murojaat qiladi.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error
import json
import sys

HIPPO_URL  = "http://127.0.0.1:8081"
BRIDGE_PORT = 8082


class CORSProxy(BaseHTTPRequestHandler):

    CORS_HEADERS = {
        "Access-Control-Allow-Origin":          "*",
        "Access-Control-Allow-Methods":         "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers":         "Content-Type, Authorization, X-Requested-With",
        "Access-Control-Allow-Private-Network": "true",   # Chrome Private Network Access
    }

    def log_message(self, format, *args):
        print(f"[Bridge] {self.address_string()} - {format % args}")

    # ── OPTIONS (preflight) ──────────────────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in self.CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    # ── GET ──────────────────────────────────────────────────────────────────
    def do_GET(self):
        self._proxy("GET", None)

    # ── POST ─────────────────────────────────────────────────────────────────
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length else b""
        self._proxy("POST", body)

    # ── Proxy ─────────────────────────────────────────────────────────────────
    def _proxy(self, method, body):
        target = HIPPO_URL + self.path
        try:
            req = urllib.request.Request(
                url    = target,
                data   = body,
                method = method,
                headers= {"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data   = resp.read()
                status = resp.status
        except urllib.error.HTTPError as e:
            data   = e.read()
            status = e.code
        except Exception as e:
            data   = json.dumps({"error": str(e)}).encode()
            status = 502

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for k, v in self.CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", BRIDGE_PORT), CORSProxy)
    print(f"╔══════════════════════════════════════════════════╗")
    print(f"║  Hippo CORS Bridge ishga tushdi                  ║")
    print(f"║  Tinglash:  http://127.0.0.1:{BRIDGE_PORT}              ║")
    print(f"║  Hippo URL: {HIPPO_URL}              ║")
    print(f"║  To'xtatish: Ctrl+C                              ║")
    print(f"╚══════════════════════════════════════════════════╝")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBridge to'xtatildi.")
        sys.exit(0)
