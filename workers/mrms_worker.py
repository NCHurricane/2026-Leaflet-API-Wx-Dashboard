"""
MRMS Worker
Downloads the latest GRIB2 for the currently-active MRMS product from S3
and stores it in cache/mrms/{product}/conus.grib2.gz.

The active product is tracked via FastAPI app.state.active_mrms_product.
Only ONE product is refreshed at a time (active product pivots on user request).
"""

import os
import shutil
from datetime import datetime

_CACHE_ROOT = os.path.join(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))), "cache")
_MRMS_CACHE = os.path.join(_CACHE_ROOT, "mrms")

# Module-level active product state (also mirrored in app.state for API access)
_active_product: str = "PrecipRate"


def set_active_product(product: str) -> None:
    global _active_product
    _active_product = product


def get_active_product() -> str:
    return _active_product


def run_mrms_worker() -> None:
    """Download the latest GRIB2 for the active MRMS product."""
    global _active_product
    product = _active_product

    try:
        from mrms.mrms_nodd_utils import get_latest_mrms_file
    except Exception as exc:
        print(f"[mrms_worker] Import error: {exc}")
        return

    product_cache_dir = os.path.join(_MRMS_CACHE, product)
    os.makedirs(product_cache_dir, exist_ok=True)

    try:
        result = get_latest_mrms_file(
            product, lookback_minutes=30, local_dir=product_cache_dir)
        if result is None:
            print(f"[mrms_worker] No files found for {product}")
            return

        local_path, file_dt = result
        dest = os.path.join(product_cache_dir, "conus.grib2.gz")

        # Atomic replace: move to final destination only after successful download
        if local_path != dest:
            tmp = dest + ".tmp"
            shutil.move(local_path, tmp)
            if os.path.exists(dest):
                os.remove(dest)
            os.rename(tmp, dest)

        print(
            f"[mrms_worker] {product} cached at {file_dt.strftime('%Y-%m-%d %H:%M UTC')}")
    except Exception as exc:
        print(f"[mrms_worker] Error fetching {product}: {exc}")
