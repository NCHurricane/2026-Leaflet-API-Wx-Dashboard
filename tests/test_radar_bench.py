import json

import pytest
from PIL import Image

from radar import bench


def test_safe_scratch_root_stays_below_radar_bench(tmp_path):
    assert bench._safe_scratch_root(tmp_path, "run-1") == (
        tmp_path / "radar" / ".bench" / "run-1"
    ).resolve()
    with pytest.raises(ValueError, match="Unsafe Radar benchmark run id"):
        bench._safe_scratch_root(tmp_path, "../escape")


def test_append_jsonl_requires_benchmark_gate(tmp_path, monkeypatch):
    sink = tmp_path / "results.jsonl"
    monkeypatch.delenv("WX_RADAR_BENCH", raising=False)
    with pytest.raises(RuntimeError, match="WX_RADAR_BENCH=1"):
        bench._append_jsonl(sink, {"total_ms": 1.0})
    assert not sink.exists()

    monkeypatch.setenv("WX_RADAR_BENCH", "1")
    bench._append_jsonl(sink, {"total_ms": 1.0})
    assert json.loads(sink.read_text(encoding="utf-8")) == {"total_ms": 1.0}


def test_png_contract_records_container_and_rgba_evidence(tmp_path):
    path = tmp_path / "golden.png"
    image = Image.new("RGBA", (3, 2), (0, 0, 0, 0))
    image.putpixel((1, 1), (10, 20, 30, 255))
    image.save(path)

    contract = bench._png_contract(path)

    assert contract["width"] == 3
    assert contract["height"] == 2
    assert contract["nontransparent_pixels"] == 1
    assert contract["rgba_bbox"] == [1, 1, 2, 2]
    assert len(contract["png_sha256"]) == 64
    assert len(contract["rgba_sha256"]) == 64


def test_main_writes_raw_results_only_under_scratch_and_compact_outputs(
    tmp_path, monkeypatch
):
    source = tmp_path / "KGSP20260725_120000_V06"
    source.write_bytes(b"pinned")
    cache_root = tmp_path / "cache"
    output_dir = tmp_path / "docs" / "perf"
    golden_dir = output_dir / "golden"

    context = {
        "site": "KGSP",
        "product": "L2_REF",
        "product_cfg": {"label": "L2 Reflectivity"},
        "level": "Level 2",
        "level_code": "L2",
        "product_code": "REF",
        "source_product_code": "REF",
        "bounds": [-85.0, -80.0, 32.0, 37.0],
        "cache_product_key": "L2_REF__ELEV_0P5",
        "elevation": "0.5",
    }
    record = {
        "total_ms": 10.0,
        "source_key": source.name,
        "source_sha256": "a" * 64,
        "source_size": source.stat().st_size,
        "png_size": 100,
        "png_sha256": "b" * 64,
        "rgba_sha256": "c" * 64,
        "width": 10,
        "height": 10,
        "nontransparent_pixels": 50,
        "rgba_bbox": [1, 1, 9, 9],
        "frame_key": "2026_07_25_12_00_00",
        "bounds": context["bounds"],
        "cache_key": context["cache_product_key"],
        "selected_elevation": 0.5,
        "available_elevations": [0.5],
    }
    monkeypatch.setattr(bench, "_product_context", lambda *_args: dict(context))
    monkeypatch.setattr(
        bench,
        "_run_scenario",
        lambda _scenario, _context, _sources, _scratch: dict(record),
    )
    monkeypatch.setattr(
        bench,
        "_environment_manifest",
        lambda _repo, current, _note: {"benchmark": dict(current)},
    )
    monkeypatch.setattr(bench, "_FRESH_PROCESS_SCENARIOS", set())

    result = bench.main(
        [
            "--site",
            "KGSP",
            "--product",
            "L2_REF",
            "--source",
            str(source),
            "--elevation",
            "0.5",
            "--scenario",
            "render-one",
            "--repeat",
            "2",
            "--cache-root",
            str(cache_root),
            "--output-dir",
            str(output_dir),
            "--golden",
            "capture",
            "--golden-dir",
            str(golden_dir),
            "--run-id",
            "run-1",
        ]
    )

    assert result == 0
    scratch = cache_root / "radar" / ".bench" / "run-1"
    assert len(bench._read_jsonl(scratch / "results.jsonl")) == 2
    assert (scratch / "manifest.json").exists()
    assert (scratch / "summary.md").exists()
    assert (output_dir / "run-1-manifest.json").exists()
    assert (output_dir / "run-1-summary.md").exists()
    assert (output_dir / "matrix-manifest.json").exists()
    assert (output_dir / "baseline-summary.md").exists()
    assert (golden_dir / "01-KGSP-L2_REF.json").exists()
    assert list(output_dir.glob("*.jsonl")) == []
    bench._update_matrix(output_dir)


def test_backfill_requires_twelve_sources(tmp_path):
    source = tmp_path / "one"
    source.write_bytes(b"x")
    with pytest.raises(SystemExit, match="backfill-12 requires at least 12"):
        bench.main(
            [
                "--site",
                "KGSP",
                "--product",
                "L2_REF",
                "--source",
                str(source),
                "--scenario",
                "backfill-12",
                "--cache-root",
                str(tmp_path / "cache"),
            ]
        )
