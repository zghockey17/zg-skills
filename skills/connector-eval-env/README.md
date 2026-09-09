# connector-eval-env

See what your AI integration is doing, test failure scenarios, and inspect the evidence.

You drive the app in a browser. A read-only monitor page shows every record moving through the pipeline, every model call with its prompt, response, tokens, and timing, and the redaction diff. The terminal switches failure scenarios (duplicate webhooks, stale signatures, slow or failing vendor fetches, revoked keys), scores each run against planted expectations, and freezes the whole session into one shareable HTML file.

This is a Claude Code skill. It works as a plain command-line tool too.

## What you get

| Capability | Works after install | Needs adapter work |
| --- | --- | --- |
| Live monitor with per-record timeline, model-call tabs, diff, events | yes (demo) | no |
| Capture proxy that records every OpenAI-compatible chat call | yes | point your app's model base URL at it |
| Vendor stub with signed webhooks, retries, and named failure scenarios | yes (demo vendor) | write the stub for your vendor's API shape |
| Nine rule checks with evidence event ids, judge verdicts, findings, snapshot | yes | targets for your corpus; three hooks for app-backed checks |
| Reset to a clean slate | yes (demo) | a reset hook that targets only disposable data |
| A real model provider instead of the stand-in | with a key, see `references/live-provider.md` | no |

Everything binds to 127.0.0.1. Nothing is reachable from another machine.

## Dependencies

- Python 3.10 or newer, standard library only. No pip installs.
- A browser for the monitor page and the demo app.
- `lsof` and `ps` (present on macOS and Linux). Windows is untested.
- Optional: a model provider API key for live runs. The demo needs none.

## Installation

As a Claude Code plugin (recommended):

```
/plugin marketplace add zghockey17/zg-skills
/plugin install connector-eval-env@zg-skills
```

Then invoke it as `/connector-eval-env`. Run `/reload-plugins` if the install summary asks for it.

As a personal skill, without the plugin system:

```
git clone https://github.com/zghockey17/zg-skills ~/zg-skills
ln -s ~/zg-skills/skills/connector-eval-env ~/.claude/skills/connector-eval-env
```

As a plain CLI, clone the repo and run `python3 engine/evalenv.py` from `skills/connector-eval-env/`.

Other agent hosts are not verified. The `SKILL.md` follows the Agent Skills specification, so a host that reads that format should load it, but only Claude Code has been tested.

## Quick start (the demo)

From `skills/connector-eval-env/`:

```
python3 engine/evalenv.py demo up
```

That prints three URLs. Open the **app** (`http://127.0.0.1:8227/`) and the **monitor** (`http://127.0.0.1:8230/`) in a browser. On the app page, paste the API key `demo_key_priya_0001` (also shown on the vendor page at `http://127.0.0.1:8226/settings`) and press Connect. The app registers a signed webhook with the vendor.

Now send a recording through:

```
python3 engine/evalenv.py demo arrive rec_demo_001
python3 engine/evalenv.py demo eval rec_demo_001
```

Watch the monitor: the record appears, moves through fetching, redacting, summarizing, and linking, and lands as Filed. The three model-call tabs show the exact prompt and completion; the Diff tab shows what was cut. The eval prints `"passed": 9`.

Now break it. The demo app has one planted bug: it does not deduplicate repeated webhook deliveries.

```
python3 engine/evalenv.py demo scenario dup
python3 engine/evalenv.py demo arrive rec_demo_003
python3 engine/evalenv.py demo eval rec_demo_003
```

Two checks fail, `no_duplicate_filing` and `llm_call_budget`, each with the event ids that prove it. Record it and freeze the session:

```
python3 engine/evalenv.py demo finding "Duplicate delivery files twice" --expected "one item" --actual "two items, six model calls" --repro "scenario dup; arrive rec_demo_003" --severity high
python3 engine/evalenv.py demo snapshot
python3 engine/evalenv.py demo down
```

`snapshot.html` in the session folder opens anywhere with no server. `down` stops exactly the four processes `up` started. `up` again starts a fresh session; `reset` while running does the same without leaving the app.

What is live and what is not: the vendor, the app, the webhooks, the pipeline, the capture proxy, and the evals all run live. The **model is a local deterministic stand-in** (`connectors/demo/model.py`) that redacts by rule, so the demo tests the pipeline, not model quality. Nothing leaves the machine.

## Usage

The verbs, in the order a session uses them:

| Verb | What it does |
| --- | --- |
| `up` | Start a session: stub, sidecar, the adapter's processes; seed; print URLs |
| `status` | Process liveness plus the adapter's booleans (model routed through the sidecar, storage inside the session) |
| `arrive <rec_id>` | A record appears at the vendor; webhooks fire per the scenario |
| `backfill <n>` | n records appear in the past, for the discovery path |
| `scenario <name>` | `off`, `dup`, `out-of-order`, `slow-fetch`, `retry-500`, `stale-sig`, `revoke-key` (demo set) |
| `eval [rec_id]` | Rule checks: expected spans absent, must-not-cut present, category counts, state reached, stage order, stage caps, no duplicate filing, artifacts exist, model call budget |
| `judge <rec_id> --verdict pass\|fail --reason ... [--evidence ids]` | Your verdict, citing event ids |
| `finding "<title>" --expected --actual --repro [--severity]` | A finding for the report |
| `snapshot` | `snapshot.html` and `findings.md` |
| `reset` | Clean slate, new session folder. Refuses unless the adapter declares disposable data |
| `down` | Stop the session's processes and run the adapter's cleanup hook |

Every command prints one JSON object. `grep` the session log directly: `sessions/<stamp>/events.jsonl`.

With Claude Code, describe what you want: "start the demo eval and send a recording through", "switch to the dup scenario and grade rec_demo_003", "snapshot this session". The skill's `SKILL.md` carries the process; the agent runs the verbs.

## Example configuration

`connectors/demo/adapter.json` is a complete, working configuration to read and copy. `references/adapter-contract.md` documents every field.

`upstream` is where the sidecar forwards model calls. For a real provider, set it to the provider base URL (or leave it out for `https://api.openai.com`), name an `env_file` that holds the key, and read `references/live-provider.md` first.

## Adapting it to your app

`ADAPTING.md` walks the six phases against `connectors/_template/`, a placeholder with every required file and a comment per field. The short version:

1. Copy `connectors/_template/` to `connectors/<name>/`.
2. Fill `decisions.md` and `vendor.md` (phases 1 and 2).
3. Fill `adapter.json` from your app's tables and prompts (phase 3).
4. Write `stub.py` for the vendor's API shape, `adapter.py` hooks for your app, a corpus with `targets.json`, and the one app-side change that routes model calls through the sidecar (phase 4).
5. `up`, `arrive`, `eval`, `snapshot` (phase 5).

The engine assumes a pipeline shape: a vendor delivers records, the app processes each through ordered stages with model calls, and files artifacts. If your integration looks different, the monitor and the event log still work; the rule checks may not all apply.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `port 8226 for stub is already in use` | Something else holds a demo port. `lsof -i tcp:8226` to see what; change `ports` in `adapter.json` if it is yours to keep. The engine never kills a process it did not start. |
| `up` says `already_running` | A session is live. Use it, or `down` first. |
| `/connector-eval-env` is not found | The plugin ships this one skill at its root, so some hosts expose it namespaced as `/connector-eval-env:connector-eval-env`. |
| Monitor shows "poll stale" | The `observe` hook raised or took over 3 s. `sessions/<stamp>/run/sidecar.log` has the reason. |
| A record never appears after `arrive` | The app is not connected (no webhook URL at the vendor), or the scenario rejects the delivery (`stale-sig`). The vendor page lists every delivery and its status. |
| `eval` reports `no redacted transcript captured` | The record never reached the redaction stage, or the adapter has no `transcript` hook and the poller saw no `redacted_words`. |
| `reset refused` | `disposable.confirmed` is not true or there is no reset hook. This is deliberate. |
| Events missing from the monitor after a browser reload | The page resumes from the last id it saw; hard-reload to replay from the start. |
| Leftover process after a crash | `down` reads `sessions/<stamp>/pids.json` and kills only pids whose command line still matches. If the marker no longer matches, the engine reports it under `skipped` and leaves it for you. |

Logs for every process are in `sessions/<stamp>/run/`.

## Limitations

- One worker is assumed for model-call correlation. Concurrent workers report `ambiguous` and the call is logged uncorrelated.
- The demo model is a stand-in. Nothing about model quality is being tested until you point `upstream` at a real provider.
- The capture proxy speaks the OpenAI chat-completions shape. Other provider shapes pass through but are not parsed for tokens or stage.
- The stub is a mock. Vendor behaviors you did not research (rate limits, pagination quirks) are not simulated.
- Windows is untested. The engine shells out to `ps` for process ownership checks.
- Only Claude Code has been verified as a host for the skill.

## Uninstall

Plugin: `/plugin uninstall connector-eval-env@zg-skills`, then `/plugin marketplace remove zg-skills` if nothing else uses it.

Personal skill: `rm ~/.claude/skills/connector-eval-env` (the symlink) and delete the clone.

Either way, run `python3 engine/evalenv.py demo down` first if a session is live. The skill writes only inside its own folder (`sessions/`), so deleting the folder removes everything.

## License

MIT. See `LICENSE` at the repository root.
