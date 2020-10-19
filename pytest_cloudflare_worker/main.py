import asyncio
import json
import os
import subprocess
import uuid
import warnings
from pathlib import Path
from threading import Event, Thread
from time import time
from typing import Any, Dict, List, Optional, Tuple

import requests
import toml
import websockets
from requests import Response, Session

from .version import VERSION

__all__ = 'deploy', 'TestClient', 'WorkerError'


def deploy(wrangler_dir: Path, *, authenticate: bool, test_client: Optional['TestClient'] = None) -> str:
    source_path, wrangler_data = build_source(wrangler_dir)

    if authenticate:
        url = (
            f'https://api.cloudflare.com/client/v4/'
            f'accounts/{wrangler_data["account_id"]}/workers/scripts/{wrangler_data["name"]}/preview'
        )
        api_token = get_api_token()
        headers = {'Authorization': f'Bearer {api_token}'}
    else:
        url = 'https://cloudflareworkers.com/script'
        headers = None

    bindings: List[Dict[str, str]] = [{'name': '__TESTING__', 'type': 'plain_text', 'text': 'TRUE'}]
    for k, v in wrangler_data.get('vars', {}).items():
        bindings.append({'name': k, 'type': 'plain_text', 'text': v})

    if authenticate:
        for namespace in wrangler_data.get('kv_namespaces', []):
            if preview_id := namespace.get('preview_id'):
                bindings.append({'name': namespace['binding'], 'type': 'kv_namespace', 'namespace_id': preview_id})

    # debug(bindings)
    script_name = source_path.stem
    metadata = json.dumps({'bindings': bindings, 'body_part': script_name}, separators=(',', ':'))

    files = {
        'metadata': ('metadata.json', metadata, 'application/json'),
        script_name: (source_path.name, source_path.read_bytes(), 'application/javascript'),
    }

    if isinstance(test_client, TestClient):
        r = test_client.direct_request('POST', url, files=files, headers=headers)
    else:
        r = requests.post(url, files=files, headers=headers)

    # debug(r.request.body)
    if r.status_code not in {200, 201}:
        raise ValueError(f'unexpected response {r.status_code} when deploying to {url}:\n{r.text}')
    obj = r.json()

    if authenticate:
        return obj['result']['preview_id']
    else:
        return obj['id']


def build_source(wrangler_dir: Path) -> Tuple[Path, Dict[str, Any]]:
    wrangler_path = wrangler_dir / 'wrangler.toml'
    wrangler_data = toml.loads(wrangler_path.read_text())
    if wrangler_data['type'] == 'javascript':
        source_path = wrangler_dir / 'index.js'
    else:
        subprocess.run(('wrangler', 'build'), check=True)
        source_path = wrangler_dir / 'dist' / 'index.js'
    assert source_path.is_file(), f'source path "{source_path}" not found'
    return source_path, wrangler_data


def get_api_token() -> str:
    if api_token := os.getenv('CLOUDFLARE_API_TOKEN'):
        return api_token

    if path := os.getenv('CLOUDFLARE_API_TOKEN_PATH'):
        api_token_path = Path(path).expanduser()
    else:
        api_token_path = Path.home() / '.wrangler' / 'config' / 'default.toml'

    return toml.loads(api_token_path.read_text())['api_token']


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
        self._root = 'https://00000000000000000000000000000000.cloudflareworkers.com'
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

    def request(self, method: str, path: str, **kwargs: Any) -> Response:
        assert self.preview_id, 'preview_id not set in test client'
        assert path.startswith('/'), f'path "{path}" must be relative'

        if self.inspect_enabled:
            if self._inspect_thread is None:
                self._start_inspect()
            self._inspect_ready.wait(2)

        assert 'cookies' not in kwargs, '"cookies" kwarg not allowed'
        cookies = {'__ew_fiddle_preview': f'{self.preview_id}{self._session_id}{1}{self.fake_host}'}

        logs_before = len(self.inspect_logs)
        response = super().request(method, self._root + path, cookies=cookies, **kwargs)
        if response.status_code >= 500:
            error_logs = []
            for i in range(100):  # pragma: no branch
                error_logs = [msg for msg in self.inspect_logs[logs_before:] if msg.level == 'ERROR']
                if error_logs:
                    break
                self._wait_for_log()
            raise WorkerError(error_logs)
        return response

    def inspect_log_wait(self, count: Optional[int] = None, wait_time: float = 5) -> List['LogMsg']:
        assert self.inspect_enabled, 'inspect_log_wait make no sense without inspect_enabled=True'
        start = time()
        while True:
            if count is not None and len(self.inspect_logs) >= count:
                return self.inspect_logs
            elif time() - start > wait_time:
                raise TimeoutError(f'{len(self.inspect_logs)} logs received, expected {count}')
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
        value = arg.get('value')
        if arg_type == 'string':
            return value
        if arg_type == 'number':
            return float(value)
        elif arg_type == 'boolean':
            return value == 'true'
        elif value == 'null':
            return None
        elif value == 'undefined':
            # no good python equivalent
            return '<undefined>'

        sub_type = arg.get('subtype')
        preview = arg.get('preview')
        if (arg_type, sub_type) == ('object', 'array'):
            return [cls.parse_arg(item) for item in preview['properties']]
        elif (arg_type, sub_type) == ('object', 'date'):
            return arg['description']
        elif arg_type == 'object' and arg.get('className') == 'Object':
            return {p['name']: cls.parse_arg(p) for p in preview['properties']}
        else:  # pragma: no cover
            warnings.warn(f'unknown inspect log argument {arg}')
            return str(arg)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return other == str(self)
        elif isinstance(other, dict):
            self_dict = {k: self.__dict__[k] for k in other.keys()}
            return other == self_dict
        else:
            return False

    def endswith(self, *s: str) -> bool:
        return str(self).endswith(*s)

    def startswith(self, *s: str) -> bool:
        return str(self).startswith(*s)

    def __str__(self):
        return f'{self.level} {self.file}:{self.line}> {self.message}'

    def __repr__(self):
        return repr(str(self))
