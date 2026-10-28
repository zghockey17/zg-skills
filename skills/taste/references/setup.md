# taste: first-run setup

Goal: turn the starter kit into the user's own taste, grounded in what they actually correct.
Paths below are relative to the skill folder unless they name the taste folder (`$TASTE_HOME`, else `~/.taste/`).

## 1. Interview, one batch

Ask these together in one message (use the host's question tool if it has one), and say any except question 4 can be skipped:

1. What do you make that gets rendered? (landing pages, slide decks, dashboards, product UI, reports)
2. Three things that bug you most in AI-built UI. Quote yourself if you can.
3. Do you have a house look? Font, colors (hex for text ink, accent, and any background, border or panel tones you know), light or dark, colors you never want.
4. For each of the nine starter principles in `assets/starter-principles.md`, keep or drop? List all nine by bold name (spacing scale, simple, text earns its place, readable floors, calm motion, quiet hover, no accent strip, small text stays human, look before you report) and ask for a keep or drop on each, so nothing is inherited by default.
5. May I scan your Claude Code and Codex session logs on this machine, read-only, for your recurring UI corrections? Quotes stay in your taste folder.

Done when every question has an answer or an explicit skip, and each of the nine starters has a keep or drop.

## 2. Mine (only on a yes to question 5)

Run from the skill folder (it covers the last 180 days by default):

```
python3 scripts/mine_corrections.py --min-sessions 2 --quotes 5
```

`--help` lists flags; pass `--claude-dir` or `--codex-dir` if the logs live elsewhere.
On a host without a shell, skip this step and say so.

For each rule listed, read its quotes, then pull the rest one rule at a time with `--only <rule> --json` so the full quote set never lands in context at once.
Keep a hit only when it is the user correcting rendered work in their own words; drop pasted briefs, agent reports, matches on unrelated meanings ("simplify the code"), and the user describing someone else's design.
Praise is not a correction: "I love the gradient" is evidence for a house default, not a principle.
When mined evidence contradicts an interview answer, the interview wins; note the conflict in the ledger.
Leave out anything legal, financial, medical, or otherwise sensitive.
For each recurring correction that matches no pattern, run again with `--rule "name=regex"` to count it.

Done when each rule has a confirmed distinct-session count and up to two short quotes with source and session id.

## 3. Write the taste folder

Create the taste folder, then write three files:

- `principles.md` from `assets/starter-principles.md`:
  - Set each starter's status: `confirmed` with 3+ confirmed sessions, else `stated` if the interview said it, else keep `starter`.
  - Delete starters the user dropped; record them under "Rejected starters" in the ledger. If the user holds the opposite view ("I like mono labels"), write that view as a `stated` house default.
  - Rewrite each tell in the user's own words where a quote gives them.
  - Add each new rule from question 2 (`stated`) or from mining with 3+ sessions (`confirmed`), same shape: bold name, status, target, tell.
  - Principles never name a color, font, or brand. Color and font likes and dislikes ("never purple") go to `house.md`, as does any rule seen on one brand or project only.
  - Remove the STARTER FILE note.
- `house.md` from `assets/house-template.md`, filled from question 3 and brand-specific mined rules; unanswered rows stay `not set`.
- `ledger.md` from `assets/ledger-template.md`: one row per rule with layer, status, sessions, last seen, and evidence; set "Last refresh" to today.

Done when all three files exist and every rule in `principles.md` has a ledger row.
Keep `principles.md` within the size ceiling in `SKILL.md`.

## 4. Show the user

Show the final `principles.md` and `house.md`, a one-line count of confirmed, stated, and starter rules, and the taste folder path.
Remind them the ledger holds quotes from their sessions and should stay private.

Done when the user has seen the files; then return to the task that triggered setup.
