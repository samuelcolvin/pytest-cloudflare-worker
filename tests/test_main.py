from pathlib import Path

from pytest_cloudflare_worker.main import TestClient, TestServer, DeployPreview


async def test_anon_client(wrangler_dir: Path, loop):
    preview_id = await DeployPreview(wrangler_dir, loop=loop).deploy_anon()
    assert len(preview_id) == 32

    server = TestServer(preview_id, loop=loop)
    async with TestClient(server, loop=loop) as client:
        r = await client.get('/the/path/')
        assert r.status == 200, await client.logs(sleep=1)
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
        logs = await client.logs(log_count=1)
        assert logs == ['LOG worker.js:5: handling request: GET /the/path/']
