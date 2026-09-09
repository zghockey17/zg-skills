# Grill checklist

The phase 1 question tree. Walk every branch before building an adapter. No branch is silently assumed: each one lands in the adapter's `decisions.md` with its chosen option and reason.

These are the branches that change an adapter's implementation. Three questions the shipped design already settles are not asked: the monitor stays read-only and the terminal drives, sharing is a frozen self-contained HTML snapshot, and one session log carries everything.

| # | Branch | Options to offer | What the choice decides |
| --- | --- | --- | --- |
| 1 | Model policy | real provider every run, local stand-in, scripted fixed responses | Whether model quality is under test, and what a run costs |
| 2 | Corpus policy | author all upfront, reuse a reviewed set first, author live on request | How many records exist before the first session |
| 3 | Realism (webhook path) | app-side simulation, real signed webhooks from the stub, skip webhooks | Whether the connect step and signature verification get rehearsed |
| 4 | Reset semantics | clean slate every session, incremental, snapshot-restore | What `reset` deletes and how the app is re-entered |
| 5 | Capture mechanism | patch each model call site, base-URL config, request middleware proxy | How model calls reach the sidecar and what the app carries |
| 6 | Users | one seeded user, two seeded users, real accounts | Per-user settings coverage and login path |
| 7 | Scenarios | happy path only, a named failure set, ad hoc | Which vendor assumptions get a scenario |
| 8 | Where outcomes land | memory or wiki writes, ticket tracker, local session folder | Where findings and lessons go |

Judge policy is settled alongside these branches: who grades a run, from what evidence, and where verdicts are written. Grading a model with the same model is circular; the default is a person or a different agent reading the captured prompt, response, and diff, writing verdicts as `eval.judge` events that cite evidence ids.

Exit criterion: `decisions.md` records a chosen option and reason for every branch.
