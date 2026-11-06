import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

from utils.privacy import redact_text, privacy_scope, validate_protected_terms
from utils.name_detection import PrivacyDetectionUnavailable
from services import ngo_store


class LocalProtectionTests(unittest.TestCase):
    def test_person_names_masked_without_masking_budget_or_geography(self):
        result = redact_text('Jane Doe and John Smith run volunteer training in Los Angeles, California. They request $150,000 for 20 volunteers.')
        self.assertNotIn('Jane Doe', result.text)
        self.assertNotIn('John Smith', result.text)
        for value in ('Los Angeles', 'California', '$150,000', '20 volunteers'):
            self.assertIn(value, result.text)

    def test_custom_terms_catch_unknown_identifiers_and_json_escaped_unicode(self):
        with privacy_scope(['Zyqra', 'José Li', '张伟']):
            original = 'Zyqra works with José Li and 张伟参加活动. ' + json.dumps({'name': 'José Li'}, ensure_ascii=True)
            result = redact_text(original)
            self.assertNotIn('Zyqra', result.text)
            self.assertNotIn('José Li', result.text)
            self.assertNotIn(r'Jos\u00e9', result.text)
            self.assertNotIn('张伟', result.text)
            self.assertGreaterEqual(result.counts['custom'], 4)

    def test_matching_respects_words_and_flexible_whitespace(self):
        result = redact_text('Ann uses an annual budget. Jane\nDoe reviews it.', custom_terms=['Ann', 'Jane Doe'], detect_names=False)
        self.assertIn('annual budget', result.text)
        self.assertNotIn('Jane\nDoe', result.text)
        self.assertEqual(result.counts['custom'], 2)

    def test_detector_failure_never_falls_back_to_sending_unmasked_names(self):
        with patch('utils.privacy.person_spans', side_effect=PrivacyDetectionUnavailable('Detector unavailable')):
            with self.assertRaises(PrivacyDetectionUnavailable):
                redact_text('Jane Doe requests support.')

    def test_terms_are_validated_and_deduplicated(self):
        self.assertEqual(validate_protected_terms(['Jane  Doe', 'jane doe', 'Zyqra']), ('Jane Doe', 'Zyqra'))
        for value in ('Jane Doe', [None], ['a'], ['x' * 201], ['[REDACTED_NAME]'], ['valid'] * 101):
            with self.assertRaises(ValueError):
                validate_protected_terms(value)

    def test_private_terms_are_not_published_in_collaborator_profiles(self):
        db, doc = MagicMock(), MagicMock()
        doc.to_dict.return_value = {'id': 'user-a', 'org_name': 'Example nonprofit', 'privacy_redaction_terms': ['Private person']}
        db.collection.return_value.where.return_value.stream.return_value = [doc]
        with patch.object(ngo_store, '_get_db', return_value=db):
            public = ngo_store.list_collab_profiles()
        self.assertNotIn('privacy_redaction_terms', public[0])
        self.assertEqual(public[0]['org_name'], 'Example nonprofit')


class IsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_accounts_and_worker_threads_keep_separate_lists(self):
        async def account(own, other):
            with privacy_scope([own]):
                await asyncio.sleep(0)
                return await asyncio.to_thread(redact_text, f'{own} and {other}', detect_names=False)
        first, second = await asyncio.gather(account('Zyqra', 'Vexqun'), account('Vexqun', 'Zyqra'))
        self.assertEqual(first.text, '[REDACTED_CUSTOM] and Vexqun')
        self.assertEqual(second.text, '[REDACTED_CUSTOM] and Zyqra')
        self.assertEqual(redact_text('Zyqra Vexqun', detect_names=False).text, 'Zyqra Vexqun')


if __name__ == '__main__':
    unittest.main()
