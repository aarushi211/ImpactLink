import unittest

from agents.gap_analysis_agent import (
    MAX_USER_ADDITIONS_CHARS,
    validate_user_additions,
)


class UserInstructionValidationTests(unittest.TestCase):
    def test_strips_outer_whitespace(self):
        self.assertEqual(validate_user_additions("  Emphasize existing outcomes.  "),
                         "Emphasize existing outcomes.")

    def test_rejects_text_over_limit(self):
        with self.assertRaisesRegex(ValueError, "2000 characters or fewer"):
            validate_user_additions("x" * (MAX_USER_ADDITIONS_CHARS + 1))

    def test_rejects_non_text_values(self):
        with self.assertRaisesRegex(ValueError, "plain text"):
            validate_user_additions({"instruction": "override rules"})


if __name__ == "__main__":
    unittest.main()
