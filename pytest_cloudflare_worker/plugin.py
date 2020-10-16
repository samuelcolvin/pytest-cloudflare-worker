import subprocess
from pathlib import Path

import pytest
import rtoml
from aiohttp.test_utils import loop_context

from .main import deploy_preview, TestServer, TestClient
__version__ = ('pytest_addoption',)


def pytest_addoption(parser):  # type: ignore
    parser.addoption(
        '--wrangler-dir', action='store', default='.',
        help='which directory to find wrangler.toml in')


@pytest.fixture(name='load_source', scope='session')
def _fix_load_source(request):
    """
    Load source from wrangler, optionally building if required.
    """
    wrangler_dir = Path(request.config.getoption('--wrangler-dir')).resolve()
    assert wrangler_dir.is_dir()
    wrangler_path = wrangler_dir / 'wrangler.toml'
    assert wrangler_path.is_file()
    data = rtoml.loads(wrangler_path.read_text())
    if data['type'] == 'javascript':
        source_path = wrangler_dir / 'index.js'
    else:
        subprocess.run(('wrangler', 'build'), check=True)
        source_path = Path('dist/index.js')
    assert source_path.is_file()
    return source_path


@pytest.fixture(name='preview_id', scope='session')
def _fix_preview_id(load_source: Path):
    """
    Deploy the preview and return the preview id.
    """
    with loop_context(fast=True) as loop:
        preview_id = loop.run_until_complete(deploy_preview(load_source))
    return preview_id


@pytest.fixture(name='client')
async def _fix_client(preview_id: str, loop):
    """
    Create a test client.
    """
    server = TestServer(preview_id, loop=loop)
    async with TestClient(server, loop=loop) as client:
        yield client
