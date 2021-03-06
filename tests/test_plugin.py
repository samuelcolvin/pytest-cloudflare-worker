import pytest

from pytest_cloudflare_worker import TestClient, WorkerError


def test_client_get(client: TestClient):
    r = client.get('/')
    assert r.status_code == 200
    obj = r.json()
    assert obj['method'] == 'GET'
    assert obj['headers']['host'] == 'example.com'
    assert r.headers['x-foo'] == 'bar'
    log = client.inspect_log_wait(1)
    assert log == [{'level': 'LOG', 'message': '"handling request:", "GET", "/"'}]


def test_client_post(client: TestClient):
    client.fake_host = 'different.com'
    r = client.put('/foo/bar', params={'x': 123}, json={'foo': 'bar'})
    assert r.status_code == 200
    obj = r.json()
    headers = obj.pop('headers')
    assert headers['host'] == 'different.com'
    assert headers['user-agent'].startswith('pytest-cloudflare-worker/')
    assert obj == {
        'method': 'PUT',
        'url': {
            'hostname': 'different.com',
            'pathname': '/foo/bar',
            'params': {'x': '123'},
        },
        'body': '{"foo": "bar"}',
        'TESTING': True,
    }
    assert r.headers['x-foo'] == 'bar'
    log = client.inspect_log_wait(1)
    assert log == [{'level': 'LOG', 'message': '"handling request:", "PUT", "/foo/bar"'}]


def test_client_request(client: TestClient):
    assert client.get('/1').status_code == 200
    assert client.get('/2').status_code == 200
    assert client.get('https://example.com/3').status_code == 200
    log = client.inspect_log_wait(3)
    # debug(log)
    assert log == [
        {'level': 'LOG', 'message': '"handling request:", "GET", "/1"'},
        {'level': 'LOG', 'message': '"handling request:", "GET", "/2"'},
        {'level': 'LOG', 'message': '"handling request:", "GET", "/3"'},
    ]


def test_invalid_url(client: TestClient):
    with pytest.raises(ValueError, match=r'path "https://wrong\.com" must be relative or match "\^https\?://'):
        client.get('https://wrong.com')


def test_worker_error(client: TestClient):
    """
    Use the fact that anon clients don't have access to KV worker to cause a 500 error
    """
    with pytest.raises(WorkerError, match='worker.js:28> ReferenceError: THINGS is not defined'):
        client.get('/kv/')


def test_client_console(client: TestClient):
    r = client.get('/console')
    assert r.status_code == 200
    logs = client.inspect_log_wait(4)
    # debug(logs)
    assert logs == [
        {'level': 'LOG', 'message': '"handling request:", "GET", "/console"'},
        # {'level': 'LOG', 'line': 31, 'message': '"object", {"foo": "bar", "spam": 1.0}'},
        {'level': 'LOG', 'line': 31, 'message': '"object", "Object"'},
        # {'level': 'LOG', 'message': '"list", ["s", 1.0, 2.0, true, false, null, "<undefined>"]'},
        {'level': 'LOG', 'message': '"list", "Array(7)"'},
        {'level': 'LOG', 'file': 'worker.js'},
    ]
    assert logs[0] == 'LOG worker.js:7> "handling request:", "GET", "/console"'
    assert logs[0].startswith('LOG worker.js:7>')
    assert repr(logs[0]) == '\'LOG worker.js:7> "handling request:", "GET", "/console"\''
    assert logs[0] != 123
    # assert logs[2].message == '"list", ["s", 1.0, 2.0, true, false, null, "<undefined>"]'
    # assert logs[2].args == ['list', ['s', 1, 2, True, False, None, '<undefined>']]
    assert logs[3].endswith('(Coordinated Universal Time)"')
    with pytest.raises(TimeoutError, match='4 logs received, expected 10'):
        client.inspect_log_wait(10, wait_time=0)


def test_inspect_disabled(client: TestClient):
    client.inspect_enabled = False
    r = client.get('/console')
    assert r.status_code == 200

    assert len(client.inspect_logs) == 0
