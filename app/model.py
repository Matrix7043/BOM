"""Layers 1-3: diminishing-returns transform, OLS predictive engine, and explainability primitives."""
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from . import metrics
from .data import Dataset

log = logging.getLogger(__name__)

try:
    import shap  # heavy import (numba); optional so the API still works if it is unavailable
    SHAP_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the environment
    shap = None
    SHAP_AVAILABLE = False
    log.warning("shap not importable; using the exact closed-form linear SHAP values instead")


# Each transform: f(x), f'(x). Both are concave on x >= 0, which is what makes the optimum unique.
TRANSFORMS = {
    "sqrt": (np.sqrt, lambda x: 0.5 / np.sqrt(x)),
    "log1p": (np.log1p, lambda x: 1.0 / (1.0 + x)),
}


@dataclass
class ChannelStats:
    name: str
    coef: float
    std_err: float
    p_value: float
    ci_low: float
    ci_high: float
    status: str  # "active" | "insignificant" | "negative"
    train_min: float
    train_max: float
    train_mean: float


class MixModel:
    def __init__(self, dataset: Dataset, transform: str, alpha: float):
        if transform not in TRANSFORMS:
            raise ValueError(f"Unknown transform {transform!r}")
        self.dataset = dataset
        self.transform = transform
        self.alpha = alpha
        self.f, self.df_ = TRANSFORMS[transform]
        self.channels = dataset.channels
        self.results = None
        self.fitted_at: float | None = None

    # -- Layer 1 -----------------------------------------------------------------
    def features(self, spend: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({f"{self.transform}_{c}": self.f(spend[c].astype(float)) for c in self.channels},
                            index=spend.index)

    # -- Layer 2 -----------------------------------------------------------------
    def fit(self) -> "MixModel":
        started = time.perf_counter()
        try:
            X = sm.add_constant(self.features(self.dataset.df), has_constant="add")
            y = self.dataset.df[self.dataset.target].astype(float)
            self.results = sm.OLS(y, X).fit()
        except Exception:
            metrics.MODEL_FITS.labels(self.dataset.id, "error").inc()
            raise
        self._X_train = X
        self.fitted_at = time.time()
        metrics.MODEL_FITS.labels(self.dataset.id, "ok").inc()
        metrics.MODEL_R2.labels(self.dataset.id).set(self.results.rsquared)
        metrics.MODEL_ADJ_R2.labels(self.dataset.id).set(self.results.rsquared_adj)
        log.info("model fitted", extra={
            "dataset": self.dataset.id, "transform": self.transform, "rows": int(self.results.nobs),
            "r2": round(self.results.rsquared, 4), "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        })
        if self.results.condition_number > 1000:
            log.warning("high condition number; channel effects may be collinear",
                        extra={"dataset": self.dataset.id, "condition_number": round(self.results.condition_number)})
        return self

    @property
    def intercept(self) -> float:
        return float(self.results.params["const"])

    def coef(self, channel: str) -> float:
        return float(self.results.params[f"{self.transform}_{channel}"])

    def channel_stats(self) -> list[ChannelStats]:
        ci = self.results.conf_int(alpha=self.alpha)
        spend = self.dataset.df
        out = []
        for c in self.channels:
            key = f"{self.transform}_{c}"
            coef, p = float(self.results.params[key]), float(self.results.pvalues[key])
            if p > self.alpha:
                status = "insignificant"
            elif coef <= 0:
                status = "negative"
            else:
                status = "active"
            out.append(ChannelStats(c, coef, float(self.results.bse[key]), p, float(ci.loc[key, 0]),
                                    float(ci.loc[key, 1]), status, float(spend[c].min()), float(spend[c].max()),
                                    float(spend[c].mean())))
        return out

    def summary(self) -> dict:
        r = self.results
        return {
            "dataset": self.dataset.id,
            "transform": self.transform,
            "alpha": self.alpha,
            "equation": f"{self.dataset.target} = b0 + " + " + ".join(f"b_{c}*{self.transform}({c})" for c in self.channels),
            "intercept": self.intercept,
            "intercept_p_value": float(r.pvalues["const"]),
            "channels": [vars(s) for s in self.channel_stats()],
            "r_squared": float(r.rsquared),
            "adj_r_squared": float(r.rsquared_adj),
            "f_p_value": float(r.f_pvalue),
            "aic": float(r.aic),
            "residual_sd": float(np.sqrt(r.scale)),
            "condition_number": float(r.condition_number),
            "n_obs": int(r.nobs),
            "fitted_at": self.fitted_at,
            "shap_backend": "shap.LinearExplainer" if SHAP_AVAILABLE else "closed-form",
        }

    def save_artifacts(self, folder: Path) -> None:
        """Persist the fitted statsmodels object plus a human-readable JSON of the parameters."""
        folder.mkdir(parents=True, exist_ok=True)
        self.results.save(str(folder / "model.pickle"))
        (folder / "model.json").write_text(json.dumps(self.summary(), indent=2))
        (folder / "summary.txt").write_text(str(self.results.summary()))

    # -- Prediction & Layer 3 primitives -------------------------------------------
    def _design(self, alloc: dict[str, float]) -> pd.DataFrame:
        spend = pd.DataFrame([{c: float(alloc.get(c, 0.0)) for c in self.channels}])
        return sm.add_constant(self.features(spend), has_constant="add")

    def predict(self, alloc: dict[str, float]) -> dict:
        frame = self.results.get_prediction(self._design(alloc)).summary_frame(alpha=self.alpha)
        row = frame.iloc[0]
        # low/high: where a single market would land (includes residual noise).
        # mean_low/mean_high: where the *expected* sales lie (coefficient uncertainty only).
        return {"mean": float(row["mean"]), "low": float(row["obs_ci_lower"]), "high": float(row["obs_ci_upper"]),
                "mean_low": float(row["mean_ci_lower"]), "mean_high": float(row["mean_ci_upper"]),
                "interval": f"{int((1 - self.alpha) * 100)}% prediction interval"}

    def gain(self, new: dict[str, float], base: dict[str, float]) -> dict:
        """Expected sales change from `base` to `new`, with a worst/best-case confidence bound.

        The intercept cancels, so the difference is d @ beta with d = f(new) - f(base); its variance is
        d' Cov(beta) d. Comparing two plans this way is much tighter than subtracting two separate intervals,
        because the shared uncertainty (intercept, common coefficients) cancels out. The bound covers
        coefficient uncertainty only; it assumes the curve's shape holds, which is only checkable inside
        the observed spend range.
        """
        d = (self._design(new) - self._design(base)).values[0]
        value = float(d @ self.results.params.values)
        se = float(np.sqrt(max(d @ self.results.cov_params().values @ d, 0.0)))
        t = float(stats.t.ppf(1 - self.alpha / 2, self.results.df_resid))
        base_mean = self.predict(base)["mean"]
        pct = (lambda v: v / base_mean if base_mean > 0 else None)
        return {"value": value, "low": value - t * se, "high": value + t * se, "se": se,
                "pct": pct(value), "pct_low": pct(value - t * se), "pct_high": pct(value + t * se),
                "interval": f"{int((1 - self.alpha) * 100)}% confidence bound"}

    def contributions(self, alloc: dict[str, float]) -> dict[str, float]:
        """Lift of each channel above the zero-spend baseline (the intercept)."""
        return {c: self.coef(c) * float(self.f(max(alloc.get(c, 0.0), 0.0))) for c in self.channels}

    def shap_values(self, alloc: dict[str, float]) -> dict:
        """SHAP attribution relative to the *average* training prediction (not the intercept)."""
        X = self._X_train.drop(columns="const")
        x = self._design(alloc).drop(columns="const")
        coefs = np.array([self.coef(c) for c in self.channels])
        if SHAP_AVAILABLE:
            masker = shap.maskers.Independent(X.values, max_samples=len(X))
            explainer = shap.LinearExplainer((coefs, self.intercept), masker)
            values = np.asarray(explainer.shap_values(x.values))[0]
            base = float(np.ravel(explainer.expected_value)[0])
        else:
            means = X.values.mean(axis=0)
            values = coefs * (x.values[0] - means)
            base = float(self.intercept + coefs @ means)
        return {"base_value": base, "values": dict(zip(self.channels, map(float, values)))}

    def marginal_roi(self, alloc: dict[str, float]) -> dict[str, float | None]:
        """d(sales)/d(spend) per channel: the value of the next unit of spend. None = unbounded (spend at 0)."""
        out: dict[str, float | None] = {}
        for c in self.channels:
            x = float(alloc.get(c, 0.0))
            if self.transform == "sqrt" and x <= 0:
                out[c] = None if self.coef(c) > 0 else 0.0
            else:
                out[c] = self.coef(c) * float(self.df_(x))
        return out

    def response_curve(self, channel: str, upto: float, points: int = 60) -> list[list[float]]:
        xs = np.linspace(0, max(upto, 1e-9), points)
        return [[float(x), float(self.coef(channel) * self.f(x))] for x in xs]
