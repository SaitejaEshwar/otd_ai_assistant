import asyncio
import json
import httpx
import pytest
from otd_assistant.ai.model import HailoOllamaModel, ModelUnavailable
from otd_assistant.config import Settings


@pytest.fixture
def setup(monkeypatch):
    responses = []
    requests = []
    client = httpx.AsyncClient
    def handler(request):
        requests.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return httpx.Response(200, json=response)
    def factory(**kwargs):
        assert kwargs['trust_env'] is False
        return client(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, 'AsyncClient', factory)
    model = HailoOllamaModel(Settings(_env_file=None, ai_model='qwen2.5-instruct:1.5b'))
    return model, responses, requests


def test_interpret(setup):
    model, responses, requests = setup
    value = dict(action='create', title='Call Sam', target=None, notes=None,
                 date=None, time=None, recurrence=None, view=None, question=None)
    responses.append(dict(done=True, done_reason='stop', message={'content': json.dumps(value)}))
    messages = [{'role': 'system', 'content': 'Task assistant'}]
    assert asyncio.run(model.interpret(messages)).title == 'Call Sam'
    assert messages[0]['content'] == 'Task assistant'
    assert requests[0].url.path == '/api/chat'
    body = json.loads(requests[0].content)
    assert body['stream'] is False
    assert 'Schema:' in body['messages'][0]['content']


@pytest.mark.parametrize('payload', [[], {}, {'done': False},
    dict(done=True, done_reason='length'),
    dict(done=True, done_reason='stop', message={'content':'Task saved!'}),
    dict(done=True, done_reason='stop', message={'content':'{}'}),
    httpx.ReadTimeout('timeout')])
def test_invalid_response(setup, payload):
    model, responses, _ = setup
    responses.append(payload)
    with pytest.raises(ModelUnavailable):
        asyncio.run(model.interpret([]))


@pytest.mark.parametrize('payload, expected', [
    ({'models':[{'name':'qwen2.5-instruct:1.5b'}]}, True),
    ({'models':[{'name':'other'}]}, False),
    ({'models':None}, False), ({}, False), (httpx.ReadTimeout('timeout'), False)])
def test_available(setup, payload, expected):
    model, responses, requests = setup
    responses.append(payload)
    assert asyncio.run(model.available()) is expected
    assert requests[0].url.path == '/api/tags'
