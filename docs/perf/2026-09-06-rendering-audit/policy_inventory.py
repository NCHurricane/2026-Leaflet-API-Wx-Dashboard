"""Export current exposed Satellite recipes and configured product policies."""

import dataclasses
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from config import satellite_v2_config as config
    from config.satellite_platforms import SATELLITE_PLATFORMS
    from config.radar_config import LIVE_RADAR_PRODUCTS
    from config.mrms_config import MRMS_PRODUCTS, MRMS_TILE_MIN_ZOOM, MRMS_WARP_MAX_DIM
    from rtma.rtma_utils import PRODUCTS as RTMA_PRODUCTS
    from app_core.render_budget import _SATELLITE_RENDER_BUDGET, _configured_slots

    page = (ROOT / "frontend/pages/satellite/satellite-page.js").read_text()
    def tokens(pattern):
        return re.findall(r"'([^']+)'", re.search(pattern, page, re.S).group(1))
    meteosat = tokens(r"const METEOSAT_CHANNELS = \[(.*?)\];")
    exposed = {
        "meteosat9": meteosat, "meteosat11": meteosat,
        "meteosat12": ["Channel01", "Channel06", *meteosat],
        "gk2a": tokens(r"gk2a: new Set\(\[(.*?)\]\)"),
        "gmgsi": tokens(r"gmgsi: new Set\(\[(.*?)\]\)"),
    }
    all_products = list(config.SATELLITE_V2_PRODUCTS)
    exposed["goes18"] = exposed["goes19"] = all_products
    goes_only = tokens(r"const GOES_ONLY_CHANNELS = new Set\(\[(.*?)\]\)")
    exposed["himawari9"] = [k for k in all_products if k not in goes_only]
    maps = {"FCI": config.FCI_CHANNEL_FOR_ABI_CHANNEL,
            "SEVIRI": config.SEVIRI_CHANNEL_FOR_ABI_CHANNEL,
            "AHI": config.AHI_BAND_FOR_ABI_CHANNEL,
            "AMI": config.AMI_CHANNEL_FOR_ABI_CHANNEL}
    platforms = {}
    for sat, descriptor in SATELLITE_PLATFORMS.items():
        mapper = maps.get(descriptor["instrument"])
        recipes = []
        for product in exposed[sat]:
            spec = config.SATELLITE_V2_PRODUCTS[product]
            sources = list(spec.source_channels)
            native = [mapper.get(ch) for ch in sources] if mapper else sources
            recipes.append({**dataclasses.asdict(spec), "native_mapping": native,
                            "unmapped_sources": [ch for ch, value in zip(sources, native) if value is None],
                            "unique_mapped_inputs": list(dict.fromkeys(native))})
        platforms[sat] = {"descriptor": descriptor, "exposed_products": recipes,
                          "sectors": [{"sector": sector,
                                       "request_floor": {"FULLDISK": 1, "GLOBAL": 2, "RSS": 4, "TARGET": 4}.get(sector, 5),
                                       "request_ceiling": config.max_native_zoom_for_product(sector, "Channel02"),
                                       "configured_warming_zooms": config.zooms_for_sector(sector)}
                                      for sector in descriptor["sectors"]]}
    result = {
        "category": "static_product_and_policy_inventory_not_all_product_validation",
        "satellite": platforms,
        "radar": LIVE_RADAR_PRODUCTS,
        "mrms": {key: {k: v for k, v in row.items() if k in ("full_name", "units", "s3_prefix", "colormap")}
                 for key, row in MRMS_PRODUCTS.items()},
        "mrms_policy": {"tile_floor": MRMS_TILE_MIN_ZOOM, "whole_overlay_max_dim": MRMS_WARP_MAX_DIM},
        "rtma": {key: {k: v for k, v in row.items() if k in ("label", "kind", "var", "vars", "units", "vmin", "vmax")}
                 for key, row in RTMA_PRODUCTS.items()},
        "backend_admission": {"satellite": _SATELLITE_RENDER_BUDGET.snapshot(),
                              "heavy_slots": _configured_slots("WX_HEAVY_RENDER_SLOTS")},
        "limitations": ["Source shape/calibration verification currently covers acquired FCI, M11 RSS, KRAX and CONUS rapid RTMA only.",
                        "Frontend exposure is distinct from backend channel mapping; unmapped sources need service tracing.",
                        "Request floors transcribed from satellite-anim.js; actual displayed/container/DPR zoom requires browser checks.",
                        "Configured warming zooms do not prove those tiles exist or are warmed by an active worker."]}
    (OUT / "policy-inventory.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps({"satellite_products": {k: len(v["exposed_products"]) for k, v in platforms.items()},
                      "radar_products": len(LIVE_RADAR_PRODUCTS), "mrms_products": len(MRMS_PRODUCTS),
                      "rtma_products": len(RTMA_PRODUCTS), "admission": result["backend_admission"]}, indent=2))


if __name__ == "__main__":
    main()
