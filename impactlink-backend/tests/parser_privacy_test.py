from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import unittest

from docx import Document
from services import parser


class ParserPrivacyTests(unittest.TestCase):
    def test_upload_extraction_uses_a_redacted_copy_and_preserves_original_text(self):
        document = Document()
        document.add_paragraph('Project: Youth restoration. Contact email: jane@example.org; SSN: 123-45-6789. Request $150,000.')
        data = BytesIO(); document.save(data)
        prompt, chain = MagicMock(), MagicMock()
        prompt.__or__.return_value = chain
        chain.invoke.return_value = SimpleNamespace(model_dump=lambda: {'organization_name': 'Example nonprofit', 'project_title': 'Youth restoration'})
        with patch.object(parser, 'EXTRACTION_PROMPT', prompt), patch.object(parser, '_get_llm'):
            result = parser.parse_proposal(data.getvalue(), 'proposal.docx')
        outbound = chain.invoke.call_args.args[0]['text']
        self.assertNotIn('jane@example.org', outbound)
        self.assertNotIn('123-45-6789', outbound)
        self.assertIn('$150,000', outbound)
        self.assertIn('jane@example.org', result['raw_text'])
        self.assertEqual(result['ai_privacy']['redaction_counts']['email'], 1)
        self.assertTrue(result['ai_privacy']['original_retained'])


if __name__ == '__main__':
    unittest.main()
