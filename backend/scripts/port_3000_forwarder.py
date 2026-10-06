import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


from typing import Any


class RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        target = f"http://localhost:8000{self.path}"
        self.send_response(302)
        self.send_header("Location", target)
        self.end_headers()

    def do_POST(self) -> None:
        self.do_GET()

    def do_HEAD(self) -> None:
        self.do_GET()

    def log_message(self, format: str, *args: Any) -> None:
        pass

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    try:
        server = HTTPServer(("127.0.0.1", port), RedirectHandler)
        server.serve_forever()
    except Exception:
        pass
