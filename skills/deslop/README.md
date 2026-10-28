# deslop

A delete-first review of a diff, run before a human reviews it or a pull request opens.
Agents (and people) tend to ship more structure than the request needed: an abstraction with one caller, an options object nobody passes, a state enum where one boolean would do, a guard a later guard already covers, a comment explaining complexity the change itself introduced.
`deslop` reads the diff looking for what to delete, names the smaller form and the check it must still pass, measures complexity on changed functions, and proves surviving changes in the real flow rather than from screenshots.
It optimizes for the least new structure, not the fewest lines.

## When to use it

- A diff is ready for review, or a pull request is about to open.
- An agent reports a build done and you want a second read before trusting it.
- You suspect a change is over-built: "is this too complex?"

By default it reviews and proposes without editing files.
Ask it to apply or simplify and it makes the cuts, verifying after each one.

## Install

`deslop` ships in the `zg` plugin with the rest of zg-skills. Pick one route per agent; mixing them installs every skill twice.

```
# Claude Code
claude plugin install zg --marketplace zghockey17/zg-skills

# Codex
codex plugin marketplace add zghockey17/zg-skills && codex plugin add zg@zg-skills

# Any agent that reads SKILL.md files (Cursor, Copilot, OpenCode, and others)
npx skills@latest add zghockey17/zg-skills -g -s deslop
```

In Claude Code the skill is `/zg:deslop`. Inside a session, `/plugin install zg --marketplace zghockey17/zg-skills` does the same as the first command.

## Usage

```
/deslop review this branch against main
```

or in plain language: "deslop this diff before I open the PR", "simplify this, apply the cuts".

The report is a Before | After | Why table, a list of what was deleted, a complexity table when a number moved, and one line per surviving change on how it was proved.

## Uninstall

Claude Code: `claude plugin uninstall zg`. Codex: `codex plugin remove zg@zg-skills`. `npx skills`: `npx skills@latest remove deslop -g`.

## Credits

Complexity measurement uses [lizard](https://github.com/terryyin/lizard) by Terry Yin.

## License

MIT. See `LICENSE` at the repository root.
