import subprocess
from pathlib import Path

import pytest
import toml
from aiohttp.test_utils import loop_context

from .main import TestClient, TestServer, deploy_preview

__version__ = ('pytest_addoption',)


def pytest_addoption(parser):
    parser.addoption('--wrangler-dir', action='store', default='.', help='directory in which to find wrangler.toml')


@pytest.fixture(name='js_source', scope='session')
def _fix_js_source(request):
    """
    Find javascript source, optionally build using wrangler if required.
    """
    wrangler_dir = Path(request.config.getoption('--wrangler-dir')).resolve()
    assert wrangler_dir.is_dir()
    wrangler_path = wrangler_dir / 'wrangler.toml'
    assert wrangler_path.is_file()
    data = toml.loads(wrangler_path.read_text())
    if data['type'] == 'javascript':
        source_path = wrangler_dir / 'index.js'
    else:
        subprocess.run(('wrangler', 'build'), check=True)
        source_path = Path('dist/index.js')
    assert source_path.is_file()
    return source_path


@pytest.fixture(name='preview_id', scope='session')
def _fix_preview_id(js_source: Path):
    """
    Deploy the preview and return the preview id.
    """
    with loop_context(fast=True) as loop:
        preview_id = loop.run_until_complete(deploy_preview(js_source))
    return preview_id


@pytest.fixture(name='client')
def _fix_client(preview_id: str, loop):
    """
    Create a test client.
    """
    server = TestServer(preview_id, loop=loop)
    client = TestClient(server, loop=loop)
    loop.run_until_complete(client.start_server())

    yield client

    loop.run_until_complete(client.close())
