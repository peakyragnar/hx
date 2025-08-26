from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import os
import json
import yaml


@dataclass
class RunConfig:
    claim: str
    model: str = "gpt-5"
    prompt_version: str = "rpl_g5_v2"
    K: int = 8
    R: int = 2
    T: Optional[int] = None  # number of templates to use (defaults to all in YAML)
    B: int = 5000
    seed: Optional[int] = None
    max_output_tokens: int = 1024
    no_cache: bool = False
    prompts_file: Optional[str] = None  # explicit path; defaults by prompt_version

    # Derived at runtime; not part of input
    prompt_file_path: Optional[str] = None


def load_run_config(path: str | Path) -> RunConfig:
    p = Path(path)
    data = yaml.safe_load(p.read_text()) if p.suffix in {".yaml", ".yml"} else json.loads(p.read_text())
    cfg = RunConfig(**data)
    # env overrides
    if os.getenv("HERETIX_RPL_SEED") is not None:
        try:
            cfg.seed = int(os.getenv("HERETIX_RPL_SEED"))
        except Exception:
            pass
    if os.getenv("HERETIX_RPL_NO_CACHE"):
        cfg.no_cache = True
    if cfg.prompts_file is None:
        # default prompts path by version name
        cfg.prompt_file_path = str(Path(__file__).parent / "prompts" / f"{cfg.prompt_version}.yaml")
    else:
        cfg.prompt_file_path = cfg.prompts_file
    return cfg

