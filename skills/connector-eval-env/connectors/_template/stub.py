"""Placeholder mock vendor. Replace with the real vendor's API shape.

The engine starts this on adapter.json ports.vendor and expects the admin
surface below (the CLI drives it) plus whatever API your app calls. Copy
connectors/demo/stub.py as the starting point: it already has bearer auth,
signed webhook delivery with retries, a settings page, and scenarios.

Required admin endpoints (JSON):
  POST /_admin/arrive    {rec_id, account?, webhook?}   make a record visible and deliver its webhooks
  POST /_admin/backfill  {n, account?}                  make the first n corpus records visible in the past
  POST /_admin/scenario  {scenario}                     switch behavior; emit scenario.changed
  POST /_admin/reset                                     forget everything typed during the session
  GET  /_admin/state                                     accounts, scenario, delivered list
Plus GET <vendor_page> as the HTML settings page.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))


class PlaceholderHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/settings":
            raw = b"<!doctype html><title>Placeholder vendor</title><h1>Placeholder vendor</h1><p>Replace stub.py.</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if self.path == "/_admin/state":
            return self._json(200, {"scenario": "off", "accounts": [], "delivered": []})
        self._json(404, {"ok": False, "error": "placeholder stub: replace stub.py"})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        self._json(501, {"ok": False, "error": "placeholder stub: replace stub.py"})


if __name__ == "__main__":
    with open(os.path.join(_HERE, "adapter.json")) as fh:
        port = json.load(fh)["ports"]["vendor"]
    server = ThreadingHTTPServer(("127.0.0.1", port), PlaceholderHandler)
    sys.stderr.write("placeholder vendor stub on http://127.0.0.1:%d\n" % port)
    server.serve_forever()
