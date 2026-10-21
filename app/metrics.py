"""Prometheus metrics, exposed at GET /metrics.

Labels are kept low-cardinality: routes use their template ("/api/datasets/{dataset_id}"),
never the raw path, and dataset ids are bounded by what users upload.
"""
from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter("mmm_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "mmm_http_request_duration_seconds", "HTTP request latency", ["route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

MODEL_FITS = Counter("mmm_model_fits_total", "Model fits", ["dataset", "status"])
MODEL_R2 = Gauge("mmm_model_r_squared", "R-squared of the fitted model", ["dataset"])
MODEL_ADJ_R2 = Gauge("mmm_model_adj_r_squared", "Adjusted R-squared of the fitted model", ["dataset"])

OPTIMIZATIONS = Counter("mmm_optimizations_total", "Budget optimisations", ["dataset", "status"])
OPTIMIZER_LATENCY = Histogram(
    "mmm_optimizer_duration_seconds", "SLSQP solve time",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)
OPTIMIZER_ANALYTIC_GAP = Gauge(
    "mmm_optimizer_analytic_gap_ratio",
    "Relative gap between SLSQP and closed-form optimum (last run; ~0 is healthy)", ["dataset"],
)
EXTRAPOLATIONS = Counter(
    "mmm_extrapolation_warnings_total", "Recommendations outside the training spend range", ["dataset", "channel"],
)
UPLOADS = Counter("mmm_uploads_total", "Dataset uploads", ["status"])
