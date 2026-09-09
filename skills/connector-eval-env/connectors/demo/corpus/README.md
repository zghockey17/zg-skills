# Demo corpus

Three fabricated recordings plus `targets.json`, the mechanical scoring key.
Each `rec_*.json` is the vendor detail envelope (`{success, data:{...}}`) with a
short speech-timed transcript. No real people; the phone numbers use the 555
reserved range and the figures are invented.

| id | title | planted categories | must_not_cut |
|---|---|---|---|
| `rec_demo_001` | Weekly sync with planted spans | contact, health | Priya, Dana, Omar |
| `rec_demo_002` | Design critique, onboarding flow | (clean) | Dana, Omar, Priya |
| `rec_demo_003` | Vendor negotiation, hosting renewal | compensation, contact | Priya, Omar |

The stand-in model cuts these spans by rule (see `../model.py`), so with the
`off` scenario every recording passes. The evals fail when the pipeline
misbehaves (the `dup` scenario), not when the model does.
