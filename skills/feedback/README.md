# feedback

Click-to-annotate review for any HTML page, and an agent that applies the notes.

Prose feedback on a rendered page loses precision ("the second card, the bit about synergy"), and editing the page yourself collides with the agent's own edits.
This skill forks the page into a feedback copy with a small annotation toolkit.
You press `A`, click elements (or drag-select a phrase first), tag each note as cut, rewrite, expand, wrong, question, or keep, and export a markdown prompt.
Paste it back and the agent finds each element in the source by its text, applies the directive, and reports what it changed.
The source page never carries the toolkit.

## When to use it

- Reviewing an HTML prototype, report, deck, or generated artifact where you can see what is wrong but describing where would take longer than fixing it.
- Handing review to someone else: they annotate the copy in a browser, send you the export, and any agent can apply it.

For a design critique you want the agent to do itself, ask for that instead; this skill carries your notes, not its opinions.

## Install

`feedback` ships in the `zg` plugin with the rest of zg-skills. Pick one route per agent; mixing them installs every skill twice.

```
# Claude Code
claude plugin install zg --marketplace zghockey17/zg-skills

# Codex
codex plugin marketplace add zghockey17/zg-skills && codex plugin add zg@zg-skills

# Any agent that reads SKILL.md files (Cursor, Copilot, OpenCode, and others)
npx skills@latest add zghockey17/zg-skills -g -s feedback
```

In Claude Code the skill is `/zg:feedback`. Inside a session, `/plugin install zg --marketplace zghockey17/zg-skills` does the same as the first command.

## Usage

```
> /feedback site/pricing.html
Forked to site/pricing.feedback.html and opened it.
Press A, click an element, type a note, save. Export Prompt, then paste it back.

> # Feedback on Pricing · 2026-10-28
> **Apply to:** `site/pricing.html`
> ...
Applied 3 of 4: Team seat cap 50 -> 25 (unverified, no plans config found),
rewrote the Pro tagline, removed the Popular ribbon. Answered the FAQ question in chat.
Delete site/pricing.feedback.html? (y/N)
```

In Claude Code the plugin namespaces it as `/zg:feedback`.
The script also runs on its own: `python3 scripts/inject.py page.html --title "Pricing v3" [--reviewer Sam]`.
The export format is documented in `references/export-format.md`.

## Uninstall

Claude Code: `claude plugin uninstall zg`. Codex: `codex plugin remove zg@zg-skills`. `npx skills`: `npx skills@latest remove feedback -g`.

## License

MIT. See `LICENSE` at the repository root.
