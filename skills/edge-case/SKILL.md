---
name: edge-case
description: Edge-case testing by using the real thing like a user after it is built. Drive the UI, run the CLI, or call the API; hunt the inputs and behaviors that break it; capture evidence for each case; fix or report; re-verify. Use when asked to "test edge cases", "use the app", "try to break it", "test it like a user", or "mimic weird human behavior", and before calling a feature done.
license: MIT
metadata:
  author: Zave Greene
  version: "1.0.0"
---

# edge-case

Use the thing you built the way a real person would, then the way a careless, impatient, or unlucky one would.
Tests passing is the starting line. The finish is a case table where every row has evidence from the running thing and a status.

Run against a local, staging, or throwaway copy with disposable data.
If the only target is production or shared live data, stop and ask before running anything that writes.

## The loop

### 1. Map the surfaces

Start the real thing (dev server, built CLI, local API, imported library) and use the happy path once end to end.
List every surface a user touches: each page, form, route, command, flag, endpoint, or public function, plus the transitions between them (navigation, redirects, retries).

Done when: the happy path ran and you have a written list of surfaces.

### 2. List the cases

For each surface, pick the categories from [`references/categories.md`](references/categories.md) that fit it.
Write each case as one concrete action with an expected result: "Paste a 10,000 character name into Name, press Save; expect a length error, no crash."
Favor what a real person plausibly does over contrived inputs. Spend the most cases on the riskiest surfaces: anything that writes data, takes money, handles auth, or is new in this change.

Done when: every surface has at least one case, and the risky surfaces have one per fitting category.

### 3. Run each case against the real thing

Run every case through the same interface a user has. Pick the strongest driver available:

| Surface | Driver |
| --- | --- |
| Web UI | Playwright (script or MCP), a browser-control extension such as Claude in Chrome, or manual steps the user runs |
| CLI | the shell, with real args, stdin, pipes, and exit codes |
| API | `curl` or a short script, showing the raw request and response |
| Library | a scratch script that imports the public API as a consumer would |

Start each case from a clean state (fresh page, fresh temp directory, fresh record) so one case cannot mask another.
When no browser driver is available, write the case as numbered steps for the user and mark it `needs-manual` rather than guessing the result.
When a run suggests a case you had not listed, add it as a new row and run it.
On a large app with subagents available, give each subagent one surface and its rows, tell it to act like a real and slightly careless user, and merge their rows into one table.

Done when: every case ran, or is marked `needs-manual` with steps.

### 4. Capture evidence

Save evidence as files in one folder (for example `edge-case-evidence/`), named by case number and `before` or `after`.
Keep that folder out of version control: add it to `.gitignore`, or put it outside the repo.
Every case gets evidence from the run: a screenshot or recording for UI, the exact command and its output plus exit code for CLI, the request and response for API, the script and its output for a library.
Console errors, dialogs, and server logs count; check them on every UI case.
Prefer a measured check to eyeballing: page width greater than viewport width proves horizontal scroll, a fired dialog proves injected script ran, a non-zero exit code proves failure.
Record each case as one row:

| # | Surface | Case | Expected | Actual | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |

Status is one of `pass`, `fixed`, `reported`, `needs-manual`.
A crash, a data loss, a confusing state, a frozen spinner, a layout that breaks, or a misleading message all count as failures. Weird is a bug.

Done when: every row has evidence and a status.

### 5. Fix or report

Fix failures in scope for the change, at the cause. Add a regression test where one is cheap and the bug could plausibly return.
Report failures that are out of scope, need a product decision, or need access you lack: give the row, the evidence, and a suggested fix.

Done when: every failing row is `fixed` or `reported`.

### 6. Re-verify

Re-run the whole table through the same driver, not only the fixed rows: a fix for one case often changes how a neighboring case fails.
Keep the `before` evidence and add `after` evidence beside it, so the change is provable.

Done when: every row has `after` evidence, every `fixed` row passes, and every row that passed before still passes.

## Finish

Hand back the case table, the paths to the evidence, and a two-line summary: how many cases, how many fixed, what is still open.
The work is complete when every listed case has evidence from the running thing and a status, and every fix was re-verified.

## Credits

Builds on exploratory testing as named by Cem Kaner and taught in Elisabeth Hendrickson's *Explore It!* (https://pragprog.com/titles/ehxta/explore-it/).
