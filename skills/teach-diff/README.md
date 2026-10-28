# teach-diff

Turn a pull request, branch, or commit range into a lesson you can learn from in ten minutes.

The agent reads the whole diff, the commit messages, and the PR description, picks the 3 to 5 ideas that carry the change, and writes one self-contained HTML file.
Each idea gets a diagram, the real before/after lines from the diff, a plain-English walkthrough, and a multiple-choice question that explains every answer.
A required defense section covers how the change was tested, a risk table, what was deferred, the assumptions, and what was not tested, with every piece of evidence labeled as a deterministic proof, a live sample, an adversarial critique, or residual judgment.
The file has no external dependencies, so it opens offline from disk years later.

Built on Geoffrey Litt's explain-diff idea ([essay](https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck.html), [prompt](https://gist.github.com/geoffreylitt/a29df1b5f9865506e8952488eac3d524)).

## When to use it

- Before you review or merge a change you did not write.
- Before you explain or defend a change to a reviewer, a lead, or a team adopting it.
- When a stacked or sprawling PR needs a mental model before line-by-line review.

## Install

As a Claude Code plugin:

```
/plugin marketplace add zghockey17/zg-skills
/plugin install teach-diff@zg-skills
```

Manual: clone the repo and symlink the skill into your agent's skills folder.

```
git clone https://github.com/zghockey17/zg-skills ~/zg-skills
ln -s ~/zg-skills/skills/teach-diff ~/.claude/skills/teach-diff    # Claude Code
ln -s ~/zg-skills/skills/teach-diff ~/.codex/skills/teach-diff     # Codex
```

Works best with `git` and, for PR numbers, the GitHub CLI (`gh`) or GitLab CLI (`glab`). A local Chrome or Chromium lets the agent screenshot the lesson to check it renders.

## Usage

```
teach me PR 482
walk me through main...feature/retry-queue, I know Python but not Go
explain the last commit; I have to defend it to my team tomorrow
```

The agent reports the path of the HTML file, the one-sentence thesis, and the one thing to watch after the change ships.
To restyle the lesson, name your colors or fonts; the agent swaps the theme tokens in `assets/lesson-template.html` and keeps the structure.

## Uninstall

Plugin: `/plugin uninstall teach-diff@zg-skills`.
Manual: `rm ~/.claude/skills/teach-diff` (or the Codex symlink).
Lessons are plain HTML files wherever the agent saved them; delete them by hand.

## License

MIT. See `LICENSE` at the repository root.
