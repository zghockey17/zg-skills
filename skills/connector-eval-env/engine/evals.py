"""Mechanical rule checks, the judge writer, and the finding writer.

`run_rules` reads a session's `events.jsonl`, correlates every event to a vendor
record, and emits one `eval.rule` event per check per record. The checks are
deterministic: they compare what the app did (redacted text, redaction counts,
item states, stage order, model call count, filed artifacts) against the corpus
`targets.json` and the adapter contract. `judge` and `finding` are the writers
the CLI's `judge` and `finding` verbs call.

Every writer goes through an `emit(kind, rec, user, data)` callable so the one
`/emit` path in the sidecar stays the single writer to the log; tests pass a
capturing callable instead of posting. Two checks ask the adapter for more than
the log holds (`transcript`, `artifacts`); an adapter without those hooks gets
the event-only answer or a stated failure, never an exception.
"""
import json
import os
import re
import types
import urllib.request

# Vendor record ids reach adapter hooks that may build queries or file paths
# from them, so the alphabet is restricted here once.
_SAFE_REC = re.compile(r"^[A-Za-z0-9_.-]+$")


# --- reading and correlation ------------------------------------------------

def read_events(session_dir):
    path = os.path.join(session_dir, "events.jsonl")
    events = []
    if not os.path.exists(path):
        return events
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    return events


def _item_rec_map(events):
    """item_id -> record external id, from any event that knows both."""
    mapping = {}
    for ev in events:
        data = ev.get("data") or {}
        item_id = data.get("item_id")
        if item_id is None:
            continue
        rec = ev.get("rec") or data.get("external_id")
        if rec:
            mapping.setdefault(item_id, rec)
    return mapping


def _rec_of(ev, item_map):
    if ev.get("rec"):
        return ev["rec"]
    data = ev.get("data") or {}
    if data.get("external_id"):
        return data["external_id"]
    item_id = data.get("item_id")
    if item_id is not None:
        return item_map.get(item_id)
    return None


def _recs(events, item_map):
    found = set()
    for ev in events:
        rec = _rec_of(ev, item_map)
        if rec:
            found.add(rec)
    return sorted(found)


def _kind(rec_events, kind):
    return [ev for ev in rec_events if ev.get("kind") == kind]


def _last_words(item_changes):
    words, ev_id = None, None
    for ev in item_changes:
        value = (ev.get("data") or {}).get("redacted_words")
        if value is not None:
            words, ev_id = value, ev.get("id")
    return words, ev_id


def _last_counts(item_changes):
    counts, ev_id = None, None
    for ev in item_changes:
        raw = (ev.get("data") or {}).get("redaction_counts")
        if not raw:
            continue
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            continue
        if isinstance(parsed, dict):
            counts, ev_id = parsed, ev.get("id")
    return counts, ev_id


def _normalize(text):
    return " ".join((text or "").lower().split())


def _safe(rec):
    if not _SAFE_REC.match(rec or ""):
        raise ValueError("unsafe rec id: %r" % rec)
    return rec


def _words(ctx):
    """Redacted text for the rec: the adapter's transcript hook when it answers,
    else the copy the poller attached to the filed event."""
    if ctx.hooks is not None and ctx.hooks.has("transcript"):
        try:
            text = ctx.hooks.call("transcript", ctx.adapter, os.environ, _safe(ctx.rec))
        except Exception:
            text = None
        if text:
            _, wid = _last_words(ctx.item_changes)
            return text, wid
    return _last_words(ctx.item_changes)


def _toggles(all_events):
    toggles = {}
    for ev in all_events:
        if ev.get("kind") == "connection.changed":
            redact = (ev.get("data") or {}).get("redact")
            if isinstance(redact, dict):
                toggles = redact
    return toggles


def _attempts(item_changes, processing_state):
    """Split item.changed events into pipeline attempts.

    A retry re-dispatches the pipeline, so one rec can legitimately enter the
    processing state more than once. Each entry into it from another state
    starts a new attempt."""
    attempts, current, prev_state = [], [], None
    for ev in item_changes:
        state = (ev.get("data") or {}).get("state")
        if state == processing_state and prev_state != processing_state and current:
            attempts.append(current)
            current = []
        current.append(ev)
        prev_state = state
    if current:
        attempts.append(current)
    return attempts


# --- the checks -------------------------------------------------------------
# Each takes the per-rec context and returns (pass, evidence ids, detail).

def _check_expected_spans_absent(ctx):
    words, wid = _words(ctx)
    spans = [s for s in ctx.spans if not s.get("best_effort")]
    toggles = _toggles(ctx.all_events)
    spans = [s for s in spans if toggles.get(s.get("category")) is not False]
    if words is None:
        return False, [], "no redacted transcript captured for the rec"
    norm = _normalize(words)
    survived = [s["substring"] for s in spans if _normalize(s["substring"]) in norm]
    if survived:
        return False, [wid], "expected spans survived redaction: " + "; ".join(survived)
    return True, [wid], "all %d expected spans absent from the redacted transcript" % len(spans)


def _check_must_not_cut_present(ctx):
    names = ctx.target.get("must_not_cut", [])
    words, wid = _words(ctx)
    if not names:
        return True, [wid] if wid else [], "no must_not_cut names for the rec"
    if words is None:
        return False, [], "no redacted transcript captured for the rec"
    norm = _normalize(words)
    missing = [n for n in names if _normalize(n) not in norm]
    if missing:
        return False, [wid], "must_not_cut names dropped: " + ", ".join(missing)
    return True, [wid], "all %d must_not_cut names present" % len(names)


def _check_category_counts(ctx):
    counts, cid = _last_counts(ctx.item_changes)
    required, oneof = set(), []
    for span in ctx.spans:
        if span.get("best_effort"):
            continue
        category = span["category"]
        if " or " in category:
            oneof.append(tuple(c.strip() for c in category.split(" or ")))
        else:
            required.add(category)
    expected = set(required)
    for group in oneof:
        expected.update(group)
    actual = counts or {}

    def count(category):
        return int(actual.get(category, 0) or 0)

    problems = []
    toggles = _toggles(ctx.all_events)
    off = {c for c in required if toggles.get(c) is False}
    required = required - off
    for category in sorted(required):
        if count(category) < 1:
            problems.append("expected %s>=1, got %d" % (category, count(category)))
    for group in oneof:
        if sum(count(c) for c in group) < 1:
            problems.append("expected one of %s>=1, got 0" % "/".join(group))
    # Over-redaction is acceptable per the corpus contract: a nonzero count in a
    # category the targets do not assert is reported, never scored as a fail.
    over_cuts = ["%s=%d" % (c, count(c)) for c in sorted(actual)
                 if c not in expected and count(c) > 0]
    detail_tail = "actual=%s" % json.dumps(actual, sort_keys=True)
    if over_cuts:
        detail_tail += "; over-cuts (acceptable): " + ", ".join(over_cuts)
    if off:
        detail_tail += "; toggles off, not expected: " + ", ".join(sorted(off))
    if problems:
        return False, [cid] if cid else [], "; ".join(problems) + "; " + detail_tail
    return True, [cid] if cid else [], "counts satisfy targets; " + detail_tail


def _check_state_reached(ctx):
    if not ctx.item_changes:
        return False, [], "no item.changed events for the rec"
    last = ctx.item_changes[-1]
    state = (last.get("data") or {}).get("state")
    filed = ctx.adapter.get("filed_state", "filed")
    if state == filed:
        return True, [last.get("id")], "reached %s" % filed
    # States a record may legitimately end in without being filed (held for
    # approval, dismissed by the user) are declared by the adapter.
    if state in ctx.adapter.get("terminal_ok_states", []):
        return True, [last.get("id")], "ended in %s (allowed terminal)" % state
    return False, [last.get("id")], "ended in %s, not %s" % (state, filed)


def _check_stage_order(ctx):
    order = {stage: i for i, stage in enumerate(ctx.adapter["stages"])}
    seen, ids = [], []
    attempts = _attempts(ctx.item_changes, ctx.adapter.get("processing_state", "filing"))
    for n, attempt in enumerate(attempts):
        if n:
            seen.append("|")
        for ev in attempt:
            stage = (ev.get("data") or {}).get("stage")
            if stage and (not seen or seen[-1] != stage):
                seen.append(stage)
                ids.append(ev.get("id"))
    detail = "stage sequence: " + (" -> ".join(seen) if seen else "(none)")
    if len(attempts) > 1:
        detail += " (%d attempts)" % len(attempts)
    # An empty sequence passes vacuously; safe because a rec with no pipeline
    # events still fails state_reached and expected_spans_absent.
    prev = -1
    for stage in seen:
        if stage == "|":
            prev = -1
            continue
        if stage not in order:
            return False, ids, detail + "; unknown stage %s" % stage
        if order[stage] < prev:
            return False, ids, detail + "; backwards move to %s" % stage
        prev = order[stage]
    return True, ids, detail


def _check_stage_caps(ctx):
    caps = ctx.adapter.get("stage_caps_ms", {})
    over, ids = [], []
    for ev in _kind(ctx.rec_events, "llm.response"):
        data = ev.get("data") or {}
        stage, ms = data.get("stage"), data.get("ms")
        if stage in caps and ms is not None:
            ids.append(ev.get("id"))
            if ms > caps[stage]:
                over.append("%s %dms over %dms" % (stage, ms, caps[stage]))
    if over:
        return False, ids, "stage caps exceeded: " + "; ".join(over)
    return True, ids, "all %d capped model responses under stage caps" % len(ids)


def _check_no_duplicate_filing(ctx):
    filed_state = ctx.adapter.get("filed_state", "filed")
    filed_ids, prev_state = [], None
    for ev in ctx.item_changes:
        state = (ev.get("data") or {}).get("state")
        if state == filed_state and prev_state != filed_state:
            filed_ids.append(ev.get("id"))
        prev_state = state
    # Two item rows for one external id is the other duplicate shape: the app
    # created a second item for the same vendor record.
    item_ids = {(ev.get("data") or {}).get("item_id") for ev in ctx.item_changes}
    item_ids.discard(None)
    filed = len(filed_ids)
    ok = filed <= 1 and len(item_ids) <= 1
    return ok, filed_ids, "%d filed transition(s), %d item row(s)" % (filed, len(item_ids))


def _check_artifacts_exist(ctx):
    if ctx.hooks is None or not ctx.hooks.has("artifacts"):
        return False, [], "adapter has no artifacts hook"
    try:
        ok, detail = ctx.hooks.call("artifacts", ctx.adapter, os.environ,
                                    ctx.session_dir, _safe(ctx.rec))
    except Exception as err:
        return False, [], "artifacts hook failed: %s" % err
    return bool(ok), [], str(detail)


def _check_llm_call_budget(ctx):
    requests = _kind(ctx.rec_events, "llm.request")
    budget = ctx.adapter.get("llm_call_budget", len(ctx.adapter.get("llm_fingerprints", {})))
    by_stage = {}
    for ev in requests:
        stage = (ev.get("data") or {}).get("stage")
        by_stage[stage] = by_stage.get(stage, 0) + 1
    count = len(requests)
    breakdown = ", ".join("%s:%d" % (s, by_stage[s]) for s in sorted(by_stage, key=str))
    detail = "%d of %d allowed; %s" % (count, budget, breakdown or "none")
    return count <= budget, [ev.get("id") for ev in requests], detail


CHECKS = (
    ("expected_spans_absent", _check_expected_spans_absent),
    ("must_not_cut_present", _check_must_not_cut_present),
    ("category_counts", _check_category_counts),
    ("state_reached", _check_state_reached),
    ("stage_order", _check_stage_order),
    ("stage_caps", _check_stage_caps),
    ("no_duplicate_filing", _check_no_duplicate_filing),
    ("artifacts_exist", _check_artifacts_exist),
    ("llm_call_budget", _check_llm_call_budget),
)


# --- emit -------------------------------------------------------------------

def default_emit(adapter):
    """POST to the sidecar /emit, the same single writer the CLI uses."""
    base = "http://127.0.0.1:%d/emit" % adapter["ports"]["sidecar"]

    def emit(kind, rec, user, data):
        body = json.dumps({"kind": kind, "rec": rec, "user": user, "data": data}).encode()
        req = urllib.request.Request(base, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            reply = json.loads(resp.read().decode() or "{}")
        return {"id": reply.get("id"), "kind": kind, "rec": rec, "user": user, "data": data}

    return emit


# --- public writers ---------------------------------------------------------

def run_rules(session_dir, adapter, rec_id=None, hooks=None, targets=None, emit=None):
    """Run every rule check against the session and emit one eval.rule each.

    With rec_id set, only that record is scored; otherwise every record the
    events mention is scored. `targets` is the records map (rec id ->
    {spans, must_not_cut}); it defaults to the connector's corpus targets.json.
    `emit` defaults to the sidecar POST. Returns the emitted event dicts.
    """
    events = read_events(session_dir)
    if targets is None:
        targets = load_targets(adapter)
    if emit is None:
        emit = default_emit(adapter)
    item_map = _item_rec_map(events)
    recs = [rec_id] if rec_id else _recs(events, item_map)

    emitted = []
    for rec in recs:
        rec_events = [ev for ev in events if _rec_of(ev, item_map) == rec]
        ctx = types.SimpleNamespace(
            rec=rec,
            target=targets.get(rec, {}),
            spans=targets.get(rec, {}).get("spans", []),
            rec_events=rec_events,
            item_changes=_kind(rec_events, "item.changed"),
            all_events=events,
            adapter=adapter,
            hooks=hooks,
            session_dir=session_dir,
        )
        for name, check in CHECKS:
            passed, evidence, detail = check(ctx)
            emitted.append(emit("eval.rule", rec, None, {
                "check": name, "pass": bool(passed),
                "evidence": [e for e in evidence if e is not None], "detail": detail,
            }))
    return emitted


def load_targets(adapter):
    path = os.path.join(adapter["_dir"], "corpus", "targets.json")
    with open(path) as fh:
        return json.load(fh).get("recordings", {})


def judge(emit, rec, verdict, reason, evidence):
    """Write one eval.judge event and return it. rubric_version is fixed at 1."""
    return emit("eval.judge", rec, None, {
        "verdict": verdict, "reason": reason or "", "evidence": evidence or [],
        "rubric_version": "1",
    })


def next_finding_id(events):
    n = sum(1 for ev in events if ev.get("kind") == "finding")
    return "F-%03d" % (n + 1)


def finding(emit, events, title, expected, actual, repro, severity):
    """Allocate the next F-nnn from the log and write one finding event."""
    finding_id = next_finding_id(events)
    ev = emit("finding", None, None, {
        "finding_id": finding_id, "title": title, "expected": expected or "",
        "actual": actual or "", "repro": repro or "", "severity": severity,
    })
    return finding_id, ev
