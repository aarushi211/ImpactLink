import io
import json
import logging
import unittest

from utils.privacy import PrivacyLogFilter, redact_text, redact_values


class RedactionTests(unittest.TestCase):
    def test_contacts_ids_and_secrets_masked_without_exposing_original_values_in_counts(self):
        source = 'Contact name: Jane Doe; email: jane@example.org; Phone: (213) 555-0199; SSN: 123-45-6789; account_number: 123456789; password: test-password'
        result = redact_text(source)
        for original in ('Jane Doe', 'jane@example.org', '213', '123-45-6789', '123456789', 'test-password'):
            self.assertNotIn(original, result.text)
            self.assertNotIn(original, json.dumps(result.counts))
        self.assertEqual(set(result.counts), {'email', 'phone', 'ssn', 'financial_id', 'name', 'secret'})

    def test_financial_calculations_dates_grant_ids_and_geography_stay_usable(self):
        source = 'Grant 190509 supports 200 youth in Los Angeles, CA. Budget $150,000; 2 staff at 0.5 FTE; fringe 20%; 2026-11-05 to 2027-11-05. Award ID grants-gov:363920.'
        self.assertEqual(redact_text(source).text, source)

    def test_patterns_are_idempotent(self):
        source = 'Full name: Jane Doe; DOB: 1990-01-02; contact_email: "jane@example.org"; EIN: 12-3456789'
        first = redact_text(source)
        second = redact_text(first.text)
        self.assertEqual(second.text, first.text)
        self.assertEqual(second.counts, {})

    def test_unformatted_labeled_identifiers_are_masked_without_masking_unlabeled_grant_numbers(self):
        result = redact_text('SSN 123456789; Phone 2135550199; grant 123456789')
        self.assertIn('[REDACTED_SSN]', result.text)
        self.assertIn('[REDACTED_PHONE]', result.text)
        self.assertIn('grant 123456789', result.text)

    def test_quoted_fields_do_not_swallow_neighboring_budget_values(self):
        source = json.dumps({'contact_name': 'Jane Doe', 'ssn': '123456789', 'annual_salary': 60000, 'months': 6})
        output = json.loads(redact_text(source).text)
        self.assertEqual(output['annual_salary'], 60000)
        self.assertEqual(output['months'], 6)
        self.assertEqual(output['contact_name'], '[REDACTED_NAME]')

    def test_nested_json_values_protected_without_changing_ids_and_property_names(self):
        value = {'grant_id': '190509', 'call_id': 'call_12345', 'args': {'ssn': 123456789, 'budget': 150000, 'email': 'jane@example.org'}}
        sanitized = redact_values(value)
        self.assertEqual(sanitized['args']['ssn'], '[REDACTED_SSN]')
        self.assertEqual(sanitized['args']['budget'], 150000)
        self.assertEqual(sanitized['grant_id'], '190509')
        self.assertEqual(value['args']['ssn'], 123456789)

    def test_long_labeled_secrets_and_escaped_quotes_are_fully_masked(self):
        secret = 'sensitive-material-' * 80
        for source in (f'client_secret: {secret}', json.dumps({'client_secret': secret, 'budget': 150000})):
            result = redact_text(source)
            self.assertNotIn('sensitive-material', result.text)
        source = json.dumps({'full_name': 'Jane "JJ" Doe', 'budget': 150000})
        output = json.loads(redact_text(source).text)
        self.assertEqual(output, {'full_name': '[REDACTED_NAME]', 'budget': 150000})

    def test_international_phones_api_tokens_and_private_keys(self):
        examples = [('+44 20 7946 0958', 'phone'), ('sk-proj-' + 'x' * 40, 'secret'), ('Bearer ' + 'x' * 30, 'secret'),
                    ('-----BEGIN PRIVATE KEY-----\nprivate-material\n-----END PRIVATE KEY-----', 'secret')]
        for source, kind in examples:
            with self.subTest(kind=kind):
                result = redact_text(source)
                self.assertEqual(result.text, f'[REDACTED_{kind.upper()}]')

    def test_local_model_detects_unlabeled_names_while_sensitive_narratives_still_need_review(self):
        text = 'Jane Doe needs confidential case support.'
        result = redact_text(text)
        self.assertNotIn('Jane Doe', result.text)
        self.assertIn('confidential case support', result.text)
        self.assertEqual(result.counts['name'], 1)

    def test_logging_filters_formatted_arguments_and_exception_text(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.addFilter(PrivacyLogFilter())
        logger = logging.Logger('privacy-test')
        logger.addHandler(handler)
        try:
            raise ValueError('Sensitive response: jane@example.org, SSN: 123-45-6789')
        except ValueError:
            logger.exception('Request failed for %s', 'jane@example.org')
        rendered = output.getvalue()
        self.assertNotIn('jane@example.org', rendered)
        self.assertNotIn('123-45-6789', rendered)
        self.assertIn('ValueError', rendered)
        self.assertIn('[REDACTED_EMAIL]', rendered)

    def test_uvicorn_access_formatter_keeps_required_fields_and_masks_private_paths(self):
        from uvicorn.logging import AccessFormatter
        record = logging.LogRecord('uvicorn.access', logging.INFO, __file__, 1,
                                   '%s - "%s %s HTTP/%s" %d',
                                   ('127.0.0.1:63147', 'POST', '/api/match?email=jane@example.org', '1.1', 200), None)
        privacy = PrivacyLogFilter()
        formatter = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False)
        # Multiple handlers may apply the same filter to the record.
        for _ in range(2):
            privacy.filter(record)
            rendered = formatter.format(record)
            self.assertEqual(len(record.args), 5)
            self.assertNotIn('jane@example.org', rendered)
            self.assertIn('[REDACTED_EMAIL]', rendered)
            self.assertIn('200 OK', rendered)

    def test_uvicorn_access_formatter_stays_safe_when_redaction_fails(self):
        from unittest.mock import patch
        from uvicorn.logging import AccessFormatter
        record = logging.LogRecord('uvicorn.access', logging.INFO, __file__, 1, '%s %s %s %s %d',
                                   ('private', 'POST', '/private', '1.1', 200), None)
        with patch('utils.privacy.redact_text', side_effect=RuntimeError('failure')):
            PrivacyLogFilter().filter(record)
        rendered = AccessFormatter('%(request_line)s %(status_code)s', use_colors=False).format(record)
        self.assertNotIn('/private', rendered)
        self.assertIn('withheld', rendered)


if __name__ == '__main__':
    unittest.main()
