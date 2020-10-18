import json
import os
import subprocess
import uuid
from asyncio import AbstractEventLoop, CancelledError, Event, sleep as async_sleep
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
import toml
from aiohttp import ClientResponse, FormData, WSMessage, WSMsgType
from aiohttp.test_utils import BaseTestServer as AiohttpTestServer, TestClient as AiohttpTestClient
from aiohttp.web_runner import BaseRunner
from yarl import URL

__all__ = 'DeployPreview', 'TestServer', 'TestClient'


class DeployPreview:
    def __init__(self, wrangler_dir: Path, loop: Optional[AbstractEventLoop] = None) -> None:
        self._wrangler_dir = wrangler_dir
        self._loop = loop

    async def deploy_auth(self) -> str:
        source_path, wrangler_data = self._build_source()

        url = (
            f'https://api.cloudflare.com/client/v4/'
            f'accounts/{wrangler_data["account_id"]}/workers/scripts/{wrangler_data["name"]}/preview'
        )

        bindings: List[Dict[str, str]] = []
        for k, v in wrangler_data.get('vars', {}).items():
            bindings.append({'name': k, 'type': 'plain_text', 'text': v})
        for namespace in wrangler_data.get('kv_namespaces', []):
            if preview_id := namespace.get('preview_id'):
                bindings.append({'name': namespace['binding'], 'type': 'kv_namespace', 'namespace_id': preview_id})
        metadata = json.dumps({'body_part': source_path.name, 'binding': bindings})

        data = FormData()
        data.add_field('metadata', metadata, filename=source_path.name, content_type='application/json')
        data.add_field(source_path.name, source_path.read_text(), filename=source_path.name)

        api_token = self.get_api_token()
        r = await self._upload(url, data, {'Authorization': f'Bearer {api_token}'})
        return r['result']['preview_id']

    async def deploy_anon(self) -> str:
        source_path, wrangler_data = self._build_source()

        r = await self._upload('https://cloudflareworkers.com/script', source_path.read_bytes())
        return r['id']

    def _build_source(self) -> Tuple[Path, Dict[str, Any]]:
        assert self._wrangler_dir.is_dir()
        wrangler_path = self._wrangler_dir / 'wrangler.toml'
        assert wrangler_path.is_file()
        wrangler_data = toml.loads(wrangler_path.read_text())
        if wrangler_data['type'] == 'javascript':
            source_path = self._wrangler_dir / 'index.js'
        else:
            subprocess.run(('wrangler', 'build'), check=True)
            source_path = self._wrangler_dir / 'dist' / 'index.js'
        assert source_path.is_file(), f'source path "{source_path}" not found'
        return source_path, wrangler_data

    @classmethod
    def get_api_token(cls) -> str:
        if api_token := os.getenv('CLOUDFLARE_API_TOKEN'):
            return api_token

        if path := os.getenv('CLOUDFLARE_API_TOKEN_PATH'):
            api_token_path = Path(path).expanduser()
        else:
            api_token_path = Path.home() / '.wrangler' / 'config' / 'default.toml'

        assert api_token_path.is_file(), f'api token file "{api_token_path}" does not exist'
        return toml.loads(api_token_path.read_text())['api_token']

    async def _upload(self, url: str, data: Union[bytes, FormData], headers: Dict[str, str] = None) -> Dict[str, Any]:
        async with aiohttp.ClientSession(loop=self._loop) as client:
            async with client.post(url, data=data, headers=headers) as r:
                r.raise_for_status()
                return await r.json()


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
        self.session_id = uuid.uuid4().hex
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

        if log_count == 0:
            msg = 'no logs received'
        elif log_count == 1:
            msg = '1 log not received'
        else:
            msg = f'{log_count} logs not received'
        raise RuntimeError(msg)

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
            self.args = [parse_arg(arg) for arg in params['args']]
            self.display = ' '.join(str(arg) for arg in self.args)
            frame = params['stackTrace']['callFrames'][0]
            self.line = f"{frame['url']}:{frame['lineNumber'] + 1}"
        elif method == 'Runtime.exceptionThrown':
            self.level = 'ERROR'
            self.display = params['exceptionDetails']['exception']['preview']['description']
            self.line = ''  # TODO

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
        return f'{self.level} {self.line}: {self.display}'

    def __repr__(self):
        return repr(str(self))


def parse_arg(arg: Dict[str, Any]) -> Any:
    arg_type = arg['type']
    if arg_type in {'string', 'number'}:
        return arg['value']
    elif arg_type == 'object':
        return {p['name']: p['value'] for p in arg['preview']['properties']}
    else:
        # TODO
        return str(arg['preview'])
