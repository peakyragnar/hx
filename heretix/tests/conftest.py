from __future__ import annotations

import os
from pathlib import Path
import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_db_path(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Ensure tests write to an isolated SQLite file, not the main DB.

    This prevents test executions from polluting `runs/heretix.sqlite`.
    """
    db_dir = tmp_path_factory.mktemp("heretix_db")
    os.environ["HERETIX_DB_PATH"] = str(Path(db_dir) / "heretix_test.sqlite")
    # Nothing to yield; env var is set for the entire session
