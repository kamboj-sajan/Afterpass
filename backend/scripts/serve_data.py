"""Serve data/public on :8787 with CORS, for local frontend development."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from afterpass.config import PUBLIC_DIR


class CORSHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 8787), partial(CORSHandler, directory=PUBLIC_DIR))
    print(f"Serving {PUBLIC_DIR} at http://127.0.0.1:8787")
    server.serve_forever()
