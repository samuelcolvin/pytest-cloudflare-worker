from pathlib import Path

import pytest
from aiohttp.test_utils import loop_context

from .main import DeployPreview, TestClient, TestServer

__version__ = ('pytest_addoption',)


def pytest_addoption(parser):
    parser.addoption('--cf-wrangler-dir', action='store', default='.', help='directory in which to find wrangler.toml')
    parser.addoption(
        '--cf-anon-client',
        action='store_true',

        default=False,
        help=(
            "whether the anonymous cloudflare worker preview endpoint, if set "  # noqa: Q000
            "env variables, KV worker, secrets etc. won't work"
        ),
    )


@pytest.fixture(name='preview_id', scope='session')
def _fix_preview_id(request):
    """
    Deploy the preview and return the preview id.
    """
    wrangler_dir = Path(request.config.getoption('--cf-wrangler-dir')).resolve()
    anon_client: bool = request.config.getoption('--cf-anon-client')
    with loop_context(fast=True) as loop:
        deployer = DeployPreview(wrangler_dir, loop)
        if anon_client:
            preview_id = loop.run_until_complete(deployer.deploy_anon())
        else:
            preview_id = loop.run_until_complete(deployer.deploy_auth())
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
