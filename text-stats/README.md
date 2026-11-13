# text-stats

A minimal, dependency-free [Claude Code](https://docs.claude.com/en/docs/claude-code) skill
that reports size and readability statistics for a text file.

It is deliberately small: it exists as a reference for the skill format and as a
smoke test that skill loading, argument passing, and bundled scripts all work.

## Layout

```
text-stats/
├── SKILL.md                  # frontmatter + instructions the agent reads
├── scripts/text_stats.py     # the actual work, plain Python 3 stdlib
└── tests/test_text_stats.py  # unittest coverage for the script
```

`SKILL.md` is the only required file. Its YAML frontmatter carries two fields:

- `name` — the invocation name, matching the directory name.
- `description` — what the skill does and when to use it. This is the only part
  loaded into context up front, so it is what determines whether the agent
  reaches for the skill at all. Write it for a reader deciding "is this relevant?"

## Install

Clone the repo and symlink the skill into your skills directory:

```bash
git clone https://github.com/fbsamples/meta-business-agents-samples.git
ln -s "$PWD/meta-business-agents-samples/text-stats" ~/.claude/skills/text-stats
```

Per-project instead of per-user: symlink into `.claude/skills/` in the repo.

## Use

Ask the agent something the description covers, e.g. "how long does this README
take to read?" — or invoke it directly with `/text-stats`.

Standalone, without an agent:

```bash
python3 scripts/text_stats.py README.md
python3 scripts/text_stats.py README.md --json
cat README.md | python3 scripts/text_stats.py
```

## Test

```bash
python3 -m unittest discover -s tests -v
```

## Notes

No network access, no filesystem writes, no third-party dependencies. Input is
capped at 10 MB. Sentence splitting is a naive `.`/`!`/`?` split, so abbreviations
inflate the count.
