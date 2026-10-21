# Explainable Marketing Mix Optimizer

Splits a marketing budget across channels and explains why it chose that split, using p-values, SHAP and marginal ROI.

| Layer | Implementation | File |
|---|---|---|
| 1. Data transformation | `sqrt(spend)` (or `log1p`): builds diminishing returns into the model | `app/model.py` |
| 2. Predictive engine | `statsmodels.OLS` with an explicit constant (the zero-spend baseline) | `app/model.py` |
| 3. Explainability | p-value check, `shap.LinearExplainer`, marginal ROI, prediction intervals, extrapolation warnings | `app/model.py`, `app/explain.py` |
| 4. Optimisation | `scipy.optimize.minimize(method="SLSQP")`: total spend equals the budget, each channel stays within its min/max (default: 0 to budget). Every run is checked against the closed-form answer (see below). | `app/optimizer.py` |
| 5. Application | FastAPI REST API, plus a static dashboard served by the same app (no build step, no CDN) | `app/main.py`, `app/static/` |

## Run it

The only requirement is Docker.

```bash
docker compose up --build
```

Open <http://localhost:8000>. API docs are at <http://localhost:8000/docs>.

Run the tests (in a container, so they match production):

```bash
docker compose --profile test run --rm tests
```

To change any setting, copy `.env.example` to `.env` and edit it. For example, `HOST_PORT=9000` changes the port and `TRANSFORM=log1p` switches the transform.

## Datasets

* **ISLR Advertising** (built in): 200 markets. Spend is in $ thousands and sales are in thousands of units, so a budget of `100` means $100,000. Newspaper is not significant (p ≈ 0.6), so the model gives it $0.
* **Synthetic (known answer)** (built in): generated from `3 + 0.9√TV + 1.4√Search + 0.5√Social + 0·√Print + noise`. Use it to check that the model recovers the true coefficients and that the optimizer puts $0 into Print.
* **Upload**: any CSV with a numeric sales column and spend columns. You choose the columns in the UI. Some good public options:
  * Meta Robyn `dt_simulated_weekly` (TV, OOH, print, Facebook, search; weekly)
  * Google Meridian `national_all_channels.csv`
  * PyMC-Marketing `mmm_example.csv`

  Uploads are saved to the `mmm-storage` volume and reloaded when the app restarts.

## Why the optimizer is checked against a closed-form answer

With `sales = b0 + Σ bᵢ·√xᵢ`, the best split is where the next $1 earns the same in every channel. That means `bᵢ / (2√xᵢ)` is equal across channels, which gives **xᵢ ∝ bᵢ²**. The optimizer solves this exactly, honouring the min/max limits, and compares SLSQP's result against it on every request:

* The gap between the two is exported as `mmm_optimizer_analytic_gap_ratio`.
* If SLSQP falls short, the app logs a warning and returns the exact solution instead.

The SHAP baseline is the **average training prediction**, not the intercept. The justification reports "lift above intercept" and "SHAP vs average" separately for that reason.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/datasets` | List datasets with spend ranges and units |
| POST | `/api/datasets` | Upload a CSV (multipart: `file`, `target`, `channels`, `spend_unit`, `sales_unit`, `name`) |
| GET | `/api/datasets/{id}/model` | Coefficients, p-values, CIs, R², condition number |
| POST | `/api/datasets/{id}/optimize` | `{"budget": 100, "constraints": {"TV": {"min": 10, "max": 60}}}` |
| POST | `/api/datasets/{id}/predict` | `{"allocation": {"TV": 50, "Radio": 30}}`: explains a split you choose and compares it with the optimum |

Bad input returns `422` with `{"detail", "request_id"}`.

## Logging and monitoring

* **Logs**: one JSON object per line on stdout (or `LOG_FORMAT=text`). Every line includes a `request_id`; the app accepts one sent as `X-Request-ID` and echoes it back. There is one access line per request, plus events for model fits, optimisations, rejected requests and SLSQP fallbacks. Docker rotates the logs (10 MB × 5). Set `LOG_FILE` to also write a rotating file.
* **`/health`**: liveness check, used by the Docker `HEALTHCHECK`.
* **`/ready`**: returns 503 until the datasets are loaded and the built-in models are fitted.
* **`/metrics`**: Prometheus text format. Point any Prometheus or Grafana Agent at it.
  * `mmm_http_requests_total`, `mmm_http_request_duration_seconds`
  * `mmm_optimizations_total{status}`, `mmm_optimizer_duration_seconds`, `mmm_optimizer_analytic_gap_ratio`
  * `mmm_model_r_squared`, `mmm_model_fits_total`, `mmm_extrapolation_warnings_total{channel}`, `mmm_uploads_total`
* **Model artifacts**: for each dataset, `storage/artifacts/<dataset>/` holds `model.pickle` (statsmodels results), `model.json` (coefficients, p-values, metrics) and `summary.txt`.

## Limitations

The model has no adstock (carry-over between weeks), no seasonality and no controls. It treats each row as independent, which suits the cross-sectional Advertising data. For weekly data like Robyn's, this is a starting point rather than a full MMM.
