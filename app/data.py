"""Datasets: the bundled Advertising data, a synthetic set with a known answer, and user uploads."""
import io
import json
import logging
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Settings

log = logging.getLogger(__name__)


class DatasetError(ValueError):
    """Invalid dataset input; surfaced to the client as HTTP 422."""


@dataclass
class Dataset:
    id: str
    name: str
    df: pd.DataFrame
    channels: list[str]
    target: str
    spend_unit: str = "$"
    sales_unit: str = "units"
    source: str = "upload"
    description: str = ""
    ground_truth: dict | None = None  # synthetic only: true coefficients used to generate the data
    meta: dict = field(default_factory=dict)

    def summary(self) -> dict:
        spend = self.df[self.channels]
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "description": self.description,
            "rows": len(self.df),
            "channels": self.channels,
            "target": self.target,
            "spend_unit": self.spend_unit,
            "sales_unit": self.sales_unit,
            "spend_ranges": {c: {"min": float(spend[c].min()), "max": float(spend[c].max()),
                                 "mean": float(spend[c].mean())} for c in self.channels},
            "typical_total_budget": float(spend.sum(axis=1).median()),
            "ground_truth": self.ground_truth,
        }


def load_advertising(data_dir: Path) -> Dataset:
    df = pd.read_csv(data_dir / "advertising.csv", index_col=0)
    return Dataset(
        id="advertising",
        name="ISLR Advertising",
        df=df,
        channels=["TV", "Radio", "Newspaper"],
        target="Sales",
        spend_unit="$K",
        sales_unit="K units",
        source="builtin",
        description="200 markets: TV / Radio / Newspaper spend (thousands of dollars) vs product sales "
                    "(thousands of units). From 'An Introduction to Statistical Learning'.",
    )


SYNTHETIC_TRUTH = {
    "intercept": 3.0,
    "coefficients": {"TV": 0.9, "Search": 1.4, "Social": 0.5, "Print": 0.0},
    "noise_sd": 0.8,
    "transform": "sqrt",
}


def make_synthetic(n: int = 260, seed: int = 42) -> Dataset:
    """Weekly-style data generated from a known sqrt model; 'Print' has zero true effect."""
    rng = np.random.default_rng(seed)
    upper = {"TV": 300, "Search": 60, "Social": 100, "Print": 80}
    df = pd.DataFrame({c: rng.uniform(0, hi, n).round(2) for c, hi in upper.items()})
    truth = SYNTHETIC_TRUTH
    sales = truth["intercept"] + sum(b * np.sqrt(df[c]) for c, b in truth["coefficients"].items())
    df["Sales"] = (sales + rng.normal(0, truth["noise_sd"], n)).round(3)
    return Dataset(
        id="synthetic",
        name="Synthetic (known answer)",
        df=df,
        channels=list(upper),
        target="Sales",
        spend_unit="$K",
        sales_unit="K units",
        source="builtin",
        description="260 rows generated from Sales = 3 + 0.9*sqrt(TV) + 1.4*sqrt(Search) + 0.5*sqrt(Social) "
                    "+ 0*sqrt(Print) + noise. Use it to check that the model recovers the truth.",
        ground_truth=truth,
    )


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "dataset"


def parse_upload(raw: bytes, *, name: str, target: str, channels: list[str], spend_unit: str,
                 sales_unit: str, settings: Settings) -> Dataset:
    if len(raw) > settings.max_upload_mb * 1_000_000:
        raise DatasetError(f"File exceeds {settings.max_upload_mb} MB limit")
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:  # pandas raises many types for malformed CSVs
        raise DatasetError(f"Could not parse CSV: {exc}") from exc

    channels = [c.strip() for c in channels if c.strip()]
    target = target.strip()
    if not channels:
        raise DatasetError("Select at least one spend channel")
    if len(channels) > settings.max_channels:
        raise DatasetError(f"At most {settings.max_channels} channels are supported")
    if target in channels:
        raise DatasetError("The sales column cannot also be a channel")
    if len(set(channels)) != len(channels):
        raise DatasetError("Duplicate channel columns")
    missing = [c for c in [target, *channels] if c not in df.columns]
    if missing:
        raise DatasetError(f"Columns not found in CSV: {missing}")

    df = df[[*channels, target]].apply(pd.to_numeric, errors="coerce")
    before = len(df)
    df = df.dropna()
    dropped = before - len(df)
    if dropped:
        log.warning("upload dropped rows with missing/non-numeric values", extra={"dropped_rows": dropped})

    if len(df) < max(settings.min_rows, len(channels) + 5):
        raise DatasetError(f"Need at least {max(settings.min_rows, len(channels) + 5)} complete rows, got {len(df)}")
    negative = [c for c in channels if (df[c] < 0).any()]
    if negative:
        raise DatasetError(f"Spend cannot be negative (columns: {negative})")
    constant = [c for c in channels if df[c].nunique() < 2]
    if constant:
        raise DatasetError(f"Channels with no variation cannot be modelled: {constant}")

    return Dataset(
        id=f"{_slug(name)}-{uuid.uuid4().hex[:6]}",
        name=name.strip() or "Uploaded dataset",
        df=df.reset_index(drop=True),
        channels=channels,
        target=target,
        spend_unit=spend_unit.strip() or "$",
        sales_unit=sales_unit.strip() or "units",
        source="upload",
        description=f"Uploaded CSV, {len(df)} rows ({dropped} incomplete rows dropped).",
        meta={"dropped_rows": dropped},
    )


class DatasetStore:
    """In-memory dataset registry; uploads are persisted under storage/uploads/<id>/ to survive restarts."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._datasets: dict[str, Dataset] = {}

    def load(self) -> None:
        self.add(load_advertising(self.settings.data_dir), persist=False)
        self.add(make_synthetic(), persist=False)
        uploads = self.settings.uploads_dir
        if uploads.exists():
            for meta_path in sorted(uploads.glob("*/meta.json")):
                try:
                    meta = json.loads(meta_path.read_text())
                    df = pd.read_csv(meta_path.parent / "data.csv")
                    self.add(Dataset(df=df, **meta), persist=False)
                except Exception:
                    log.exception("failed to restore uploaded dataset", extra={"path": str(meta_path)})
        log.info("datasets loaded", extra={"datasets": list(self._datasets)})

    def add(self, ds: Dataset, persist: bool = True) -> None:
        if persist:
            folder = self.settings.uploads_dir / ds.id
            folder.mkdir(parents=True, exist_ok=True)
            ds.df.to_csv(folder / "data.csv", index=False)
            meta = {k: getattr(ds, k) for k in ("id", "name", "channels", "target", "spend_unit", "sales_unit",
                                                "source", "description", "ground_truth", "meta")}
            (folder / "meta.json").write_text(json.dumps(meta, indent=2))
        with self._lock:
            self._datasets[ds.id] = ds

    def get(self, dataset_id: str) -> Dataset | None:
        return self._datasets.get(dataset_id)

    def all(self) -> list[Dataset]:
        return list(self._datasets.values())
