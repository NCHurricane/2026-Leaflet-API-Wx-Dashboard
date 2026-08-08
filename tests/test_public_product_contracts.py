import inspect
from pathlib import Path

from mrms import publication as mrms_publication
from rtma import overlay_publication as rtma_publication
from satellite_v2 import meteosat_prefetch_worker, rapid_worker, worker_support
from tropical import product_data as tropical_product_data
from workers import tropical_worker


ROOT = Path(__file__).resolve().parents[1]


def test_cross_worker_product_helpers_have_public_domain_owners():
    assert callable(mrms_publication.render_mrms_png_standalone)
    assert callable(mrms_publication.write_mrms_overlay_cache)
    assert callable(rtma_publication.render_overlay_for_source)
    assert callable(tropical_product_data.extract_gis_layers_from_zip)
    assert callable(tropical_product_data.parse_advisory)
    assert callable(tropical_product_data.parse_track)


def test_tropical_worker_compatibility_names_resolve_to_product_contracts():
    assert inspect.getmodule(tropical_worker._parse_advisory) is tropical_product_data
    assert inspect.getmodule(tropical_worker._parse_track) is tropical_product_data


def test_satellite_workers_share_one_lifecycle_helper_contract():
    assert rapid_worker._parse_jobs is worker_support.parse_jobs
    assert meteosat_prefetch_worker._parse_jobs is worker_support.parse_jobs
    assert rapid_worker._worker_lock is worker_support.worker_lock
    assert meteosat_prefetch_worker._worker_lock is worker_support.worker_lock
    assert worker_support.parse_jobs("goes19:MESO1") == (("goes19", "MESO1"),)


def test_production_code_does_not_import_private_product_worker_helpers():
    forbidden = (
        "from workers.mrms_worker import _",
        "from workers.rtma_worker import _",
        "from workers.tropical_worker import _",
    )
    for root_name in ("app_core", "mrms", "routes", "rtma", "services", "tropical", "workers"):
        for path in (ROOT / root_name).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert not any(marker in source for marker in forbidden), path
