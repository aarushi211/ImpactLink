import unittest

from utils.diff import (
    diff_sections,
    normalize_numbered_headings,
    normalize_section_headings,
    word_diff,
)


class WordDiffTests(unittest.TestCase):
    def test_preserves_whitespace_and_paragraphs(self):
        original = "First paragraph.\n\nSecond paragraph.\n"
        revised = "First revised paragraph.\n\nSecond paragraph.\n"
        tokens = word_diff(original, revised)

        reconstructed_original = "".join(
            token["text"] for token in tokens if token["type"] in ("equal", "remove")
        )
        reconstructed_revised = "".join(
            token["text"] for token in tokens if token["type"] in ("equal", "add")
        )

        self.assertEqual(reconstructed_original, original)
        self.assertEqual(reconstructed_revised, revised)

    def test_keeps_unchanged_sections_in_full_diff(self):
        text = "Unchanged section.\n\nSecond paragraph."
        diffs = diff_sections(
            {"summary": text, "evaluation": "Old wording."},
            {"summary": text, "evaluation": "Updated wording."},
        )

        self.assertEqual(diffs["summary"], [{"type": "equal", "text": text}])
        self.assertTrue(any(token["type"] == "add" for token in diffs["evaluation"]))
        self.assertTrue(any(token["type"] == "remove" for token in diffs["evaluation"]))

    def test_renumbers_numbered_markdown_headings_without_gaps(self):
        content = "## 01 Executive Summary\nText.\n\n## 03 Project Design\nMore text."
        self.assertEqual(
            normalize_numbered_headings(content),
            "## 01 Executive Summary\nText.\n\n## 02 Project Design\nMore text.",
        )

    def test_numbers_unnumbered_and_unchanged_sections_in_document_order(self):
        sections = {
            "summary": {"content": "## 01 Executive Summary\nText."},
            "design": {"content": "## 03 Project Design\nMore text."},
            "evaluation": {"content": "## Evaluation Plan\nMeasures."},
        }

        normalized = normalize_section_headings(sections)

        self.assertIn("## 01 Executive Summary", normalized["summary"]["content"])
        self.assertIn("## 02 Project Design", normalized["design"]["content"])
        self.assertIn("## 03 Evaluation Plan", normalized["evaluation"]["content"])


if __name__ == "__main__":
    unittest.main()
