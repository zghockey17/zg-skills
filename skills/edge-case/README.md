# edge-case

Tests passing does not mean the feature works. This skill makes the agent use what it just built the way a real person would, through the real interface: a browser for web apps, the shell for CLIs, raw requests for APIs, a consumer script for libraries. It lists edge cases for each surface (empty, huge, malformed, unicode, duplicate, double-click, slow network, back and refresh, permissions, narrow screens, interrupted flows), runs every one, saves evidence, fixes what is in scope, reports the rest, and re-runs the whole set to prove the fixes. Weird or confusing behavior counts as a bug, not only crashes.

## When to use it

- After building or changing a feature, before calling it done.
- When you would otherwise say "use the app and test for edge cases" or "try to break it".
- Before a demo or a release, on the flows that write data, handle auth, or take money.

## Install

`edge-case` ships in the `zg` plugin with the rest of zg-skills. Pick one route per agent; mixing them installs every skill twice.

```
# Claude Code
claude plugin install zg --marketplace zghockey17/zg-skills

# Codex
codex plugin marketplace add zghockey17/zg-skills && codex plugin add zg@zg-skills

# Any agent that reads SKILL.md files (Cursor, Copilot, OpenCode, and others)
npx skills@latest add zghockey17/zg-skills -g -s edge-case
```

In Claude Code the skill is `/zg:edge-case`. Inside a session, `/plugin install zg --marketplace zghockey17/zg-skills` does the same as the first command.

## Example

> I just added the signup form. Edge-case it.

The agent starts the dev server, signs up once, lists cases per field and flow, runs them in a browser, and returns a table like:

| # | Surface | Case | Expected | Actual | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | Signup | Double-click Submit | One account | Two accounts | `03-before.png`, `03-after.png` | fixed |
| 7 | Signup | `<img onerror>` as name | Shown as text | Script ran | `07-before.png`, `07-after.png` | fixed |
| 9 | Signup | Refresh on step 2 | Draft kept | Form cleared | `09-before.png` | reported |

## Uninstall

Claude Code: `claude plugin uninstall zg`. Codex: `codex plugin remove zg@zg-skills`. `npx skills`: `npx skills@latest remove edge-case -g`.

## License

MIT. See `LICENSE` at the repository root.
