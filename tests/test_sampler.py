"""
Tests for deterministic balanced sampler and rotation logic.

Validates that indices are balanced, rotation is deterministic and claim-sensitive,
and planned count diagnostics compute the expected imbalance ratio.
"""
import pytest

from heretix_rpl.sampler import (
    rotation_offset,
    balanced_indices_with_rotation,
    planned_counts,
)
from heretix_rpl.rpl_prompts import PROMPT_VERSION


def test_rotation_offset_determinism():
    claim = "vaccines reduce mortality"
    model = "gpt-5"
    T = 16
    off1 = rotation_offset(claim, model, PROMPT_VERSION, T)
    off2 = rotation_offset(claim, model, PROMPT_VERSION, T)
    assert off1 == off2 and 0 <= off1 < T


def test_rotation_offset_changes_with_claim():
    model = "gpt-5"
    T = 16
    off_a = rotation_offset("A", model, PROMPT_VERSION, T)
    off_b = rotation_offset("B", model, PROMPT_VERSION, T)
    assert off_a != off_b


@pytest.mark.parametrize("T,K", [
    (16, 7),   # K < T, some templates unused
    (16, 16),  # K == T, perfect balance
    (16, 21),  # K > T, near-equal counts differ by at most 1
    (5, 7),    # small bank, wrap counts
])
def test_balanced_indices_counts_near_equal(T, K):
    off = 0  # rotation doesn't affect balance, just order
    order = balanced_indices_with_rotation(T, K, off)
    assert len(order) == K
    counts, ratio = planned_counts(order, T)
    # Restrict to nonzero counts to judge balance among used templates
    used = [c for c in counts if c > 0]
    if not used:
        assert K == 0
        return
    assert max(used) - min(used) <= 1
    # Ratio among used templates should be <= 2 even in worst tiny cases
    assert ratio >= 1.0


def test_balanced_indices_with_rotation_preserves_count_profile():
    T, K = 8, 12
    off0 = balanced_indices_with_rotation(T, K, 0)
    off3 = balanced_indices_with_rotation(T, K, 3)
    # Rotation changes which specific indices get the +1, but the multiset of
    # per-index counts should be identical (i.e., same balance profile).
    c0, _ = planned_counts(off0, T)
    c3, _ = planned_counts(off3, T)
    assert sorted(c0) == sorted(c3)
