from __future__ import annotations

import copy
import json

import alerts.alerts_utils as alerts_utils
import services.alerts_service as alerts_service
import workers.alerts_worker as alerts_worker


def _feature(alert_id: str, headline: str) -> dict:
    return {
        "id": alert_id,
        "type": "Feature",
        "properties": {"event": "Test Warning", "headline": headline},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-80, 35], [-79, 35], [-79, 36], [-80, 35]]],
        },
    }


def _metrics() -> dict:
    return {
        "total_features": 1,
        "simplified_features": 1,
        "excluded_features": 0,
        "total_vertices_before": 4,
        "total_vertices_after": 4,
        "vertex_reduction_percent": 0.0,
    }


def test_processed_feature_cache_reuses_unchanged_alerts(monkeypatch):
    enriched_batches = []
    simplified_ids = []

    def enrich(features, *, measurement_fields=None):
        enriched_batches.append([feature["id"] for feature in features])

    def simplify(features):
        feature = copy.deepcopy(features[0])
        simplified_ids.append(feature["id"])
        feature["_simplified"] = True
        return [feature], _metrics()

    monkeypatch.setattr(alerts_service, "enrich_alert_features_geometry", enrich)
    monkeypatch.setattr(alerts_utils, "_create_display_low_features", simplify)
    with alerts_worker._PROCESSED_FEATURE_CACHE_LOCK:
        alerts_worker._PROCESSED_FEATURE_CACHE.clear()

    first_features = [_feature("one", "First"), _feature("two", "Second")]
    first_entries, first_metrics, first_cache = (
        alerts_worker._prepare_feature_artifacts(
            first_features,
            measurement_fields={"process_pass": "cold"},
        )
    )
    second_entries, second_metrics, second_cache = (
        alerts_worker._prepare_feature_artifacts(
            copy.deepcopy(first_features),
            measurement_fields={"process_pass": "warm"},
        )
    )

    assert enriched_batches == [["one", "two"]]
    assert simplified_ids == ["one", "two"]
    assert first_cache["cache_misses"] == 2
    assert second_cache["cache_hits"] == 2
    assert [entry["full_json"] for entry in second_entries] == [
        entry["full_json"] for entry in first_entries
    ]
    assert second_metrics == first_metrics


def test_processed_feature_cache_rebuilds_only_changed_alert(monkeypatch):
    enriched_batches = []
    simplified_ids = []

    def enrich(features, *, measurement_fields=None):
        enriched_batches.append([feature["id"] for feature in features])

    def simplify(features):
        feature = copy.deepcopy(features[0])
        simplified_ids.append(feature["id"])
        feature["_simplified"] = True
        return [feature], _metrics()

    monkeypatch.setattr(alerts_service, "enrich_alert_features_geometry", enrich)
    monkeypatch.setattr(alerts_utils, "_create_display_low_features", simplify)
    with alerts_worker._PROCESSED_FEATURE_CACHE_LOCK:
        alerts_worker._PROCESSED_FEATURE_CACHE.clear()

    alerts_worker._prepare_feature_artifacts(
        [_feature("one", "First"), _feature("two", "Second")],
        measurement_fields={"process_pass": "cold"},
    )
    entries, _, cache_metrics = alerts_worker._prepare_feature_artifacts(
        [_feature("one", "Updated"), _feature("two", "Second")],
        measurement_fields={"process_pass": "warm"},
    )

    assert enriched_batches == [["one", "two"], ["one"]]
    assert simplified_ids == ["one", "two", "one"]
    assert cache_metrics["cache_hits"] == 1
    assert cache_metrics["cache_misses"] == 1
    assert json.loads(entries[0]["full_json"])["properties"]["headline"] == "Updated"


def test_feature_collection_serialization_matches_json_dumps():
    metadata = {
        "type": "FeatureCollection",
        "_source": "test",
        "_updated": "2026-07-23T00:00:00+00:00",
        "_geometry_mode": "full",
    }
    features = [_feature("one", "First"), _feature("two", "Second")]

    actual = alerts_worker._serialize_feature_collection(
        metadata,
        [json.dumps(feature) for feature in features],
    )

    assert actual == json.dumps({**metadata, "features": features})


def test_unresolved_alert_geometry_is_retried(monkeypatch):
    enriched_batches = []

    def enrich(features, *, measurement_fields=None):
        enriched_batches.append([feature["id"] for feature in features])

    monkeypatch.setattr(alerts_service, "enrich_alert_features_geometry", enrich)
    monkeypatch.setattr(
        alerts_utils,
        "_create_display_low_features",
        lambda features: ([copy.deepcopy(features[0])], _metrics()),
    )
    with alerts_worker._PROCESSED_FEATURE_CACHE_LOCK:
        alerts_worker._PROCESSED_FEATURE_CACHE.clear()

    unresolved = _feature("one", "First")
    unresolved["geometry"] = None
    for process_pass in ("cold", "warm"):
        alerts_worker._prepare_feature_artifacts(
            [copy.deepcopy(unresolved)],
            measurement_fields={"process_pass": process_pass},
        )

    assert enriched_batches == [["one"], ["one"]]
