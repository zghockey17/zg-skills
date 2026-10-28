# zg-skills

The agent skills I use every day to build, made general purpose so you can use them too.
Each skill lives under `skills/<name>/` with its own `SKILL.md` and README. One plugin, `zg`, installs all of them in Claude Code or Codex, and `npx skills` installs them in any other agent.

## Skills

### Engineering

| Skill | What it does |
| --- | --- |
| [deslop](skills/deslop/) | Delete-first review of a diff. Cuts the structure the request did not need before anyone reviews it. |
| [teach-diff](skills/teach-diff/) | Turns a pull request or diff into an interactive HTML lesson, with quizzes and an honest defense of how it was tested. |
| [pr-explainer](skills/pr-explainer/) | Writes the PR description in plain English: what it is, the problem, the fix, where to look, and the real evidence it works. |
| [feedback](skills/feedback/) | Click-to-annotate any HTML page, export the notes as a prompt, and have your agent apply each one. |
| [connector-eval-env](skills/connector-eval-env/) | A local eval environment for AI integrations: a live monitor of every model call, failure scenarios, rule checks, and snapshots. |

### Creativity and design

| Skill | What it does |
| --- | --- |
| [edge-case](skills/edge-case/) | Uses what you built like a real user, hunts the edge cases that break it, and proves each fix with evidence. |
| [taste](skills/taste/) | Builds your own taste skill from the UI corrections you keep making, then holds every render to it. |

## Install

One command installs every skill. Pick one route per agent; mixing them installs every skill twice.

```
# Claude Code
claude plugin install zg --marketplace zghockey17/zg-skills

# Codex
codex plugin marketplace add zghockey17/zg-skills && codex plugin add zg@zg-skills

# Any agent that reads SKILL.md files (Cursor, Copilot, OpenCode, and others)
npx skills@latest add zghockey17/zg-skills -g
```

In Claude Code the skills are namespaced by the plugin: `/zg:deslop`, `/zg:taste`, and so on. Inside a session, `/plugin install zg --marketplace zghockey17/zg-skills` does the same as the first command. To install a single skill with `npx skills`, add `-s <skill>`.

Not sure which to try? Paste this into your agent:

```
Read https://github.com/zghockey17/zg-skills and each skill's SKILL.md. Based on how I work in this repo and my recent sessions, recommend the two or three skills that would help me most, say why in one line each, and offer to install them.
```

## License

MIT. See [LICENSE](LICENSE).
