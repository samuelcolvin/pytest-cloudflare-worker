import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from threading import Event, Thread
from time import time
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict

import requests
import toml
from requests import Response, Session

from .inspect import LogMsg, inspect
from .version import VERSION

__all__ = 'deploy', 'TestClient', 'WorkerError'


class Binding(TypedDict, total=False):
    name: str
    type: Literal['plain_text', 'kv_namespace']
    text: str
    namespace_id: str


def deploy(
    wrangler_dir: Path, *, authenticate: bool, test_client: Optional['TestClient'] = None
) -> Tuple[str, List[Binding]]:
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

    bindings = build_bindings(wrangler_data, authenticate)

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
        return obj['result']['preview_id'], bindings
    else:
        return obj['id'], bindings


def build_bindings(wrangler_data: Dict[str, Any], authenticate: bool) -> List[Binding]:
    bindings: List[Binding] = [{'name': '__TESTING__', 'type': 'plain_text', 'text': 'TRUE'}]

    vars = wrangler_data.get('vars')
    if (preview := wrangler_data.get('preview')) and 'vars' in preview:
        # vars are not inherited by environments, if preview exists and vars is in it, it completely overrides vars
        # in the root namespace
        vars = preview['vars']

    if vars:
        bindings += [{'name': k, 'type': 'plain_text', 'text': v} for k, v in vars.items()]

    if authenticate:
        for namespace in wrangler_data.get('kv_namespaces', []):
            if preview_id := namespace.get('preview_id'):
                bindings.append({'name': namespace['binding'], 'type': 'kv_namespace', 'namespace_id': preview_id})

    return bindings


def build_source(wrangler_dir: Path) -> Tuple[Path, Dict[str, Any]]:
    wrangler_path = wrangler_dir / 'wrangler.toml'
    wrangler_data = toml.loads(wrangler_path.read_text())
    if wrangler_data['type'] == 'javascript':
        source_path = wrangler_dir / 'index.js'
    else:
        subprocess.run(('wrangler', 'build'), check=True, cwd=str(wrangler_dir))
        source_path = wrangler_dir / 'dist' / 'worker.js'
    assert source_path.is_file(), f'source path "{source_path}" not found'
    return source_path, wrangler_data


def get_api_token() -> str:
    if api_token := os.getenv('CLOUDFLARE_API_TOKEN'):
        return api_token

    api_token_path_str = os.getenv('CLOUDFLARE_API_TOKEN_PATH', '~/.wrangler/config/default.toml')
    api_token_path = Path(api_token_path_str).expanduser()
    return toml.loads(api_token_path.read_text())['api_token']


class WorkerError(Exception):
    def __init__(self, logs: List['LogMsg']):
        super().__init__('\n'.join(str(msg) for msg in logs))
        self.logs = logs


class TestClient(Session):
    __test__ = False

    def __init__(
        self, *, preview_id: Optional[str] = None, bindings: List[Binding] = None, fake_host: str = 'example.com'
    ):
        super().__init__()
        self._original_fake_host = fake_host
        self.fake_host = self._original_fake_host
        self.preview_id = preview_id
        self.bindings: List[Binding] = bindings or []
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
        host_regex = '^https?://' + re.escape(self.fake_host)
        path = re.sub(host_regex, '', path)
        if not path.startswith('/'):
            raise ValueError(f'path "{path}" must be relative or match "{host_regex}"')

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
                if count is None:
                    return self.inspect_logs
                else:
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
