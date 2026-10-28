# Learnings

Why each step exists, and tool notes. Append new lessons at the bottom.

## The baseline that justified the skill

A builder agent shipped a UI mock (Alpine.js) with a clean self-report and screenshots.
A delete-first read by a different model found: a four-value state enum where the markup read one boolean; timestamp guards that a `settled` flag and a single timer already covered; a duplicated reset; an unhandled clipboard promise; a keyboard handler at cyclomatic 13.
Lizard scored everything except the handler at 1 or 2, so the metric alone would have passed the diff.

The real bug came from step 4, not from reading.
Every tile of one type rendered as a disabled checkbox because Alpine treats `:disabled="s.locked"` as disabled when `locked` is undefined.
Static screenshots showed the tiles correctly; one click in a real browser did not toggle them.

A deletion the reviewer made (folding two duplicate template groups into a nested `x-for`) broke `x-model` scope resolution and leaked the outer loop index into another control.
It looked like a pure simplification and was reverted only because the real flow ran after the cut.
That is why step 4 says prove after every deletion and why the loop red flag exists.

## Tool notes

- macOS has no `timeout` command; run lizard directly rather than wrapping it.
- Lizard reads `.html` with `-l javascript`, but extracting the inline script to a `.js` file lists every function.
- For a diff, pass only changed files: `git diff --name-only <base>...HEAD | xargs lizard`.
