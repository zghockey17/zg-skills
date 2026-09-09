"""Fixture and monitor-page invariants.

The fixture is what the monitor page renders and what a snapshot inlines, so it
must stay valid against the event schema: strictly increasing ids and, for each
kind, the required data keys. The page must never route event data through
innerHTML, so the HTML carries no innerHTML assignment.
"""
import json
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.dirname(_HERE)
FIXTURE = os.path.join(_HERE, "fixtures", "events-sample.jsonl")
MONITOR = os.path.join(_ENGINE, "monitor.html")

REQUIRED = {
    "api.request": ["path", "method", "status", "latency_ms", "account"],
    "webhook.sent": ["event", "attempt", "url", "timestamp_header", "signature_valid"],
    "webhook.result": ["event", "attempt", "status", "latency_ms"],
    "scenario.changed": ["scenario", "previous"],
    "llm.request": ["call_id", "stage", "model", "prompt", "item_id", "job_reserved", "ambiguous"],
    "llm.response": ["call_id", "stage", "model", "status", "ms", "tokens", "completion", "error"],
    "item.changed": ["item_id", "state", "stage", "last_error", "redaction_counts", "title"],
    "connection.changed": ["connection_id", "status", "review_before_filing", "redact"],
    "delivery.changed": ["delivery_id", "state", "attempts", "event"],
    "poll.stale": ["reason", "ms"],
    "eval.rule": ["check", "pass", "evidence", "detail"],
    "eval.judge": ["verdict", "reason", "evidence", "rubric_version"],
    "finding": ["finding_id", "title", "expected", "actual", "repro", "severity"],
}


class FixtureTest(unittest.TestCase):
    def setUp(self):
        with open(FIXTURE) as fh:
            self.events = [json.loads(line) for line in fh if line.strip()]

    def test_every_kind_is_represented(self):
        kinds = {e["kind"] for e in self.events}
        for kind in REQUIRED:
            self.assertIn(kind, kinds)

    def test_ids_strictly_increasing(self):
        ids = [e["id"] for e in self.events]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_required_keys_per_kind(self):
        for e in self.events:
            for key in ("id", "ts", "kind", "data"):
                self.assertIn(key, e)
            for key in REQUIRED.get(e["kind"], []):
                self.assertIn(key, e["data"], "%s missing %s" % (e["kind"], key))

    def test_hostile_markup_present_for_render_check(self):
        # A prompt carries a literal script tag so a browser check of the
        # rendered page proves textContent handling.
        self.assertIn("<script>alert(1)</script>", json.dumps(self.events))


class MonitorTest(unittest.TestCase):
    def setUp(self):
        with open(MONITOR) as fh:
            self.html = fh.read()

    def test_no_innerhtml_assignment(self):
        self.assertNotRegex(self.html, r"\.innerHTML\s*=")
        self.assertNotIn("insertAdjacentHTML", self.html)
        self.assertNotIn("document.write", self.html)

    def test_no_external_resources(self):
        # A snapshot must open offline with no network at all.
        self.assertNotIn("<link", self.html)
        self.assertNotIn("src=\"http", self.html)
        self.assertNotIn("@import", self.html)

    def test_diff_cap_present(self):
        self.assertIn("DIFF_CELL_CAP", self.html)

    def test_no_em_dashes(self):
        self.assertNotIn("—", self.html)


if __name__ == "__main__":
    unittest.main()
