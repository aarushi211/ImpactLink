import unittest
import os
import importlib
from unittest.mock import MagicMock, patch
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import AIMessage
from agents import gap_analysis_agent
from agents.slot_extractor import initial_slots, next_question, slots_to_profile, apply_extractions
from services.application_extraction import extract_application_setup, ExtractedSetup
from fastapi.testclient import TestClient


class SetupTests(unittest.TestCase):
    def extract(self, source, draft):
        model = MagicMock()
        model.with_structured_output.return_value = RunnableLambda(lambda _: ExtractedSetup.model_validate(draft))
        with patch('services.application_extraction.get_chat_model', return_value=model):
            return extract_application_setup({'description': source, 'source_url': 'https://example.test/rfp'})

    def test_only_source_supported_requirements_are_prefilled_and_limits_require_units(self):
        result = self.extract('Describe the need in 100 words. Attach a board list.', {
            'sections': [{'key': 'need', 'title': 'Need', 'evidence': 'Describe the need in 100 words.', 'max_words': 100},
                         {'key': 'invented', 'title': 'Invented', 'evidence': 'Submit a sustainability plan.'}],
            'attachments': [{'id': 'board', 'title': 'Board list', 'evidence': 'Attach a board list.', 'status': 'ready'}],
        })
        spec = result['application_spec']
        self.assertEqual([item['key'] for item in spec['sections']], ['need'])
        self.assertEqual(spec['sections'][0]['max_words'], 100)
        self.assertEqual(spec['sections'][0]['instructions'], 'Describe the need in 100 words.')
        self.assertEqual(spec['attachments'][0]['status'], 'not_started')
        self.assertTrue(result['requires_review'])

    def test_absent_policy_stage_and_limits_remain_unknown_not_invented(self):
        result = self.extract('Explain the project.', {'stage': 'loi', 'stage_evidence': 'LOI first', 'sections': [{'key': 'project', 'title': 'Project', 'evidence': 'Explain the project.', 'max_words': 250}], 'ai_policy': {'status': 'permitted', 'disclosure_ready': True}, 'policy_evidence': 'AI is permitted.'})
        spec = result['application_spec']
        self.assertEqual(spec['stage'], 'full_proposal')
        self.assertEqual(spec['ai_policy']['status'], 'unknown')
        self.assertFalse(spec['ai_policy']['disclosure_ready'])
        self.assertIsNone(spec['sections'][0]['max_words'])

    def test_empty_source_and_recorded_setup_do_not_need_ai(self):
        with patch('services.application_extraction.get_chat_model') as model:
            empty = extract_application_setup({})
            recorded = extract_application_setup({'application_spec': {'stage': 'loi'}})
        self.assertEqual(empty['application_spec']['sections'], [])
        self.assertEqual(recorded['application_spec']['stage'], 'loi')
        model.assert_not_called()

    def test_oversized_source_is_not_silently_truncated(self):
        with patch('services.application_extraction.get_chat_model') as model:
            with self.assertRaises(ValueError):
                extract_application_setup({'description': 'x' * 60001})
        model.assert_not_called()

    def test_funder_questions_drive_interview_order_and_answers_reach_drafting_profile(self):
        grant = {'application_spec': {'sections': [
            {'key': 'timeline', 'title': 'Work plan', 'instructions': 'Describe milestones and dates.', 'max_words': 120},
            {'key': 'evidence', 'title': 'Evidence', 'instructions': 'What evidence supports the need?'}]}}
        slots = initial_slots({'org_name': 'Example', 'mission': 'Restore habitat'}, grant)
        key, question = next_question(slots)
        self.assertEqual(key, 'application_timeline')
        self.assertIn('Describe milestones and dates.', question)
        self.assertIn('120 words', question)
        slots = apply_extractions(slots, {key: 'January outreach; June planting.'}, key)
        self.assertEqual(next_question(slots)[0], 'application_evidence')
        self.assertEqual(slots_to_profile(slots)['application_answers']['timeline']['answer'], 'January outreach; June planting.')

    def test_general_interview_still_available_when_no_questions_are_recorded(self):
        self.assertEqual(next_question(initial_slots({'org_name': 'Example', 'mission': 'Mission'}))[0], 'problem')

    def test_gap_analysis_receives_exact_custom_instructions_and_late_grant_text(self):
        seen = []
        def reply(prompt):
            seen.append(prompt.to_string())
            return AIMessage(content='{"missing_content": [], "weak_evidence": [], "wrong_vocabulary": [], "misalignment": [], "sections_to_rewrite": []}')
        grant = {'description': 'Background. ' * 300 + 'Final important requirement.', 'application_spec': {'sections': [{'key': 'timeline', 'title': 'Work plan', 'instructions': 'Include named milestone owners.', 'max_words': 120}]}}
        with patch.object(gap_analysis_agent, '_get_llm', return_value=RunnableLambda(reply)):
            gap_analysis_agent.analyze_gaps({'proposal': 'Existing project'}, grant, [])
        self.assertIn('Include named milestone owners.', seen[0])
        self.assertIn('Final important requirement.', seen[0])


class SetupEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://test:test@localhost:1/test', 'FIREBASE_STORAGE_BUCKET': 'test-not-network', 'OPENAI_API_KEY': 'test-key-not-network'}), patch('firebase_admin.initialize_app'), patch('psycopg_pool.ConnectionPool.connection'), patch('langgraph.checkpoint.postgres.PostgresSaver.setup'):
            cls.backend = importlib.import_module('main')

    def setUp(self):
        async def account():
            yield 'test-user'
        self.backend.app.dependency_overrides[self.backend.verify_ai_user] = account
        self.client = TestClient(self.backend.app)

    def tearDown(self):
        self.client.close()
        self.backend.app.dependency_overrides.clear()

    def test_prefill_reads_selected_grant_from_database_instead_of_request_text(self):
        grant = {'grant_id': 'g1', 'description': 'Actual database instructions'}
        with patch.object(self.backend, 'get_grant_by_id', return_value=grant) as lookup, patch.object(self.backend, 'extract_application_setup', return_value={'requires_review': True}) as extract:
            response = self.client.post('/api/grants/g1/application-requirements', json={'description': 'Client replacement'})
        self.assertEqual(response.status_code, 200)
        lookup.assert_called_once_with('g1')
        extract.assert_called_once_with(grant)

    def test_missing_grant_does_not_call_extractor(self):
        with patch.object(self.backend, 'get_grant_by_id', return_value=None), patch.object(self.backend, 'extract_application_setup') as extract:
            response = self.client.post('/api/grants/missing/application-requirements')
        self.assertEqual(response.status_code, 404)
        extract.assert_not_called()

    def test_prefill_requires_authentication_before_database_or_ai(self):
        self.backend.app.dependency_overrides.clear()
        with patch.object(self.backend, 'get_grant_by_id') as lookup:
            response = self.client.post('/api/grants/g1/application-requirements')
        self.assertIn(response.status_code, (401, 403))
        lookup.assert_not_called()

    def test_upload_parses_without_matching_until_a_separate_request(self):
        with patch.object(self.backend, 'parse_proposal', return_value={'raw_text': 'Uploaded proposal text'}), patch.object(self.backend, 'get_profile', return_value={'applicant_type': 'nonprofit', 'project_states': ['CA']}), patch.object(self.backend.storage, 'bucket'), patch.object(self.backend, 'find_similar_grants') as matcher:
            response = self.client.post('/api/upload', files={'file': ('Project.pdf', b'synthetic upload', 'application/pdf')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['matches'], [])
        self.assertEqual(response.json()['proposal']['raw_text'], 'Uploaded proposal text')
        matcher.assert_not_called()


if __name__ == '__main__':
    unittest.main()
