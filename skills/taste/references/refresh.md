# taste: monthly refresh

Taste is trained on what the user corrects, not on opinion.
Run this monthly, after any session with three or more UI corrections, or on "refresh my taste".
Files named here live in the taste folder (`$TASTE_HOME`, else `~/.taste/`); the script lives in this skill.

## Steps

1. **Mine.** From the skill folder run `python3 scripts/mine_corrections.py --since <ledger's "mined since" date, or 90 days ago>` with the default quote count, then pull each rule's full quote set one rule at a time with `--only <rule> --json`. Add `--rule "name=regex"` for every ledger rule without a built-in pattern so it gets counted too.
2. **Confirm.** Regex counts overcount. Read each hit in context and keep only fresh corrections in the user's own words, not pasted briefs or agent reports. Leave out anything legal, financial, medical, or otherwise sensitive.
3. **Update `ledger.md`.** New session counts, last-seen dates, at most two short quotes per rule with source and session id, and today's "Last refresh".
4. **Apply the gates.**
   - Promote: a mined rule with quotes from 3 distinct sessions enters `principles.md` if it spans unrelated projects, or `house.md` if it is tied to one brand.
   - Demote: a mined rule with no sighting in 90 days leaves `principles.md` and stays in the ledger as a candidate.
   - Cut: a rule a capable frontend agent already gets right unprompted stays in the ledger only.
   - Starters never seen in any session: list them for the user to keep or delete.
   - Stated rules stay until the user removes them.
5. **Trim.** Keep `principles.md` within the size ceiling in `SKILL.md`.
6. **Show the diff** of `principles.md` and `house.md` to the user before saving.

Done when the ledger reflects every session since the last refresh and every change to `principles.md` or `house.md` cites a ledger row.
