import json
import os
import unittest
from unittest.mock import patch

import httpx
from pydantic import BaseModel
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage
from utils.llm import InstrumentedChatOpenAI, get_chat_model
from utils.privacy import configure_privacy, privacy_scope
from utils.name_detection import PrivacyDetectionUnavailable


class Reply(BaseModel):
    answer: str


class CaptureCallback(BaseCallbackHandler):
    def __init__(self):
        self.prompts = []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.prompts.extend(message.content for batch in messages for message in batch)


def fixture(include_usage=True):
    captured = []
    def handle(request):
        payload = json.loads(request.content)
        captured.append(payload)
        if payload.get('stream'):
            chunks = [
                {'id': 'chat-test', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'privacy-test', 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': 'Safe draft'}, 'finish_reason': None}]},
                {'id': 'chat-test', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'privacy-test', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]},
            ]
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, text=''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n')
        text = json.dumps({'answer': 'Safe draft'}) if payload.get('response_format') else 'Safe draft'
        return httpx.Response(200, json={'id': 'chat-test', 'object': 'chat.completion', 'created': 1, 'model': 'privacy-test', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 13} if include_usage else None})
    sync = httpx.Client(transport=httpx.MockTransport(handle))
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    model = InstrumentedChatOpenAI(model='privacy-test', api_key='test-key-not-network', base_url='https://example.test/v1', http_client=sync, http_async_client=async_client, use_responses_api=False, cache=False, store=True)
    return model, captured, sync, async_client


SOURCE = 'Email jane@example.org; SSN 123-45-6789; grant_id 190509; requested budget 150000; California'


class ModelPrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.model, self.captured, self.sync, self.async_client = fixture()

    async def asyncTearDown(self):
        self.sync.close()
        await self.async_client.aclose()

    def assert_private(self):
        self.assertTrue(self.captured)
        for payload in self.captured:
            serialized = json.dumps(payload)
            self.assertNotIn('jane@example.org', serialized)
            self.assertNotIn('123-45-6789', serialized)
            self.assertIn('190509', serialized)
            self.assertIn('150000', serialized)
            self.assertFalse(payload['store'])

    async def test_sync_async_streaming_and_direct_message_batches_use_redacted_wire_payloads(self):
        callback = CaptureCallback()
        message = HumanMessage(content=SOURCE)
        self.assertEqual(self.model.invoke([message], config={'callbacks': [callback]}, store=True).content, 'Safe draft')
        self.assertEqual((await self.model.ainvoke([message], config={'callbacks': [callback]}, store=True)).content, 'Safe draft')
        self.assertEqual(''.join(chunk.content for chunk in self.model.stream([message], config={'callbacks': [callback]})), 'Safe draft')
        output = []
        async for chunk in self.model.astream([message], config={'callbacks': [callback]}):
            output.append(chunk.content)
        self.assertEqual(''.join(output), 'Safe draft')
        self.model.generate([[message]], callbacks=[callback])
        await self.model.agenerate([[message]], callbacks=[callback])
        self.assert_private()
        self.assertEqual(message.content, SOURCE)
        self.assertTrue(callback.prompts)
        self.assertTrue(all('jane@example.org' not in content for content in callback.prompts))

    async def test_structured_output_keeps_schema_and_returns_typed_result(self):
        reply = self.model.with_structured_output(Reply, method='json_schema').invoke(SOURCE)
        self.assertEqual(reply.answer, 'Safe draft')
        self.assertIn('answer', self.captured[0]['response_format']['json_schema']['schema']['properties'])
        self.assert_private()

    async def test_account_terms_and_unlabelled_names_are_masked_on_streamed_wire(self):
        with privacy_scope(['Zyqra']):
            async for _ in self.model.astream('Jane Doe supports Zyqra in California with a budget of 150000.'):
                pass
        payload = json.dumps(self.captured)
        self.assertNotIn('Jane Doe', payload)
        self.assertNotIn('Zyqra', payload)
        self.assertIn('California', payload)
        self.assertIn('150000', payload)

    async def test_local_detector_failure_stops_request_before_provider(self):
        with patch('utils.privacy.person_spans', side_effect=PrivacyDetectionUnavailable('Detector unavailable')):
            with self.assertRaises(PrivacyDetectionUnavailable):
                await self.model.ainvoke('Jane Doe requests support.')
        self.assertEqual(self.captured, [])

    async def test_missing_usage_metadata_does_not_discard_a_successful_response(self):
        model, captured, sync, async_client = fixture(include_usage=False)
        try:
            self.assertEqual(model.invoke(SOURCE).content, 'Safe draft')
            self.assertNotIn('jane@example.org', json.dumps(captured))
        finally:
            sync.close()
            await async_client.aclose()

    async def test_tool_history_arguments_redacted_without_corrupting_tool_ids(self):
        message = AIMessage(content='', tool_calls=[{'id': 'call_190509', 'name': 'lookup', 'args': {'email': 'jane@example.org', 'ssn': 123456789, 'budget': 150000}}])
        payload = self.model._get_request_payload([message])
        call = payload['messages'][0]['tool_calls'][0]
        self.assertEqual(call['id'], 'call_190509')
        args = json.loads(call['function']['arguments'])
        self.assertEqual(args['ssn'], '[REDACTED_SSN]')
        self.assertEqual(args['budget'], 150000)
        self.assertEqual(message.tool_calls[0]['args']['email'], 'jane@example.org')

    async def test_multimodal_and_alternate_body_bypasses_are_rejected_before_network(self):
        with self.assertRaises(ValueError):
            self.model.invoke([HumanMessage(content=[{'type': 'image_url', 'image_url': {'url': 'https://example.test/photo'}}])])
        with self.assertRaises(ValueError):
            self.model.invoke(SOURCE, extra_body={'messages': [{'role': 'user', 'content': 'jane@example.org'}]})
        with self.assertRaises(ValueError):
            self.model.invoke(SOURCE, previous_response_id='previous-unredacted-conversation')
        self.assertEqual(self.captured, [])

    async def test_factory_disables_optional_storage_and_cache_and_external_environment_tracing(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key-not-network', 'LANGSMITH_TRACING': 'true', 'LANGCHAIN_TRACING_V2': 'true'}):
            configure_privacy()
            model = get_chat_model()
            self.assertFalse(model.store)
            self.assertFalse(model.cache)
            self.assertFalse(model.verbose)
            self.assertEqual(os.environ['LANGSMITH_TRACING'], 'false')
            self.assertEqual(os.environ['LANGCHAIN_TRACING_V2'], 'false')
            from langsmith import utils as tracing_utils
            self.assertFalse(tracing_utils.tracing_is_enabled())


if __name__ == '__main__':
    unittest.main()
