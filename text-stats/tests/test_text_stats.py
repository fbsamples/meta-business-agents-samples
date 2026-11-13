# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import text_stats  # noqa: E402


class AnalyzeTest(unittest.TestCase):
    def test_counts_words_lines_and_sentences(self):
        stats = text_stats.analyze("Hello world. This is a test!\nSecond line?\n")
        self.assertEqual(stats["words"], 8)
        self.assertEqual(stats["lines"], 2)
        self.assertEqual(stats["sentences"], 3)

    def test_empty_input_does_not_divide_by_zero(self):
        stats = text_stats.analyze("")
        self.assertEqual(stats["words"], 0)
        self.assertEqual(stats["avg_words_per_sentence"], 0.0)
        self.assertEqual(stats["longest_line_number"], 0)

    def test_longest_line_is_located(self):
        stats = text_stats.analyze("ab\nabcdef\nabc\n")
        self.assertEqual(stats["longest_line_length"], 6)
        self.assertEqual(stats["longest_line_number"], 2)

    def test_reading_time_scales_with_word_count(self):
        stats = text_stats.analyze("word " * text_stats.WORDS_PER_MINUTE)
        self.assertEqual(stats["reading_time_minutes"], 1.0)
