"""Unit tests for the rule checks, the judge writer, and the finding writer.

Two fixture sessions under fixtures/ are copied into a temp session directory,
targets are passed inline, and a scripted hooks object stands in for the app.
Both the hooks-present and hooks-absent paths are exercised.
"""
import os
import shutil
import tempfile
import unittest

from engine import adapter as adapter_mod
from engine import evals

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

ADAPTER = {
    "connector": "t", "ports": {"sidecar": 0},
    "stages": ["fetching", "redacting", "summarizing", "linking"],
    "processing_state": "filing", "filed_state": "filed",
    "terminal_ok_states": ["dismissed"],
    "stage_caps_ms": {"redact": 5000, "summarize": 5000, "link": 5000},
    "llm_call_budget": 3,
}

GOOD_TARGETS = {"rec_g01": {
    "spans": [{"category": "health", "substring": "knee surgery"},
              {"category": "contact", "substring": "415-555-0142"}],
    "must_not_cut": ["Amir"],
}}
BAD_TARGETS = {"rec_b01": {
    "spans": [{"category": "health", "substring": "knee surgery"}],
    "must_not_cut": ["Amir"],
}}


class _Hooks:
    def artifacts(self, adapter, env, session_dir, rec):
        return True, "page present"


def _capture():
    captured = []
    counter = {"n": 0}

    def emit(kind, rec, user, data):
        counter["n"] += 1
        event = {"id": counter["n"], "kind": kind, "rec": rec, "user": user, "data": data}
        captured.append(event)
        return event

    return captured, emit


def _by_check(captured):
    return {ev["data"]["check"]: ev["data"] for ev in captured if ev["kind"] == "eval.rule"}


class RunRulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _session(self, *fixtures):
        with open(os.path.join(self.tmp, "events.jsonl"), "w") as out:
            for fixture in fixtures:
                with open(os.path.join(_FIXTURES, fixture)) as fh:
                    out.write(fh.read())
        return self.tmp

    def test_good_session_all_pass(self):
        session = self._session("good-session.jsonl")
        captured, emit = _capture()
        evals.run_rules(session, ADAPTER, "rec_g01", hooks=adapter_mod.Hooks(_Hooks()),
                        targets=GOOD_TARGETS, emit=emit)
        checks = _by_check(captured)
        self.assertEqual(len(checks), 9)
        for name, data in checks.items():
            self.assertTrue(data["pass"], "%s should pass: %s" % (name, data["detail"]))

    def test_without_hooks_only_artifacts_degrades(self):
        session = self._session("good-session.jsonl")
        captured, emit = _capture()
        evals.run_rules(session, ADAPTER, "rec_g01", hooks=None, targets=GOOD_TARGETS, emit=emit)
        checks = _by_check(captured)
        self.assertFalse(checks["artifacts_exist"]["pass"])
        self.assertIn("no artifacts hook", checks["artifacts_exist"]["detail"])
        for name in ("expected_spans_absent", "must_not_cut_present", "category_counts",
                     "state_reached", "stage_order", "stage_caps", "no_duplicate_filing",
                     "llm_call_budget"):
            self.assertTrue(checks[name]["pass"], name)

    def test_category_counts_tolerates_over_cut(self):
        with open(os.path.join(_FIXTURES, "good-session.jsonl")) as fh:
            source = fh.read()
        patched = source.replace(r'{\"contact\": 1, \"health\": 1}',
                                 r'{\"contact\": 1, \"health\": 1, \"compensation\": 1}')
        with open(os.path.join(self.tmp, "events.jsonl"), "w") as out:
            out.write(patched)
        captured, emit = _capture()
        evals.run_rules(self.tmp, ADAPTER, "rec_g01", targets=GOOD_TARGETS, emit=emit)
        counts = _by_check(captured)["category_counts"]
        self.assertTrue(counts["pass"], counts["detail"])
        self.assertIn("over-cuts", counts["detail"])

    def test_bad_session_exact_failures(self):
        session = self._session("bad-session.jsonl")
        captured, emit = _capture()
        evals.run_rules(session, ADAPTER, "rec_b01", hooks=adapter_mod.Hooks(_Hooks()),
                        targets=BAD_TARGETS, emit=emit)
        checks = _by_check(captured)
        failed = {name for name, data in checks.items() if not data["pass"]}
        self.assertEqual(failed, {"expected_spans_absent", "category_counts", "stage_order", "llm_call_budget"})
        self.assertIn("knee surgery", checks["expected_spans_absent"]["detail"])
        self.assertIn("backwards", checks["stage_order"]["detail"])
        self.assertIn("4 of 3", checks["llm_call_budget"]["detail"])
        # evidence ids point at real events in the log
        self.assertEqual(sorted(checks["llm_call_budget"]["evidence"]), [23, 26, 29, 32])

    def test_duplicate_item_rows_fail(self):
        with open(os.path.join(_FIXTURES, "good-session.jsonl")) as fh:
            source = fh.read()
        dup = source.replace('"item_id": 1', '"item_id": 9').replace('"id": 16', '"id": 17')
        with open(os.path.join(self.tmp, "events.jsonl"), "w") as out:
            out.write(source + dup)
        captured, emit = _capture()
        evals.run_rules(self.tmp, ADAPTER, "rec_g01", targets=GOOD_TARGETS, emit=emit)
        check = _by_check(captured)["no_duplicate_filing"]
        self.assertFalse(check["pass"])
        self.assertIn("2 item row(s)", check["detail"])

    def test_all_recs_when_no_rec_id(self):
        self._session("good-session.jsonl", "bad-session.jsonl")
        captured, emit = _capture()
        targets = dict(GOOD_TARGETS)
        targets.update(BAD_TARGETS)
        evals.run_rules(self.tmp, ADAPTER, None, targets=targets, emit=emit)
        self.assertEqual({ev["rec"] for ev in captured}, {"rec_g01", "rec_b01"})
        self.assertEqual(len(captured), 18)

    def test_unsafe_rec_id_never_reaches_a_hook(self):
        self._session("good-session.jsonl")
        seen = []

        class Spy:
            def artifacts(self, adapter, env, session_dir, rec):
                seen.append(rec)
                return True, "ok"
        captured, emit = _capture()
        evals.run_rules(self.tmp, ADAPTER, "rec_g01'; DROP TABLE x", hooks=adapter_mod.Hooks(Spy()),
                        targets={}, emit=emit)
        self.assertEqual(seen, [])
        self.assertFalse(_by_check(captured)["artifacts_exist"]["pass"])


class JudgeFindingTest(unittest.TestCase):
    def test_judge_emits_rubric_v1(self):
        captured, emit = _capture()
        ev = evals.judge(emit, "rec_g01", "fail", "health phrase survived", [12, 15])
        self.assertEqual(ev["kind"], "eval.judge")
        self.assertEqual(ev["data"]["verdict"], "fail")
        self.assertEqual(ev["data"]["evidence"], [12, 15])

    def test_finding_allocates_monotonic_id(self):
        captured, emit = _capture()
        fid, ev = evals.finding(emit, [{"kind": "finding"}, {"kind": "finding"}],
                                "Fetch 500 fails without retry", "retry", "failed", "scenario retry-500", "high")
        self.assertEqual(fid, "F-003")
        self.assertEqual(ev["data"]["severity"], "high")


if __name__ == "__main__":
    unittest.main()
