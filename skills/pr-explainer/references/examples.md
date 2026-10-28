# Examples

Two explainers for an imagined notes app, one per destination.
The projects, numbers, and commands are illustrative; in a real explainer every number comes from the PR or its evidence, and an unknown one is written as `N`.

## Message: two PRs announced to a team

> **2 PRs, both ready for review.** Together they stop notes from going missing after save, and they make sure new notes are stored in one consistent format while every existing note keeps working.
>
> **#38: read and write notes from the same folder**
> **What it is:** saving and loading notes now both use one folder, `notes/`.
> **Problem:** notes were saved to one folder and loaded from another, so a note could be saved and then not found. The cause was two separate pieces of code that each picked the folder on their own and disagreed.
> **How it fixes it:** both now ask one function for the folder. Existing notes are moved, not copied, so no duplicates are left behind. No action needed from users.
> **Where to look:**
> - `storage/paths.py`, `notes_dir()`: the one function both sides now call. This is the actual fix.
> - `migrations/0007_move_notes.py`: moves existing files. Check that it is safe to run twice.
> - The 14 call-site edits in `api/` are mechanical and can be skimmed.
> **How it was verified:**
> 1. Ran the migration against copies of 5 real user accounts: every note opens afterward, including the one account that had notes in both folders (it now shows all 12, where before it showed 7).
> 2. 3 new tests fail on `main` and pass on this branch; the full suite of 214 tests passes.
>
> **#39: check note format when a note is saved**
> **What it is:** a new note must have a valid header (title, date, tags) before it saves.
> **Problem:** notes were saved with any header shape, so the stored data drifted into many formats over time. Nothing checked the header on the save path.
> **How it fixes it:** the check runs only where notes are saved, in 2 places. Loading never checks, so every old note still opens. A rejected save returns a corrected header, so the caller knows exactly how to fix it. No action needed from users; this affects only notes saved from now on.
> **Where to look:**
> - `notes/validate.py`: the rules. The tag rule is the strictest and the one most likely to reject real input.
> - `notes/save.py`, the 2 call sites: confirm no other save path skips the check.
> **How it was verified:**
> 1. Loaded all 3,400 existing notes across the 5 account copies; each read back byte for byte.
> 2. 22 validation tests pass. I broke the validator on purpose 4 ways (removed the date rule, allowed any tag, and so on); the tests caught 4 of 4.
> 3. Not caused by these PRs: 9 broken links inside old notes in one account predate this work and are tracked in #41.
>
> Both are ready for review. After deploy, `make verify-notes` confirms the move landed.

What it does: leads with the combined effect, gives the cause and not the symptom, says "No action needed" where true, points the reviewer at the real fix and away from mechanical edits, leads each verification list with its strongest evidence, keeps the inherited problem separate, and ends on the readiness line with the deploy command attached.

## PR body: one PR

```markdown
Caches the exchange-rate lookup for 10 minutes so checkout stops timing out when the rates service is slow. Ready for review.

## What it is
Checkout now reuses an exchange rate fetched in the last 10 minutes instead of fetching a fresh one on every page load.

## Problem
Every checkout page load called the rates service, and that service sometimes takes 8 seconds to answer. Our checkout gives up after 5 seconds, so a slow answer became a failed checkout. 41 checkouts failed this way last week (from the error dashboard).

## How it fixes it
The first lookup is stored for 10 minutes; later lookups in that window use the stored value. If the rates service fails and a stored value exists, checkout uses it rather than failing. No action needed from users.

## Where to look
- `checkout/rates.py`, `get_rate()`: the cache and the fallback. The key decision is 10 minutes; rates can move in that window. Finance confirmed in #212 that 10 minutes is acceptable for display prices.
- `checkout/tests/test_rates.py`: the slow-service test fakes a 9-second response.

## How it was verified
1. On staging with the rates service slowed to 9 seconds: 50 of 50 checkouts completed; before the change, 0 of 50 did.
2. 6 new tests pass; with the cache removed, 4 of them fail.
3. Not measured: behavior with more than one app server sharing the cache. Each server keeps its own copy today, which is safe but means up to one fetch per server per 10 minutes.
```
