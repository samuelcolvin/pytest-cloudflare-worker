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
    assert log == ['LOG worker.js:5> "handling request:", "GET", "/"']


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
    }
    assert r.headers['x-foo'] == 'bar'
    log = client.inspect_log_wait(1)
    assert log == ['LOG worker.js:5> "handling request:", "PUT", "/foo/bar"']


def test_client_request(client: TestClient):
    assert client.get('/1').status_code == 200
    assert client.get('/2').status_code == 200
    assert client.get('/3').status_code == 200
    log = client.inspect_log_wait(3)
    # debug(log)
    assert log == [
        'LOG worker.js:5> "handling request:", "GET", "/1"',
        'LOG worker.js:5> "handling request:", "GET", "/2"',
        'LOG worker.js:5> "handling request:", "GET", "/3"',
    ]


def test_worker_error(client: TestClient):
    """
    Use the fact that anon clients don't have access to vars to cause a 500 error
    """
    with pytest.raises(WorkerError, match='worker.js:19> ReferenceError: FOO is not defined'):
        client.get('/vars/')


def test_client_console(client: TestClient):
    r = client.get('/console')
    assert r.status_code == 200
    logs = client.inspect_log_wait(4)
    # debug(log)
    assert logs == [
        'LOG worker.js:5> "handling request:", "GET", "/console"',
        'LOG worker.js:28> "object", {"foo": "bar", "spam": 1.0}',
        'LOG worker.js:29> "list", ["s", 1.0, 2.0, true, false, null, "<undefined>"]',
        {'level': 'LOG', 'file': 'worker.js', 'line': 31},
    ]
    assert logs[2].message == '"list", ["s", 1.0, 2.0, true, false, null, "<undefined>"]'
    assert logs[2].args == ['list', ['s', 1, 2, True, False, None, '<undefined>']]
    assert logs[3].endswith('(Coordinated Universal Time)"')
