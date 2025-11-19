from __future__ import annotations

import os
from pathlib import Path
import sys
import shutil
import pytest


@pytest.fixture(scope="session", autouse=True)
def _protect_main_db() -> None:
    """Protect the main DB during tests by backup/restore.

    Tests assume the default DB path `runs/heretix.sqlite`. To avoid polluting
    a developer's existing DB, we temporarily move it away for the session and
    restore it afterwards. This keeps tests exercising the real DB path while
    leaving the user's data untouched.
    """
    db = Path("runs/heretix.sqlite")
    bak = Path("runs/heretix.sqlite.pretest.bak")
    try:
        if db.exists():
            bak.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(db), str(bak))
    except Exception:
        # Best-effort backup; continue tests even if move fails
        pass
    try:
        yield
    finally:
        # Remove test DB and restore backup if present
        try:
            if db.exists():
                db.unlink()
        except Exception:
            pass
        try:
            if bak.exists():
                shutil.move(str(bak), str(db))
        except Exception:
            pass
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
