from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from heretix.config import RunConfig
from heretix.rpl import run_single_version


DB_PATH = Path("runs/heretix.sqlite")
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "rpl_g5_v2.yaml"


def test_prompt_len_in_outputs_and_db(tmp_path: Path):
    cfg = RunConfig(
        claim="short claim",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=4,
        R=1,
        T=4,
        B=1000,
        max_output_tokens=128,
        max_prompt_chars=5000,  # ensure not enforcing in this test
    )
    res = run_single_version(cfg, prompt_file=str(PROMPT_PATH), mock=True)
    max_len = res["aggregation"]["prompt_char_len_max"]
    assert isinstance(max_len, int) and max_len > 0
    # DB has the value in runs and executions
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute("SELECT prompt_char_len_max FROM runs WHERE run_id=?", (res["run_id"],)).fetchone()
    assert row is not None and int(row[0]) == max_len
    row2 = conn.execute("SELECT prompt_char_len_max FROM executions WHERE execution_id=?", (res["execution_id"],)).fetchone()
    assert row2 is not None and int(row2[0]) == max_len
    conn.close()


def test_prompt_len_enforcement_raises(tmp_path: Path):
    cfg = RunConfig(
        claim="this is a deliberately long claim to trigger prompt-length enforcement" * 30,
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=1,
        R=1,
        T=1,
        B=100,
        max_output_tokens=64,
        max_prompt_chars=300,  # small cap to force failure
    )
    with pytest.raises(ValueError):
        run_single_version(cfg, prompt_file=str(PROMPT_PATH), mock=True)

