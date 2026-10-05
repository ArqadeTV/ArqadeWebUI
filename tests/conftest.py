import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Never touch the real ~/.arqade during tests."""
    monkeypatch.setenv("ARQADE_HOME", str(tmp_path / "arqade_home"))
    from arqade import scanner

    scanner.STATE.models = {}
    scanner.STATE.running = False
    scanner.STATE.cancel = False
    yield
