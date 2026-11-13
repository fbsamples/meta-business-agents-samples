---
name: text-stats
description: Report readability and size statistics for a text file or piped text — word/line/character counts, longest line, average sentence length, and estimated reading time. Use when asked to measure, summarize the size of, or check the readability of a document, README, changelog, or any plain-text/markdown file.
---

# Text Stats

Compute deterministic statistics for a chunk of text. Useful for checking whether
a README is getting too long, whether a commit message body is readable, or how
long a doc takes to read.

## Usage

Run the bundled script. It accepts either a file path or text on stdin.

```bash
python3 scripts/text_stats.py path/to/file.md
cat path/to/file.md | python3 scripts/text_stats.py
```

Add `--json` for machine-readable output:

```bash
python3 scripts/text_stats.py README.md --json
```

## Reporting results

Present the numbers as a short list, not a wall of prose. Lead with the two that
usually matter — word count and reading time — then mention the longest line only
if it exceeds 120 characters, since that is the common signal of an unwrapped
paragraph or a pasted URL.

If the caller asked a yes/no question ("is this README too long?"), answer it
directly first and use the statistics as support.

## Constraints

- The script reads one file at a time and refuses inputs over 10 MB.
- It makes no network calls and writes no files.
- Sentence detection is a simple `.`/`!`/`?` split, so abbreviations inflate the
  sentence count. Treat average sentence length as an approximation.
