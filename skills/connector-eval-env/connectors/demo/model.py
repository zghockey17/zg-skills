"""A local, deterministic stand-in for an OpenAI-compatible chat model.

The demo app calls the sidecar proxy, and the proxy forwards here. There is no
network call, no key check beyond presence, and no randomness, so every run of
the demo produces the same completions. This is a stand-in, not a model:
evals against it test the pipeline, never model quality. Point the sidecar's
upstream at a real provider to test the model (references/live-provider.md).

Three behaviors, chosen by the request shape the demo app sends:
  * redaction requests (response_format json_object) get rule-based cuts:
    phone numbers, dollar amounts, and a short list of health phrases
  * summarization requests get a two-line summary of the transcript
  * linking requests get a JSON list of link suggestions
"""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BIND = "127.0.0.1"
MODEL_NAME = "demo-stand-in-1"

RULES = (
    ("contact", re.compile(r"\b\d{3}-\d{3}-\d{4}\b")),
    ("compensation", re.compile(r"\$\d[\d,]*(?:\.\d+)?")),
    ("health", re.compile(r"\b(knee surgery|chemotherapy|diagnosed with [a-z ]+?)\b", re.I)),
)
LINE = re.compile(r"^(\d+) \[([^\]]*)\]: (.*)$")


def redact_lines(user_content):
    """Apply the rules to every numbered transcript line; return (lines, counts)."""
    lines, counts = {}, {}
    in_transcript = False
    for raw in user_content.split("\n"):
        if raw.startswith("TRANSCRIPT"):
            in_transcript = True
            continue
        if raw.startswith("CATEGORIES") or raw.startswith("OUTPUT"):
            in_transcript = False
        if not in_transcript:
            continue
        match = LINE.match(raw)
        if not match:
            continue
        number, text = match.group(1), match.group(3)
        for category, pattern in RULES:
            text, n = pattern.subn("[redacted: %s]" % category, text)
            if n:
                counts[category] = counts.get(category, 0) + n
        lines[number] = text
    return lines, counts


def _summary(user_content):
    speakers = sorted({m.group(2) for m in map(LINE.match, user_content.split("\n")) if m})
    speakers = [s for s in speakers if s and s != "title"]
    count = sum(1 for m in map(LINE.match, user_content.split("\n")) if m)
    return ("Summary: %d transcript lines across %d speakers (%s).\n"
            "Action items: none recorded by the stand-in model."
            % (count, len(speakers), ", ".join(speakers) or "none"))


def complete(body):
    messages = body.get("messages") or []
    user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
    if body.get("response_format"):
        lines, counts = redact_lines(user)
        content = json.dumps({"lines": lines, "counts": counts})
    elif system.startswith("You are linking a meeting summary"):
        content = json.dumps({"links": [{"title": "Team notes", "path": "notes/team.md"}]})
    else:
        content = _summary(user)
    prompt_tokens = max(1, len(json.dumps(messages)) // 4)
    completion_tokens = max(1, len(content) // 4)
    return {
        "id": "demo-completion",
        "object": "chat.completion",
        "model": MODEL_NAME,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                  "total_tokens": prompt_tokens + completion_tokens},
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        if not self.headers.get("Authorization", "").startswith("Bearer "):
            return self._send(401, {"error": {"message": "missing bearer token"}})
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            return self._send(400, {"error": {"message": "invalid json"}})
        self._send(200, complete(body))


def make_server(port):
    return ThreadingHTTPServer((BIND, port), Handler)


if __name__ == "__main__":
    port = int(os.environ.get("DEMO_MODEL_PORT", "8228"))
    server = make_server(port)
    sys.stderr.write("demo stand-in model on http://%s:%d\n" % (BIND, port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
