from pytest_cloudflare_worker import TestClient


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
    debug(log)
    assert log == [
        'LOG worker.js:5> "handling request:", "GET", "/1"',
        'LOG worker.js:5> "handling request:", "GET", "/2"',
        'LOG worker.js:5> "handling request:", "GET", "/3"',
    ]
