from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from shapely.geometry import Polygon

import alerts.alerts_utils as alerts_utils
import services.alerts_service as alerts_service
import workers.alerts_worker as alerts_worker
from app_core.paths import BASE_DIR
from app_core.refresh_coordinator import Submission, get_refresh_coordinator


def _polygon(west: float, south: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [west, south],
                [west + 1, south],
                [west + 1, south + 1],
                [west, south],
            ]
        ],
    }


def test_zone_disk_cache_load_is_lazy_and_single_shot(monkeypatch):
    calls = []
    monkeypatch.setattr(alerts_utils, "_ZONE_DISK_CACHE_LOADED", False)
    monkeypatch.setattr(
        alerts_utils,
        "_load_zone_disk_cache",
        lambda: calls.append("loaded"),
    )

    alerts_utils._ensure_zone_disk_cache_loaded()
    alerts_utils._ensure_zone_disk_cache_loaded()

    assert calls == ["loaded"]


def _feature(alert_id: str, west: float, *, provenance: str) -> dict:
    return {
        "id": alert_id,
        "type": "Feature",
        "properties": {"event": "Test Advisory"},
        "geometry": _polygon(west, 35),
        "_geometry_provenance": provenance,
    }


class _Coordinator:
    def __init__(self, submission: Submission | None = None) -> None:
        self.submission = submission or Submission(True, "queued")
        self.presence = []
        self.submissions = []

    def record_presence(self, **kwargs) -> None:
        self.presence.append(kwargs)

    def submit(self, **kwargs) -> Submission:
        self.submissions.append(kwargs)
        return self.submission


def _install_generation(
    root: Path,
    *,
    generation: str = "generation-one",
    stale: bool = False,
) -> None:
    generation_dir = root / "generations" / generation
    generation_dir.mkdir(parents=True)
    full = {
        "type": "FeatureCollection",
        "_source": "test",
        "_updated": "2026-07-23T12:00:00+00:00",
        "_generation": generation,
        "features": [
            _feature("inside", -80, provenance="native"),
            _feature("outside", -110, provenance="native"),
        ],
    }
    low = {
        **full,
        "_geometry_mode": "display",
        "features": [
            _feature("inside", -80, provenance="zone_derived"),
            _feature("outside", -110, provenance="zone_derived"),
        ],
    }
    (generation_dir / "national_full.geojson").write_text(
        json.dumps(full), encoding="utf-8"
    )
    (generation_dir / "national_display_low.geojson").write_text(
        json.dumps(low), encoding="utf-8"
    )
    manifest = {
        "generation": generation,
        "files": {
            "full": f"generations/{generation}/national_full.geojson",
            "display_low": (
                f"generations/{generation}/national_display_low.geojson"
            ),
            "compatibility": f"generations/{generation}/national_full.geojson",
        },
    }
    manifest_path = root / "current_generation.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    if stale:
        old = time.time() - alerts_service._ALERTS_CACHE_TTL_SECONDS - 1
        os.utime(manifest_path, (old, old))


def _patch_cache_root(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(alerts_service, "_ALERTS_CACHE_DIR", root)
    monkeypatch.setattr(
        alerts_service,
        "_ALERTS_GENERATION_MANIFEST",
        root / "current_generation.json",
    )


def test_only_derived_geometry_is_simplified():
    native = _feature("native", -80, provenance="native")
    derived = _feature("derived", -78, provenance="zone_derived")

    display, metrics = alerts_utils._create_display_low_features(
        [native, derived]
    )

    assert display[0]["geometry"] == native["geometry"]
    assert display[0]["_simplified"] is False
    assert display[1]["_simplified"] is True
    assert metrics["simplified_features"] == 1


def test_strict_fetch_rejects_empty_fallback_after_nws_failure(monkeypatch):
    def fail_nws(*args, **kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr(alerts_utils.requests, "get", fail_nws)
    monkeypatch.setattr(
        alerts_utils.alerts_iem_utils,
        "fetch_active_alerts_iem",
        lambda state: [],
    )

    with pytest.raises(RuntimeError, match="NWS and IEM alerts downloads"):
        alerts_utils.fetch_active_alerts_with_source(
            state=None,
            source="nws",
            strict=True,
        )


def test_geometry_enrichment_records_native_and_derived_provenance(monkeypatch):
    polygon = Polygon([(-80, 35), (-79, 35), (-79, 36), (-80, 35)])
    native = _feature("native", -80, provenance="")
    native.pop("_geometry_provenance")
    derived = {
        "id": "derived",
        "type": "Feature",
        "properties": {
            "event": "Test Advisory",
            "affectedZones": [
                "https://api.weather.gov/zones/forecast/NCZ001"
            ],
            "geocode": {"SAME": []},
        },
        "geometry": None,
    }
    monkeypatch.setattr(
        alerts_utils, "_prefetch_zone_geometries", lambda features: None
    )
    monkeypatch.setattr(
        alerts_utils, "_resolve_zone_geometry", lambda zones: polygon
    )
    with alerts_service._ENRICHED_GEOMETRY_CACHE_LOCK:
        alerts_service._ENRICHED_GEOMETRY_CACHE.clear()

    alerts_service.enrich_alert_features_geometry([native, derived])

    assert native["_geometry_provenance"] == "native"
    assert native["geometry"] == _polygon(-80, 35)
    assert derived["_geometry_provenance"] == "zone_derived"
    assert derived["geometry"] is not None


def test_low_zoom_is_national_and_high_zoom_is_bbox_filtered(
    tmp_path, monkeypatch
):
    coordinator = _Coordinator()
    _install_generation(tmp_path)
    _patch_cache_root(monkeypatch, tmp_path)
    monkeypatch.setattr(
        alerts_service, "get_refresh_coordinator", lambda: coordinator
    )

    low = alerts_service.get_alerts_data(
        geometry_mode="full",
        zoom_bucket="low",
        west=-82,
        east=-78,
        south=34,
        north=37,
    )
    high = alerts_service.get_alerts_data(
        geometry_mode="display",
        zoom_bucket="high",
        west=-82,
        east=-78,
        south=34,
        north=37,
    )

    assert low["_geometry_mode"] == "display"
    assert [feature["id"] for feature in low["features"]] == [
        "inside",
        "outside",
    ]
    assert high["_geometry_mode"] == "full"
    assert [feature["id"] for feature in high["features"]] == ["inside"]
    assert all(
        "_geometry_provenance" not in feature
        for feature in low["features"] + high["features"]
    )
    assert low["_generation"] == high["_generation"] == "generation-one"
    assert low["cache_ttl_seconds"] == alerts_service._ALERTS_CACHE_TTL_SECONDS
    assert coordinator.submissions == []


def test_frontend_uses_low_high_zoom_vocabulary_and_one_map_payload():
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")

    assert "zoom_bucket: highZoom ? 'high' : 'low'" in engine
    assert "const mapParams = requestParams(region);" in engine
    assert "const fullParams" not in engine
    assert "const displayParams" not in engine
    assert "? 'local'" not in engine
    assert "? 'regional'" not in engine
    assert ": 'national'" not in engine


def test_stale_generation_is_served_while_one_refresh_is_queued(
    tmp_path, monkeypatch
):
    coordinator = _Coordinator()
    _install_generation(tmp_path, stale=True)
    _patch_cache_root(monkeypatch, tmp_path)
    monkeypatch.setattr(
        alerts_service, "get_refresh_coordinator", lambda: coordinator
    )

    result = alerts_service.get_alerts_data(zoom_bucket="low")

    assert result["cache_state"] == "stale_refreshing"
    assert result["refreshing"] is True
    assert result["features"]
    assert coordinator.submissions[0]["key"] == ("alerts", "national")
    assert coordinator.submissions[0]["provider"] == "nws-alerts"


def test_missing_generation_returns_warming_instead_of_empty_success(
    tmp_path, monkeypatch
):
    coordinator = _Coordinator()
    _patch_cache_root(monkeypatch, tmp_path)
    monkeypatch.setattr(
        alerts_service, "get_refresh_coordinator", lambda: coordinator
    )

    with pytest.raises(HTTPException) as caught:
        alerts_service.get_alerts_data(zoom_bucket="low")

    assert caught.value.status_code == 503
    assert caught.value.detail["cache_state"] == "refreshing"
    assert coordinator.submissions[0]["key"] == ("alerts", "national")


def test_worker_publishes_one_generation_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(alerts_worker, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(alerts_worker, "CACHE_FILE_FULL", tmp_path / "full.json")
    monkeypatch.setattr(
        alerts_worker, "CACHE_FILE_DISPLAY_LOW", tmp_path / "low.json"
    )
    monkeypatch.setattr(alerts_worker, "CACHE_FILE", tmp_path / "legacy.json")
    monkeypatch.setattr(
        alerts_worker, "GENERATION_DIR", tmp_path / "generations"
    )
    monkeypatch.setattr(
        alerts_worker,
        "CURRENT_GENERATION_FILE",
        tmp_path / "current_generation.json",
    )

    alerts_worker._publish_generation(
        generation="generation-one",
        updated="2026-07-23T12:00:00+00:00",
        full_payload_text='{"_generation":"generation-one","kind":"full"}',
        display_payload_text='{"_generation":"generation-one","kind":"low"}',
    )

    manifest = json.loads(
        (tmp_path / "current_generation.json").read_text(encoding="utf-8")
    )
    full = tmp_path / manifest["files"]["full"]
    low = tmp_path / manifest["files"]["display_low"]
    compatibility = tmp_path / manifest["files"]["compatibility"]
    assert manifest["generation"] == "generation-one"
    assert json.loads(full.read_text(encoding="utf-8"))["_generation"] == (
        "generation-one"
    )
    assert json.loads(low.read_text(encoding="utf-8"))["_generation"] == (
        "generation-one"
    )
    assert compatibility == full


def test_incomplete_generation_does_not_replace_current_manifest(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(alerts_worker, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(alerts_worker, "CACHE_FILE_FULL", tmp_path / "full.json")
    monkeypatch.setattr(
        alerts_worker, "CACHE_FILE_DISPLAY_LOW", tmp_path / "low.json"
    )
    monkeypatch.setattr(alerts_worker, "CACHE_FILE", tmp_path / "legacy.json")
    monkeypatch.setattr(
        alerts_worker, "GENERATION_DIR", tmp_path / "generations"
    )
    monkeypatch.setattr(
        alerts_worker,
        "CURRENT_GENERATION_FILE",
        tmp_path / "current_generation.json",
    )
    alerts_worker._publish_generation(
        generation="generation-one",
        updated="2026-07-23T12:00:00+00:00",
        full_payload_text='{"_generation":"generation-one"}',
        display_payload_text='{"_generation":"generation-one"}',
    )
    original_atomic_write_text = alerts_worker.atomic_write_text

    def fail_second_generation(path, text):
        target = Path(path)
        if (
            target.parent.name == "generation-two"
            and target.name == "national_display_low.geojson"
        ):
            raise OSError("simulated interrupted publish")
        original_atomic_write_text(path, text)

    monkeypatch.setattr(
        alerts_worker, "atomic_write_text", fail_second_generation
    )

    with pytest.raises(OSError, match="simulated interrupted publish"):
        alerts_worker._publish_generation(
            generation="generation-two",
            updated="2026-07-23T12:01:00+00:00",
            full_payload_text='{"_generation":"generation-two"}',
            display_payload_text='{"_generation":"generation-two"}',
        )

    manifest = json.loads(
        (tmp_path / "current_generation.json").read_text(encoding="utf-8")
    )
    assert manifest["generation"] == "generation-one"


def test_nws_alerts_policy_has_35_second_floor():
    policy = get_refresh_coordinator().snapshot()["policies"]["nws-alerts"]

    assert policy["min_request_interval"] == 35.0
    assert policy["max_concurrency"] == 1
