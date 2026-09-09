# demo adapter decisions

| # | Branch | Choice | Why |
| --- | --- | --- | --- |
| 1 | Monitor scope | App and monitor in the browser, agent in the terminal | Same shape as a real session |
| 2 | Model policy | Local deterministic stand-in | Zero cost, nothing leaves the machine, same output every run |
| 3 | Corpus policy | Three tiny records authored upfront | Enough for one clean, one planted, one dup-scenario run |
| 4 | Realism | Real signed webhooks with retries; the app registers its own webhook via the vendor API | Rehearses the connect step and signature verification |
| 5 | Control surface | Terminal only; the pages are observation and product surfaces | Keeps the monitor read-only |
| 6 | Reset semantics | Clean slate: new session folder, old app state deleted | Simplest correct behavior |
| 7 | Capture mechanism | App reads its model base URL from the environment; the engine sets it to the sidecar | No app patching needed |
| 8 | Users | Two seeded vendor accounts | Exercises account selection on `arrive --account` |
| 9 | Scenarios | Named set: dup, out-of-order, slow-fetch, retry-500, stale-sig, revoke-key | One per common vendor failure |
| 10 | Sharing | Frozen self-contained snapshot | Opens anywhere |
| 11 | Where outcomes land | The session folder | No external writes |

Judge policy: the person or agent running the session grades with `judge`, citing event ids.
