# Meta Business Agents Samples

Sample [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills) for coding
agents, published by Meta's Monetization Partner Engineering team.

A skill is a folder containing a `SKILL.md` file. The agent reads the skill's
`description` up front and loads the rest only when the task calls for it, so a
skill adds capability without permanently consuming context. Skills are portable
across agent harnesses that support the format.

Each directory in this repo is one self-contained, runnable skill.

## Skills

| Skill | What it does |
| --- | --- |
| [`text-stats`](./text-stats) | Reports word/line/sentence counts and reading time for a text file. A minimal reference for the skill format. |

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

Python 3.8+ for the bundled scripts. No third-party packages. Any agent that
supports the `SKILL.md` format can load these.

## Notes and limitations

These are reference samples, not production tooling. They are deliberately small
so the format stays legible. Read a skill's own README for its specific caveats.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). This repo is a one-way sync from Meta's
internal monorepo, so pull requests are imported manually rather than merged
directly on GitHub.

## License

Licensed under the Apache License 2.0. See [LICENSE](./LICENSE).
