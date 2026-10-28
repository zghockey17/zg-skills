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

As a Claude Code plugin:

```
/plugin marketplace add zghockey17/zg-skills
/plugin install deslop@zg-skills
```

Manually: clone the repo and symlink the skill into your agent's skills folder.

```
git clone https://github.com/zghockey17/zg-skills ~/zg-skills
ln -s ~/zg-skills/skills/deslop ~/.claude/skills/deslop    # Claude Code
ln -s ~/zg-skills/skills/deslop ~/.codex/skills/deslop     # Codex
```

Optional: [lizard](https://github.com/terryyin/lizard) for cyclomatic complexity (`pipx install lizard` or run it with `uvx lizard`).
Without it the skill falls back to a labeled manual estimate.

## Usage

```
/deslop review this branch against main
```

or in plain language: "deslop this diff before I open the PR", "simplify this, apply the cuts".

The report is a Before | After | Why table, a list of what was deleted, a complexity table when a number moved, and one line per surviving change on how it was proved.

## Uninstall

Plugin: `/plugin uninstall deslop@zg-skills`.
Manual: `rm ~/.claude/skills/deslop` (or the Codex symlink).

## Credits

Complexity measurement uses [lizard](https://github.com/terryyin/lizard) by Terry Yin.

## License

MIT. See `LICENSE` at the repository root.
