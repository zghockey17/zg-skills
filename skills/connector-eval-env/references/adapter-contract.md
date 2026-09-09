# Adapter contract

What `connectors/<name>/` provides and the interfaces every part shares. Change this file first, then the engine and adapters, never the reverse.

## Event (one JSON object per line in `sessions/<stamp>/events.jsonl`)

```json
{"id": 1234, "ts": "2026-01-12T19:02:11.412Z", "kind": "llm.response", "rec": "rec_a05", "user": "priya", "data": {}}
```

- `id`: monotonic integer assigned by the sidecar. `ts`: ISO 8601 UTC with milliseconds, assigned by the sidecar. `rec`: vendor external id or null. `user`: seeded account slug or null.
- Kinds and required `data` keys:
  - `api.request`: `path, method, status, latency_ms, account`
  - `webhook.sent`: `event, attempt, url, timestamp_header, signature_valid`
  - `webhook.result`: `event, attempt, status, latency_ms`
  - `scenario.changed`: `scenario, previous`
  - `llm.request`: `call_id, stage, model, prompt` (the full JSON body as sent), `item_id, job_reserved, ambiguous`
  - `llm.response`: `call_id, stage, model, status, ms, tokens: {prompt, completion, total}, completion` (full response body), `error`
  - `item.changed`: `item_id, external_id, state, stage, last_error, redaction_counts, title`; optionally `redacted_words`
  - `connection.changed`: `connection_id, status, review_before_filing, redact` (toggle map)
  - `delivery.changed`: `delivery_id, external_id, state, attempts, event`
  - `poll.stale`: `reason, ms`
  - `action.*`: `args` (the CLI argv), `result`
  - `eval.rule`: `check, pass, evidence` (list of event ids), `detail`
  - `eval.judge`: `verdict` (pass|fail), `reason, evidence, rubric_version`
  - `finding`: `finding_id` (F-001 style, monotonic per session), `title, expected, actual, repro, severity`

Request headers are never recorded. The proxy forwards `Authorization` upstream and drops it.

## Sidecar HTTP (port `ports.sidecar`, loopback only)

- `POST /emit` body `{kind, rec, user, data}` returns `{id}`. Only writer to `events.jsonl`. Serialized with a lock, fsynced per line.
- `GET /events?after=<id>` Server-Sent Events. Replays every event with id greater than `after`, then tails. `: heartbeat` every 15 s. Event name `ev`.
- `GET /` serves `engine/monitor.html`.
- `GET /session` returns `{session, connector, started, last_id, llm_stages, stages, states, filed_state, failed_state, limitations, labels}`. The monitor and the snapshot read their configuration from this.
- `POST /v1/chat/completions` (any path ending in `/chat/completions`): emits `llm.request`, forwards to `upstream` with the incoming `Authorization`, emits `llm.response`, returns the upstream status and body unchanged. `upstream` is `EVALENV_UPSTREAM`, else `adapter.json` `upstream`, else `https://api.openai.com`.
- Poller: once a second, calls the `observe` hook, diffs against the previous cycle, emits one `*.changed` per row that appeared or moved. A cycle over 3 s or a raise emits `poll.stale`.

## adapter.json

| Field | Meaning |
| --- | --- |
| `connector` | Folder name |
| `ports` | `vendor`, `sidecar` required; `app` printed by `up`; others for your hooks |
| `stub` | Relative path to the mock vendor script the engine starts |
| `hooks` | Relative path to the hooks module (default `adapter.py`) |
| `vendor_page` | Path on the stub printed as the vendor dashboard (default `/settings`) |
| `upstream` | Model provider base URL for the proxy; null means OpenAI |
| `env` | Static environment for every child process |
| `env_file` | Optional `.env` whose values enter the child environment. The only place a real key comes from |
| `secret_env_keys` | Names scrubbed from every CLI output |
| `disposable` | `{confirmed, description, paths}`. `reset` refuses unless `confirmed` is true and a reset hook exists |
| `users` | Seeded accounts: `slug, email, name, api_key` |
| `scenarios` | Names `scenario <name>` accepts |
| `stages` | Pipeline stages in order |
| `states`, `processing_state`, `filed_state`, `failed_state`, `terminal_ok_states` | Item state vocabulary |
| `llm_fingerprints` | `{stage: {body_contains}}` or `{stage: {prompt_prefix}}`; first match in order wins |
| `llm_call_budget` | Model calls allowed per record |
| `stage_caps_ms` | Latency cap per model-call stage |
| `labels` | Optional display names per state |
| `limitations` | Shown on the monitor and in every snapshot |

## Hooks (`adapter.py`)

All optional. `env` is the child environment the engine built (for the sidecar, the process environment).

| Hook | Signature | Called by | Returns | Missing means |
| --- | --- | --- | --- | --- |
| `processes` | `(adapter, env, session_dir)` | `up`, `reset` | list of `{role, argv, cwd, port?, match?}` to start after the stub and sidecar (app server, worker) | only the stub and sidecar start |
| `seed` | `(adapter, env, session_dir)` | `up`, `reset` | dict, printed by `up` | no seeding |
| `reset` | `(adapter, env, old_session_dir, new_session_dir)` | `reset` | dict; deletes disposable data, verifying the target is throwaway and raising otherwise | `reset` refuses |
| `observe` | `(adapter, env)` | sidecar, once a second | `{items: {id: row}, connections: {...}, deliveries: {...}}` (dicts or lists of rows) | no `*.changed` events |
| `in_flight` | `(adapter, env)` | sidecar, per model call | `{item_id, rec, job_reserved, ambiguous}` from the reserved job row | model calls uncorrelated |
| `transcript` | `(adapter, env, rec)` | `eval` | redacted text with speaker names, or None | checks use `redacted_words` from item events |
| `artifacts` | `(adapter, env, session_dir, rec)` | `eval` | `(ok, detail)` for the filed artifacts | `artifacts_exist` fails with a stated reason |
| `status` | `(adapter, env, session_dir)` | `status` | dict of booleans, `ok` optional | `status` reports processes only |
| `down` | `(adapter, env, session_dir)` | `down` | dict; undoes any app modification `up` made | nothing to undo |

Row keys the poller projects: items `item_id, external_id, state, stage, last_error, redaction_counts, title, redacted_words`; connections `connection_id, status, review_before_filing, redact`; deliveries `delivery_id, external_id, state, attempts, event`. Extra keys are ignored.

`rec` values passed to hooks match `^[A-Za-z0-9_.-]+$`; anything else is rejected before the hook runs.

## Process ownership

`pids.json` records `{role: {pid, match}}`. `match` is a substring of the command line (by default the script's basename). `down` and `reset` kill a pid only when it is alive and its command line still contains `match`. `up` refuses to start a role whose port is already taken and never kills the holder.

## CLI

`python3 engine/evalenv.py <connector> <verb> [args]`. Verbs: `up`, `down`, `status`, `reset`, `arrive`, `backfill`, `scenario`, `eval`, `judge`, `finding`, `snapshot`. The full argument syntax and what each does are in `README.md` under Usage.

`EVALENV_SESSIONS_ROOT` moves the sessions folder (tests use it).

## Rule checks

`expected_spans_absent`, `must_not_cut_present`, `category_counts`, `state_reached`, `stage_order`, `stage_caps`, `no_duplicate_filing`, `artifacts_exist`, `llm_call_budget`. Each emits one `eval.rule` per record with evidence event ids. `corpus/targets.json` is keyed by record id: `{spans: [{category, substring, best_effort?}], must_not_cut: [...]}`. A category written as `a or b` is satisfied by either bucket. Over-redaction never fails a check.

## Stub admin surface (port `ports.vendor`)

- `POST /_admin/arrive` `{rec_id, account?, webhook?}`; `POST /_admin/backfill` `{n, account?}`; `POST /_admin/scenario` `{scenario}`; `POST /_admin/reset`; `GET /_admin/state`.
- `GET <vendor_page>` HTML settings page. The stub emits every event via `POST <sidecar>/emit` and carries on if the sidecar is down.
- The stub persists operator-typed state in `<session>/stub-state.json` so a restart mid-session keeps the connection.
