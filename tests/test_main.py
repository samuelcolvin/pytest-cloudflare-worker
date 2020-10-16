import asyncio
from pathlib import Path

from pytest_cloudflare_worker.main import TestClient, TestServer, deploy_preview


async def test_test_client(code_path: Path, loop):
    preview_id = await deploy_preview(code_path, loop=loop)
    assert len(preview_id) == 32

    server = TestServer(preview_id, loop=loop)
    async with TestClient(server, loop=loop) as client:
        r = await client.get('/the/path/')
        assert r.status == 200
        assert r.headers['x-foo'] == 'bar'
        obj = await r.json()
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
        assert headers['user-agent'].startswith('Python')
        logs = await client.logs(1)
        assert logs == ['LOG: handling request: GET /the/path/']
