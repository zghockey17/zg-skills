"""Tests for the demo adapter: vendor stub, stand-in model, app webhook receiver,
and the reset hook's fail-closed behavior.

Ephemeral loopback ports and temp folders only.
"""
import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from connectors.demo import adapter as demo_hooks
from connectors.demo import app as demo_app
from connectors.demo import model as demo_model
from connectors.demo import stub as demo_stub

GOOD_KEY = "demo_key_priya_0001"


class _Sink(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _serve(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()


def _status(url, method="GET", data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        body = err.read()
        err.close()
        return err.code, body


class ModelTest(unittest.TestCase):
    def test_redaction_rules_are_deterministic(self):
        prompt = ("TRANSCRIPT\n0 [title]: T\n1 [Priya]: Call 415-555-0142 about my knee surgery.\n"
                  "2 [Omar]: Budget is $48,000.\nCATEGORIES\nx\nOUTPUT\ny")
        lines, counts = demo_model.redact_lines(prompt)
        self.assertEqual(lines["1"], "Call [redacted: contact] about my [redacted: health].")
        self.assertEqual(lines["2"], "Budget is [redacted: compensation].")
        self.assertEqual(counts, {"contact": 1, "health": 1, "compensation": 1})
        self.assertEqual(demo_model.redact_lines(prompt), (lines, counts))

    def test_complete_shapes(self):
        redact = demo_model.complete({"response_format": {"type": "json_object"}, "messages": [
            {"role": "user", "content": "TRANSCRIPT\n1 [A]: hi\nOUTPUT"}]})
        self.assertIn("lines", json.loads(redact["choices"][0]["message"]["content"]))
        self.assertIn("usage", redact)
        summary = demo_model.complete({"messages": [
            {"role": "system", "content": "You are a meeting summarization assistant."},
            {"role": "user", "content": "TRANSCRIPT\n1 [A]: hi\n2 [B]: yo"}]})
        self.assertIn("2 transcript lines", summary["choices"][0]["message"]["content"])

    def test_server_requires_bearer(self):
        server = demo_model.make_server(0)
        _serve(server)
        try:
            url = "http://127.0.0.1:%d/v1/chat/completions" % server.server_address[1]
            code, _ = _status(url, "POST", b"{}", {"Content-Type": "application/json"})
            self.assertEqual(code, 401)
            code, _ = _status(url, "POST", b'{"messages":[]}',
                              {"Content-Type": "application/json", "Authorization": "Bearer any"})
            self.assertEqual(code, 200)
        finally:
            server.shutdown()
            server.server_close()


class StubTest(unittest.TestCase):
    def setUp(self):
        self.sink = ThreadingHTTPServer(("127.0.0.1", 0), _Sink)
        _serve(self.sink)
        os.environ["EVALENV_SIDECAR"] = "http://127.0.0.1:%d" % self.sink.server_address[1]
        self.server = demo_stub.make_app(0)
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        _serve(self.server)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.sink.shutdown()
        self.sink.server_close()
        os.environ.pop("EVALENV_SIDECAR", None)

    def test_sign_matches_reference(self):
        body = '{"event":"transcription.completed","recording":{"id":"rec_1"}}'
        expected = hmac.new(b"whsec_x", ("1757358131412." + body).encode(), hashlib.sha256).hexdigest()
        self.assertEqual(demo_stub.sign("whsec_x", "1757358131412", body), expected)

    def test_plan_deliveries(self):
        dup = [d["event"] for d in demo_stub.plan_deliveries("dup", "r")]
        self.assertEqual(dup.count("transcription.completed"), 2)
        ooo = [d["event"] for d in demo_stub.plan_deliveries("out-of-order", "r")]
        self.assertLess(ooo.index("transcription.completed"), ooo.index("recording.created"))
        stale = demo_stub.plan_deliveries("stale-sig", "r")[0]["timestamp"]
        self.assertLess(int(stale), int(time.time() * 1000) - 500 * 1000)

    def test_auth_and_revoke(self):
        code, _ = _status(self.base + "/api/v1/recordings", headers={"Authorization": "Bearer bogus"})
        self.assertEqual(code, 401)
        code, _ = _status(self.base + "/api/v1/recordings", headers={"Authorization": "Bearer " + GOOD_KEY})
        self.assertEqual(code, 200)
        _status(self.base + "/_admin/scenario", "POST", b'{"scenario":"revoke-key"}',
                {"Content-Type": "application/json"})
        code, _ = _status(self.base + "/api/v1/recordings", headers={"Authorization": "Bearer " + GOOD_KEY})
        self.assertEqual(code, 401)

    def test_webhook_registration_requires_loopback(self):
        code, _ = _status(self.base + "/api/v1/webhooks", "POST",
                          json.dumps({"url": "http://example.com/hook", "secret": "s"}).encode(),
                          {"Content-Type": "application/json", "Authorization": "Bearer " + GOOD_KEY})
        self.assertEqual(code, 400)
        code, _ = _status(self.base + "/api/v1/webhooks", "POST",
                          json.dumps({"url": "http://127.0.0.1:9/hook", "secret": "s"}).encode(),
                          {"Content-Type": "application/json", "Authorization": "Bearer " + GOOD_KEY})
        self.assertEqual(code, 200)

    def test_retry_500_fails_first_detail_fetch_once(self):
        _status(self.base + "/_admin/scenario", "POST", b'{"scenario":"retry-500"}',
                {"Content-Type": "application/json"})
        h = {"Authorization": "Bearer " + GOOD_KEY}
        first, _ = _status(self.base + "/api/v1/recordings/rec_demo_002", headers=h)
        second, _ = _status(self.base + "/api/v1/recordings/rec_demo_002", headers=h)
        self.assertEqual((first, second), (500, 200))

    def test_settings_page_escapes_values(self):
        _status(self.base + "/settings", "POST", b"account=priya&webhook_url=%3Cscript%3Ex%3C/script%3E&webhook_secret=s")
        _, body = _status(self.base + "/settings")
        self.assertNotIn(b"<script>x</script>", body)
        self.assertIn(b"&lt;script&gt;", body)


class WebhookVerificationTest(unittest.TestCase):
    def setUp(self):
        self.session = tempfile.mkdtemp(prefix="demo-session-")
        state = demo_app.AppState(self.session)
        state.connections["1"] = {"connection_id": 1, "status": "active", "api_key": "k", "account": "priya",
                                  "token": "tok", "secret": "whsec_test", "webhook_url": "u"}
        self.state = state
        pipeline = type("P", (), {"enqueue": lambda self, i: None})()
        self.server = demo_app.AppServer(0, state, pipeline, "http://127.0.0.1:1", "http://127.0.0.1:1", "k")
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        _serve(self.server)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _post(self, body, ts, sig):
        return _status(self.base + "/webhooks/demo/tok", "POST", body.encode(),
                       {"Content-Type": "application/json", demo_app.TS_HEADER: ts, demo_app.SIG_HEADER: sig})

    def test_valid_signature_accepted_and_item_created(self):
        body = '{"event":"transcription.completed","recording":{"id":"rec_demo_002"}}'
        ts = str(int(time.time() * 1000))
        code, _ = self._post(body, ts, demo_stub.sign("whsec_test", ts, body))
        self.assertEqual(code, 200)
        self.assertEqual(len(self.state.items), 1)

    def test_bad_signature_and_stale_timestamp_rejected(self):
        body = '{"event":"transcription.completed","recording":{"id":"rec_demo_002"}}'
        ts = str(int(time.time() * 1000))
        code, _ = self._post(body, ts, "0" * 64)
        self.assertEqual(code, 401)
        stale = str(int(time.time() * 1000) - 600 * 1000)
        code, _ = self._post(body, stale, demo_stub.sign("whsec_test", stale, body))
        self.assertEqual(code, 401)
        self.assertEqual(len(self.state.items), 0)
        self.assertEqual({d["state"] for d in self.state.deliveries.values()}, {"rejected"})

    def test_unknown_token_is_404(self):
        code, _ = _status(self.base + "/webhooks/demo/other", "POST", b"{}")
        self.assertEqual(code, 404)


class ResetHookTest(unittest.TestCase):
    def test_reset_deletes_only_declared_session_paths(self):
        with tempfile.TemporaryDirectory() as root:
            old = os.path.join(root, "old")
            os.makedirs(os.path.join(old, "filed"))
            open(os.path.join(old, "app-state.json"), "w").write("{}")
            open(os.path.join(old, "filed", "r.md"), "w").write("x")
            open(os.path.join(old, "events.jsonl"), "w").write("")
            adapter = {"disposable": {"confirmed": True, "paths": ["app-state.json", "filed"]}}
            out = demo_hooks.reset(adapter, {}, old, os.path.join(root, "new"))
            self.assertEqual(sorted(out["removed"]), ["app-state.json", "filed"])
            self.assertTrue(os.path.exists(os.path.join(old, "events.jsonl")))

    def test_reset_refuses_paths_outside_session(self):
        with tempfile.TemporaryDirectory() as root:
            old = os.path.join(root, "old")
            os.makedirs(old)
            outside = os.path.join(root, "precious.txt")
            open(outside, "w").write("keep")
            for bad in (["../precious.txt"], [outside], ["a/../../precious.txt"]):
                with self.assertRaises(RuntimeError):
                    demo_hooks.reset({"disposable": {"paths": bad}}, {}, old, old)
            self.assertTrue(os.path.exists(outside))


if __name__ == "__main__":
    unittest.main()
