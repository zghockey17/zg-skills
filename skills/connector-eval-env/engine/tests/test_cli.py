"""Unit tests for the CLI's pure functions and its safety rails.

Self-contained: temp directories and in-memory data. No test starts a server,
reads a real env file, or touches anything outside the temp folders.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

from engine import evalenv

ADAPTER = {
    "connector": "x", "_dir": "/tmp/x",
    "ports": {"vendor": 1, "sidecar": 2},
    "env": {"APP_ENV": "eval"},
    "secret_env_keys": ["MODEL_API_KEY"],
}

ENV_TEXT = """
APP_NAME="Some App"
APP_ENV=local
# a comment line
export QUEUE=sync
MODEL_API_KEY=sk-TESTONLY-0000
"""


class BuildEnvTest(unittest.TestCase):
    def test_overrides_and_pointers(self):
        env = evalenv.build_env(ADAPTER, ENV_TEXT, "/tmp/sess/1")
        self.assertEqual(env["APP_ENV"], "eval")           # adapter env wins
        self.assertEqual(env["APP_NAME"], "Some App")      # env_file value survives
        self.assertEqual(env["QUEUE"], "sync")             # export prefix stripped
        self.assertEqual(env["MODEL_API_KEY"], "sk-TESTONLY-0000")
        self.assertEqual(env["EVALENV_SESSION_DIR"], "/tmp/sess/1")
        self.assertEqual(env["EVALENV_SIDECAR"], "http://127.0.0.1:2")
        self.assertEqual(env["EVALENV_CORPUS"], "/tmp/x/corpus")

    def test_missing_env_file_is_an_error_not_a_silent_read(self):
        adapter = dict(ADAPTER, env_file="/nonexistent/.env")
        with self.assertRaises(RuntimeError):
            evalenv._env_file_text(adapter)


class SecretHandlingTest(unittest.TestCase):
    def test_pids_file_holds_only_pid_and_marker(self):
        with tempfile.TemporaryDirectory() as d:
            evalenv.write_pids(d, {"stub": {"pid": 11, "match": "stub.py"},
                                   "app": {"pid": 22, "match": "app.py"}})
            with open(evalenv.pids_path(d)) as fh:
                blob = fh.read()
        self.assertNotIn("sk-", blob)
        self.assertNotIn("MODEL_API_KEY", blob)
        self.assertEqual(json.loads(blob)["app"], {"pid": 22, "match": "app.py"})

    def test_scrub_removes_names_and_values(self):
        out = evalenv.scrub({"MODEL_API_KEY": "sk-TESTONLY-0000", "nested": {"error": "used sk-TESTONLY-0000 here"},
                             "list": ["sk-TESTONLY-0000"]}, {"MODEL_API_KEY"}, ["sk-TESTONLY-0000"])
        self.assertEqual(out["MODEL_API_KEY"], "<redacted>")
        self.assertEqual(out["nested"]["error"], "used <redacted> here")
        self.assertEqual(out["list"], ["<redacted>"])

    def test_cli_output_never_prints_a_secret(self):
        # Force a verb to fail with the secret in its message; main() must scrub it.
        class Boom(Exception):
            pass

        def handler(adapter, hooks, args):
            raise RuntimeError("leak: " + os.environ.get("EVALENV_TEST_SECRET", ""))

        with tempfile.TemporaryDirectory() as root:
            cdir = os.path.join(root, "connectors", "leaky")
            os.makedirs(cdir)
            with open(os.path.join(cdir, ".env"), "w") as fh:
                fh.write("MODEL_API_KEY=sk-LEAK-1234\n")
            with open(os.path.join(cdir, "adapter.json"), "w") as fh:
                json.dump({"ports": {"vendor": 1, "sidecar": 2}, "env_file": ".env",
                           "secret_env_keys": ["MODEL_API_KEY"]}, fh)
            original = evalenv.adapter_mod.ROOT
            evalenv.adapter_mod.ROOT = root
            evalenv.VERBS["boom"] = handler
            os.environ["EVALENV_TEST_SECRET"] = "sk-LEAK-1234"
            try:
                import io
                from contextlib import redirect_stdout
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = evalenv.main(["leaky", "boom"])
            finally:
                evalenv.adapter_mod.ROOT = original
                del evalenv.VERBS["boom"]
                del os.environ["EVALENV_TEST_SECRET"]
        self.assertEqual(code, 1)
        self.assertNotIn("sk-LEAK-1234", buf.getvalue())
        self.assertIn("<redacted>", buf.getvalue())


class ProcessOwnershipTest(unittest.TestCase):
    def test_owned_requires_matching_command_line(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertTrue(evalenv.owned(proc.pid, "time.sleep(30)"))
            self.assertFalse(evalenv.owned(proc.pid, "some-other-marker"))
            # terminate_owned refuses a mismatched marker and kills a matching one
            self.assertFalse(evalenv.terminate_owned({"pid": proc.pid, "match": "nope"}))
            self.assertTrue(evalenv._is_alive(proc.pid))
            self.assertTrue(evalenv.terminate_owned({"pid": proc.pid, "match": "time.sleep(30)"}, hard_after=3))
            deadline = time.time() + 5
            while evalenv._is_alive(proc.pid) and time.time() < deadline:
                proc.poll()
                time.sleep(0.1)
            self.assertFalse(evalenv.owned(proc.pid, "time.sleep(30)"))
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()

    def test_dead_pid_is_not_owned(self):
        self.assertFalse(evalenv.owned(None, "x"))
        self.assertFalse(evalenv.owned(2 ** 22 - 1, "x"))


class ResetFailsClosedTest(unittest.TestCase):
    def _sessions(self, root):
        os.environ["EVALENV_SESSIONS_ROOT"] = root
        evalenv.write_current(root, "s1")
        os.makedirs(os.path.join(root, "s1"), exist_ok=True)

    def tearDown(self):
        os.environ.pop("EVALENV_SESSIONS_ROOT", None)

    def test_refuses_without_disposable_confirmation(self):
        with tempfile.TemporaryDirectory() as root:
            self._sessions(root)
            adapter = dict(ADAPTER, _dir=root)
            hooks = evalenv.adapter_mod.Hooks(type("M", (), {"reset": staticmethod(lambda *a: {})}))
            out = evalenv.verb_reset(adapter, hooks, [])
        self.assertFalse(out["ok"])
        self.assertIn("disposable", out["error"])

    def test_refuses_without_reset_hook(self):
        with tempfile.TemporaryDirectory() as root:
            self._sessions(root)
            adapter = dict(ADAPTER, _dir=root, disposable={"confirmed": True})
            out = evalenv.verb_reset(adapter, evalenv.adapter_mod.Hooks(None), [])
        self.assertFalse(out["ok"])
        self.assertIn("reset hook", out["error"])


class SessionFileTest(unittest.TestCase):
    def test_current_roundtrip(self):
        with tempfile.TemporaryDirectory() as sessions:
            self.assertIsNone(evalenv.read_current(sessions))
            evalenv.write_current(sessions, "2026-01-01T00-00-00")
            self.assertEqual(evalenv.read_current(sessions), "2026-01-01T00-00-00")


class SnapshotTest(unittest.TestCase):
    def test_truncates_long_strings(self):
        events = [{"id": 1, "kind": "llm.request", "data": {"prompt": "x" * 25000, "short": "ok"}}]
        snap = evalenv.build_snapshot({"session": "s", "last_id": 1}, events, 1)
        ev = snap["events"][0]["data"]
        self.assertEqual(len(ev["prompt"]), 20000)
        self.assertTrue(ev["prompt_truncated"])
        self.assertNotIn("short_truncated", ev)

    def test_json_escapes_script_close(self):
        snap = {"events": [{"data": {"payload": "</script><img src=x onerror=alert(1)>"}}]}
        blob = evalenv._snapshot_json(snap)
        self.assertNotIn("<", blob)
        self.assertIn("\\u003c/script", blob)

    def test_inline_places_json_in_slot_and_keeps_page_inert(self):
        with open(os.path.join(os.path.dirname(evalenv.__file__), "monitor.html")) as fh:
            html = fh.read()
        hostile = "</script><script>window.__pwned=1</script>"
        snap = {"session": {"session": "s", "connector": "c"}, "frozen_at_id": 1,
                "events": [{"id": 1, "ts": "2026-01-01T00:00:00.000Z", "kind": "llm.request", "rec": "r",
                            "user": None, "data": {"call_id": "1", "stage": "redact", "model": "m",
                                                   "prompt": {"messages": [{"role": "user", "content": hostile}]},
                                                   "item_id": 1, "job_reserved": True, "ambiguous": False}}]}
        out = evalenv.inline_snapshot(html, snap)
        # The hostile string is present only in its escaped form, so the data
        # slot is still one JSON script element and no new script is opened.
        self.assertNotIn(hostile, out)
        self.assertIn("\\u003c/script>\\u003cscript>window.__pwned=1", out)
        self.assertEqual(out.count("<script"), html.count("<script"))


class FindingTest(unittest.TestCase):
    def test_allocates_next_id(self):
        self.assertEqual(evalenv.next_finding_id([]), "F-001")
        events = [{"kind": "finding"}, {"kind": "llm.request"}, {"kind": "finding"}]
        self.assertEqual(evalenv.next_finding_id(events), "F-003")

    def test_findings_md_has_section_per_finding(self):
        events = [{"kind": "finding", "data": {
            "finding_id": "F-001", "title": "Redaction missed a phone number",
            "expected": "redacted", "actual": "leaked", "repro": "arrive rec_demo_001",
            "severity": "high"}}]
        md = evalenv.render_findings_md(events)
        self.assertIn("F-001", md)
        self.assertIn("Redaction missed a phone number", md)


if __name__ == "__main__":
    unittest.main()
