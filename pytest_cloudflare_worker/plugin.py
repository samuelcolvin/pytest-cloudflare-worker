from pathlib import Path

import pytest

from .main import TestClient, deploy

__version__ = ('pytest_addoption',)


def pytest_addoption(parser):
    parser.addoption('--cf-wrangler-dir', action='store', default='.', help='directory in which to find wrangler.toml')
    parser.addoption(
        '--cf-auth-client',
        action='store_true',
        default=False,
        help=(
            'whether to use the authenticated cloudflare worker preview endpoint, the KV worker database '
            'will only work with this set'
        ),
    )


@pytest.fixture(name='session_client', scope='session')
def _fix_session_client(request):
    """
    Create a test client and deploy the worker preview to cloudflare.
    """
    wrangler_dir = Path(request.config.getoption('--cf-wrangler-dir')).resolve()
    auth_client: bool = request.config.getoption('--cf-auth-client')
    client = TestClient()
    preview_id, bindings = deploy(wrangler_dir, authenticate=auth_client, test_client=client)
    client.preview_id = preview_id
    client.bindings = bindings

    yield client

    client.close()


@pytest.fixture(name='client')
def _fix_client(session_client: TestClient):
    """
    Create a test client.
    """
    session_client.new_cf_session()

    return session_client
