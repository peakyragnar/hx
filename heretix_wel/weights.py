from __future__ import annotations

from math import exp, log, sqrt
from typing import Tuple


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def logit(p: float, eps: float = 1e-6) -> float:
    p = clamp01(p)
    p = min(max(p, eps), 1 - eps)
    return log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + exp(-x))


def recency_score(claim_is_timely: bool, median_age_days: float, tau_days: float = 7.0) -> float:
    r_claim = 1.0 if claim_is_timely else 0.0
    r_docs = exp(-max(median_age_days, 0.0) / max(tau_days, 1e-6))
    return clamp01(0.3 * r_claim + 0.7 * r_docs)


def strength_score(
    n_docs: int,
    n_domains: int,
    dispersion: float,
    json_valid_rate: float = 1.0,
) -> float:
    coverage = 1.0 - exp(-max(n_docs, 0) / 12.0)
    diversity = min(1.0, max(n_domains, 0) / 6.0)
    agreement = 1.0 - min(1.0, max(dispersion, 0.0) / 0.25)
    base = 0.5 * coverage + 0.3 * diversity + 0.2 * agreement
    return clamp01(base * clamp01(json_valid_rate))


def web_weight(r: float, s: float, wmin: float = 0.20, wmax: float = 0.90) -> float:
    w = 0.6 * clamp01(r) + 0.4 * clamp01(s)
    return max(wmin, min(wmax, w))


def var_from_ci_prob(lo_p: float, hi_p: float) -> float:
    lo_l = logit(lo_p)
    hi_l = logit(hi_p)
    sigma = (hi_l - lo_l) / (2.0 * 1.96)
    return max(sigma, 0.0) ** 2


def fuse_probabilities(
    prior_p: float,
    prior_ci: Tuple[float, float],
    web_p: float,
    web_ci: Tuple[float, float],
    w: float,
) -> Tuple[float, Tuple[float, float]]:
    lp = logit(prior_p)
    lw = logit(web_p)
    vp = var_from_ci_prob(*prior_ci)
    vw = var_from_ci_prob(*web_ci)
    weight = clamp01(w)
    l_post = (1.0 - weight) * lp + weight * lw
    v_post = (1.0 - weight) ** 2 * vp + (weight**2) * vw
    sigma = sqrt(max(v_post, 0.0))
    lo_l = l_post - 1.96 * sigma
    hi_l = l_post + 1.96 * sigma
    return sigmoid(l_post), (sigmoid(lo_l), sigmoid(hi_l))
