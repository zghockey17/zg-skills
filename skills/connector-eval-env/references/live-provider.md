# Running against a live model provider

The demo uses a local stand-in model so it costs nothing and sends nothing off the machine. A real adapter usually wants the real model, because checking the model's work is the point. This page is what changes.

## What the sidecar does with a real provider

The app sends its chat-completion calls to the sidecar (`ports.sidecar`). The sidecar records the request body as `llm.request`, forwards the request to `upstream` with the app's `Authorization` header, records the response body as `llm.response`, and returns the provider's status and body unchanged. Headers are never written to the log.

## Configuration

In `adapter.json`:

- `upstream`: the provider base URL. Omit it or set null for `https://api.openai.com`. Any OpenAI-compatible chat-completions endpoint works; token counts and stage names are parsed from that shape.
- `env_file`: a `.env` the engine reads at `up` and hands to child processes. Put the provider key there, under whatever name the app expects. Relative paths resolve from the adapter folder; `~` expands.
- `secret_env_keys`: the key names. The CLI scrubs their values from every printed object.

The key travels: env file, child process environment, the app's request header, the sidecar's forwarded header, the provider. It never lands in the skill folder, a session folder, `pids.json`, the event log, a snapshot, or stdout. `grep` a session for it after a run if you want to see for yourself.

`EVALENV_UPSTREAM` in the environment overrides `upstream` for one run.

## What leaves the machine

Every prompt the app builds. For a redaction pipeline that means the full un-redacted transcript goes to the provider, the same as it does in production. If the corpus were real data, the provider would see it; keep corpus content fabricated.

Nothing else leaves. The vendor stub, the app, the sidecar, and the monitor are loopback only.

## Cost

Three calls per record in the reference pipeline (redact, summarize, link). Cost scales with transcript length; a 30-record corpus of short meetings costs cents on current small models, more on large ones. `llm.response` events carry the provider's token usage, and the monitor's header sums total tokens for the session, so a run's cost is arithmetic against the provider's price list. No dollar figure is invented anywhere.

## Rate limits and failures

A provider 429 or 5xx returns to the app unchanged and is recorded in `llm.response` with `status` and `error`. The `stage_caps` check flags slow responses; the `llm_call_budget` check flags an app that retries by re-calling.

## Turning it back off

Set `upstream` to a local stand-in (the demo's `connectors/demo/model.py` serves any adapter whose prompts follow the same TRANSCRIPT line format) and remove `env_file`. Nothing else changes.
