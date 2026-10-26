"""Layer 4: budget optimisation with SLSQP, cross-checked against the closed-form KKT optimum.

For a concave response sum(b_i * f(x_i)) under sum(x_i) = B, the optimum equalises marginal ROI:
b_i * f'(x_i) = lambda for every channel not pinned at a bound. That gives an exact solution
(x_i = clip(f'^-1(lambda / b_i), lo_i, hi_i), with lambda found by bisection) which we use to
verify SLSQP on every request.
"""
import logging
import time
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from . import metrics
from .model import MixModel

log = logging.getLogger(__name__)

GAP_TOLERANCE = 1e-4   # relative objective gap above which SLSQP is considered to have under-performed
EPS = 1e-12


class OptimizationError(ValueError):
    """Infeasible or unjustifiable request; surfaced as HTTP 422."""


@dataclass
class Bounds:
    lo: float = 0.0
    hi: float | None = None


def _inverse_marginal(transform: str, beta: float, lam: float) -> float:
    """Spend x at which beta * f'(x) == lam."""
    if transform == "sqrt":
        return (beta / (2.0 * lam)) ** 2
    return beta / lam - 1.0  # log1p


def kkt_solution(transform: str, betas: np.ndarray, lo: np.ndarray, hi: np.ndarray, total: float) -> np.ndarray:
    def alloc(lam: float) -> np.ndarray:
        raw = np.array([_inverse_marginal(transform, b, lam) for b in betas])
        return np.clip(raw, lo, hi)

    lam_lo, lam_hi = 1e-12, 1.0
    while alloc(lam_hi).sum() > total:  # grow until allocation undershoots the budget
        lam_hi *= 2.0
    for _ in range(200):
        mid = np.sqrt(lam_lo * lam_hi)  # geometric bisection: lambda spans many orders of magnitude
        if alloc(mid).sum() > total:
            lam_lo = mid
        else:
            lam_hi = mid
    x = alloc(np.sqrt(lam_lo * lam_hi))
    # tiny residual from bisection: hand it to the channels with room left
    free = (x > lo + 1e-9) & (x < hi - 1e-9)
    if free.any():
        x[free] += (total - x.sum()) / free.sum()
    return np.clip(x, lo, hi)


def optimize_budget(model: MixModel, total_budget: float, bounds: dict[str, Bounds] | None = None,
                    cap_to_observed: bool = False) -> dict:
    """cap_to_observed: never put more into a channel than the most any row of the training data spent on it,
    so every recommendation stays inside the range the model was actually fitted on."""
    ds_id = model.dataset.id
    bounds = bounds or {}
    stats = {s.name: s for s in model.channel_stats()}
    channels = model.channels

    unknown = set(bounds) - set(channels)
    if unknown:
        raise OptimizationError(f"Unknown channels in constraints: {sorted(unknown)}")
    if not total_budget or total_budget <= 0:
        raise OptimizationError("Total budget must be positive")
    for c, b in bounds.items():
        if b.lo < 0 or (b.hi is not None and b.hi < b.lo):
            raise OptimizationError(f"Invalid bounds for {c}: min must be >= 0 and <= max")

    lo_all = {c: bounds.get(c, Bounds()).lo for c in channels}
    if sum(lo_all.values()) > total_budget + 1e-9:
        raise OptimizationError("Channel minimums add up to more than the total budget")

    # Statistical gating (Layer 3 feeds Layer 4): only significant, positive channels are optimised.
    # Excluded channels receive exactly their user-set minimum (default 0).
    active = [c for c in channels if stats[c].status == "active"]
    excluded = [c for c in channels if c not in active]
    remaining = total_budget - sum(lo_all[c] for c in excluded)
    if not active:
        if remaining > 1e-9:
            raise OptimizationError("No channel has a statistically significant positive effect on sales, so the "
                                    "model cannot justify allocating budget. Try more data or a different transform.")

    betas = np.array([stats[c].coef for c in active])
    lo = np.array([lo_all[c] for c in active])
    hi = np.array([bounds.get(c, Bounds()).hi if bounds.get(c, Bounds()).hi is not None else remaining
                   for c in active])
    hi = np.minimum(hi, remaining)
    observed_max = np.array([stats[c].train_max for c in active])
    if cap_to_observed:
        hi = np.minimum(hi, np.maximum(observed_max, lo))  # a user minimum above the observed max still wins
    if active and lo.sum() > remaining + 1e-9:
        raise OptimizationError("Constraints are infeasible: active channel minimums exceed the budget")
    if active and hi.sum() < remaining - 1e-9:
        if cap_to_observed:
            raise OptimizationError(
                f"With spend capped at observed levels, the significant channels ({', '.join(active)}) can absorb at "
                f"most {hi.sum():,.1f}, less than the {remaining:,.1f} to allocate. Lower the budget or allow "
                "extrapolation beyond the observed range.")
        raise OptimizationError("Constraints are infeasible: active channel min/max cannot sum to the budget")

    solver = {"method": "SLSQP", "success": True, "message": "no active channels", "iterations": 0,
              "duration_ms": 0.0, "analytic_gap": 0.0, "used": "SLSQP"}
    x_active = np.zeros(0)
    if active:
        f, fprime = model.f, model.df_

        def objective(x):  # SciPy minimises, so negate predicted sales
            return -(model.intercept + float(np.sum(betas * f(np.maximum(x, 0)))))

        def gradient(x):
            return -(betas * fprime(np.maximum(x, EPS)))

        x0 = np.clip(np.full(len(active), remaining / len(active)), lo, hi)
        x0 *= remaining / x0.sum() if x0.sum() > 0 else 1
        started = time.perf_counter()
        res = minimize(objective, x0, jac=gradient, method="SLSQP",
                       bounds=list(zip(lo, hi)),
                       constraints=[{"type": "eq", "fun": lambda x: remaining - np.sum(x),
                                     "jac": lambda x: -np.ones_like(x)}],
                       options={"ftol": 1e-12, "maxiter": 500})
        duration = time.perf_counter() - started
        metrics.OPTIMIZER_LATENCY.observe(duration)

        x_slsqp = np.clip(res.x, lo, hi)
        x_kkt = kkt_solution(model.transform, betas, lo, hi, remaining)
        obj_slsqp, obj_kkt = -objective(x_slsqp), -objective(x_kkt)
        gap = (obj_kkt - obj_slsqp) / max(abs(obj_kkt), EPS)
        metrics.OPTIMIZER_ANALYTIC_GAP.labels(ds_id).set(gap)
        budget_ok = abs(x_slsqp.sum() - remaining) <= 1e-6 * max(remaining, 1)

        used = "SLSQP"
        x_active = x_slsqp
        if not res.success or gap > GAP_TOLERANCE or not budget_ok:
            used = "closed-form (SLSQP fallback)"
            x_active = x_kkt
            log.warning("SLSQP under-performed closed-form optimum; using closed-form", extra={
                "dataset": ds_id, "slsqp_success": bool(res.success), "slsqp_message": res.message,
                "gap": gap, "budget_ok": budget_ok})
        solver = {"method": "SLSQP", "success": bool(res.success), "message": str(res.message),
                  "iterations": int(res.nit), "duration_ms": round(duration * 1000, 2),
                  "analytic_gap": float(gap), "used": used}

    allocation = {c: float(lo_all[c]) for c in excluded}
    allocation.update({c: float(v) for c, v in zip(active, x_active)})
    allocation = {c: allocation[c] for c in channels}

    # Marginal ROI should be equal across active channels that are not pinned at a bound.
    mroi = model.marginal_roi(allocation)
    interior = [c for c, l, h, v in zip(active, lo, hi, x_active) if l + 1e-6 < v < h - 1e-6]
    interior_vals = [mroi[c] for c in interior if mroi[c] is not None]
    spread = (max(interior_vals) - min(interior_vals)) / max(np.mean(interior_vals), EPS) if len(interior_vals) > 1 else 0.0

    log.info("budget optimised", extra={
        "dataset": ds_id, "budget": total_budget, "allocation": {c: round(v, 3) for c, v in allocation.items()},
        "solver_used": solver["used"], "gap": solver["analytic_gap"]})
    return {
        "allocation": allocation,
        "active": active,
        "excluded": excluded,
        "pinned": [c for c in active if c not in interior],
        "cap_to_observed": cap_to_observed,
        "at_observed_cap": [c for c, v, mx in zip(active, x_active, observed_max)
                            if cap_to_observed and v >= mx - 1e-6],
        "solver": solver,
        "marginal_roi": mroi,
        "marginal_equalized": bool(spread < 0.01),
        "marginal_spread": float(spread),
        "lambda": float(np.mean(interior_vals)) if interior_vals else None,
    }
