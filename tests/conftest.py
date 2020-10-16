from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).parent.parent


@pytest.fixture(name='wrangler_dir')
def _fix_wrangler_dir():
    path = ROOT_DIR / 'example'
    assert path.is_dir()
    return path
