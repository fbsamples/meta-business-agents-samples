#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Report size and readability statistics for a text file or stdin."""

import argparse
import json
import re
import sys

MAX_BYTES = 10 * 1024 * 1024
WORDS_PER_MINUTE = 238  # Brysbaert 2019, silent reading of non-fiction prose

WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)
SENTENCE_RE = re.compile(r"[.!?]+(?:\s|$)")


def read_input(path):
    if path is None:
        return sys.stdin.read()
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
    except OSError as exc:
        raise SystemExit(f"error: cannot read {path}: {exc.strerror}")
    if len(raw) > MAX_BYTES:
        raise SystemExit(f"error: {path} exceeds the {MAX_BYTES} byte limit")
    return raw.decode("utf-8", errors="replace")


def analyze(text):
    lines = text.splitlines()
    words = WORD_RE.findall(text)
    sentences = [s for s in SENTENCE_RE.split(text) if s.strip()]
    longest = max(lines, key=len, default="")
    return {
        "characters": len(text),
        "words": len(words),
        "lines": len(lines),
        "blank_lines": sum(1 for line in lines if not line.strip()),
        "sentences": len(sentences),
        "avg_words_per_sentence": round(len(words) / len(sentences), 1)
        if sentences
        else 0.0,
        "longest_line_length": len(longest),
        "longest_line_number": lines.index(longest) + 1 if lines else 0,
        "reading_time_minutes": round(len(words) / WORDS_PER_MINUTE, 1),
    }


def format_text(stats):
    labels = {
        "words": "Words",
        "characters": "Characters",
        "lines": "Lines",
        "blank_lines": "Blank lines",
        "sentences": "Sentences",
        "avg_words_per_sentence": "Avg words/sentence",
        "longest_line_length": "Longest line (chars)",
        "longest_line_number": "Longest line (number)",
        "reading_time_minutes": "Reading time (min)",
    }
    width = max(len(label) for label in labels.values())
    return "\n".join(f"{labels[key]:<{width}}  {stats[key]}" for key in labels)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path", nargs="?", help="file to analyze; reads stdin when omitted"
    )
    parser.add_argument(
        "--json", action="store_true", help="emit JSON instead of a table"
    )
    args = parser.parse_args(argv)

    stats = analyze(read_input(args.path))
    print(json.dumps(stats, indent=2) if args.json else format_text(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
