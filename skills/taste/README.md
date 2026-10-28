# taste

A starter kit for your own taste skill.
AI agents build rendered UI that looks fine in code and wrong on screen: uneven spacing, faint tiny text, busy chrome, bouncy motion, "done" reported without anyone looking.
You correct the same things session after session.
This skill turns those corrections into written principles your agent applies before it builds, then makes it screenshot the real render and check every principle before it says done.

It ships nine generic starter principles.
On first run it interviews you, optionally mines your own Claude Code and Codex logs for the corrections you actually repeat, and rewrites the starters into your taste.
A rule earns its place with evidence from 3 distinct sessions or because you said it outright; a mined rule unseen for 90 days drops back out.

## When to use it

- Before building or editing anything rendered: pages, decks, dashboards, prototypes, product UI.
- Before reporting that rendered work is done.
- Monthly, to refresh your taste from new sessions.

## Install

As a Claude Code plugin:

```
/plugin marketplace add zghockey17/zg-skills
/plugin install taste@zg-skills
```

Manual: clone the repo and symlink the skill into your agent's skills folder.

```
git clone https://github.com/zghockey17/zg-skills ~/zg-skills
ln -s ~/zg-skills/skills/taste ~/.claude/skills/taste    # Claude Code
ln -s ~/zg-skills/skills/taste ~/.codex/skills/taste     # Codex
```

## Your files

Your taste lives outside the skill, so updates never overwrite it: `~/.taste/` by default, or `$TASTE_HOME`.

| File | What it holds |
|---|---|
| `principles.md` | Rules for every surface, each a target plus the tell that you missed it |
| `house.md` | Your font, palette, theme and motion when a project sets none |
| `ledger.md` | Evidence per rule, quoted from your sessions. Private: keep it out of public repos |

Edit any of them by hand whenever you like.

## Usage

```
> set up my taste
  (answers five questions, scans logs if you agree, writes ~/.taste/)
> build a pricing page for the app
  (applies your principles, screenshots desktop and phone, reports each check)
> refresh my taste
```

The mining script also runs on its own. It is read-only, standard-library Python, and prints to stdout:

```
python3 scripts/mine_corrections.py --help
python3 scripts/mine_corrections.py --since 2026-01-01 --quotes 2
```

Each line of output is a date, the source (`claude` or `codex`), a session id, the project, and a short quote.

## Uninstall

Plugin: `/plugin uninstall taste@zg-skills`.
Manual: remove the symlink.
Delete `~/.taste/` (or `$TASTE_HOME`) to remove your taste files.

## Credits

The starter principles draw on Anthropic's [frontend-design skill](https://github.com/anthropics/skills) and Emil Kowalski's writing on [interface motion](https://emilkowal.ski).

## License

MIT. See `LICENSE` at the repository root.
