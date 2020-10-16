from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).parent.parent


@pytest.fixture(name='code_path')
def _fix_code_path():
    path = ROOT_DIR / 'example' / 'index.js'
    assert path.is_file()
    return path
