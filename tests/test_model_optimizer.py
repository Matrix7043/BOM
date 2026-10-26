from pathlib import Path

import numpy as np
import pytest

from app.data import SYNTHETIC_TRUTH, load_advertising, make_synthetic
from app.explain import explain_allocation
from app.model import MixModel
from app.optimizer import Bounds, OptimizationError, optimize_budget

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def synth():
    return MixModel(make_synthetic(), "sqrt", 0.05).fit()


@pytest.fixture(scope="module")
def adv():
    return MixModel(load_advertising(DATA), "sqrt", 0.05).fit()


def test_synthetic_recovers_true_coefficients(synth):
    for s in synth.channel_stats():
        true = SYNTHETIC_TRUTH["coefficients"][s.name]
        assert s.ci_low <= true <= s.ci_high, s
    status = {s.name: s.status for s in synth.channel_stats()}
    assert status["Print"] == "insignificant"
    assert {status[c] for c in ("TV", "Search", "Social")} == {"active"}


def test_optimum_matches_closed_form_and_equalises_marginal_roi(synth):
    budget = 200.0
    opt = optimize_budget(synth, budget)
    alloc = opt["allocation"]
    assert sum(alloc.values()) == pytest.approx(budget, rel=1e-6)
    assert alloc["Print"] == 0.0
    betas = {c: synth.coef(c) for c in ("TV", "Search", "Social")}
    total_sq = sum(b * b for b in betas.values())
    for c, b in betas.items():  # sqrt model: share proportional to beta^2
        assert alloc[c] == pytest.approx(budget * b * b / total_sq, rel=1e-3)
    assert opt["marginal_equalized"]
    assert opt["solver"]["analytic_gap"] < 1e-6


def test_optimum_beats_random_splits(synth):
    budget = 150.0
    best = synth.predict(optimize_budget(synth, budget)["allocation"])["mean"]
    active = ["TV", "Search", "Social"]  # Print is excluded by its p-value, so compare within the same channels
    rng = np.random.default_rng(0)
    for _ in range(200):
        w = rng.dirichlet(np.ones(len(active)))
        assert synth.predict(dict(zip(active, w * budget)))["mean"] <= best + 1e-9


def test_advertising_excludes_newspaper(adv):
    opt = optimize_budget(adv, 100.0)
    assert opt["allocation"]["Newspaper"] == 0.0
    assert "Newspaper" in opt["excluded"]
    report = explain_allocation(adv, opt["allocation"], opt)
    text = " ".join(report["justification"])
    assert "Newspaper allocation is $0.00K because its p-value" in text
    assert "Marginal ROI is equalised" in text


def test_bounds_are_respected(adv):
    opt = optimize_budget(adv, 100.0, {"TV": Bounds(0, 20), "Newspaper": Bounds(5, None)})
    a = opt["allocation"]
    assert a["TV"] == pytest.approx(20)
    assert a["Newspaper"] == pytest.approx(5)
    assert sum(a.values()) == pytest.approx(100.0)
    assert "TV" in opt["pinned"]


@pytest.mark.parametrize("budget,bounds", [
    (-5, {}),
    (10, {"TV": Bounds(8, None), "Radio": Bounds(8, None)}),
    (100, {"TV": Bounds(0, 10), "Radio": Bounds(0, 10)}),
    (100, {"Nope": Bounds()}),
])
def test_infeasible_requests_raise(adv, budget, bounds):
    with pytest.raises(OptimizationError):
        optimize_budget(adv, budget, bounds)


def test_shap_values_sum_to_prediction(adv):
    alloc = {"TV": 150, "Radio": 50, "Newspaper": 0}
    s = adv.shap_values(alloc)
    assert s["base_value"] + sum(s["values"].values()) == pytest.approx(adv.predict(alloc)["mean"], rel=1e-6)


def test_log1p_transform():
    m = MixModel(make_synthetic(), "log1p", 0.05).fit()
    opt = optimize_budget(m, 200.0)
    assert sum(opt["allocation"].values()) == pytest.approx(200.0)
    assert opt["solver"]["analytic_gap"] < 1e-6


def test_extrapolation_is_flagged(adv):
    opt = optimize_budget(adv, 2000.0)
    report = explain_allocation(adv, opt["allocation"], opt)
    assert any("extrapolated" in w for w in report["warnings"])


def test_cap_to_observed_keeps_every_channel_in_range(adv):
    df = adv.dataset.df
    current = {c: float(df[c].mean()) for c in adv.channels}
    budget = sum(current.values())
    opt = optimize_budget(adv, budget, cap_to_observed=True)
    a = opt["allocation"]
    assert sum(a.values()) == pytest.approx(budget)
    assert all(a[c] <= df[c].max() + 1e-6 for c in adv.channels)
    assert a["Radio"] == pytest.approx(df["Radio"].max())  # Radio's optimum is beyond its observed max
    assert opt["at_observed_cap"] == ["Radio"]
    report = explain_allocation(adv, a, opt)
    assert not report["warnings"] or all("extrapolated" not in w for w in report["warnings"])
    assert any("capped at the highest level" in line for line in report["justification"])


def test_cap_to_observed_rejects_budget_beyond_observed_range(adv):
    with pytest.raises(OptimizationError, match="capped at observed levels"):
        optimize_budget(adv, 1000.0, cap_to_observed=True)


def test_gain_bound_matches_difference_of_predictions(adv):
    base = {"TV": 147.0, "Radio": 23.3, "Newspaper": 30.6}
    new = {"TV": 151.3, "Radio": 49.6, "Newspaper": 0.0}
    g = adv.gain(new, base)
    assert g["value"] == pytest.approx(adv.predict(new)["mean"] - adv.predict(base)["mean"])
    assert g["low"] < g["value"] < g["high"]
    assert g["low"] > 0  # the capped move is a reliable improvement
    # comparing plans directly is tighter than subtracting two independent intervals
    pn, pb = adv.predict(new), adv.predict(base)
    assert g["high"] - g["low"] < (pn["mean_high"] - pn["mean_low"]) + (pb["mean_high"] - pb["mean_low"])
