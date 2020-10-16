import json
import secrets
import subprocess
from asyncio import AbstractEventLoop, CancelledError, Event, sleep as async_sleep
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import toml
from aiohttp import ClientResponse, WSMessage, WSMsgType
from aiohttp.test_utils import BaseTestServer as AiohttpTestServer, TestClient as AiohttpTestClient
from aiohttp.web_runner import BaseRunner
from yarl import URL


async def deploy_preview(wrangler_dir: Path, *, loop: Optional[AbstractEventLoop] = None) -> str:
    assert wrangler_dir.is_dir()
    wrangler_path = wrangler_dir / 'wrangler.toml'
    assert wrangler_path.is_file()
    wrangler_data = toml.loads(wrangler_path.read_text())
    if wrangler_data['type'] == 'javascript':
        source_path = wrangler_dir / 'index.js'
    else:
        subprocess.run(('wrangler', 'build'), check=True)
        source_path = wrangler_dir / 'dist' / 'index.js'
    assert source_path.is_file()

    # url= 'https://cloudflareworkers.com/script'
    url = (
        f'https://api.cloudflare.com/client/v4/'
        f'accounts/{wrangler_data["account_id"]}/workers/scripts/{wrangler_data["name"]}/preview'
    )
    bindings = [{'name': k, 'type': 'plain_text', 'text': v} for k, v in wrangler_data.get('vars', {}).items()]
    metadata = {
        'body_part': source_path.name,
        'binding': bindings
    }
    metadata = json.dumps(metadata)
    data = aiohttp.FormData()
    data.add_field('metadata', metadata.encode(), filename=source_path.name, content_type='application/json')
    data.add_field(source_path.name, source_path.read_text(), filename=source_path.name)

    config_path = Path.home() / '.wrangler' / 'config' / 'default.toml'
    assert config_path.is_file(), config_path
    api_token = toml.loads(config_path.read_text())['api_token']
    headers = {'Authorization': f'Bearer {api_token}'}

    async with aiohttp.ClientSession(loop=loop) as client:
        async with client.post(url, data=data, headers=headers) as r:
            r.raise_for_status()
            data = await r.json()

    return data['result']['preview_id']
    # return data['id']


class TestServer(AiohttpTestServer):
    root: URL

    def __init__(self, preview_id: str, loop: Optional[AbstractEventLoop] = None):
        super().__init__(loop=loop)
        self.preview_id: str = preview_id
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


# we don't need all of these, but not clear which we do
inspect_start_msgs = [
    json.dumps({'id': 1, 'method': 'Profiler.enable'}),
    json.dumps({'id': 2, 'method': 'Runtime.enable'}),
    json.dumps({'id': 3, 'method': 'Debugger.enable'}),
    json.dumps({'id': 4, 'method': 'Debugger.setPauseOnExceptions', 'params': {'state': 'none'}}),
    json.dumps({'id': 5, 'method': 'Debugger.setAsyncCallStackDepth', 'params': {'maxDepth': 32}}),
    json.dumps({'id': 6, 'method': 'Network.enable', 'params': {'maxPostDataSize': 65536}}),
    json.dumps({'id': 7, 'method': 'Debugger.setBlackboxPatterns', 'params': {'patterns': []}}),
    # json.dumps({'id': 7, 'method': 'Runtime.runIfWaitingForDebugger'}),
    json.dumps({'id': 8, 'method': 'Runtime.getIsolateId'}),
]


class TestClient(AiohttpTestClient):
    """
    A test client implementation.

    To write functional tests for aiohttp based servers.
    """

    def __init__(self, server: TestServer, fake_host: str = 'example.com', **kwargs):
        super().__init__(server, **kwargs)
        self.fake_host = fake_host
        self._log: List[LogMsg] = []
        self.session_id = secrets.token_hex()[:32]
        self.watch_task = None

    async def start_server(self) -> None:
        ready = Event()
        self.watch_task = self._loop.create_task(self._watch(ready))
        await ready.wait()
        await super().start_server()

    async def close(self) -> None:
        self.watch_task.cancel()
        await self.watch_task
        await super().close()

    async def _request(
        self, method: str, path: str, *, headers: Dict[str, str] = None, **kwargs: Any
    ) -> ClientResponse:
        url = URL(path)
        assert not url.is_absolute(), f'path "{url}" must be relative'

        headers = headers or {}
        assert 'cookie' not in {h.lower() for h in headers.keys()}, '"Cookie" header should not be set'

        server: TestServer = self._server
        headers['Cookie'] = f'__ew_fiddle_preview={server.preview_id}{self.session_id}{1}{self.fake_host}{path}'

        return await super()._request(method, path, headers=headers, **kwargs)

    async def logs(self, *, log_count: int = 0, sleep: float = None) -> List['LogMsg']:
        if sleep is not None:
            await async_sleep(sleep)
            return self._log
        for _ in range(200):
            if len(self._log) >= log_count:
                return self._log
            await async_sleep(0.01)
        raise RuntimeError(f'{log_count} logs not received')

    async def _watch(self, ready_event: Event):
        try:
            async with self.session.ws_connect(f'wss://cloudflareworkers.com/inspect/{self.session_id}') as ws:
                for msg in inspect_start_msgs:
                    await ws.send_str(msg)
                ready_event.set()
                async for msg in ws:
                    log_msg = LogMsg.from_raw(msg)
                    if log_msg:
                        self._log.append(log_msg)
        except CancelledError:
            # happens when the task is cancelled
            pass


ignored_methods = {
    'Runtime.executionContextCreated',
    'Runtime.executionContextDestroyed',
    'Debugger.scriptParsed',
    'Profiler.enable',
    'Network.enable',
}


class LogMsg:
    def __init__(self, method: str, data):
        self.extra = data
        params = data['params']
        if method == 'Runtime.consoleAPICalled':
            self.level = params['type'].upper()
            str_args = []
            for arg in params['args']:
                if arg['type'] in {'string', 'number'}:
                    str_args.append(arg['value'])
                else:
                    str_args.append(str(arg['preview']))
            self.display = ' '.join(str_args)
        elif method == 'Runtime.exceptionThrown':
            self.level = 'ERROR'
            self.display = params['exceptionDetails']['exception']['preview']['description']

    @classmethod
    def from_raw(cls, msg: WSMessage) -> Optional['LogMsg']:
        if msg.type != WSMsgType.TEXT:
            return

        data = json.loads(msg.data)
        method = data.get('method')
        if not method or method in ignored_methods:
            return

        if method in {'Runtime.consoleAPICalled', 'Runtime.exceptionThrown'}:
            return cls(method, data)
        else:
            raise RuntimeError(f'unknown message from inspect websocket, type {method}\n{data}')

    def __eq__(self, other: Any) -> str:
        return other == str(self)

    def __str__(self):
        return f'{self.level.upper()}: {self.display}'

    def __repr__(self):
        return repr(str(self))
