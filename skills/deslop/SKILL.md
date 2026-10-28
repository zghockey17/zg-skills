---
name: deslop
description: Delete-first review of a diff. Use when a diff is ready for review, before a pull request opens, or after an agent reports a build done; also on "deslop", "simplify this diff", or "is this too complex". Any language, including inline scripts in HTML templates.
license: MIT
metadata:
  author: Zave Greene
  version: "1.0.0"
---

# Deslop

## Scope and mode

For a review or audit, report findings and the smallest proposed changes without editing files.
Apply changes only when the user requests implementation or simplification.
Keep this mode when handing work to another skill or agent, and preserve unrelated user changes.

The job is to delete as much of the diff as possible without violating the requested behavior.
Slop is structure the request did not need.
Optimize for the least new structure, never for fewer lines.

When the agent reviewing the diff also wrote it, or the change is large or touches risky paths (auth, data writes, migrations, money), use a second reviewer (another model or agent) if one is available.
Otherwise, or when none is available, the review proceeds without one.

## Steps

1. **Bound the diff.** Run `git diff <base>...HEAD --stat`, where `<base>` is the branch the change targets (usually `main`); add `git diff --stat` for uncommitted work. Then write the requested behavior in one sentence. Every changed file outside that sentence's causal path is a finding.
2. **Read for deletion.** For each flag in the table below, name the smaller implementation and the acceptance condition it must still meet. A guard or branch you cannot explain is not a deletion yet: find its reason first (`git log -S`, the tests, the docs), then decide.
3. **Measure.** Use the project's complexity check, or [lizard](https://github.com/terryyin/lizard) on changed functions if it is already available (`lizard`, `uvx lizard`, or `pipx run lizard`); install nothing just for a routine review. Without a tool, count decision points by hand and label the count an estimate. Any function over the project threshold (default 10) is a finding: propose splitting it into named functions, never into clever one-liners. Tool gotchas are in `references/learnings.md`.
4. **Review or apply.** In review mode, propose each cut and its acceptance check. In apply mode, make authorized cuts and run the narrowest decisive check after each one; when no test covers the behavior, a throwaway script at the boundary values counts. For UI, that is the real flow: load it, click it, read the state. A static screenshot proves layout, not behavior.
5. **Report.** A Before | After | Why table, a Deleted list, the complexity table only when a number moved, and one line on how each surviving change was proved.

Review is done when each actionable finding has evidence, a smaller proposal, and a relevant acceptance check.
Implementation is done when authorized cuts are verified and each retained flag has a reason.

## Flags

| Flag | Smaller form |
|---|---|
| Abstraction with one real use | Inline it at the call site |
| Duplicated existing capability | Call the existing thing |
| Speculative extensibility (options, enums, hooks nobody calls) | The one case that exists |
| New dependency | Existing capability, or plain code |
| File outside the causal path | Propose removing it from this patch; preserve unrelated user work |
| Comment, type, or wrapper explaining complexity the change introduced | Delete the complexity, then the explanation |
| State with values nothing reads | One boolean, or nothing |
| Guard that a later guard already covers | The later guard alone |
| Test asserting implementation detail | Assert user-visible behavior, or delete |

Comments that stay: the ones that say why, what breaks if it changes, how it scales, and where to read next.

## Red flags in your own reasoning

- "Only five lines." Five lines of dead state is still a second source of truth.
- "The screenshots look right." Layout is not behavior.
- "I'll fold the duplicates into a loop." A loop that changes scope or evaluation is a new behavior; prove it in the real flow before keeping it.
- "The metric says it is fine." Lizard scores dead code at 1.
