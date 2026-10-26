import io

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_ready_metrics(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").json()["ready"] is True
    body = client.get("/metrics").text
    assert "mmm_model_r_squared" in body and "mmm_http_requests_total" in body


def test_request_id_is_propagated(client):
    r = client.get("/api/datasets", headers={"X-Request-ID": "trace-123"})
    assert r.headers["X-Request-ID"] == "trace-123"
    r = client.get("/api/datasets", headers={"X-Request-ID": "bad id with spaces"})
    assert r.headers["X-Request-ID"] != "bad id with spaces"


def test_optimize_endpoint(client):
    r = client.post("/api/datasets/advertising/optimize", json={"budget": 100})
    assert r.status_code == 200, r.text
    body = r.json()
    alloc = {c["name"]: c["amount"] for c in body["channels"]}
    assert alloc["Newspaper"] == 0
    assert sum(alloc.values()) == pytest.approx(100)
    assert body["justification"] and set(body["curves"]) == {"TV", "Radio", "Newspaper"}
    assert 'mmm_optimizations_total{dataset="advertising",status="ok"}' in client.get("/metrics").text


def test_predict_endpoint_compares_with_optimum(client):
    r = client.post("/api/datasets/advertising/predict", json={"allocation": {"TV": 50, "Radio": 10, "Newspaper": 40}})
    assert r.status_code == 200
    body = r.json()
    assert body["optimal_for_same_total"] > body["prediction"]["mean"]


def test_validation_errors_are_422_with_request_id(client):
    r = client.post("/api/datasets/advertising/optimize",
                    json={"budget": 10, "constraints": {"TV": {"min": 50}}})
    assert r.status_code == 422 and "request_id" in r.json()
    assert client.post("/api/datasets/advertising/optimize", json={"budget": -1}).status_code == 422
    assert client.post("/api/datasets/missing/optimize", json={"budget": 1}).status_code == 404


def test_upload_roundtrip(client):
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"week": range(80), "Email": rng.uniform(0, 50, 80), "Video": rng.uniform(0, 200, 80)})
    df["Revenue"] = 10 + 2 * np.sqrt(df.Email) + 1 * np.sqrt(df.Video) + rng.normal(0, 0.5, 80)
    csv = df.to_csv(index=False).encode()
    r = client.post("/api/datasets", files={"file": ("camp.csv", io.BytesIO(csv), "text/csv")},
                    data={"name": "Campaign", "target": "Revenue", "channels": "Email,Video", "spend_unit": "$"})
    assert r.status_code == 201, r.text
    ds_id = r.json()["dataset"]["id"]
    assert r.json()["model"]["r_squared"] > 0.8
    opt = client.post(f"/api/datasets/{ds_id}/optimize", json={"budget": 120}).json()
    alloc = {c["name"]: c["amount"] for c in opt["channels"]}
    assert alloc["Email"] > alloc["Video"]  # beta^2: 4 vs 1


def test_upload_rejects_bad_columns(client):
    csv = b"a,b\n1,2\n3,4\n"
    r = client.post("/api/datasets", files={"file": ("x.csv", io.BytesIO(csv), "text/csv")},
                    data={"target": "b", "channels": "zzz"})
    assert r.status_code == 422


def test_compare_endpoint_returns_three_plans_with_bounds(client):
    r = client.post("/api/datasets/advertising/compare",
                    json={"current": {"TV": 147.0, "Radio": 23.3, "Newspaper": 30.6}})
    assert r.status_code == 200, r.text
    plans = {p["key"]: p for p in r.json()["plans"]}
    assert set(plans) == {"current", "capped", "uncapped"}
    assert plans["current"]["gain"] is None
    capped, uncapped = plans["capped"], plans["uncapped"]
    assert capped["extrapolated"] == [] and uncapped["extrapolated"]
    assert 0 < capped["gain"]["low"] < capped["gain"]["value"] < uncapped["gain"]["value"]
    assert len(r.json()["summary"]) == 2


def test_compare_reports_capped_plan_unavailable_for_huge_budget(client):
    r = client.post("/api/datasets/advertising/compare", json={"current": {"TV": 800, "Radio": 100, "Newspaper": 100}})
    plans = {p["key"]: p for p in r.json()["plans"]}
    assert "error" in plans["capped"] and "gain" in plans["uncapped"]
