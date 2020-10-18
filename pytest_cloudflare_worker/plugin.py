from pathlib import Path

import pytest

from .main import DeployPreview, TestClient

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


@pytest.fixture(name='session_client', scope='session')
def _fix_session_client(request):
    """
    Create a test client and deploy the worker preview to cloudflare.
    """
    wrangler_dir = Path(request.config.getoption('--cf-wrangler-dir')).resolve()
    anon_client: bool = request.config.getoption('--cf-anon-client')
    client = TestClient()
    deployer = DeployPreview(wrangler_dir, client)
    if anon_client:
        client.preview_id = deployer.deploy_anon()
    else:
        client.preview_id = deployer.deploy_auth()
    yield client

    client.close()


@pytest.fixture(name='client')
def _fix_client(session_client: TestClient):
    """
    Create a test client.
    """
    session_client.new_cf_session()

    return session_client
