# Adapting connector-eval-env to your app

Six phases, walked against `connectors/_template/`. Copy that folder to `connectors/<name>/` first. Every `_about_*` key in its `adapter.json` says what a real value looks like and where the engine reads it; delete those keys when done. `connectors/demo/` is a complete working adapter to crib from.

The first real adapter, a wearable-recorder connector for a meeting app, took the shape below: a vendor that posts signed webhooks, an app with a queue worker and three model calls per record, filed artifacts in a database plus a page on disk.

## Phase 1: Grill (writes `decisions.md`)

Walk `references/grill-checklist.md` with whoever owns the integration. Eight branches; each gets a choice and a reason in the table. Two choices shape everything after:

- **Model policy.** Real provider every run, or the stand-in? Real is the point when checking the model's work; the stand-in is for pipeline bugs and for CI.
- **Capture mechanism.** The app has to send model calls to the sidecar. Three ways: base-URL config (best if the app already reads one), a request middleware that rewrites the provider host (survives rebases, catches new call sites), or patching each call site (last resort).

## Phase 2: Research the vendor (writes `vendor.md`, shapes `stub.py`)

Label every claim Confirmed, Assumed, or Unknown per `references/vendor-research.md`. Each Assumed row becomes a scenario in `stub.py` that flips the shape, and the stub default holds the assumed-correct shape. `adapter.json` `scenarios` lists the names the CLI accepts.

The stub the engine expects (see the contract): the vendor's API as your app calls it, a `GET /settings` page playing the vendor dashboard, signed webhook delivery with retries, and the `/_admin/*` endpoints the CLI drives. Start from `connectors/demo/stub.py`; change the API paths, response envelope, signature headers, and event names to match the vendor.

## Phase 3: Map the pipeline (fills `adapter.json`)

Read the app and fill:

| Field | Find it in |
| --- | --- |
| `stages` | The item table's stage column values, in pipeline order |
| `states`, `processing_state`, `filed_state`, `failed_state`, `terminal_ok_states` | The item table's state column and the transitions |
| `llm_fingerprints` | Each model call site: a substring of the request body or the start of a message. Keys become the monitor's tabs |
| `llm_call_budget`, `stage_caps_ms` | How many calls one record should cost and how long each may take |
| `users` | The seeded accounts your seed creates; the stub keys API access by `api_key` |
| `env`, `env_file`, `secret_env_keys` | How to point the app at the sidecar and the throwaway database; where the provider key lives |
| `disposable` | What reset deletes. Leave `confirmed: false` until the reset hook exists and targets only throwaway data |

## Phase 4: Build (writes `adapter.py`, `seed.py`, `corpus/`)

Write the hooks in `adapter.py`, the seed, and the corpus. The hook signatures, which verb calls each one, what it returns, and what a missing hook degrades are all in `references/adapter-contract.md`. Every hook is optional; skip one and the engine drops that feature rather than failing. Crib from `connectors/demo/adapter.py`.

If the app needs a file placed to route model calls (a provider or middleware), place it in `processes` or a `seed` step and remove it in `down`; record the original file's hash and refuse to place over a file that differs. Never commit that file to the app.

Corpus: records in the vendor's exact detail shape, plus `targets.json` with planted spans and must-not-cut names. Clean records too.

**Exit:** `up` is green and one `arrive` files a record end to end, producing every event kind a successful record should: `action.arrive`, `api.request`, `connection.changed`, `webhook.sent`, `webhook.result`, `delivery.changed`, `item.changed`, `llm.request`, `llm.response`. Then run one more real record before calling it done; per-task review does not catch a column that does not exist.

## Phase 5: Run sessions

`reset`, drive the app, watch the monitor, `scenario`, `eval`, `judge` with evidence ids, `finding`, `snapshot`. Let the user drive the app in their own browser while the agent reads the log.

## Phase 6: Feed back

Product bugs become tests in the app. Harness lessons append to `SKILL.md` under Lessons. Adapter gaps go in `connectors/<name>/README.md`. The snapshot goes to the integration's owner.

## Verifying an adapter

- `python3 -m unittest discover -s engine/tests -t .` still passes.
- `up`, `status` (all booleans true), `arrive`, `eval` (nine checks), `scenario dup` then `eval` (fails with evidence), `snapshot` (opens offline), `down` (ports free), `up` again (fresh session).
- `grep` the session folder and the CLI output for the provider key. It must not be there.
