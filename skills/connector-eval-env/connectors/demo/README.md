# demo adapter

Runnable end to end with nothing but Python. Four processes on loopback:

| Port | Process | Role |
| --- | --- | --- |
| 8226 | `stub.py` | Fake recorder vendor: REST API, webhook registration, signed deliveries with retries, settings page, scenarios |
| 8227 | `app.py` | Fake notes app: connect step, webhook receiver with HMAC verification, four-stage pipeline, filed pages |
| 8228 | `model.py` | Deterministic stand-in for an OpenAI-compatible chat model |
| 8230 | sidecar | Engine: capture proxy, event log, monitor |

The hooks in `adapter.py` talk to the app over `/_eval/*` endpoints and touch files only inside the session folder.

## What is live and what is not

Live: vendor API calls, webhook signing and verification, the pipeline, the capture proxy, the evals, the snapshot. Not live: the model. `model.py` redacts by regex and answers summaries with a template, so the same input always produces the same output. Evals here prove the pipeline works, not that a model redacts well.

## The planted bug

`app.py` creates a new item for every `transcription.completed` delivery without checking for an existing one. `scenario dup` delivers that event twice; `eval` then fails `no_duplicate_filing` (two item rows, two filed transitions) and `llm_call_budget` (six calls of three). This is the demo's failing case and it is deliberate.

## Scenarios

`off`, `dup`, `out-of-order`, `slow-fetch` (2.5 s detail fetch), `retry-500` (first detail fetch per record fails once; the app retries), `stale-sig` (10-minute-old timestamp; the app rejects with 401 and no item is created), `revoke-key` (every API call returns 401).

## Reset

`disposable.paths` names `app-state.json` and `filed/` inside the old session folder. The reset hook verifies each path resolves inside that folder and refuses otherwise. Nothing outside a session folder is ever deleted.

## Known gaps

- After `reset` the app must be reconnected; the connection lives in the session's app state by design.
- The demo app runs one worker, so `in_flight` is never ambiguous.
