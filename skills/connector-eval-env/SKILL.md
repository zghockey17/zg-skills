---
name: connector-eval-env
description: Eval environment for an AI-powered third-party integration (connector or webhook pipeline). Use when the user wants to test or demo an integration end to end, watch its model calls live, replay vendor failures such as duplicate or stale-signature webhooks, or score a run and export a shareable snapshot.
license: MIT
compatibility: Python 3.10+ standard library only. Loopback network. A browser for the monitor page. Optional model provider access for live runs.
metadata:
  author: Zave Greene
  version: "1.0.1"
---

# connector-eval-env

Turn "does this integration actually work" into a repeatable session. You drive the app in a browser, a read-only page shows every record moving through the pipeline with each model call, and the terminal runs scenarios and evals against one session log.

The skill is the process plus a small engine. One adapter folder per connector under `connectors/<name>/` supplies the app-specific parts; the engine and the session steps stay the same for every adapter. Two adapters ship: `demo` (runnable, everything fake and local) and `_template` (a placeholder to copy).

## Start here

- **Never used it:** run the demo from the quick start in `README.md`.
- **Adapting to a real app:** follow the six phases in `ADAPTING.md`.
- **Running a session on an existing adapter:** the steps are below.

Read `references/adapter-contract.md` before touching the engine or an adapter. It holds the event schema, the sidecar HTTP surface, the adapter.json fields, the hooks, the CLI, and the stub admin surface.

## Running a session

All verbs run as `python3 engine/evalenv.py <connector> <verb> [args]` from the skill folder. Each prints one JSON object and exits non-zero on failure; the full verb table is in `README.md` under Usage.

1. **`up`** starts a fresh session: the stub, the sidecar, the adapter's processes, and the seed. It prints the vendor, app, and monitor URLs.
2. **`reset`** gives a clean slate mid-session without leaving the app. It refuses unless the adapter declares its data disposable.
3. **Drive the app**: the user drives it in their own browser window while the agent reads the log.
4. **Watch the monitor**: each record moving through the pipeline, every model call with its prompt and response, and the redaction diff.
5. **`scenario <name>`** switches the stub to a named failure: duplicate delivery, stale signature, slow or failing fetch, revoked key.
6. **`eval [rec_id]`** runs the rule checks against `corpus/targets.json` and appends `eval.rule` events with evidence ids.
7. **`judge <rec_id>`** records your verdict after you read the captured prompt, response, and diff, citing evidence event ids. Grading a model with the same model is circular, so a person or a different agent grades.
8. **`finding`** logs an observation for the report: expected, actual, repro, severity.
9. **`snapshot`** freezes the page into a self-contained `snapshot.html`, plus `findings.md`, for whoever owns the integration.
10. **`down`** stops exactly the processes this session started and runs the adapter's cleanup hook.

Feeding back: product bugs become tests in the app, never harness workarounds; harness lessons append to `## Lessons` at the end of this file; adapter gaps go in `connectors/<name>/README.md` under known gaps.

## The session log

`sessions/<stamp>/events.jsonl` is the single session log, so anything on the page is greppable in the terminal and anything the terminal finds is on the page. The sidecar is the only writer; the stub, the app hooks, and the CLI post to `/emit`, and each event gets a monotonic id. Cite those ids as evidence in every verdict and finding.

## Layout

```
connector-eval-env/
  SKILL.md                 this file
  README.md                quick start, install, usage, troubleshooting, limits, uninstall
  ADAPTING.md              the six phases against the _template adapter
  references/
    adapter-contract.md    event schema, sidecar HTTP, adapter.json, hooks, CLI, stub admin
    grill-checklist.md     the eight-branch question tree
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

Harness lessons accumulate here. Append; do not rewrite.

- Per-task review cannot see schema drift. Run one real record end to end before calling an adapter done; the first live run of the first real adapter found a poller selecting a column that did not exist.
- Stub state an operator typed by hand must persist inside the session folder; a process restart mid-session must never ask them to retype it.
- If the app re-runs the pipeline after a user action (approve, retry), split item events into attempts before checking stage order, and treat the re-run's fresh model call as its own evidence.
- Let the user drive the app in their own browser window while the agent reads the log. Two sessions on one connection confuse who did what.
