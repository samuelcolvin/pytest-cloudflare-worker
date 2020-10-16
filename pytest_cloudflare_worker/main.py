import secrets
from asyncio import AbstractEventLoop
from pathlib import Path
from typing import Optional, Any, Dict

import aiohttp
from aiohttp import ClientResponse
from aiohttp.test_utils import TestClient as AiohttpTestClient, BaseTestServer as AiohttpTestServer
from aiohttp.web_runner import BaseRunner
from yarl import URL


async def deploy_preview(code: Path, *, loop: Optional[AbstractEventLoop] = None) -> str:
    async with aiohttp.ClientSession(loop=loop) as client:
        async with client.post('https://cloudflareworkers.com/script', data=code.read_bytes()) as r:
            r.raise_for_status()
            data = await r.json()
    return data['id']


class TestServer(AiohttpTestServer):
    root: URL

    def __init__(self, preview_id: str, loop: Optional[AbstractEventLoop] = None):
        super().__init__(loop=loop)
        self.preview_id: str = preview_id
        self.session_id = secrets.token_hex()[:32]
        self.host = '0000000000000000.cloudflareworkers.com'
        self.port = 443
        self.scheme = 'https'
        self.root = self._root = URL(f'{self.scheme}://{self.host}')

    async def start_server(self, loop: Optional[AbstractEventLoop] = None, **kwargs: Any) -> None:
        return None

    async def _make_runner(self, **kwargs: Any) -> BaseRunner:
        pass

    def make_url(self, path: str) -> URL:
        assert self._root is not None
        return self._root

    async def close(self) -> None:
        pass


class TestClient(AiohttpTestClient):
    """
    A test client implementation.

    To write functional tests for aiohttp based servers.
    """
    def __init__(self, server: TestServer, fake_host: str = 'example.com', **kwargs):
        super().__init__(server, **kwargs)
        self.fake_host = fake_host

    async def _request(self, method: str, path: str, *, headers: Dict[str, str] = None, **kwargs: Any) -> ClientResponse:
        url = URL(path)
        assert not url.is_absolute(), f'path "{url}" must be relative'

        headers = headers or {}
        assert 'cookie' not in {h.lower() for h in headers.keys()}, '"Cookie" header should not be set'
        server: TestServer = self._server
        headers['Cookie'] = f'__ew_fiddle_preview={server.preview_id}{server.session_id}{1}{self.fake_host}{path}'

        return await super()._request(method, path, headers=headers, **kwargs)
