"""Layer 3 output: turns model statistics, SHAP values and marginal ROI into a structured, plain-English report."""
import logging

from . import metrics
from .model import MixModel

log = logging.getLogger(__name__)


def fmt_money(value: float, unit: str) -> str:
    num = f"{value:,.2f}" if abs(value) < 100 else f"{value:,.1f}"
    if unit.startswith("$"):
        return f"${num}{unit[1:]}"
    return f"{num} {unit}"


def _p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def _p_eq(p: float) -> str:
    """'p < 0.001' / 'p = 0.042' for inline use."""
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def explain_allocation(model: MixModel, allocation: dict[str, float], opt: dict | None = None) -> dict:
    """Prediction + SHAP + per-channel diagnostics for any allocation; adds optimiser reasoning if `opt` given."""
    ds = model.dataset
    su, yu = ds.spend_unit, ds.sales_unit
    stats = {s.name: s for s in model.channel_stats()}
    total = sum(allocation.values())
    pred = model.predict(allocation)
    contrib = model.contributions(allocation)
    shap_out = model.shap_values(allocation)
    mroi = opt["marginal_roi"] if opt else model.marginal_roi(allocation)
    lift_total = sum(contrib.values())

    warnings: list[str] = []
    channels = []
    for c in model.channels:
        s, amount = stats[c], allocation[c]
        extrapolated = amount > s.train_max * 1.0001
        if extrapolated:
            metrics.EXTRAPOLATIONS.labels(ds.id, c).inc()
            warnings.append(f"{c} spend ({fmt_money(amount, su)}) is above the highest value in the training data "
                            f"({fmt_money(s.train_max, su)}); its effect is extrapolated from the fitted curve.")
        channels.append({
            "name": c, "amount": amount, "share": amount / total if total else 0.0, "status": s.status,
            "coef": s.coef, "p_value": s.p_value, "ci": [s.ci_low, s.ci_high],
            "marginal_roi": mroi[c], "contribution": contrib[c], "shap": shap_out["values"][c],
            "lift_share": contrib[c] / lift_total if lift_total > 0 else 0.0,
            "train_max": s.train_max, "extrapolated": extrapolated,
        })

    r2 = model.results.rsquared
    if r2 < 0.5:
        warnings.append(f"The model explains only {r2:.0%} of the variance in {ds.target} (R² = {r2:.2f}); "
                        "treat recommendations as directional.")
    if opt and opt["solver"]["used"] != "SLSQP":
        warnings.append("SLSQP did not reach the analytic optimum, so the closed-form solution was used instead.")

    report = {
        "total": total,
        "prediction": pred,
        "baseline": model.intercept,
        "lift_total": lift_total,
        "shap_base_value": shap_out["base_value"],
        "channels": channels,
        "warnings": warnings,
    }
    report["justification"] = _justify(model, report, opt) if opt else _describe(model, report)
    return report


def _justify(model: MixModel, rep: dict, opt: dict) -> list[str]:
    ds = model.dataset
    su, yu, alpha = ds.spend_unit, ds.sales_unit, model.alpha
    pred, ch = rep["prediction"], {c["name"]: c for c in rep["channels"]}
    lines = [
        f"This allocation of {fmt_money(rep['total'], su)} yields a maximum projected {ds.target} of "
        f"{pred['mean']:,.2f} {yu} ({pred['interval']}: {pred['low']:,.2f} to {pred['high']:,.2f}), against a "
        f"zero-spend baseline (intercept) of {rep['baseline']:,.2f} {yu}."
    ]

    active = sorted(opt["active"], key=lambda c: -ch[c]["amount"])
    if active:
        parts = [f"{c} {fmt_money(ch[c]['amount'], su)} ({ch[c]['share']:.0%}; coefficient {ch[c]['coef']:.3f}, "
                 f"{_p_eq(ch[c]['p_value'])})" for c in active]
        line = "Budget goes to the statistically significant channels: " + "; ".join(parts) + "."
        if model.transform == "sqrt" and not opt["pinned"] and len(active) > 1:
            line += (" With square-root diminishing returns, the optimal share of each channel is proportional to "
                     "its coefficient squared, so a channel with a higher coefficient receives a larger share.")
        lines.append(line)

    for c in opt["excluded"]:
        info, amt = ch[c], fmt_money(ch[c]["amount"], su)
        forced = " (your minimum)" if ch[c]["amount"] > 0 else ""
        if info["status"] == "insignificant":
            lines.append(f"{c} allocation is {amt}{forced} because its p-value ({_p(info['p_value'])}) exceeds the "
                         f"{alpha} threshold, indicating no statistically significant impact on {ds.target}.")
        else:
            lines.append(f"{c} allocation is {amt}{forced} because its coefficient is negative "
                         f"({info['coef']:.3f}): more spend predicts lower {ds.target}.")

    interior = [c for c in active if c not in opt["pinned"]]
    if opt["lambda"] is not None and len(interior) > 1:
        vals = ", ".join(f"{c} {ch[c]['marginal_roi']:.4f}" for c in interior)
        lines.append(
            f"Marginal ROI is equalised: at this split the next {fmt_money(1, su)} returns about {opt['lambda']:.4f} "
            f"{yu} in every unconstrained channel ({vals}). Moving money from one channel to another would therefore "
            "lose more than it gains, which is why this is the optimum.")
    if opt["pinned"]:
        lines.append("Channels held at a min/max constraint: " + ", ".join(opt["pinned"]) +
                     ". Their marginal ROI can differ from the others because the constraint, not the model, sets their spend.")

    lift = rep["lift_total"]
    if active and lift > 0:
        top = max(active, key=lambda c: ch[c]["contribution"])
        lines.append(
            f"Lift above the intercept totals {lift:,.2f} {yu}; {top} alone drives {ch[top]['lift_share']:.0%} of it. "
            f"SHAP attribution, measured against the average training prediction ({rep['shap_base_value']:,.2f} {yu}), "
            "is " + ", ".join(f"{c['name']} {c['shap']:+,.2f}" for c in rep["channels"]) + ".")
    s = opt["solver"]
    lines.append(f"Solver: {s['used']} (gap to closed-form optimum {s['analytic_gap']:.1e}, {s['iterations']} "
                 f"iterations, {s['duration_ms']} ms).")
    return lines


def _describe(model: MixModel, rep: dict) -> list[str]:
    ds = model.dataset
    pred = rep["prediction"]
    lines = [f"This split of {fmt_money(rep['total'], ds.spend_unit)} is predicted to produce {pred['mean']:,.2f} "
             f"{ds.sales_unit} ({pred['interval']}: {pred['low']:,.2f} to {pred['high']:,.2f})."]
    lines.append("SHAP attribution against the average training prediction "
                 f"({rep['shap_base_value']:,.2f}): " +
                 ", ".join(f"{c['name']} {c['shap']:+,.2f}" for c in rep["channels"]) + ".")
    finite = {c["name"]: c["marginal_roi"] for c in rep["channels"] if c["marginal_roi"] is not None and c["status"] == "active"}
    if len(finite) > 1:
        best, worst = max(finite, key=finite.get), min(finite, key=finite.get)
        if finite[best] > finite[worst] * 1.01:
            lines.append(f"Marginal ROI is not equalised: the next unit of spend earns {finite[best]:.4f} in {best} "
                         f"but only {finite[worst]:.4f} in {worst}, so shifting budget from {worst} to {best} would raise sales.")
    return lines
