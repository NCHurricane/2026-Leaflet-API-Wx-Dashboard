"""One bounded, source-only audit acquisition, authorized 2026-09-06.

Uses existing provider collection/channel/path definitions, with stricter audit
transport limits. This is fixture acquisition, not a production downloader test.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT))
SCRATCH = ROOT / "cache/rendering-audit-20260906"
LIMIT_BYTES = 2 * 1024**3
LIMIT_REQUESTS = 100
LIMIT_SECONDS = 600


def main() -> None:
    import requests
    from satellite_v2 import provider_eumetsat as provider
    from satellite_v2.cache import source_path, atomic_write_json

    report_path = OUT / "meteosat-acquisition.json"
    if report_path.exists():
        raise RuntimeError("Preserve the acquisition record; do not rerun this batch implicitly.")
    started = time.monotonic()
    report = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "category": "bounded_fixture_acquisition_not_renderer_or_production_transfer_benchmark",
        "limits": {"bytes": LIMIT_BYTES, "requests": LIMIT_REQUESTS,
                   "seconds": LIMIT_SECONDS, "concurrency": 1, "retries": 0},
        "search_window": ["2026-09-06T12:00:00Z", "2026-09-06T12:30:00Z"],
        "requests": 0, "received_body_bytes": 0, "frames": [], "transfers": [],
    }
    session = requests.Session()

    def check() -> None:
        if time.monotonic() - started >= LIMIT_SECONDS:
            raise RuntimeError("Acquisition time ceiling reached")
        if report["received_body_bytes"] >= LIMIT_BYTES:
            raise RuntimeError("Acquisition byte ceiling reached")

    def fetch(method: str, url: str, *, target: Path | None = None, **kwargs):
        check()
        if report["requests"] >= LIMIT_REQUESTS:
            raise RuntimeError("Acquisition request ceiling reached")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "api.eumetsat.int":
            raise RuntimeError("Unreviewed acquisition host")
        report["requests"] += 1
        request_started = time.monotonic()
        received = 0
        response_data = bytearray()
        tmp = target.with_suffix(target.suffix + ".part") if target else None
        if target:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or tmp.exists():
                raise RuntimeError("Preserving existing acquisition file")
        handle = None
        digest = hashlib.sha256()
        try:
            remaining = max(0.1, LIMIT_SECONDS - (time.monotonic() - started))
            with session.request(method, url, timeout=(min(15, remaining), min(30, remaining)),
                                 allow_redirects=False, stream=True, **kwargs) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"Acquisition HTTP {response.status_code}; response body omitted")
                advertised = int(response.headers.get("Content-Length") or 0)
                if advertised + report["received_body_bytes"] > LIMIT_BYTES:
                    raise RuntimeError("Advertised body exceeds remaining byte budget")
                if tmp:
                    handle = tmp.open("xb")
                for chunk in response.iter_content(64 * 1024):
                    check()
                    if report["received_body_bytes"] + len(chunk) > LIMIT_BYTES:
                        raise RuntimeError("Acquisition byte ceiling reached")
                    report["received_body_bytes"] += len(chunk)
                    received += len(chunk)
                    digest.update(chunk)
                    if handle:
                        handle.write(chunk)
                    else:
                        response_data.extend(chunk)
                        if len(response_data) > 8 * 1024**2:
                            raise RuntimeError("Metadata response exceeds 8 MiB")
                if advertised and not response.headers.get("Content-Encoding") and received != advertised:
                    raise RuntimeError("Incomplete response body")
            if handle:
                handle.close()
                handle = None
                tmp.replace(target)
                row = {"path": target.relative_to(ROOT).as_posix(), "bytes": received,
                       "sha256": digest.hexdigest(),
                       "wall_seconds": time.monotonic() - request_started}
                report["transfers"].append(row)
                print(f"Source file {len(report['transfers'])}: {received:,} bytes", flush=True)
                return row
            return json.loads(response_data)
        finally:
            if handle:
                handle.close()

    try:
        token = fetch("POST", provider._TOKEN_URL, auth=provider._credentials(),
                      data={"grant_type": "client_credentials"})["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        plans = []
        for sat, sector, pseudo_channel in (
            ("meteosat12", "FULLDISK", "FCI"), ("meteosat11", "RSS", "SEVIRI")
        ):
            collection = provider._COLLECTIONS[sat]
            payload = fetch("GET", provider._SEARCH_URL, headers=headers, params={
                "format": "json", "pi": collection, "dtstart": report["search_window"][0],
                "dtend": report["search_window"][1], "c": 100,
            })
            features = sorted(payload.get("features") or [],
                              key=lambda f: f.get("properties", {}).get("date", ""))
            if not features:
                raise RuntimeError(f"No {sat} product in the fixed daylight window")
            feature = features[0]
            product_id = str(feature["id"])
            source_date = feature.get("properties", {}).get("date", "")
            slot = provider._slot_time(sat, source_date.split("/", 1)[0])
            frame_key = slot.strftime("%Y%m%dT%H%M%SZ")
            if sat == "meteosat12":
                entries = provider._fci_body_entries(feature)
                if not entries:
                    raise RuntimeError("Selected FCI product has no body chunks")
            else:
                entries = [{"title": product_id + ".nat", "href":
                            f"{provider._DOWNLOAD_URL}/collections/{quote(collection, safe='')}"
                            f"/products/{quote(product_id, safe='')}/entry?name={quote(product_id + '.nat', safe='')}"}]
            row = {"sat": sat, "sector": sector, "collection": collection,
                   "product_id": product_id, "frame_key": frame_key,
                   "source_date": source_date, "entry_count": len(entries),
                   "advertised_product_size": feature.get("properties", {}).get("productInformation", {}).get("size"),
                   "status": "pinned_before_download"}
            report["frames"].append(row)
            plans.append((row, pseudo_channel, entries))
        atomic_write_json(report_path, report)
        for row, pseudo_channel, entries in plans:
            paths = []
            for entry in entries:
                title = str(entry["title"])
                if Path(title).name != title:
                    raise RuntimeError("Unsafe source filename")
                target = source_path(SCRATCH, row["sat"], row["sector"], pseudo_channel,
                                     row["frame_key"], title)
                fetch("GET", str(entry["href"]), target=target, headers=headers)
                paths.append(target)
            if pseudo_channel == "FCI":
                atomic_write_json(paths[0].parent / "manifest.json",
                                  {"product_id": row["product_id"], "chunks": [p.name for p in paths]})
            row["status"] = "download_complete_pending_native_validation"
            atomic_write_json(report_path, report)
        report["status"] = "complete"
    except Exception as exc:
        report["status"] = "stopped"
        # Exception text may contain a signed URL or auth detail. Record type only.
        report["error_type"] = type(exc).__name__
        print(f"Acquisition stopped: {type(exc).__name__}", flush=True)
    finally:
        report["wall_seconds"] = time.monotonic() - started
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(report_path, report)
        session.close()
    print(json.dumps({k: report[k] for k in ("status", "requests", "received_body_bytes", "wall_seconds", "frames")}, indent=2))
    if report["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
