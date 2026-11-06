"""Exercise the real FastAPI dependency and SSE worker without external services."""
import importlib
import os
import unittest
from unittest.mock import patch

from fastapi import Request
from fastapi.testclient import TestClient

from utils.name_detection import PrivacyDetectionUnavailable
from utils.privacy import redact_text


class RequestPrivacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {
            'DATABASE_URL': 'postgresql://test:test@localhost:1/test',
            'FIREBASE_STORAGE_BUCKET': 'test-not-network',
            'OPENAI_API_KEY': 'test-key-not-network',
        }), patch('firebase_admin.initialize_app'), patch('psycopg_pool.ConnectionPool.connection'), patch('langgraph.checkpoint.postgres.PostgresSaver.setup'):
            cls.backend = importlib.import_module('main')

    def setUp(self):
        async def account(request: Request):
            return request.headers.get('x-test-user', 'account-a')
        self.backend.app.dependency_overrides[self.backend.verify_token] = account
        self.profile = patch.object(self.backend, 'get_profile', side_effect=lambda uid: {
            'privacy_redaction_terms': ['Zyqra' if uid == 'account-a' else 'Vexqun']
        })
        self.profile.start()
        self.client = TestClient(self.backend.app)

    def tearDown(self):
        self.client.close()
        self.profile.stop()
        self.backend.app.dependency_overrides.clear()

    def test_saved_account_terms_survive_stream_response_and_worker_context(self):
        def stream(*args, **kwargs):
            # Executed after the route returns, inside the actual SSE worker.
            yield {'type': 'complete', 'response': redact_text('Zyqra and Vexqun', detect_names=False).text}
        with patch.object(self.backend, 'stream_advance_session', side_effect=stream):
            first = self.client.post('/api/session/test/advance/stream', json={}, headers={'x-test-user': 'account-a'})
            second = self.client.post('/api/session/test/advance/stream', json={}, headers={'x-test-user': 'account-b'})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertIn('[REDACTED_CUSTOM] and Vexqun', first.text)
        self.assertIn('Zyqra and [REDACTED_CUSTOM]', second.text)
        self.assertEqual(redact_text('Zyqra and Vexqun', detect_names=False).text, 'Zyqra and Vexqun')

    def test_preview_can_check_unsaved_terms_without_changing_account_policy(self):
        preview = self.client.post('/api/privacy/preview', json={'text': 'Zyqra and Vexqun', 'custom_terms': ['Vexqun']})
        self.assertEqual(preview.status_code, 200)
        self.assertNotIn('Vexqun', preview.json()['text'])
        with patch.object(self.backend, 'refine_budget', side_effect=lambda *a, **kw: {'text': redact_text('Zyqra and Vexqun', detect_names=False).text}):
            response = self.client.post('/api/budget/refine', json={'current_budget': {}, 'user_request': 'Review it'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('[REDACTED_CUSTOM] and Vexqun', response.text)

    def test_missing_settings_or_detector_blocks_ai_handler(self):
        for target, error in [('get_profile', RuntimeError('private diagnostic')), ('ensure_name_detection', PrivacyDetectionUnavailable('Local protection unavailable'))]:
            with self.subTest(target=target), patch.object(self.backend, target, side_effect=error), patch.object(self.backend, 'stream_advance_session') as ai:
                response = self.client.post('/api/session/test/advance/stream', json={})
                self.assertEqual(response.status_code, 503)
                self.assertNotIn('private diagnostic', response.text)
                ai.assert_not_called()


if __name__ == '__main__':
    unittest.main()
