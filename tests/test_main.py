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
            'TESTING': False,
        }
        assert headers['host'] == 'example.com'
        assert headers['user-agent'].startswith('pytest-cloudflare-worker')
        logs = client.inspect_log_wait(1)
        assert logs == [{'level': 'LOG', 'message': '"handling request:", "GET", "/the/path/"'}]


@auth_test
def test_auth_client_vars(wrangler_dir: Path):
    preview_id = DeployPreview(
        wrangler_dir,
    ).deploy_auth()

    with TestClient(preview_id=preview_id, fake_host='foobar.com') as client:
        r = client.get('/vars/')
        assert r.status_code == 200
        obj = r.json()
        # debug(obj)
        assert obj['url'] == {
            'hostname': 'foobar.com',
            'pathname': '/vars/',
            'params': {},
        }
        assert obj['TESTING'] is True
        assert obj['headers']['host'] == 'foobar.com'
        assert obj['method'] == 'GET'
        assert obj['vars'] == {'FOO': 'bar', 'SPAM': 'spam'}
        logs = client.inspect_log_wait(1)
        assert logs == [{'level': 'LOG', 'message': '"handling request:", "GET", "/vars/"'}]


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

        logs = client.inspect_log_wait(2)
        assert logs == [
            {'level': 'LOG', 'message': '"handling request:", "POST", "/kv/"'},
            {'level': 'LOG', 'message': '"settings KV", "foo", "this is a test"'},
        ]


def test_non_api_token(wrangler_dir: Path):
    env_api_token = os.environ.pop('CLOUDFLARE_API_TOKEN', None)
    os.environ['CLOUDFLARE_API_TOKEN_PATH'] = '/does/not/exist.toml'
    try:
        with pytest.raises(FileNotFoundError, match="No such file or directory: '/does/not/exist.toml'"):
            DeployPreview(wrangler_dir).deploy_auth()
    finally:
        if env_api_token:
            os.environ['CLOUDFLARE_API_TOKEN'] = env_api_token


def test_bad_upload(wrangler_dir: Path):
    env_api_token = os.environ.pop('CLOUDFLARE_API_TOKEN', None)
    os.environ['CLOUDFLARE_API_TOKEN'] = 'foobar'
    try:
        with pytest.raises(ValueError, match='unexpected response 400 when deploying to https://api.cloudflare.com'):
            DeployPreview(wrangler_dir).deploy_auth()
    finally:
        if env_api_token:
            os.environ['CLOUDFLARE_API_TOKEN'] = env_api_token
