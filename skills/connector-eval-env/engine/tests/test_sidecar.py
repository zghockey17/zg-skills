"""Unit tests for the sidecar: event log, SSE, capture proxy, poller, hooks.

Self-contained: a temp session directory, ephemeral loopback ports, a fake
upstream, and a scripted hooks object. No network beyond loopback.
"""
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from engine import adapter as adapter_mod
from engine import sidecar

UPSTREAM_RESP = {
    "choices": [{"message": {"content": "ok"}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
    "model": "fake-model",
}

ADAPTER = {
    "connector": "t", "ports": {"sidecar": 0},
    "llm_fingerprints": {
        "redact": {"body_contains": "\"response_format\""},
        "summarize": {"prompt_prefix": "You are a meeting summarization assistant"},
        "link": {"prompt_prefix": "You are linking a meeting summary"},
    },
    "stages": ["fetching", "redacting"], "states": ["discovered", "filed"],
}


class _Hooks:
    """Scripted stand-in for the adapter hooks module."""

    def __init__(self, flight=None, observed=None):
        self.flight = flight
        self.observed = observed

    def in_flight(self, adapter, env):
        return self.flight

    def observe(self, adapter, env):
        return self.observed


class _Upstream(BaseHTTPRequestHandler):
    seen_auth = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        _Upstream.seen_auth.append(self.headers.get("Authorization"))
        body = json.dumps(UPSTREAM_RESP).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _read(path):
    with open(path) as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


def _serve(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


class ServerTestBase(unittest.TestCase):
    hooks = None

    def setUp(self):
        self.session_dir = tempfile.mkdtemp(prefix="evalenv-session-")
        self.server = sidecar.build_server(0, self.session_dir, adapter=ADAPTER,
                                           hooks=adapter_mod.Hooks(self.hooks),
                                           upstream="http://127.0.0.1:1")
        self.port = self.server.server_address[1]
        _serve(self.server)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _emit(self, kind="test", rec=None, user=None, data=None):
        payload = json.dumps({"kind": kind, "rec": rec, "user": user, "data": data or {}}).encode()
        req = urllib.request.Request("http://127.0.0.1:%d/emit" % self.port, data=payload,
                                     method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def _events(self):
        with open(os.path.join(self.session_dir, "events.jsonl")) as fh:
            return [json.loads(ln) for ln in fh if ln.strip()]


class EmitTest(ServerTestBase):
    def test_emit_assigns_monotonic_ids(self):
        self.assertEqual(self._emit()["id"], 1)
        self.assertEqual(self._emit()["id"], 2)
        self.assertEqual(len(self._events()), 2)

    def test_session_reports_adapter_shape(self):
        with urllib.request.urlopen("http://127.0.0.1:%d/session" % self.port, timeout=5) as resp:
            info = json.loads(resp.read())
        self.assertEqual(info["llm_stages"], ["redact", "summarize", "link"])
        self.assertEqual(info["states"], ["discovered", "filed"])
        self.assertEqual(info["connector"], "t")

    def test_binds_loopback_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")


class SseTest(ServerTestBase):
    def _open_stream(self, after):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        sock.settimeout(0.3)
        sock.sendall(("GET /events?after=%d HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n" % after).encode())
        return sock

    def _read_ids(self, sock, count, deadline_s):
        ids, buf = [], b""
        end = time.time() + deadline_s
        while len(ids) < count and time.time() < end:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.strip().startswith(b"data: "):
                    ids.append(json.loads(line.strip()[6:])["id"])
        return ids

    def test_sse_replay_then_tail(self):
        for _ in range(3):
            self._emit()
        sock = self._open_stream(after=1)
        try:
            self.assertEqual(self._read_ids(sock, 2, 2.0), [2, 3])
            self._emit()
            self.assertIn(4, self._read_ids(sock, 1, 2.0))
        finally:
            sock.close()


class ProxyTest(unittest.TestCase):
    def setUp(self):
        _Upstream.seen_auth = []
        self.session_dir = tempfile.mkdtemp(prefix="evalenv-session-")
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
        _serve(self.upstream)
        up_url = "http://127.0.0.1:%d" % self.upstream.server_address[1]
        hooks = adapter_mod.Hooks(_Hooks(flight={"item_id": 7, "rec": "rec_x", "job_reserved": True,
                                                 "ambiguous": False}))
        self.server = sidecar.build_server(0, self.session_dir, adapter=ADAPTER, hooks=hooks, upstream=up_url)
        self.port = self.server.server_address[1]
        _serve(self.server)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()

    def test_proxy_captures_and_correlates_without_logging_auth(self):
        body = json.dumps({"model": "m", "response_format": {"type": "json_object"},
                           "messages": [{"role": "user", "content": "hi"}]}).encode()
        req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % self.port, data=body,
                                     method="POST", headers={"Content-Type": "application/json",
                                                             "Authorization": "Bearer sk-SECRET-42"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertEqual(json.loads(resp.read()), UPSTREAM_RESP)
        # forwarded upstream, never written to the log
        self.assertEqual(_Upstream.seen_auth, ["Bearer sk-SECRET-42"])
        with open(os.path.join(self.session_dir, "events.jsonl")) as fh:
            raw = fh.read()
        self.assertNotIn("sk-SECRET-42", raw)
        events = [json.loads(ln) for ln in raw.splitlines() if ln.strip()]
        request = next(e for e in events if e["kind"] == "llm.request")
        response = next(e for e in events if e["kind"] == "llm.response")
        self.assertEqual(request["data"]["stage"], "redact")
        self.assertEqual(request["rec"], "rec_x")
        self.assertEqual(request["data"]["item_id"], 7)
        self.assertEqual(response["data"]["tokens"]["total"], 6)
        self.assertEqual(response["data"]["status"], 200)


class ClassifyStageTest(unittest.TestCase):
    def test_classify_stage(self):
        fp = ADAPTER["llm_fingerprints"]
        redact = {"response_format": {"type": "json_object"}, "messages": []}
        summarize = {"messages": [{"role": "system", "content": "You are a meeting summarization assistant. Do X."}]}
        link = {"messages": [{"role": "system", "content": "You are linking a meeting summary to notes."}]}
        self.assertEqual(sidecar.classify_stage(redact, fp), "redact")
        self.assertEqual(sidecar.classify_stage(summarize, fp), "summarize")
        self.assertEqual(sidecar.classify_stage(link, fp), "link")
        self.assertIsNone(sidecar.classify_stage({"messages": [{"content": "unknown"}]}, fp))


class PollerTest(unittest.TestCase):
    def test_diff_emits_only_changed_rows(self):
        prev = sidecar.normalize_rows({"items": {"1": {"item_id": 1, "state": "discovered"}}})
        cur = sidecar.normalize_rows({"items": {"1": {"item_id": 1, "state": "filing", "stage": "fetching"},
                                                "2": {"item_id": 2, "state": "discovered"}}})
        events = sidecar.Poller.diff(prev, cur)
        self.assertEqual([e["kind"] for e in events], ["item.changed", "item.changed"])
        self.assertEqual({e["data"]["item_id"] for e in events}, {1, 2})
        self.assertEqual(sidecar.Poller.diff(cur, cur), [])

    def test_normalize_accepts_lists_and_fills_missing_keys(self):
        rows = sidecar.normalize_rows({"deliveries": [{"delivery_id": 3, "state": "accepted"}]})
        self.assertEqual(rows["deliveries"]["3"]["attempts"], None)
        self.assertEqual(rows["items"], {})

    def test_poll_once_writes_events_and_stale_on_error(self):
        session = tempfile.mkdtemp(prefix="evalenv-session-")
        log = sidecar.EventLog(os.path.join(session, "events.jsonl"))
        hooks = adapter_mod.Hooks(_Hooks(observed={"items": {"1": {"item_id": 1, "external_id": "rec_p",
                                                                     "state": "filed"}}}))
        ctx = sidecar.SidecarContext(ADAPTER, hooks, log, session, "http://127.0.0.1:1")
        poller = sidecar.Poller(ctx)
        poller._poll_once()
        events = _read(log.path)
        self.assertEqual(events[-1]["kind"], "item.changed")
        self.assertEqual(events[-1]["rec"], "rec_p")

        class Broken:
            def observe(self, adapter, env):
                raise RuntimeError("app down")
        ctx.hooks = adapter_mod.Hooks(Broken())
        poller._poll_once()
        events = _read(log.path)
        self.assertEqual(events[-1]["kind"], "poll.stale")
        self.assertIn("app down", events[-1]["data"]["reason"])


if __name__ == "__main__":
    unittest.main()
