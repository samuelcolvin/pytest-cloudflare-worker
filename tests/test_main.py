import os
from pathlib import Path

import pytest
from requests import Session

from pytest_cloudflare_worker.main import DeployPreview, TestClient

auth_test = pytest.mark.skipif(not os.getenv('CLOUDFLARE_API_TOKEN'), reason='requires CLOUDFLARE_API_TOKEN env var')


def test_anon_client(wrangler_dir: Path):
    client = TestClient()
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
            'hash': '',
            'params': {},
        },
        'body': '',
    }
    assert headers['user-agent'].startswith('pytest-cloudflare-worker')
    logs = client.logs(1)
    assert logs == ['LOG worker.js:5: handling request: GET /the/path/']


@auth_test
def test_auth_client_vars(wrangler_dir: Path):
    preview_id = DeployPreview(wrangler_dir, Session()).deploy_auth()

    client = TestClient(preview_id=preview_id, fake_host='foobar.com')
    r = client.get('/vars/')
    assert r.status_code == 200
    obj = r.json()
    debug(obj)
    assert obj['method'] == 'GET'
    assert obj['vars'] == {'FOO': 'bar', 'SPAM': 'spam'}
    logs = client.logs(log_count=1)
    assert logs == ['LOG worker.js:5: handling request: GET /vars/']


# @auth_test
# async def test_auth_client_kv(wrangler_dir: Path, loop):
#     preview_id = await DeployPreview(wrangler_dir, loop=loop).deploy_auth()
#     server = TestServer(preview_id, loop=loop)
#     async with TestClient(server, loop=loop) as client:
#         r = await client.get('/kv/', params={'key': 'foo', 'value': 'swoffle'})
#         assert r.status == 200, await client.logs(sleep=1)
#         obj = await r.json()
#
#         assert obj['method'] == 'GET'
#         assert obj['KV'] == {'foo': 'swoffle'}
#
#         logs = await client.logs(log_count=1)
#         assert logs == [
#             'LOG worker.js:5: handling request: GET /kv/',
#             "LOG worker.js:24: settings KV {'foo': 'swoffle'}",
#         ]
