from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from flows import section_subgraph as sections


class SectionTokenTests(unittest.TestCase):
    def test_tokens_are_forwarded_and_complete_content_is_returned_for_scoring(self):
        chain = MagicMock()
        chain.stream.return_value = [
            SimpleNamespace(content=[{"type": "text", "text": "Hello "}, {"type": "reasoning", "text": "Private reasoning"}]),
            SimpleNamespace(content=""), SimpleNamespace(content="world"),
        ]
        prompt = MagicMock()
        prompt.__or__.return_value = chain
        tokens = []
        with patch.object(sections, "SECTION_PROMPT", prompt), \
             patch.object(sections, "_get_llm") as model, \
             patch.object(sections, "get_grant_requirement", return_value={}), \
             patch.object(sections, "format_grant_requirements", return_value=""):
            text = sections.SectionDraftAgent.draft(
                {"key": "summary", "title": "Summary", "instructions": "Write a summary", "word_target": 50},
                {}, {}, {}, "", on_token=tokens.append,
            )
        self.assertEqual(tokens, ["Hello ", "world"])
        self.assertEqual(text, "Hello world")
        model.assert_called_once_with(streaming=True)
        chain.invoke.assert_not_called()

    def test_nonstreaming_call_still_uses_invoke(self):
        chain, prompt = MagicMock(), MagicMock()
        prompt.__or__.return_value = chain
        chain.invoke.return_value.content = " Completed draft "
        with patch.object(sections, "SECTION_PROMPT", prompt), \
             patch.object(sections, "_get_llm"), \
             patch.object(sections, "get_grant_requirement", return_value={}), \
             patch.object(sections, "format_grant_requirements", return_value=""):
            text = sections.SectionDraftAgent.draft(
                {"key": "summary", "title": "Summary", "instructions": "Write", "word_target": 50}, {}, {}, {}, "",
            )
        self.assertEqual(text, "Completed draft")
        chain.stream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
