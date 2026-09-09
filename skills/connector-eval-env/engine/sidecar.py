"""Sidecar for the connector eval environment.

One process that observes and records everything the app does under eval:

- `POST /emit` is the only writer to `events.jsonl`. Every producer (the vendor
  stub, the CLI, this proxy, the poller) funnels through it so ids stay
  monotonic and lines never interleave.
- `GET /events?after=<id>` streams the log as Server-Sent Events: a replay of
  everything past `after`, then a tail. The monitor page consumes it.
- `POST /v1/chat/completions` is a capture proxy. The app under test points its
  OpenAI-compatible base URL here; the sidecar records the prompt and the
  completion, asks the adapter which item is in flight, then forwards upstream
  untouched and returns the upstream status and body. The Authorization header
  is forwarded and never written to the log.
- A background poller calls the adapter's `observe` hook once a second and
  emits one change event per row that moved.

Run it against a connector:

    python3 engine/sidecar.py --connector demo

`EVALENV_SESSION_DIR` names the session folder that holds `events.jsonl` (the
file is created if absent). `EVALENV_UPSTREAM` overrides the model base URL.
Importing this module starts nothing; the CLI or a test starts serving.
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

try:
    from engine import adapter as adapter_mod
except ImportError:
    import adapter as adapter_mod

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_UPSTREAM = "https://api.openai.com"
# Loopback only. The sidecar sees every prompt and completion, so it never
# listens on a routable interface.
BIND = "127.0.0.1"


def _now_iso():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)


# --- Event log --------------------------------------------------------------

class EventLog:
    """The single writer to events.jsonl.

    A lock serializes appends so two producers never interleave a line, and each
    line is flushed and fsynced before the append returns: an SSE tailer reading
    the file, and a restart reading the last id, must never see a torn line.
    """

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        if not os.path.exists(path):
            open(path, "a").close()
        self.last_id = self._read_last_id()

    def _read_last_id(self):
        last = 0
        with open(self.path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line)["id"]
                except (ValueError, KeyError):
                    continue
        return last

    def append(self, kind, rec, user, data):
        with self.lock:
            self.last_id += 1
            event = {"id": self.last_id, "ts": _now_iso(), "kind": kind,
                     "rec": rec, "user": user, "data": data or {}}
            with open(self.path, "a") as fh:
                fh.write(json.dumps(event) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            return event


# --- LLM classification -----------------------------------------------------

def classify_stage(body_json, fingerprints):
    """Name the pipeline stage a chat request belongs to, or None.

    body_contains matches when the substring appears anywhere in the serialized
    body; prompt_prefix matches when any message content starts with the prefix.
    First fingerprint in declaration order wins.
    """
    serialized = json.dumps(body_json, separators=(",", ":"))
    messages = body_json.get("messages") if isinstance(body_json, dict) else None
    for stage, fingerprint in fingerprints.items():
        needle = fingerprint.get("body_contains")
        if needle and needle in serialized:
            return stage
        prefix = fingerprint.get("prompt_prefix")
        if prefix and isinstance(messages, list):
            for message in messages:
                content = message.get("content") if isinstance(message, dict) else None
                if isinstance(content, str) and content.startswith(prefix):
                    return stage
    return None


def _forward(url, method, raw, headers):
    """Send the request upstream and return (status, body, content_type, error).

    An explicit empty ProxyHandler is used so the call never inherits an
    HTTP(S)_PROXY from the environment. A non-2xx upstream is not an exception
    here: its status and body are returned so the caller sees exactly what the
    provider said.
    """
    request = urllib.request.Request(url, data=raw, method=method)
    request.add_header("Content-Type", headers.get("Content-Type", "application/json"))
    auth = headers.get("Authorization")
    if auth:
        request.add_header("Authorization", auth)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=120) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type"), None
    except urllib.error.HTTPError as err:
        body = err.read()
        err.close()
        return err.code, body, err.headers.get("Content-Type"), "%s %s" % (err.code, err.reason)
    except Exception as err:
        message = str(err)
        return 502, json.dumps({"error": {"message": message}}).encode(), "application/json", message


# --- Poller -----------------------------------------------------------------

# The row keys each category carries into its event. The adapter's observe hook
# returns rows with these keys (extra keys are ignored, missing keys read None).
ITEM_KEYS = ("item_id", "external_id", "state", "stage", "last_error",
             "redaction_counts", "title", "redacted_words")
CONN_KEYS = ("connection_id", "status", "review_before_filing", "redact")
DELIV_KEYS = ("delivery_id", "external_id", "state", "attempts", "event")
CATEGORY_KIND = {"items": "item.changed", "connections": "connection.changed",
                 "deliveries": "delivery.changed"}
CATEGORY_KEYS = {"items": ITEM_KEYS, "connections": CONN_KEYS, "deliveries": DELIV_KEYS}


def normalize_rows(observed):
    """Project the observe hook's answer onto the event schema keys.

    Keyed by row id per category; a category the hook omits is empty.
    """
    out = {}
    for category, keys in CATEGORY_KEYS.items():
        rows = (observed or {}).get(category) or {}
        if isinstance(rows, list):
            rows = {str(r.get(keys[0])): r for r in rows}
        out[category] = {str(k): {key: row.get(key) for key in keys} for k, row in rows.items()}
    return out


class Poller:
    """Turns observed state into change events once a second.

    Each cycle asks the adapter for items, connections, and deliveries, diffs
    them against the previous cycle, and emits one event per row that appeared
    or moved. A cycle that overruns the 3 s deadline or raises emits poll.stale
    and the poller keeps going rather than dying on a transient fault.
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self.prev = {cat: {} for cat in CATEGORY_KIND}
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if not self.ctx.hooks.has("observe"):
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            self._poll_once()
            self._stop.wait(1.0)

    @staticmethod
    def diff(prev, cur):
        events = []
        for category, kind in CATEGORY_KIND.items():
            previous = prev.get(category, {})
            current = cur.get(category, {})
            for row_id, row in current.items():
                if previous.get(row_id) != row:
                    events.append({"kind": kind, "data": dict(row)})
        return events

    def _poll_once(self):
        started = time.time()
        try:
            cur = normalize_rows(self.ctx.hooks.call("observe", self.ctx.adapter, os.environ))
        except Exception as err:
            self.ctx.log.append("poll.stale", None, None,
                                {"reason": str(err), "ms": int((time.time() - started) * 1000)})
            return
        for event in self.diff(self.prev, cur):
            data = event["data"]
            self.ctx.log.append(event["kind"], data.get("external_id"), None, data)
        self.prev = cur
        elapsed_ms = int((time.time() - started) * 1000)
        if elapsed_ms > 3000:
            self.ctx.log.append("poll.stale", None, None,
                                {"reason": "poll cycle over deadline", "ms": elapsed_ms})


# --- HTTP server ------------------------------------------------------------

class SidecarContext:
    def __init__(self, adapter, hooks, log, session_dir, upstream):
        self.adapter = adapter
        self.hooks = hooks
        self.log = log
        self.session_dir = session_dir
        self.upstream = upstream
        self.started = _now_iso()


def session_info(ctx):
    """What /session reports and what a snapshot embeds: enough for the monitor
    to label stages and states without knowing the adapter."""
    adapter = ctx.adapter
    return {
        "session": os.path.basename(os.path.normpath(ctx.session_dir)),
        "connector": adapter["connector"],
        "started": ctx.started,
        "last_id": ctx.log.last_id,
        "llm_stages": list(adapter.get("llm_fingerprints", {}).keys()),
        "stages": adapter.get("stages", []),
        "states": adapter.get("states", []),
        "filed_state": adapter.get("filed_state", "filed"),
        "failed_state": adapter.get("failed_state", "failed"),
        "limitations": adapter.get("limitations", []),
        "labels": adapter.get("labels", {}),
    }


class SidecarHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def ctx(self):
        return self.server.ctx

    def log_message(self, fmt, *args):
        pass

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(length) if length else b""

    def _send_json(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    # -- GET --

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/events":
            return self._serve_sse(parsed)
        if parsed.path == "/session":
            return self._send_json(200, session_info(self.ctx))
        if parsed.path == "/":
            return self._serve_index()
        return self._send_json(404, {"error": "not found"})

    def _serve_index(self):
        page = os.path.join(_HERE, "monitor.html")
        with open(page, "rb") as fh:
            raw = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _serve_sse(self, parsed):
        after = int((parse_qs(parsed.query).get("after", ["0"])[0]) or 0)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        last_heartbeat = time.time()
        try:
            with open(self.ctx.log.path, "rb") as fh:
                while True:
                    position = fh.tell()
                    line = fh.readline()
                    if line.endswith(b"\n"):
                        self._sse_line(line, after)
                        continue
                    # A partial line means a write is mid-flight; rewind and wait
                    # for the fsynced newline rather than sending half an event.
                    fh.seek(position)
                    now = time.time()
                    if now - last_heartbeat >= 15:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                        last_heartbeat = now
                    time.sleep(0.25)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _sse_line(self, line, after):
        text = line.strip()
        if not text:
            return
        try:
            event = json.loads(text)
        except ValueError:
            return
        if event.get("id", 0) <= after:
            return
        payload = ("event: ev\ndata: " + json.dumps(event) + "\n\n").encode()
        self.wfile.write(payload)
        self.wfile.flush()

    # -- POST --

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/emit":
            return self._serve_emit()
        if parsed.path.endswith("/chat/completions"):
            return self._serve_proxy(parsed)
        return self._send_json(404, {"error": "not found"})

    def _serve_emit(self):
        try:
            body = json.loads(self._read_body() or b"{}")
        except ValueError:
            return self._send_json(400, {"error": "invalid json"})
        event = self.ctx.log.append(
            body.get("kind"), body.get("rec"), body.get("user"), body.get("data") or {})
        self._send_json(200, {"id": event["id"]})

    def _serve_proxy(self, parsed):
        raw = self._read_body()
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            body = {}
        call_id = uuid.uuid4().hex
        stage = classify_stage(body, self.ctx.adapter.get("llm_fingerprints", {}))
        correlation = self._correlate()
        rec = correlation.get("rec")
        # Only the JSON body is recorded. Headers (the Authorization bearer
        # among them) are forwarded and dropped.
        self.ctx.log.append("llm.request", rec, None, {
            "call_id": call_id, "stage": stage, "model": body.get("model"), "prompt": body,
            "item_id": correlation.get("item_id"),
            "job_reserved": bool(correlation.get("job_reserved")),
            "ambiguous": bool(correlation.get("ambiguous")),
        })
        url = self.ctx.upstream.rstrip("/") + parsed.path
        started = time.time()
        status, resp_body, content_type, error = _forward(url, self.command, raw, self.headers)
        ms = int((time.time() - started) * 1000)
        try:
            completion = json.loads(resp_body or b"{}")
        except ValueError:
            completion = {}
        usage = completion.get("usage") or {} if isinstance(completion, dict) else {}
        self.ctx.log.append("llm.response", rec, None, {
            "call_id": call_id, "stage": stage,
            "model": completion.get("model") if isinstance(completion, dict) else None,
            "status": status, "ms": ms,
            "tokens": {"prompt": usage.get("prompt_tokens"),
                       "completion": usage.get("completion_tokens"),
                       "total": usage.get("total_tokens")},
            "completion": completion, "error": error,
        })
        self.send_response(status)
        self.send_header("Content-Type", content_type or "application/json")
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)

    def _correlate(self):
        # Synchronous, before forwarding. An adapter error must never block the
        # model call: fall back to an uncorrelated request.
        if not self.ctx.hooks.has("in_flight"):
            return {"item_id": None, "job_reserved": False, "ambiguous": False, "rec": None}
        try:
            found = self.ctx.hooks.call("in_flight", self.ctx.adapter, os.environ) or {}
        except Exception:
            return {"item_id": None, "job_reserved": False, "ambiguous": False, "rec": None}
        return found


def build_server(port, session_dir, connector=None, adapter=None, hooks=None, upstream=None):
    """Construct the sidecar HTTP server, bound but not serving.

    Threaded so a held-open SSE stream runs in its own thread and never blocks
    /emit or the proxy. `adapter`, `hooks`, and `upstream` are injectable for
    tests; in production they come from the connector folder and the environment.
    """
    if adapter is None:
        adapter = adapter_mod.load_adapter(connector)
    if hooks is None:
        hooks = adapter_mod.load_hooks(adapter) if adapter.get("_dir") else adapter_mod.Hooks(None)
    log = EventLog(os.path.join(session_dir, "events.jsonl"))
    if upstream is None:
        upstream = os.environ.get("EVALENV_UPSTREAM") or adapter.get("upstream") or DEFAULT_UPSTREAM
    server = ThreadingHTTPServer((BIND, port), SidecarHandler)
    server.daemon_threads = True
    server.ctx = SidecarContext(adapter, hooks, log, session_dir, upstream)
    return server


def main(argv):
    if "--connector" not in argv:
        sys.stderr.write("usage: sidecar.py --connector <name>\n")
        return 2
    connector = argv[argv.index("--connector") + 1]
    session_dir = os.environ.get("EVALENV_SESSION_DIR")
    if not session_dir:
        sys.stderr.write("EVALENV_SESSION_DIR is required\n")
        return 2
    adapter = adapter_mod.load_adapter(connector)
    server = build_server(adapter["ports"]["sidecar"], session_dir, connector, adapter=adapter)
    poller = Poller(server.ctx)
    poller.start()
    sys.stderr.write("sidecar on http://%s:%d\n" % (BIND, server.server_address[1]))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        poller.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
