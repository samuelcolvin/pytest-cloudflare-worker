import asyncio
import json
import os
import subprocess
import uuid
from pathlib import Path
from threading import Event, Thread
from time import time
from typing import Any, Dict, List, Optional, Tuple

import requests
import toml
import websockets
from requests import Response, Session

from .version import VERSION

__all__ = 'DeployPreview', 'TestClient', 'WorkerError'


class DeployPreview:
    def __init__(self, wrangler_dir: Path, test_client: Optional['TestClient'] = None) -> None:
        self._wrangler_dir = wrangler_dir
        self._test_client = test_client

    def deploy_auth(self) -> str:
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

        files = {
            'metadata': ('metadata.json', metadata, 'application/json'),
            source_path.name: (source_path.name, source_path.read_text(), 'text/plain'),
        }

        api_token = self.get_api_token()
        r = self._upload(url, files=files, headers={'Authorization': f'Bearer {api_token}'})
        return r['result']['preview_id']

    def deploy_anon(self) -> str:
        source_path, wrangler_data = self._build_source()

        r = self._upload('https://cloudflareworkers.com/script', data=source_path.read_bytes())
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

        # assert api_token_path.is_file(), f'api token file "{api_token_path}" does not exist'
        return toml.loads(api_token_path.read_text())['api_token']

    def _upload(self, url: str, **kwargs) -> Dict[str, Any]:
        if isinstance(self._test_client, TestClient):
            r = self._test_client.direct_request('POST', url, **kwargs)
        else:
            r = requests.post(url, **kwargs)

        if r.status_code not in {200, 201}:
            raise ValueError(f'unexpected response {r.status_code} when deploying to {url}:\n{r.text}')
        return r.json()


class WorkerError(Exception):
    def __init__(self, logs: List['LogMsg']):
        super().__init__('\n'.join(str(msg) for msg in logs))
        self.logs = logs


class TestClient(Session):
    __test__ = False

    def __init__(self, *, preview_id: Optional[str] = None, fake_host: str = 'example.com'):
        super().__init__()
        self._original_fake_host = fake_host
        self.fake_host = self._original_fake_host
        self.preview_id = preview_id
        self._root = 'https://0000000000000000.cloudflareworkers.com'
        self._session_id = uuid.uuid4().hex
        self.headers = {'user-agent': f'pytest-cloudflare-worker/{VERSION}'}
        self.inspect_logs = []

        self.inspect_enabled = True
        self._inspect_ready = Event()
        self._inspect_stop = Event()
        self._inspect_received = Event()
        self._inspect_thread: Optional[Thread] = None

    def new_cf_session(self):
        self._stop_inspect()
        self.inspect_logs = []
        self._session_id = uuid.uuid4().hex
        self.fake_host = self._original_fake_host

    def direct_request(self, method: str, url: str, **kwargs) -> Response:
        return super().request(method, url, **kwargs)

    def request(self, method: str, path: str, *, headers: Dict[str, str] = None, **kwargs: Any) -> Response:
        assert self.preview_id, 'preview_id not set in test client'
        assert path.startswith('/'), f'path "{path}" must be relative'

        if self.inspect_enabled and self._inspect_thread is None:
            self._start_inspect()
        self._inspect_ready.wait(2)

        headers = headers or {}
        assert 'cookie' not in {h.lower() for h in headers.keys()}, '"Cookie" header should not be set'

        headers['Cookie'] = f'__ew_fiddle_preview={self.preview_id}{self._session_id}{1}{self.fake_host}'

        logs_before = len(self.inspect_logs)
        response = super().request(method, self._root + path, headers=headers, **kwargs)
        if response.status_code >= 500:
            error_logs = []
            for i in range(100):
                error_logs = [msg for msg in self.inspect_logs[logs_before:] if msg.level == 'ERROR']
                if error_logs:
                    break
                self._wait_for_log()
            raise WorkerError(error_logs)
        return response

    def inspect_log_errors(self) -> List['LogMsg']:
        return [msg for msg in self.inspect_logs if msg.level == 'ERROR']

    def inspect_log_wait(self, count: Optional[int] = None, wait_time: float = 5) -> List['LogMsg']:
        start = time()
        while True:
            if count is not None and len(self.inspect_logs) >= count:
                return self.inspect_logs
            elif time() - start > wait_time:
                raise TimeoutError(f'only {len(self.inspect_logs)} logs receives, fewer than {count} expected')
            self._wait_for_log()

    def _wait_for_log(self) -> None:
        self._inspect_received.wait(0.1)
        self._inspect_received.clear()

    def _start_inspect(self):
        self._inspect_ready.clear()
        self._inspect_stop.clear()
        kwargs = dict(
            session_id=self._session_id,
            log=self.inspect_logs,
            ready=self._inspect_ready,
            stop=self._inspect_stop,
            received=self._inspect_received,
        )
        self._inspect_thread = Thread(name='inspect', target=inspect, kwargs=kwargs, daemon=True)
        self._inspect_thread.start()

    def _stop_inspect(self):
        if self._inspect_thread is not None:
            self._inspect_stop.set()
            t = self._inspect_thread
            self._inspect_thread = None
            t.join(1)

    def close(self) -> None:
        super().close()
        self._stop_inspect()


def inspect(*, session_id: str, log: List['LogMsg'], ready: Event, stop: Event, received: Event):
    async def async_inspect() -> None:
        async with websockets.connect(f'wss://cloudflareworkers.com/inspect/{session_id}') as ws:
            for msg in inspect_start_msgs:
                await ws.send(msg)

            while True:
                f = ws.recv()
                try:
                    msg = await asyncio.wait_for(f, timeout=0.1)
                except asyncio.TimeoutError:
                    pass
                else:
                    data = json.loads(msg)
                    if data.get('id') == 8:  # this is the id of the last element of inspect_start_msgs
                        ready.set()

                    log_msg = LogMsg.from_raw(data)
                    if log_msg:
                        log.append(log_msg)
                        received.set()

                if stop.is_set():
                    return

    asyncio.run(async_inspect())


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

ignored_methods = {
    'Runtime.executionContextCreated',
    'Runtime.executionContextDestroyed',
    'Debugger.scriptParsed',
    'Profiler.enable',
    'Network.enable',
}


class LogMsg:
    def __init__(self, method: str, data):
        # debug(data)
        self.full = data
        params = data['params']
        if method == 'Runtime.consoleAPICalled':
            self.level = params['type'].upper()
            self.args = [self.parse_arg(arg) for arg in params['args']]
            self.message = ', '.join(json.dumps(arg) for arg in self.args)
            frame = params['stackTrace']['callFrames'][0]
            self.file = frame['url']
            self.line = frame['lineNumber'] + 1
        elif method == 'Runtime.exceptionThrown':
            self.level = 'ERROR'
            details = params['exceptionDetails']
            self.message = details['exception']['preview']['description']
            self.file = details['url']
            self.line = details['lineNumber'] + 1

    @classmethod
    def from_raw(cls, data: Dict[str, Any]) -> Optional['LogMsg']:
        method = data.get('method')
        if not method or method in ignored_methods:
            return

        if method in {'Runtime.consoleAPICalled', 'Runtime.exceptionThrown'}:
            return cls(method, data)
        else:
            raise RuntimeError(f'unknown message from inspect websocket, type {method}\n{data}')

    @classmethod
    def parse_arg(cls, arg: Dict[str, Any]) -> Any:
        arg_type = arg['type']
        if arg_type in {'string', 'number'}:
            return arg['value']
        elif arg_type == 'object':
            if 'preview' in arg:
                return {p['name']: p['value'] for p in arg['preview']['properties']}
            else:
                # ???
                return {}
        else:
            # TODO
            return str(arg['preview'])

    def __eq__(self, other: Any) -> str:
        return other == str(self)

    def __str__(self):
        return f'{self.level} {self.file}:{self.line}> {self.message}'

    def __repr__(self):
        return repr(str(self))
