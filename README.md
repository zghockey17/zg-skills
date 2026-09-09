# zg-skills

Skills by Zave Greene for Claude Code. Each skill lives under `skills/<name>/` with its own `SKILL.md`, README, and tests, and is also packaged as a Claude Code plugin. This repository is the plugin marketplace.

## Skills

| Skill | What it does |
| --- | --- |
| [connector-eval-env](skills/connector-eval-env/) | See what your AI integration is doing, test failure scenarios, and inspect the evidence. A local eval environment with a live monitor page, a capture proxy for every model call, a mock vendor with named failure scenarios, rule checks with evidence, and one-file snapshots. Ships with a runnable demo. |

## Install

```
/plugin marketplace add zghockey17/zg-skills
/plugin install connector-eval-env@zg-skills
```

Or clone and symlink a skill into `~/.claude/skills/`. Each skill's README has the details, the quick start, and the uninstall steps.

## License

MIT. See [LICENSE](LICENSE).
