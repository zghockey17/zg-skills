---
name: pr-explainer
description: Explain one or more pull requests in plain English for a reviewer who never saw the code. Use when writing a PR description, drafting a review request or team announcement for shipped PRs, or when the user says "write the PR summary", "explain this PR", or "how do I announce these PRs".
license: MIT
metadata:
  author: Zave Greene
  version: "1.0.0"
---

# PR Explainer

The explainer is the message that hands a PR to its reviewer.
It is written for a **cold reader**: someone smart who has not seen the code, the ticket, or the chat that produced it.
It says what changed, why, where the risk sits, and how the author knows it works, with evidence a skeptic would accept.

## Steps

### 1. Pick the mode

Settle two things from the request:

- **Destination.** *PR body* (lives on the PR, read by a reviewer opening it) or *message* (chat, email, or channel post announcing the PR to a reviewer or team).
- **Count.** One PR, or several shipped together.

If the request does not say, a request made inside a branch with an open or about-to-open PR is a PR body; a request that mentions a channel, a team, or several PRs is a message.

**Done when:** you can name the destination and the list of PRs (number or branch for each).

### 2. Read the change

For each PR, read the real material, not a summary of it:

- The diff. `gh pr diff <n>` and `gh pr view <n>` when the GitHub CLI is available; otherwise `git diff <base>...<head>` and `git log <base>..<head>`, or `git show <sha>` for a single commit.
- Commit messages and the linked issue or ticket, if any.
- The tests the PR adds or changes, and the code paths they exercise.

From that, write down in your own notes:

1. The change in one sentence.
2. The **cause** of the problem: the mechanism that made the old behavior wrong, not just the symptom a user saw. If a reviewer would ask "but why did that happen," you have the symptom.
3. How the fix removes that cause.
4. Who or what is affected after merge: users, data, other services, deploy steps.
5. The 2 to 4 places in the diff where a reviewer's attention pays off most (see Where to look below).

**Done when:** all five notes exist for every PR, each traceable to a line in the diff, a commit, or the ticket.

### 3. Collect the evidence

Verification is something someone ran and observed.
For each PR, list every piece of evidence you can find, with its numbers:

- Test runs: which suite, how many tests, pass or fail. Prefer output you can see (CI logs, a run you perform now, a pasted terminal result) over a claim that tests pass.
- Manual checks: what was clicked, run, or queried, against what data, and what was observed.
- Before and after: a failing reproduction that now passes, a screenshot, a query result, a timing.
- Fault checks: a test that was shown to fail when the bug was put back, which proves the test can catch it.
- An evidence file (test report, eval manifest, benchmark output): cite its counts verbatim. Do not round or re-derive them.

When you can run a check cheaply and safely (the project's test command, a reproduction script), run it and report what you saw.
Label evidence you did not observe yourself: "Reported by the author, not re-run here: ...". A reviewer weighs a re-run differently from a claim in a commit message.
When evidence is missing, ask the author what they ran, or state the gap plainly in the explainer ("not load-tested; confidence at high traffic is judgment, not measurement").
A number that is unknown stays unknown. Write `N` and flag it rather than estimating.

**Done when:** every PR has at least one piece of observed evidence with a count or a concrete observation, or the explainer will say in plain words that it has none.

### 4. Write it

Use the format below.
Read `references/examples.md` before the first draft; it has a PR body and a multi-PR message to match.

**Done when:** every part of the format is present for every PR, and the ending follows the destination adjustments in The format: a message ends on the readiness line; a PR body ends on the verification list unless the PR is a draft or has a deploy step, in which case it ends on the readiness line.

### 5. Read it back cold

Reread the draft as the cold reader and fix each failure:

- Every term a newcomer would not know is either replaced with plain words or defined in the same sentence.
- Every quality claim is a count or an observation, never an adjective.
- Every claim is as narrow as its evidence (see Claims discipline).
- Changes this PR caused, problems it fixed, and problems it only found are kept separate.
- Sentences are short and the answer comes first.

**Done when:** a reader who saw none of the code could explain back what the PR does, why it was needed, and what proves it works.

## The format

**Opening line.** What the PR (or set of PRs) does in one or two sentences, with the status of each: draft, ready for review, or merged. For several PRs, describe what they do together.

Then, for each PR, these five labeled parts in order:

- **What it is.** One sentence. The change in plain terms.
- **Problem.** The cause of what was wrong or missing. For a new feature, the gap it fills and who felt it. For a cleanup or refactor, the concrete cost of leaving the code as it was.
- **How it fixes it.** The mechanism in plain terms. When true, say **"No action needed from users"** explicitly; that one sentence lets a busy reviewer stop worrying about blast radius. When not true, say exactly what action is needed and by whom.
- **Where to look.** 2 to 4 bullets, each naming a file, function, or area and saying why it deserves attention.
- **How it was verified.** A numbered list, strongest evidence first, with real counts and observations.

**Close with the readiness line.** One calm sentence that says the work is ready for review (or what it is waiting on). Address the team or whoever picks it up, not a named individual. If a post-merge or post-deploy step exists, include the exact command as information. The readiness line is the last sentence.

Destination adjustments:

- **PR body:** use Markdown headings for the five parts. The opening line becomes a short summary paragraph. Keep the readiness line only if the PR is a draft or has a deploy step; otherwise end on the verification list.
- **Message:** use bold labels, not headings, so it reads well in chat or email. Keep each PR to a short block a reviewer can read on a phone.

## Where to look

Pick the parts of the diff where a reviewer's judgment matters, not the parts that are large.
Good picks, roughly in priority order:

1. The line or function that actually changes behavior (often small inside a large diff).
2. Anything that touches data that already exists: migrations, file moves, format changes, deletes.
3. Boundaries: auth and permission checks, input validation, error handling, external calls.
4. A decision the author made that a reviewer might reasonably make differently. Name the alternative and why it lost.

Say what can be skimmed too: "The 30 renamed imports in `src/` are mechanical."

## Claims discipline

Phrase every claim as narrowly as the evidence supports. This is what survives a skeptical reviewer.

| Broad claim | Narrow claim the evidence actually supports |
| --- | --- |
| "Tests pass." | "All 214 unit tests pass; the 3 new ones fail on `main` and pass on this branch." |
| "Backward compatible." | "All 1,200 existing records in the staging copy load unchanged through the real read path." |
| "Auth is tested." | "A signed-in user cannot read another user's files through these 4 endpoints; 8 checks cover it." |
| "Faster." | "p95 page load went from 2.4 s to 0.9 s on 50 runs against the staging dataset." |

**Separate caused, fixed, and found.** "This PR fixes X" is a different claim from "this PR did not introduce Y; Y predates it and is tracked in #123." Keep the reviewer clear on which conditions the PR caused, which it fixed, and which it only uncovered.

## Style

- Plain English. Define a technical term in the same sentence the first time it appears, or replace it.
- Numbers over adjectives. "Thoroughly tested" is not evidence.
- Short sentences, active voice, answer first. Tables only when comparing.
- Write the author's facts, not the tool's: no AI attribution, no filler ("seamless", "robust", "it's worth noting"), no em dashes.
