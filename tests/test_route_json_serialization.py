from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app_core.http import json_safe
from config.mrms_config import MRMS_PRODUCTS
from routes.mrms import router as mrms_router


def test_json_safe_converts_numpy_datetime_and_path_values():
    timestamp = datetime(2026, 8, 7, 12, 30, tzinfo=timezone.utc)
    path = Path("cache") / "mrms" / "frame.grib2"

    actual = json_safe(
        {
            "array": np.array([[1, 2], [3, 4]], dtype=np.int16),
            "integer": np.int64(7),
            "floating": np.float32(1.25),
            "boolean": np.bool_(True),
            "timestamp": timestamp,
            "path": path,
        }
    )

    assert actual == {
        "array": [[1, 2], [3, 4]],
        "integer": 7,
        "floating": 1.25,
        "boolean": True,
        "timestamp": "2026-08-07T12:30:00+00:00",
        "path": str(path),
    }


def test_mrms_products_endpoint_serializes_existing_product_contract():
    app = FastAPI()
    app.include_router(mrms_router)

    with TestClient(app) as client:
        response = client.get("/api/mrms/products")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"status", "products", "sub_products", "groups", "count"}
    assert payload["status"] == "success"
    assert payload["count"] == len(MRMS_PRODUCTS)
    assert set(payload["products"]) == set(MRMS_PRODUCTS)
    assert (
        payload["products"]["PrecipRate"]["levels"]
        == MRMS_PRODUCTS["PrecipRate"]["levels"].tolist()
    )
