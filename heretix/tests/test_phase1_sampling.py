from __future__ import annotations

from pathlib import Path

from heretix.config import RunConfig
from heretix.rpl import run_single_version
from heretix.sampler import balanced_indices_with_rotation, planned_counts, rotation_offset
import yaml


PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "rpl_g5_v2.yaml"


def _expected_counts(claim: str, model: str, T: int, K: int) -> list[int]:
    doc = yaml.safe_load(PROMPT_PATH.read_text())
    T_bank = len(doc.get("paraphrases", []))
    T_stage = max(1, min(int(T), T_bank))
    off = rotation_offset(claim, model, str(doc.get("version")), T_bank)
    order = list(range(T_bank))
    if T_bank > 1 and off % T_bank != 0:
        rot = off % T_bank
        order = order[rot:] + order[:rot]
    # selected templates for this run
    _ = order[:T_stage]
    seq = balanced_indices_with_rotation(T_stage, K, offset=0)
    counts, _ratio = planned_counts(seq, T_stage)
    return counts


def test_sampling_counts_match_k8_t8_r2():
    cfg = RunConfig(
        claim="tariffs don't cause inflation",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=8,
        R=2,
        T=8,
        B=5000,
        max_output_tokens=256,
    )
    res = run_single_version(cfg, prompt_file=str(PROMPT_PATH), mock=True)
    agg = res["aggregation"]
    counts = agg["counts_by_template"]
    assert agg["n_templates"] == 8
    # expected planned counts per template (K only)
    planned = _expected_counts(cfg.claim, cfg.model, cfg.T or 8, cfg.K)
    # aggregation counts are attempts (planned * R)
    observed = sorted(counts.values())
    expected = sorted([c * cfg.R for c in planned])
    assert observed == expected


def test_sampling_counts_match_k12_t8_r3():
    cfg = RunConfig(
        claim="tariffs don't cause inflation",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=12,
        R=3,
        T=8,
        B=5000,
        max_output_tokens=256,
    )
    res = run_single_version(cfg, prompt_file=str(PROMPT_PATH), mock=True)
    agg = res["aggregation"]
    counts = agg["counts_by_template"]
    assert agg["n_templates"] == 8
    planned = _expected_counts(cfg.claim, cfg.model, cfg.T or 8, cfg.K)
    observed = sorted(counts.values())
    expected = sorted([c * cfg.R for c in planned])
    assert observed == expected


def test_sampling_counts_match_k12_t6_r3():
    cfg = RunConfig(
        claim="tariffs don't cause inflation",
        model="gpt-5",
        prompt_version="rpl_g5_v2",
        K=12,
        R=3,
        T=6,
        B=5000,
        max_output_tokens=256,
    )
    res = run_single_version(cfg, prompt_file=str(PROMPT_PATH), mock=True)
    agg = res["aggregation"]
    counts = agg["counts_by_template"]
    assert agg["n_templates"] == 6
    planned = _expected_counts(cfg.claim, cfg.model, cfg.T or 6, cfg.K)
    observed = sorted(counts.values())
    expected = sorted([c * cfg.R for c in planned])
    assert observed == expected

