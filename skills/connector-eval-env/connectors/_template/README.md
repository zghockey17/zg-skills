# _template adapter

A placeholder with every file the adapter contract requires. Copy this folder
to `connectors/<name>/`, then replace each file. `ADAPTING.md` at the skill
root walks the six phases against this template; every `_about_*` key in
`adapter.json` says what a real value looks like and where the engine reads it.

| File | Replace with |
| --- | --- |
| `adapter.json` | Ports, env, users, scenarios, stages, states, model-call fingerprints, caps, disposable-data declaration |
| `adapter.py` | Hooks: how to start, seed, reset, observe, correlate, and clean up your app |
| `stub.py` | The mock vendor: its API, settings page, signed webhooks, scenarios |
| `seed.py` | The users and settings your app needs before a session |
| `corpus/` | Records in the vendor's shape plus `targets.json` with planted spans |
| `decisions.md` | The eleven grill branches, each with a choice and a reason |
| `vendor.md` | Confirmed / Assumed / Unknown claims about the vendor, one scenario per assumption |

What works before any of this is replaced: `up` starts the placeholder stub,
the sidecar, and a placeholder app process; the monitor opens; `snapshot`
writes. Nothing moves through a pipeline until `stub.py` and `adapter.py` are
real. `reset` refuses to run until `disposable.confirmed` is true and the
reset hook is written.
