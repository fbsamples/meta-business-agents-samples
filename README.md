# Meta Business Agents Samples

Sample [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills) for coding
agents, published by Meta's Monetization Partner Engineering team.

A skill is a folder containing a `SKILL.md` file. The agent reads the skill's
`description` up front and loads the rest only when the task calls for it, so a
skill adds capability without permanently consuming context. Skills are portable
across agent harnesses that support the format.

The repository contains standalone skills and a larger configuration kit with bundled skills.

## Skills

| Skill | What it does |
| --- | --- |
| [`text-stats`](./text-stats) | Reports word/line/sentence counts and reading time for a text file. A minimal reference for the skill format. |
| [`mba-agent-kit`](./mba-agent-kit) | Configures and evaluates a Meta Business Agent through a CLI, with requirements and onboarding guidance. |

## Quick start

```bash
git clone https://github.com/fbsamples/meta-business-agents-samples.git
ln -s "$PWD/meta-business-agents-samples/text-stats" ~/.claude/skills/text-stats
```

Restart your agent session, then ask it something the skill's description covers —
for `text-stats`, "how long does this README take to read?"

To install a skill for one project rather than your whole account, symlink it into
`.claude/skills/` inside that project instead.

## Anatomy of a skill

```
text-stats/
├── SKILL.md                  # required: YAML frontmatter + instructions
├── scripts/text_stats.py     # optional: bundled executable code
└── tests/test_text_stats.py  # optional: tests for the bundled code
```

Only `SKILL.md` is required. Its frontmatter carries two fields:

- `name` — the invocation name, matching the directory name.
- `description` — what the skill does *and when to use it*. This is the only part
  loaded into context up front, so it alone decides whether the agent reaches for
  the skill. Write it for a reader deciding "is this relevant to my task?"

Everything below the frontmatter is instructions the agent reads once it opens the
skill. Bundled scripts keep deterministic work out of the model: the agent runs the
script instead of doing the arithmetic itself.

## Requirements

`text-stats` requires Python 3.8+ and no third-party packages. The configuration kit
requires Python 3.9+ and the dependencies listed in its [README](./mba-agent-kit/README.md).
Its assistant skills live in `mba-agent-kit/agent-guidance/`, not at the kit root.

## Notes and limitations

These are reference samples, not production tooling. They are deliberately small
so the format stays legible. Read a skill's own README for its specific caveats.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). This repo is a one-way sync from Meta's
internal monorepo, so pull requests are imported manually rather than merged
directly on GitHub.

## License

Licensed under the Apache License 2.0. See [LICENSE](./LICENSE).
