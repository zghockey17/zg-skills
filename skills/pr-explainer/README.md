# pr-explainer

Write a pull request description, or the message that hands a PR to its reviewer, in plain English for someone who never saw the code.
Each explainer covers what the PR is, the problem it solves (the cause, not just the symptom), how it fixes it, the few places a reviewer should look, and how it was verified, with real counts and observations instead of "tests pass".
It works for one PR or several, as the PR body or as a chat, email, or channel message.
The point is a review that starts from understanding, and claims that hold up when a skeptical reviewer pushes on them.

## When to use it

- You are about to open a PR and need the description.
- You shipped one or more PRs and need to tell a reviewer or the team.
- A reviewer asked "what does this do and how do you know it works?"

## Install

`pr-explainer` ships in the `zg` plugin with the rest of zg-skills. Pick one route per agent; mixing them installs every skill twice.

```
# Claude Code
claude plugin install zg --marketplace zghockey17/zg-skills

# Codex
codex plugin marketplace add zghockey17/zg-skills && codex plugin add zg@zg-skills

# Any agent that reads SKILL.md files (Cursor, Copilot, OpenCode, and others)
npx skills@latest add zghockey17/zg-skills -g -s pr-explainer
```

In Claude Code the skill is `/zg:pr-explainer`. Inside a session, `/plugin install zg --marketplace zghockey17/zg-skills` does the same as the first command.

## Usage

In a repo with your branch checked out:

```
/pr-explainer write the PR description for this branch
```

Or describe it: "draft a message to the team announcing PRs 38 and 39", "explain this PR for a reviewer who hasn't seen it".
The agent reads the diff, commits, and tests, runs cheap checks where it can, asks you for evidence it cannot find, and writes the explainer.
`references/examples.md` shows a two-PR team message and a single PR body.

## Uninstall

Claude Code: `claude plugin uninstall zg`. Codex: `codex plugin remove zg@zg-skills`. `npx skills`: `npx skills@latest remove pr-explainer -g`.

## License

MIT. See `LICENSE` at the repository root.
