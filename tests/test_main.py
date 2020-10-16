from pathlib import Path

from pytest_cloudflare_worker.main import TestClient, TestServer, deploy_preview


async def test_test_client(code_path: Path, loop):
    preview_id = await deploy_preview(code_path, loop=loop)
    assert len(preview_id) == 32

    server = TestServer(preview_id, loop=loop)
    async with TestClient(server, loop=loop) as client:
        r = await client.get('/')
        assert r.status == 200
        assert await r.text() == 'pytest-cloudflare-worker example'
        assert r.headers['x-foo'] == 'bar'
