from pathlib import Path

import pytest
from aiohttp.test_utils import loop_context

from .main import TestClient, TestServer, DeployPreview

__version__ = ('pytest_addoption',)


def pytest_addoption(parser):
    parser.addoption('--wrangler-dir', action='store', default='.', help='directory in which to find wrangler.toml')


@pytest.fixture(name='preview_id', scope='session')
def _fix_preview_id(request):
    """
    Deploy the preview and return the preview id.
    """
    wrangler_dir = Path(request.config.getoption('--wrangler-dir')).resolve()
    with loop_context(fast=True) as loop:
        preview_id = loop.run_until_complete(DeployPreview(wrangler_dir, loop).deploy_anon())
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
