# zg-skills

The agent skills I use every day to build, made general purpose so you can use them too.
Each skill lives under `skills/<name>/` with its own `SKILL.md` and README, and each one is also a Claude Code plugin. This repository is the plugin marketplace.

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

In Claude Code:

```
/plugin marketplace add zghockey17/zg-skills
/plugin install <skill>@zg-skills
```

Any other agent that reads `SKILL.md` files (Codex and others): clone this repo and symlink `skills/<skill>` into the agent's skills folder, for example `~/.codex/skills/`.

Not sure which to try? Paste this into your agent:

```
Read https://github.com/zghockey17/zg-skills and each skill's SKILL.md. Based on how I work in this repo and my recent sessions, recommend the two or three skills that would help me most, say why in one line each, and offer to install them.
```

## License

MIT. See [LICENSE](LICENSE).
