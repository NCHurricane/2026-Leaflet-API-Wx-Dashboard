"""Download a sample radar dataset for palette testing.

Grabs the latest **Level II** volume (one file — contains every moment, so it
covers all 7 L2 products) plus the latest file for **each Level III product**
in the dashboard catalog. Files are copied flat into the output folder with
clear names so they are easy to pick in the preview UI and are not touched by
the dashboard's radar worker (which prunes its own cache).

Usage (CLI):
    ../.venv/Scripts/python.exe fetch_samples.py --site KTWX --out samples

Importable:
    from fetch_samples import fetch_samples
    results = fetch_samples("KTWX", "samples")
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _level3_products() -> list[tuple[str, str]]:
    """Return (catalog_key, product_code) for each Level III product."""
    from config.radar_config import LIVE_RADAR_PRODUCTS

    out: list[tuple[str, str]] = []
    for key, cfg in LIVE_RADAR_PRODUCTS.items():
        if str(cfg.get("level", "")).strip() == "Level 3":
            code = str(cfg.get("product") or "").strip().upper()
            if code:
                out.append((key, code))
    return out


def _fetch_one(
    level: str,
    site: str,
    product: str,
    label: str,
    lookback_hours: float,
    work_dir: Path,
    out_dir: Path,
    provider: str,
    latest_only: bool,
) -> dict:
    """Download the newest file for one product; copy it flat into out_dir.

    With ``latest_only`` the downloader fetches a single file; otherwise it
    fetches the window and we keep the newest (the dashboard's latest-mode
    listing is unreliable for Level III, so callers use the window there).

    Returns a result dict: {label, product, level, ok, file, error}.
    """
    from radar import radar_nodd_utils

    result = {
        "label": label,
        "product": product,
        "level": level,
        "ok": False,
        "file": None,
        "error": None,
    }
    try:
        save_dir, total, _downloaded = radar_nodd_utils.download_radar_data(
            level,
            site,
            product,
            float(lookback_hours),
            str(work_dir),
            latest_only=latest_only,
            provider=provider,
        )
        if not save_dir or int(total or 0) <= 0:
            result["error"] = "no data in window"
            return result

        files = [p for p in Path(save_dir).glob("*") if p.is_file()]
        if not files:
            result["error"] = "downloaded but no file found"
            return result

        newest = max(files, key=lambda p: p.stat().st_mtime)
        dest = out_dir / f"{site}_{label}__{newest.name}"
        shutil.copyfile(newest, dest)
        result["ok"] = True
        result["file"] = dest.name
        return result
    except Exception as exc:  # noqa: BLE001 - surface any provider error per product
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def fetch_samples(
    site: str,
    out_dir: str | Path,
    lookback_hours: float = 3.0,
    provider: str = "aws",
) -> list[dict]:
    """Fetch one Level II volume + one file per Level III product.

    Returns a list of per-product result dicts.
    """
    site = str(site or "").strip().upper()
    if not site:
        raise ValueError("site is required")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    work = out / "_work"
    work.mkdir(parents=True, exist_ok=True)

    # Level III latest-mode listing is unreliable, so we scan a short window
    # and keep the newest file. Cap it so we do not pull a large backlog.
    l3_lookback = min(float(lookback_hours), 1.0)

    results: list[dict] = []
    try:
        # Level II: single volume covers all L2 moments (latest mode works).
        results.append(
            _fetch_one(
                "Level 2", site, "REF", "L2", lookback_hours, work, out,
                provider, latest_only=True,
            )
        )
        # Level III: newest file per product code (window scan).
        for _key, code in _level3_products():
            results.append(
                _fetch_one(
                    "Level 3", site, code, code, l3_lookback, work, out,
                    provider, latest_only=False,
                )
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return results


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Download radar sample data.")
    parser.add_argument("--site", default="KTWX", help="Radar site (e.g. KTWX)")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent / "samples"),
        help="Output folder",
    )
    parser.add_argument(
        "--lookback", type=float, default=3.0, help="Lookback hours"
    )
    parser.add_argument(
        "--provider", default="aws", choices=("aws", "gcp"), help="Cloud source"
    )
    args = parser.parse_args()

    print(f"Fetching samples for {args.site} -> {args.out}")
    results = fetch_samples(args.site, args.out, args.lookback, args.provider)

    ok = [r for r in results if r["ok"]]
    miss = [r for r in results if not r["ok"]]
    for r in results:
        status = "OK " if r["ok"] else "-- "
        detail = r["file"] if r["ok"] else r["error"]
        print(f"  {status} {r['label']:5s} ({r['product']:4s})  {detail}")
    print(f"\n{len(ok)} fetched, {len(miss)} empty/failed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
