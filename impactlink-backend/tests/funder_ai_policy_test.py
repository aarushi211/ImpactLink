import importlib
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from services.application import normalize_spec, ai_policy_check, ensure_ai_drafting_allowed, merge_checklist, validate_review_input


def grant(status, **kwargs):
    return {'title': 'Test funder', 'application_spec': {'ai_policy': {'status': status, **kwargs}}}


class PolicyTests(unittest.TestCase):
    def test_legacy_requirements_remain_unknown_and_are_not_assumed_permitted(self):
        self.assertEqual(normalize_spec({})['ai_policy']['status'], 'unknown')
        check = ai_policy_check({})
        self.assertEqual(check['verification'], 'not_verified')
        self.assertFalse(check['disclosure_pending'])
        ensure_ai_drafting_allowed({})

    def test_only_prohibited_policy_blocks_drafting(self):
        for status in ('unknown', 'permitted', 'disclosure_required'):
            ensure_ai_drafting_allowed(grant(status))
        with self.assertRaisesRegex(ValueError, 'prohibits AI use'):
            ensure_ai_drafting_allowed(grant('prohibited'))
        for policy in ({'status': 'invented'}, {'disclosure_ready': 'false'}, {'status': 'permitted', 'unrecognized': True}):
            with self.assertRaises(ValueError):
                normalize_spec({'ai_policy': policy})

    def test_disclosure_completion_preserves_source_and_never_changes_permission(self):
        original = grant('disclosure_required', source_reference='RFP page 8', notes='Disclose in cover letter')
        updated = merge_checklist(original, {'ai_disclosure_ready': True})
        self.assertFalse(ai_policy_check(updated)['disclosure_pending'])
        self.assertTrue(ai_policy_check(original)['disclosure_pending'])
        self.assertEqual(updated['application_spec']['ai_policy']['source_reference'], 'RFP page 8')
        self.assertEqual(updated['application_spec']['ai_policy']['notes'], 'Disclose in cover letter')
        self.assertEqual(ai_policy_check(merge_checklist(grant('prohibited'), {'ai_disclosure_ready': True}))['status'], 'prohibited')

    def test_disclosure_blocks_final_completion_but_allows_draft_review_and_saving(self):
        state = {'gate': 'draft_review', 'grant': grant('disclosure_required'), 'sections': {'summary': {'content': 'Confirmed text'}}}
        validate_review_input(state, {})
        state['gate'] = 'final_save'
        with self.assertRaisesRegex(ValueError, 'required AI disclosure'):
            validate_review_input(state, {})
        validate_review_input(state, {'ai_disclosure_ready': True})
        for invalid in ('true', 1, {}):
            with self.assertRaises(ValueError):
                merge_checklist(state['grant'], {'ai_disclosure_ready': invalid})


class PolicyEndpointTests(unittest.TestCase):
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

    def test_both_creation_flows_reject_prohibited_policy_before_graph_or_ai(self):
        with patch.object(self.sessions, '_graph_for') as graph:
            for flow in ('scratch', 'improve'):
                response = self.client.post('/api/session', json={'flow': flow, 'profile': {'org_name': 'Test'}, 'grant': grant('prohibited')})
                self.assertEqual(response.status_code, 400)
                self.assertIn('prohibits AI use', response.text)
            graph.assert_not_called()

    def test_standalone_revision_rejects_prohibited_policy_before_model(self):
        with patch('agents.rewriter_agent.retry_rewrite') as rewrite:
            response = self.client.post('/api/build/revise', json={'current_draft': 'Original text', 'feedback': 'Improve it', 'application_spec': grant('prohibited')['application_spec']})
            self.assertEqual(response.status_code, 422)
            rewrite.assert_not_called()

    def test_sync_and_stream_resume_use_saved_policy_not_client_override(self):
        state = {'flow': 'scratch', 'gate': 'slot_confirm', 'user_id': 'test-user', 'grant': grant('prohibited')}
        with patch.object(self.sessions, '_get_graph_state', return_value=state), patch.object(self.sessions, '_graph_for') as graph:
            body = {'confirmed': True, 'application_spec': grant('permitted')['application_spec']}
            response = self.client.post('/api/session/test/advance', json=body)
            self.assertEqual(response.status_code, 422)
            stream = self.client.post('/api/session/test/advance/stream', json=body)
            self.assertIn('prohibits AI use', stream.text)
            self.assertIn('"type": "error"', stream.text)
            graph.assert_not_called()

    def test_disclosure_error_preserves_real_checkpoint_until_ready_then_saves_policy(self):
        from langgraph.graph import StateGraph, START, END
        from langgraph.checkpoint.memory import InMemorySaver
        from flows.scratch_flow import node_final_save, ProposalState

        builder = StateGraph(ProposalState)
        builder.add_node('final_save', node_final_save)
        builder.add_edge(START, 'final_save')
        builder.add_edge('final_save', END)
        graph = builder.compile(checkpointer=InMemorySaver())
        config = {'configurable': {'thread_id': 'policy-check'}}
        graph.invoke({'session_id': 'policy-check', 'flow': 'scratch', 'gate': 'final_save', 'user_id': 'test-user', 'grant': grant('disclosure_required', source_reference='RFP page 8'), 'sections': {'summary': {'content': 'Reviewed text'}}}, config)
        with patch.object(self.sessions, '_get_graph_state', side_effect=lambda *a: graph.get_state(config).values), patch.object(self.sessions, '_graph_for', return_value=graph):
            rejected = self.client.post('/api/session/policy-check/advance', json={})
            self.assertEqual(rejected.status_code, 422)
            self.assertTrue(graph.get_state(config).tasks[0].interrupts)
            completed = self.client.post('/api/session/policy-check/advance', json={'ai_disclosure_ready': True})
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()['gate'], 'complete')
        self.assertTrue(graph.get_state(config).values['grant']['application_spec']['ai_policy']['disclosure_ready'])
        self.assertEqual(completed.json()['application_spec']['ai_policy']['source_reference'], 'RFP page 8')


if __name__ == '__main__':
    unittest.main()
