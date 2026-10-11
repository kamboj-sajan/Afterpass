"""A local stand-in for the agent's Lambda Function URL: POST /ask {"question": "..."}."""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent import handler

MAX_BODY_BYTES = 8192


class AskHandler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802 - the base class names it
        self._send(204, {})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/ask":
            self._send(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self._send(413, {"error": "too_long"})
            return
        event = {"body": self.rfile.read(length).decode("utf-8", "replace")}
        try:
            reply = handler.lambda_handler(event, None)
        except Exception:  # noqa: BLE001 - the browser needs an answer, the log has the cause
            logging.getLogger("afterpass.agent").exception("ask failed")
            self._send(502, {"error": "agent_failed"})
            return
        self._send(reply["statusCode"], json.loads(reply["body"]))


def serve(port: int = 8788) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), AskHandler)
    print(f"Ask AfterPass at http://127.0.0.1:{port}/ask  (model: {handler.model_name()})")
    server.serve_forever()
