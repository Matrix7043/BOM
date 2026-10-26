"""Layer 5: FastAPI application exposing the model, optimiser and explainability as REST endpoints."""
import logging
import re
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from . import metrics
from .config import APP_VERSION, get_settings
from .data import DatasetError, DatasetStore, parse_upload
from .explain import explain_allocation, fmt_money
from .logging_setup import configure_logging, request_id_var
from .model import MixModel
from .optimizer import Bounds, OptimizationError, optimize_budget

settings = get_settings()
configure_logging(settings.log_level, settings.log_format, settings.log_file)
log = logging.getLogger("mmm.api")

STATIC_DIR = Path(__file__).parent / "static"
STARTED_AT = time.time()
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class ModelRegistry:
    """Fits each dataset's model once, caches it, and writes its artifacts to storage/artifacts/<dataset>/."""

    def __init__(self):
        self._models: dict[str, MixModel] = {}
        self._lock = threading.Lock()

    def get(self, dataset_id: str) -> MixModel:
        ds = store.get(dataset_id)
        if ds is None:
            raise HTTPException(404, f"Unknown dataset {dataset_id!r}")
        with self._lock:
            if dataset_id not in self._models:
                model = MixModel(ds, settings.transform, settings.significance_alpha).fit()
                try:
                    model.save_artifacts(settings.artifacts_dir / dataset_id)
                except OSError:
                    log.exception("could not write model artifacts", extra={"dataset": dataset_id})
                self._models[dataset_id] = model
            return self._models[dataset_id]

    def __len__(self) -> int:
        return len(self._models)


store = DatasetStore(settings)
registry = ModelRegistry()
state = {"ready": False}


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("starting", extra={"version": APP_VERSION, "env": settings.app_env, "transform": settings.transform,
                                "alpha": settings.significance_alpha})
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    store.load()
    for ds in store.all():
        if ds.source == "builtin":
            registry.get(ds.id)
    state["ready"] = True
    log.info("ready", extra={"datasets": len(store.all()), "models": len(registry)})
    yield
    log.info("shutting down")


app = FastAPI(title="Explainable Marketing Mix Optimizer", version=APP_VERSION, lifespan=lifespan)


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "")
    rid = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex[:12]
    token = request_id_var.set(rid)
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = rid
        if request.url.path == "/" or request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-cache"  # revalidate via ETag so redeploys show immediately
        return response
    finally:
        elapsed = time.perf_counter() - started
        route = request.scope.get("route")
        route_label = getattr(route, "path", "unmatched")
        metrics.HTTP_REQUESTS.labels(request.method, route_label, str(status)).inc()
        metrics.HTTP_LATENCY.labels(route_label).observe(elapsed)
        if route_label not in ("/health", "/metrics") and not route_label.startswith("/static"):
            log.info("request", extra={"method": request.method, "path": request.url.path, "status": status,
                                       "duration_ms": round(elapsed * 1000, 1)})
        request_id_var.reset(token)


@app.exception_handler(DatasetError)
@app.exception_handler(OptimizationError)
async def validation_error(request: Request, exc: ValueError):
    log.warning("rejected request", extra={"reason": str(exc)})
    return JSONResponse(status_code=422, content={"detail": str(exc), "request_id": request_id_var.get()})


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id_var.get()})


# -- Ops endpoints -----------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION, "env": settings.app_env,
            "uptime_s": round(time.time() - STARTED_AT, 1)}


@app.get("/ready")
def ready():
    body = {"ready": state["ready"], "datasets": len(store.all()), "models_loaded": len(registry)}
    return JSONResponse(body, status_code=200 if state["ready"] else 503)


@app.get("/metrics")
def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# -- API -----------------------------------------------------------------------------

class ChannelBounds(BaseModel):
    min: float = Field(0.0, ge=0)
    max: float | None = Field(None, ge=0)


class OptimizeRequest(BaseModel):
    budget: float = Field(..., gt=0, description="Total budget, in the dataset's spend unit")
    constraints: dict[str, ChannelBounds] = Field(default_factory=dict)
    cap_to_observed: bool = Field(False, description="Cap each channel at the highest spend seen in the data")


class PredictRequest(BaseModel):
    allocation: dict[str, float]


class CompareRequest(BaseModel):
    current: dict[str, float] = Field(..., description="The split in use today; its total is the budget compared")


def _clean_allocation(model: MixModel, allocation: dict[str, float]) -> dict[str, float]:
    unknown = set(allocation) - set(model.channels)
    if unknown:
        raise OptimizationError(f"Unknown channels: {sorted(unknown)}")
    if any(v < 0 for v in allocation.values()):
        raise OptimizationError("Spend cannot be negative")
    return {c: float(allocation.get(c, 0.0)) for c in model.channels}


def _curves(model: MixModel, allocation: dict[str, float]) -> dict:
    stats = {s.name: s for s in model.channel_stats()}
    return {c: model.response_curve(c, max(stats[c].train_max, allocation.get(c, 0)) * 1.25) for c in model.channels}


@app.get("/api/datasets")
def list_datasets():
    return [ds.summary() for ds in store.all()]


@app.get("/api/datasets/{dataset_id}")
def get_dataset(dataset_id: str):
    ds = store.get(dataset_id)
    if ds is None:
        raise HTTPException(404, f"Unknown dataset {dataset_id!r}")
    return ds.summary()


@app.post("/api/datasets", status_code=201)
async def upload_dataset(file: UploadFile = File(...), name: str = Form(""), target: str = Form(...),
                         channels: str = Form(..., description="Comma-separated spend column names"),
                         spend_unit: str = Form("$"), sales_unit: str = Form("units")):
    raw = await file.read(int(settings.max_upload_mb * 1_000_000) + 1)
    try:
        ds = parse_upload(raw, name=name or Path(file.filename or "upload").stem, target=target,
                          channels=channels.split(","), spend_unit=spend_unit, sales_unit=sales_unit,
                          settings=settings)
    except DatasetError:
        metrics.UPLOADS.labels("rejected").inc()
        raise
    store.add(ds)
    metrics.UPLOADS.labels("ok").inc()
    log.info("dataset uploaded", extra={"dataset": ds.id, "rows": len(ds.df), "channels": ds.channels})
    return {"dataset": ds.summary(), "model": registry.get(ds.id).summary()}


@app.get("/api/datasets/{dataset_id}/model")
def model_summary(dataset_id: str):
    return registry.get(dataset_id).summary()


@app.post("/api/datasets/{dataset_id}/optimize")
def optimize(dataset_id: str, req: OptimizeRequest):
    model = registry.get(dataset_id)
    bounds = {c: Bounds(b.min, b.max) for c, b in req.constraints.items()}
    try:
        opt = optimize_budget(model, req.budget, bounds, cap_to_observed=req.cap_to_observed)
    except OptimizationError:
        metrics.OPTIMIZATIONS.labels(dataset_id, "rejected").inc()
        raise
    except Exception:
        metrics.OPTIMIZATIONS.labels(dataset_id, "error").inc()
        raise
    metrics.OPTIMIZATIONS.labels(dataset_id, "ok").inc()
    report = explain_allocation(model, opt["allocation"], opt)
    return {"budget": req.budget, "dataset": dataset_id, **report,
            "solver": opt["solver"], "marginal_equalized": opt["marginal_equalized"],
            "marginal_spread": opt["marginal_spread"], "curves": _curves(model, opt["allocation"])}


@app.post("/api/datasets/{dataset_id}/predict")
def predict(dataset_id: str, req: PredictRequest):
    """Explain a user-proposed split and compare it with the optimum for the same total."""
    model = registry.get(dataset_id)
    allocation = _clean_allocation(model, req.allocation)
    report = explain_allocation(model, allocation)
    total = sum(allocation.values())
    if total > 0:
        try:
            best = model.predict(optimize_budget(model, total)["allocation"])["mean"]
            report["optimal_for_same_total"] = best
            report["justification"].append(
                f"The optimal split of the same total is predicted to produce {best:,.2f} {model.dataset.sales_unit} "
                f"({best - report['prediction']['mean']:+,.2f} versus this split).")
        except OptimizationError:
            pass
    return {"dataset": dataset_id, **report, "curves": _curves(model, allocation)}


@app.post("/api/datasets/{dataset_id}/compare")
def compare(dataset_id: str, req: CompareRequest):
    """Current split vs the optimum capped at observed spend vs the unconstrained optimum, same total budget.

    Each plan carries the expected sales with its confidence bound, the single-market prediction interval,
    and (for the optimised plans) the gain over the current split with a worst/best-case bound.
    """
    model = registry.get(dataset_id)
    current = _clean_allocation(model, req.current)
    total = sum(current.values())
    if total <= 0:
        raise OptimizationError("The current split must have a positive total")
    stats = {s.name: s for s in model.channel_stats()}
    su, yu = model.dataset.spend_unit, model.dataset.sales_unit

    def plan(key: str, label: str, alloc: dict[str, float]) -> dict:
        extrapolated = [{"channel": c, "amount": alloc[c], "observed_max": stats[c].train_max,
                         "ratio": alloc[c] / stats[c].train_max if stats[c].train_max else None}
                        for c in model.channels if alloc[c] > stats[c].train_max * 1.0001]
        return {"key": key, "label": label, "allocation": alloc, "prediction": model.predict(alloc),
                "extrapolated": extrapolated, "gain": None if key == "current" else model.gain(alloc, current)}

    plans = [plan("current", "Current split", current)]
    for key, label, cap in (("capped", "Optimal, within observed spend", True),
                            ("uncapped", "Optimal, unconstrained", False)):
        try:
            plans.append(plan(key, label, optimize_budget(model, total, cap_to_observed=cap)["allocation"]))
        except OptimizationError as exc:
            plans.append({"key": key, "label": label, "error": str(exc)})

    summary = []
    for p in plans[1:]:
        if "error" in p:
            summary.append(f"{p['label']}: not available. {p['error']}")
            continue
        g = p["gain"]
        pct = f" ({g['pct']:+.0%})" if g["pct"] is not None else ""
        line = (f"{p['label']}: {g['value']:+,.2f} {yu}{pct} over the current split. Worst case {g['low']:+,.2f}, "
                f"best case {g['high']:+,.2f} ({g['interval']}).")
        if p["extrapolated"]:
            worst = max(p["extrapolated"], key=lambda e: e["ratio"] or 0)
            line += (f" It puts {worst['channel']} at {fmt_money(worst['amount'], su)}, {worst['ratio']:.1f}x the highest "
                     f"spend in the data ({fmt_money(worst['observed_max'], su)}); the bound assumes the fitted curve "
                     "keeps holding out there, which the data cannot confirm.")
        else:
            line += " Every channel stays within what some real market spent, so the bound rests on observed data."
        summary.append(line)
    log.info("plans compared", extra={"dataset": dataset_id, "budget": total,
                                      "gains": {p["key"]: round(p["gain"]["value"], 3) for p in plans[1:] if p.get("gain")}})
    return {"dataset": dataset_id, "budget": total, "plans": plans, "summary": summary,
            "confidence": 1 - model.alpha}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")
