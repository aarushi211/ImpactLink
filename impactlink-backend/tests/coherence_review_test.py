import json
import unittest
import importlib
import os
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from agents import coherence_agent as agent
from agents.coherence_agent import CoherenceAgent, CoherenceReport, CoherenceIssue, review_metadata, current_review
from flows import scratch_flow
from fastapi.testclient import TestClient


ISSUE = {'section': 'summary', 'issue': 'Summary says 200 participants but delivery says 100.', 'fix': 'Confirm the actual participant count and align both sections.', 'severity': 'high'}
SECTIONS = {'summary': {'title': 'Summary', 'content': 'We serve 200 participants.'}, 'delivery': {'title': 'Delivery', 'content': 'We serve 100 participants.'}}


class CoherenceTests(unittest.TestCase):
    def model(self, response):
        return patch.object(agent, '_get_llm', return_value=RunnableLambda(lambda _: AIMessage(content=response)))

    def test_full_text_after_first_500_characters_reaches_checker(self):
        captured = []
        def reply(prompt):
            captured.append(prompt.to_string())
            return AIMessage(content=json.dumps({'coherent': False, 'issues': [ISSUE]}))
        sections = {**SECTIONS, 'delivery': {'content': 'Background information. ' * 60 + 'We serve 100 participants. END_MARKER'}}
        with patch.object(agent, '_get_llm', return_value=RunnableLambda(reply)):
            result = CoherenceAgent.check(sections, {})
        self.assertIn('END_MARKER', captured[0])
        self.assertFalse(result.coherent)
        self.assertEqual(result.status, 'completed')

    def test_invalid_or_inconsistent_ai_verdict_never_becomes_a_pass(self):
        for response in ('not json', '{"coherent":true,"issues":[' + json.dumps(ISSUE) + ']}', '{"coherent":false,"issues":[]}', '{"coherent":"true","issues":[]}', json.dumps({'coherent': False, 'issues': [{**ISSUE, 'section': 'invented'}]})):
            with self.subTest(response=response), self.model(response):
                report = CoherenceAgent.check(SECTIONS, {})
                self.assertFalse(report.coherent)
                self.assertEqual(report.status, 'unavailable')

    def test_provider_failure_is_visible_without_losing_proposal_text(self):
        with patch.object(agent, '_get_llm', side_effect=RuntimeError('private provider response')):
            report = CoherenceAgent.check(SECTIONS, {})
        self.assertEqual(report.status, 'unavailable')
        self.assertNotIn('private provider', report.reason)

    def test_oversized_empty_or_blank_proposals_do_not_call_provider_or_pass(self):
        with patch.object(agent, '_get_llm') as model:
            for sections in ({}, {'summary': {'content': ''}}, {'summary': {'content': 'x' * agent.MAX_REVIEW_CHARACTERS}}):
                report = CoherenceAgent.check(sections, {})
                self.assertEqual(report.status, 'incomplete')
                self.assertFalse(report.coherent)
            model.assert_not_called()

    def test_manual_changes_stale_report_but_approval_metadata_does_not(self):
        review = review_metadata(CoherenceReport(coherent=True), SECTIONS)
        self.assertEqual(current_review(review, {key: {**item, 'approved': True} for key, item in SECTIONS.items()})['status'], 'passed')
        self.assertEqual(current_review(review, {**SECTIONS, 'summary': {'content': 'Different text'}})['status'], 'stale')


class CoherenceFlowTests(unittest.TestCase):
    def state(self):
        return {'session_id': 'test', 'sections': SECTIONS, 'grant': {}, 'funder_vocab': [], 'agent_trace': []}

    def test_automatic_edit_is_rechecked_and_remaining_issues_are_exposed(self):
        report = CoherenceReport(coherent=False, issues=[CoherenceIssue(**ISSUE)])
        with patch.object(scratch_flow.CoherenceAgent, 'check', side_effect=[report, report]) as check, patch.object(scratch_flow, 'targeted_retry_rewrite', return_value='We serve 100 participants.'), patch.object(scratch_flow, '_progress_writer', return_value=lambda _: None):
            result = scratch_flow.node_coherence_check(self.state())
        self.assertEqual(check.call_count, 2)
        self.assertEqual(check.call_args.args[0]['summary']['content'], 'We serve 100 participants.')
        self.assertEqual(result['coherence_review']['status'], 'issues_found')
        self.assertEqual(result['coherence_review']['fixes_attempted'], 1)
        self.assertTrue(result['sections']['summary']['flagged'])
        self.assertEqual(SECTIONS['summary']['content'], 'We serve 200 participants.')

    def test_failed_edit_retains_original_and_cannot_pass_even_if_recheck_says_pass(self):
        report = CoherenceReport(coherent=False, issues=[CoherenceIssue(**ISSUE)])
        with patch.object(scratch_flow.CoherenceAgent, 'check', side_effect=[report, CoherenceReport(coherent=True)]), patch.object(scratch_flow, 'targeted_retry_rewrite', side_effect=RuntimeError('failure')), patch.object(scratch_flow, '_progress_writer', return_value=lambda _: None):
            result = scratch_flow.node_coherence_check(self.state())
        self.assertEqual(result['coherence_review']['status'], 'incomplete')
        self.assertEqual(result['sections']['summary']['content'], SECTIONS['summary']['content'])

    def test_failed_review_reaches_human_review_with_explicit_status(self):
        report = CoherenceReport(coherent=False, status='unavailable', reason='Review unavailable')
        with patch.object(scratch_flow.CoherenceAgent, 'check', return_value=report), patch.object(scratch_flow, 'targeted_retry_rewrite') as rewrite, patch.object(scratch_flow, '_progress_writer', return_value=lambda _: None):
            result = scratch_flow.node_coherence_check(self.state())
        self.assertEqual(result['gate'], 'draft_review')
        self.assertEqual(result['coherence_review']['status'], 'unavailable')
        rewrite.assert_not_called()

    def test_only_two_automatic_fixes_are_attempted_and_all_remaining_issues_remain_visible(self):
        report = CoherenceReport(coherent=False, issues=[CoherenceIssue(**{**ISSUE, 'issue': f'Contradiction {index}'}) for index in range(5)])
        with patch.object(scratch_flow.CoherenceAgent, 'check', return_value=report), patch.object(scratch_flow, 'targeted_retry_rewrite', return_value='Text to confirm') as rewrite, patch.object(scratch_flow, '_progress_writer', return_value=lambda _: None):
            result = scratch_flow.node_coherence_check(self.state())
        self.assertEqual(rewrite.call_count, 2)
        self.assertEqual(len(result['coherence_review']['issues']), 5)

    def test_review_edits_stale_metadata_without_mutating_saved_source(self):
        state = {**self.state(), 'flagged_sections': [], 'coherence_review': review_metadata(CoherenceReport(coherent=True), SECTIONS)}
        with patch.object(scratch_flow, 'interrupt', return_value={'sections': {'summary': 'Changed participants'}}):
            result = scratch_flow.node_draft_review(state)
        self.assertEqual(result['coherence_review']['status'], 'stale')
        self.assertEqual(state['sections']['summary']['content'], 'We serve 200 participants.')


class ConsistencyEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://test:test@localhost:1/test', 'FIREBASE_STORAGE_BUCKET': 'test-not-network', 'OPENAI_API_KEY': 'test-key-not-network'}), patch('firebase_admin.initialize_app'), patch('psycopg_pool.ConnectionPool.connection'), patch('langgraph.checkpoint.postgres.PostgresSaver.setup'):
            cls.backend = importlib.import_module('main')
            cls.sessions = importlib.import_module('api.session')

    def setUp(self):
        async def user():
            yield 'test-user'
        self.backend.app.dependency_overrides[self.backend.verify_ai_user] = user
        self.client = TestClient(self.backend.app)

    def tearDown(self):
        self.client.close()
        self.backend.app.dependency_overrides.clear()

    def test_recheck_endpoint_preserves_unavailable_status_and_honors_ai_prohibition(self):
        with patch.object(CoherenceAgent, 'check', return_value=CoherenceReport(coherent=False, status='unavailable')) as check:
            response = self.client.post('/api/build/check-consistency', json={'sections': SECTIONS})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['status'], 'unavailable')
            check.reset_mock()
            prohibited = self.client.post('/api/build/check-consistency', json={'sections': SECTIONS, 'application_spec': {'ai_policy': {'status': 'prohibited'}}})
            self.assertEqual(prohibited.status_code, 422)
            check.assert_not_called()

    def test_reloaded_sessions_include_recorded_review(self):
        review = review_metadata(CoherenceReport(coherent=True), SECTIONS)
        state = {'flow': 'scratch', 'gate': 'draft_review', 'user_id': 'test-user', 'sections': SECTIONS, 'coherence_review': review}
        with patch.object(self.sessions, '_graph_for') as graph:
            graph.return_value.get_state.return_value = SimpleNamespace(values=state, tasks=())
            response = self.sessions.get_session_status('test', 'test-user')
        self.assertEqual(response['coherence_review'], review)


if __name__ == '__main__':
    unittest.main()
