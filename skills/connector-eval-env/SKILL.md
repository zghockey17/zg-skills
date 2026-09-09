---
name: connector-eval-env
description: A local eval environment for an AI-powered third-party integration. See what your integration is doing, test failure scenarios, and inspect the evidence. Use when the user wants to test, debug, or demo a connector or webhook integration end to end, watch model calls (prompts, responses, timings) on a live page, run failure scenarios like duplicate or stale-signature webhooks, or score a pipeline run against expected redactions and export a shareable snapshot. Triggers include "eval environment for <connector>", "test the integration end to end", "watch the pipeline", "run the connector demo", and "/connector-eval-env <adapter>".
license: MIT
compatibility: Python 3.10+ standard library only. Loopback network. A browser for the monitor page. Optional model provider access for live runs.
metadata:
  author: Zave Greene
  version: "1.0.0"
---

# connector-eval-env

Turn "does this integration actually work" into a repeatable session. You drive the app in a browser, a read-only page shows every record moving through the pipeline with each model call, and the terminal runs scenarios and evals against one session log.

The skill is the process plus a small engine; one adapter folder per connector under `connectors/<name>/` supplies the app-specific parts. Two adapters ship: `demo` (runnable, everything fake and local) and `_template` (a placeholder to copy). `ADAPTING.md` walks a new adapter through the six phases.

## Start here

- **Never used it:** run the demo. `README.md` has the quick start; the commands below use `demo`.
- **Adapting to a real app:** read `ADAPTING.md`, then `references/adapter-contract.md`.
- **Running a session on an existing adapter:** start at phase 5 below.

Read `references/adapter-contract.md` before touching the engine or an adapter. It holds the event schema, the sidecar HTTP surface, the adapter.json fields, the hooks, the CLI, and the stub admin surface.

## The six phases

Phases 1 to 3 produce an adapter's durable knowledge and run once per adapter, or again only when an assumption changes. Phase 4 builds the adapter. Phase 5 is a normal session. Phase 6 routes what a session found.

### Phase 1: Grill

Walk the eleven decision branches in `references/grill-checklist.md` with the user: monitor scope, model policy, corpus policy, realism, control surface, reset semantics, capture mechanism, users, scenarios, sharing, and where outcomes land. Offer the options, take the choice and reason for each.

**Exit:** `connectors/<name>/decisions.md` records a chosen option and reason for every branch.

### Phase 2: Research the vendor

Confirm auth, endpoints, response shape, webhook or polling, signature scheme, event set, and retry behavior against public docs and any recorded account evidence. Label each claim Confirmed, Assumed, or Unknown per `references/vendor-research.md`.

**Exit:** every Assumed row is a named scenario in the stub, and the stub default holds the assumed-correct shape.

### Phase 3: Map the pipeline

Read the app: the item table, its state and stage columns, stage order, the artifact tables, the model call sites and their request fingerprints, the queue or worker.

**Exit:** `adapter.json` names the stages, states, fingerprints, and caps; the hooks in `adapter.py` know where to read items and the in-flight job.

### Phase 4: Build or extend the adapter

Build the mock vendor with a settings page and scenarios, the corpus with planted targets, the seed, the hooks, and the app-side change that points model calls at the sidecar. Reuse the engine unchanged.

**Exit:** `evalenv <name> up` is green and one `arrive` files a record end to end with every event kind present in the log.

### Phase 5: Run sessions

`reset` for a clean slate, drive the app in the browser, watch the monitor, fire scenarios and evals from the terminal, and `snapshot` at the end. Grade with `judge`, reading the captured prompt, response, and diff, and cite evidence event ids. Log observations with `finding`.

**Exit:** `snapshot.html` and `findings.md` in the session folder.

### Phase 6: Feed back

- **Product bugs** become tests in the app, never harness workarounds.
- **Harness lessons** append to `## Lessons` at the end of this file.
- **Adapter gaps** go in `connectors/<name>/README.md` under known gaps.
- **The snapshot** goes to whoever owns the integration.

## The feedback loop

One session log carries everything, so anything on the page is greppable in the terminal and anything the terminal finds is on the page.

- **`events.jsonl`** in `sessions/<stamp>/` is the single session log. The sidecar is the only writer; the stub, the app hooks, and the CLI post to `/emit`. Each event gets a monotonic id.
- **`finding`** appends a stable-id finding (expected, actual, repro, severity).
- **`snapshot`** freezes the page at the current event id into a self-contained `snapshot.html` with the events inlined as inert JSON, plus `findings.md`.
- **`## Lessons`** below is where harness lessons accumulate. Append; do not rewrite.

## CLI quick reference

`python3 engine/evalenv.py <connector> <verb> [args]` from the skill folder. Every command prints one JSON object and exits non-zero on failure.

| Verb | Does |
| --- | --- |
| `up` | New session folder; start stub, sidecar, and the adapter's processes; run the seed hook; print the vendor page, app, and monitor URLs. Idempotent. |
| `status` | Which processes are alive plus the adapter's status hook (booleans only). |
| `reset` | Stop everything, run the adapter's reset hook against disposable data, open a new session folder, restart, reseed. Refuses unless the adapter declares its data disposable. |
| `arrive <rec_id> [--account slug] [--no-webhook]` | The record appears at the vendor and its webhooks are delivered per the active scenario. |
| `backfill <n> [--account slug]` | Load n corpus records into the past, for the discovery path. |
| `scenario <name>` | Switch the stub's behavior. Names come from `adapter.json`. |
| `eval [rec_id]` | The nine rule checks against `corpus/targets.json`; appends `eval.rule` events with evidence ids. |
| `judge <rec_id> --verdict pass\|fail --reason "..." [--evidence 1,2,3]` | Your verdict after reading the captured evidence. Appends `eval.judge`. |
| `finding "<title>" --expected ... --actual ... --repro "..." [--severity low\|med\|high]` | A finding for the report. Appends `finding`. |
| `snapshot` | Write `snapshot.html` and `findings.md`. |
| `down` | Stop exactly the processes this session started, run the adapter's cleanup hook, leave the session folder. |

## Layout

```
connector-eval-env/
  SKILL.md                 this file
  README.md                install, quick start, usage, troubleshooting, limits, uninstall
  ADAPTING.md              the six phases against the _template adapter
  references/
    adapter-contract.md    event schema, sidecar HTTP, adapter.json, hooks, CLI, stub admin
    grill-checklist.md     the eleven-branch question tree
    vendor-research.md     confirm vs assume; each assumption becomes a scenario
    live-provider.md       real model provider: credentials, cost, what leaves the machine
  engine/                  evalenv.py (CLI), sidecar.py, evals.py, monitor.html, adapter.py, tests/
  connectors/
    demo/                  runnable: fake vendor, fake app, stand-in model, corpus, hooks
    _template/             placeholder to copy for a real adapter
  sessions/                gitignored: <stamp>/events.jsonl, snapshot.html, findings.md, run/*.log
```

Session folders hold what the run produced. A real provider key, when used, is read from the file the adapter names and handed to child processes only; it never lands in the skill folder, a session, or the CLI output.

## Lessons

- Per-task review cannot see schema drift. Run one real record end to end before calling an adapter done; the first live run of the first real adapter (a wearable-recorder connector for a meeting app) found a poller selecting a column that did not exist.
- Stub state an operator typed by hand must persist inside the session folder; a process restart mid-session must never ask them to retype it.
- If the app re-runs the pipeline after a user action (approve, retry), split item events into attempts before checking stage order, and treat the re-run's fresh model call as its own evidence.
- Let the user drive the app in their own browser window while the agent reads the log. Two sessions on one connection confuse who did what.
