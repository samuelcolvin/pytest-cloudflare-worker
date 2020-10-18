import os
from pathlib import Path

import pytest

from pytest_cloudflare_worker.main import DeployPreview, TestClient

auth_test = pytest.mark.skipif(not os.getenv('CLOUDFLARE_API_TOKEN'), reason='requires CLOUDFLARE_API_TOKEN env var')


def test_anon_client(wrangler_dir: Path):
    with TestClient() as client:
        preview_id = DeployPreview(wrangler_dir, client).deploy_anon()
        assert len(preview_id) == 32
        client.preview_id = preview_id

        r = client.get('/the/path/')
        assert r.status_code == 200
        assert r.headers['x-foo'] == 'bar'
        obj = r.json()
        # debug(obj)
        headers = obj.pop('headers')
        assert obj == {
            'method': 'GET',
            'url': {
                'hostname': 'example.com',
                'pathname': '/the/path/',
                'params': {},
            },
            'body': '',
        }
        assert headers['host'] == 'example.com'
        assert headers['user-agent'].startswith('pytest-cloudflare-worker')
        # logs = client.logs(1)
        # assert logs == ['LOG worker.js:5: handling request: GET /the/path/']


@auth_test
def test_auth_client_vars(wrangler_dir: Path):
    preview_id = DeployPreview(wrangler_dir, ).deploy_auth()

    with TestClient(preview_id=preview_id, fake_host='foobar.com') as client:
        r = client.get('/vars/')
        assert r.status_code == 200
        obj = r.json()
        assert obj['url'] == {
            'hostname': 'foobar.com',
            'pathname': '/vars/',
            'params': {},
        }
        assert obj['headers']['host'] == 'foobar.com'
        assert obj['method'] == 'GET'
        assert obj['vars'] == {'FOO': 'bar', 'SPAM': 'spam'}
        # logs = client.logs(log_count=1)
        # assert logs == ['LOG worker.js:5: handling request: GET /vars/']


@auth_test
def test_auth_client_kv(wrangler_dir: Path):
    with TestClient() as client:
        client.preview_id = DeployPreview(wrangler_dir).deploy_auth()
        r = client.post('/kv/', params={'key': 'foo'}, data='this is a test')
        assert r.status_code == 200
        obj = r.json()

        assert obj['method'] == 'POST'
        assert obj['url'] == {
            'hostname': 'example.com',
            'pathname': '/kv/',
            'params': {'key': 'foo'},
        }
        assert obj['body'] == 'this is a test'
        assert obj['KV'] == {'foo': 'this is a test'}

        # logs = client.logs(log_count=2)
        # assert logs == [
        #     'LOG worker.js:5: handling request: GET /kv/',
        #     "LOG worker.js:24: settings KV {'foo': 'swoffle'}",
        # ]
