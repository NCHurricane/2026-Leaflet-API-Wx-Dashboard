from lib.font_utils import register_montserrat_fonts
from datetime import datetime, timedelta, timezone
import importlib
import os
import re
import traceback
import xml.etree.ElementTree as ET
from urllib.parse import quote

import time as _time
from lib.listing_cache import cached_call

try:
    from . import radar_utils as thredds_radar_utils
except ImportError:
    import radar_utils as thredds_radar_utils


register_montserrat_fonts()


def _log(msg: str):
    """Windows-safe print: strip non-BMP / surrogate chars before writing."""
    try:
        print(msg)
    except (UnicodeEncodeError, UnicodeDecodeError):
        safe = msg.encode("ascii", errors="replace").decode("ascii")
        print(safe)


NEXRAD_LEVEL2_BUCKET = "unidata-nexrad-level2"
NEXRAD_LEVEL3_BUCKET = "unidata-nexrad-level3"
NEXRAD_LEVEL2_GCP_BUCKET = "gcp-public-data-nexrad-l2"
NEXRAD_LEVEL3_GCP_BUCKET = "gcp-public-data-nexrad-l3"
NEXRAD_LEVEL3_GCP_REALTIME_BUCKET = "gcp-public-data-nexrad-l3-realtime"
CACHE_MAX_BYTES = 20 * 1024 * 1024 * 1024
DOWNLOAD_RETRY_ATTEMPTS = 3
DOWNLOAD_RETRY_SLEEP_SECONDS = 0.12


LEVEL3_PREFIX_PATTERNS = [
    "NIDS/{station}/{product}/",
    "NIDS/{station_short}/{product}/",
    "{station}_{product}_",
    "{station_short}_{product}_",
    "{product}/{station}/{year}/{month:02d}/{day:02d}/",
    "{product}/{station_short}/{year}/{month:02d}/{day:02d}/",
    "{year}/{month:02d}/{day:02d}/{station}/{product}/",
    "{year}/{month:02d}/{day:02d}/{station_short}/{product}/",
]

LEVEL3_DAY_PREFIX_PATTERNS = [
    "{product}/{station}/{year}/{month:02d}/{day:02d}/",
    "{product}/{station_short}/{year}/{month:02d}/{day:02d}/",
    "{year}/{month:02d}/{day:02d}/{station}/{product}/",
    "{year}/{month:02d}/{day:02d}/{station_short}/{product}/",
    "{year}/{month:02d}/{day:02d}/{station}/",
    "{year}/{month:02d}/{day:02d}/{station_short}/",
    "NIDS/{station}/{product}/{year:04d}{month:02d}{day:02d}/",
    "NIDS/{station_short}/{product}/{year:04d}{month:02d}{day:02d}/",
]


# Consolidated S3 client — shared across all NODD modules
from lib.s3_utils import get_s3_client  # noqa: E402


def _parse_radar_time_from_key(key):
    name = os.path.basename(key)

    match = re.search(r"(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})", name)
    if match:
        try:
            parsed = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    patterns = [
        r"(\d{8})_(\d{6})",
        r"(\d{8})(\d{6})",
        r"(\d{8})_(\d{4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, name)
        if not match:
            continue

        date_part, time_part = match.groups()
        if len(time_part) == 4:
            time_part += "00"

        try:
            parsed = datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S")
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def _iter_days(start_dt, end_dt):
    current = start_dt.date()
    final = end_dt.date()
    while current <= final:
        yield current
        current += timedelta(days=1)


def _list_objects_for_prefix(
    s3_client, bucket, prefix, start_after=None, max_keys=None
):
    def _fetch():
        keys = []
        paginator = s3_client.get_paginator("list_objects_v2")

        paginate_kwargs = {"Bucket": bucket, "Prefix": prefix}
        if start_after:
            paginate_kwargs["StartAfter"] = start_after

        # PaginationConfig.MaxItems limits total results across all pages.
        # MaxKeys only limits per-page size; the paginator keeps paging.
        pagination_config = {}
        if max_keys is not None:
            pagination_config["MaxItems"] = int(max_keys)
            paginate_kwargs["MaxKeys"] = int(max_keys)

        for page in paginator.paginate(
            **paginate_kwargs,
            **({"PaginationConfig": pagination_config} if pagination_config else {}),
        ):
            for obj in page.get("Contents", []):
                key = obj.get("Key", "")
                if key and not key.endswith("/"):
                    keys.append(key)

        return keys

    return cached_call(
        namespace="radar_nodd_aws_prefix",
        key=(bucket, prefix, start_after or "", max_keys or 0),
        fetch_fn=_fetch,
        ttl_seconds=120,
    )


def _list_gcs_keys_for_prefix(bucket, prefix, start_offset=None, max_results=None):
    requests = importlib.import_module("requests")

    def _fetch():
        keys = []
        page_token = None

        while True:
            params = {
                "prefix": prefix,
                "maxResults": int(max_results) if max_results is not None else 1000,
            }
            if start_offset:
                params["startOffset"] = start_offset
            if page_token:
                params["pageToken"] = page_token

            resp = requests.get(
                f"https://storage.googleapis.com/storage/v1/b/{bucket}/o",
                params=params,
                timeout=30,
            )
            if resp.status_code in {401, 403}:
                return _list_gcs_keys_for_prefix_public(bucket, prefix)
            resp.raise_for_status()

            payload = resp.json()
            for item in payload.get("items", []):
                name = item.get("name")
                if name and not name.endswith("/"):
                    keys.append(name)
                    if max_results is not None and len(keys) >= int(max_results):
                        return keys

            page_token = payload.get("nextPageToken")
            if not page_token:
                break

        return keys

    return cached_call(
        namespace="radar_nodd_gcp_prefix",
        key=(bucket, prefix, start_offset or "", max_results or 0),
        fetch_fn=_fetch,
        ttl_seconds=120,
    )


def _list_gcs_keys_for_prefix_public(bucket, prefix):
    requests = importlib.import_module("requests")

    def _fetch():
        keys = []
        continuation_token = None

        while True:
            params = {
                "list-type": 2,
                "prefix": prefix,
                "max-keys": 1000,
            }
            if continuation_token:
                params["continuation-token"] = continuation_token

            resp = requests.get(
                f"https://storage.googleapis.com/{bucket}",
                params=params,
                timeout=30,
            )
            if resp.status_code in {401, 403}:
                _log(
                    f"[WARN] GCP public listing returned {resp.status_code} for bucket={bucket} prefix={prefix}"
                )
                return []
            resp.raise_for_status()

            root = ET.fromstring(resp.content)
            for key_node in root.findall(".//{*}Contents/{*}Key"):
                key = (key_node.text or "").strip()
                if key and not key.endswith("/"):
                    keys.append(key)

            next_token = root.find(".//{*}NextContinuationToken")
            continuation_token = (
                (next_token.text or "").strip() if next_token is not None else ""
            )
            if not continuation_token:
                break

        return keys

    return cached_call(
        namespace="radar_nodd_gcp_public_prefix",
        key=(bucket, prefix),
        fetch_fn=_fetch,
        ttl_seconds=120,
    )


def list_nexrad_files(
    s3_client,
    level,
    station_id,
    product,
    start_dt,
    end_dt,
    provider="aws",
    latest_only=False,
):
    provider = str(provider).lower()
    level_lower = str(level).lower().replace(" ", "")
    keys = []

    level2_bucket = (
        NEXRAD_LEVEL2_GCP_BUCKET if provider == "gcp" else NEXRAD_LEVEL2_BUCKET
    )
    level3_buckets = (
        [NEXRAD_LEVEL3_GCP_BUCKET] if provider == "gcp" else [NEXRAD_LEVEL3_BUCKET]
    )

    _t0 = _time.perf_counter()
    _log(
        f"[NODD] list_nexrad_files: level={level} site={station_id} "
        f"product={product} provider={provider} latest_only={latest_only} "
        f"start_dt={start_dt} end_dt={end_dt}"
    )

    # ------------------------------------------------------------------
    # LEVEL 2
    # ------------------------------------------------------------------
    if level_lower == "level2":
        for day in _iter_days(start_dt, end_dt):
            prefix = f"{day.year}/{day.month:02d}/{day.day:02d}/{station_id}/"
            _log(f"[NODD] Level2: Probing prefix {prefix} on {level2_bucket}")
            try:
                if provider == "gcp":
                    day_keys = _list_gcs_keys_for_prefix(level2_bucket, prefix)
                else:
                    day_keys = _list_objects_for_prefix(
                        s3_client, level2_bucket, prefix
                    )
                _log(f"[NODD] Level2: Found {len(day_keys)} files in {prefix}")
                keys.extend(day_keys)
            except Exception as e:
                _log(
                    f"[WARN] Level2 list failed provider={provider} "
                    f"prefix={prefix}: {type(e).__name__}: {e}"
                )

    # ------------------------------------------------------------------
    # LEVEL 3
    # ------------------------------------------------------------------
    else:
        station_short = (
            station_id[1:]
            if station_id.startswith("K") and len(station_id) == 4
            else station_id
        )

        # =============================
        # FAST LATEST MODE
        # =============================
        if latest_only:
            latest_candidate = None

            # ---- Flat prefix probe (AWS fastest path) ----
            flat_prefixes = [
                f"{station_short}_{product}_",
                f"{station_id}_{product}_",
            ]

            for flat_prefix in flat_prefixes:
                for hours_back in (0, 24):
                    ref_dt = end_dt - timedelta(hours=hours_back)

                    if provider == "gcp":
                        marker = f"{flat_prefix}{ref_dt:%Y%m%d}"
                    else:
                        marker = f"{flat_prefix}{ref_dt:%Y_%m_%d}"

                    for bucket in level3_buckets:
                        try:
                            if provider == "gcp":
                                probe_keys = _list_gcs_keys_for_prefix(
                                    bucket,
                                    flat_prefix,
                                    start_offset=marker,
                                    max_results=128,
                                )
                            else:
                                probe_keys = _list_objects_for_prefix(
                                    s3_client,
                                    bucket,
                                    flat_prefix,
                                    start_after=marker,
                                    max_keys=128,
                                )
                        except Exception:
                            continue

                        for key in probe_keys:
                            file_dt = _parse_radar_time_from_key(key)
                            if file_dt is None:
                                continue
                            if not (start_dt <= file_dt <= end_dt):
                                continue

                            if (
                                latest_candidate is None
                                or file_dt > latest_candidate[0]
                            ):
                                latest_candidate = (file_dt, key)

                    if latest_candidate:
                        _log(
                            f"[NODD] Latest found via flat probe "
                            f"in {_time.perf_counter() - _t0:.2f}s"
                        )
                        return [latest_candidate[1]]

            # ---- Fallback: today + yesterday only ----
            for day in (
                end_dt.date(),
                (end_dt - timedelta(days=1)).date(),
            ):
                for template in LEVEL3_DAY_PREFIX_PATTERNS:
                    try:
                        prefix = template.format(
                            product=product,
                            station=station_id,
                            station_short=station_short,
                            year=day.year,
                            month=day.month,
                            day=day.day,
                        )
                    except KeyError:
                        continue

                    for bucket in level3_buckets:
                        try:
                            if provider == "gcp":
                                day_keys = _list_gcs_keys_for_prefix(bucket, prefix)
                            else:
                                day_keys = _list_objects_for_prefix(
                                    s3_client, bucket, prefix
                                )
                        except Exception:
                            continue

                        for key in day_keys:
                            file_dt = _parse_radar_time_from_key(key)
                            if file_dt is None:
                                continue
                            if not (start_dt <= file_dt <= end_dt):
                                continue

                            if (
                                latest_candidate is None
                                or file_dt > latest_candidate[0]
                            ):
                                latest_candidate = (file_dt, key)

                    if latest_candidate:
                        _log(
                            f"[NODD] Latest found via day prefix "
                            f"in {_time.perf_counter() - _t0:.2f}s"
                        )
                        return [latest_candidate[1]]

            # No deep scan in latest mode
            _log(
                f"[NODD] Latest mode found nothing in {_time.perf_counter() - _t0:.2f}s"
            )
            return []

        # =============================
        # ARCHIVE / TIMEFRAME MODE
        # =============================
        prefixes = set()

        for day in _iter_days(start_dt, end_dt):
            for template in LEVEL3_DAY_PREFIX_PATTERNS:
                try:
                    prefix = template.format(
                        product=product,
                        station=station_id,
                        station_short=station_short,
                        year=day.year,
                        month=day.month,
                        day=day.day,
                    )
                except KeyError:
                    continue
                prefixes.add(prefix)

        for prefix in sorted(prefixes):
            for bucket in level3_buckets:
                try:
                    if provider == "gcp":
                        keys.extend(_list_gcs_keys_for_prefix(bucket, prefix))
                    else:
                        keys.extend(_list_objects_for_prefix(s3_client, bucket, prefix))
                except Exception as e:
                    _log(
                        f"[WARN] Level3 archive list failed "
                        f"provider={provider} prefix={prefix}: "
                        f"{type(e).__name__}: {e}"
                    )

        # Flat key fallback (common on AWS L3 archive): TLX_N0Q_YYYY_MM_DD_HH_MM_SS
        flat_prefixes = [
            f"{station_short}_{product}_",
            f"{station_id}_{product}_",
        ]

        for day in _iter_days(start_dt, end_dt):
            for flat_prefix in flat_prefixes:
                marker = (
                    f"{flat_prefix}{day:%Y%m%d}"
                    if provider == "gcp"
                    else f"{flat_prefix}{day:%Y_%m_%d}"
                )

                for bucket in level3_buckets:
                    try:
                        if provider == "gcp":
                            keys.extend(
                                _list_gcs_keys_for_prefix(
                                    bucket,
                                    flat_prefix,
                                    start_offset=marker,
                                    max_results=2000,
                                )
                            )
                        else:
                            keys.extend(
                                _list_objects_for_prefix(
                                    s3_client,
                                    bucket,
                                    flat_prefix,
                                    start_after=marker,
                                    max_keys=2000,
                                )
                            )
                    except Exception as e:
                        _log(
                            f"[WARN] Level3 flat list failed provider={provider} "
                            f"prefix={flat_prefix} marker={marker}: "
                            f"{type(e).__name__}: {e}"
                        )

    # ------------------------------------------------------------------
    # FINAL FILTER + SORT
    # ------------------------------------------------------------------
    _log(f"[NODD] Total keys collected: {len(keys)}")
    filtered = []
    unparseable = 0
    out_of_range = 0
    for key in set(keys):
        file_dt = _parse_radar_time_from_key(key)
        if file_dt is None:
            unparseable += 1
            continue
        if not (start_dt <= file_dt <= end_dt):
            out_of_range += 1
            continue
        filtered.append((file_dt, key))

    filtered.sort(key=lambda x: x[0])

    _log(
        f"[NODD] Filtered: {len(filtered)} pass, {unparseable} unparseable, "
        f"{out_of_range} out of range {start_dt}—{end_dt} "
        f"({_time.perf_counter() - _t0:.2f}s)"
    )

    return [k for _, k in filtered]


def _enforce_cache_size(root_dir, max_bytes=CACHE_MAX_BYTES):
    if not os.path.isdir(root_dir):
        return

    all_files = []
    total_size = 0
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            try:
                stat = os.stat(file_path)
                total_size += stat.st_size
                all_files.append((stat.st_mtime, stat.st_size, file_path))
            except OSError:
                continue

    if total_size <= max_bytes:
        return

    all_files.sort(key=lambda x: x[0])
    bytes_to_free = total_size - max_bytes
    freed = 0

    for _, size, file_path in all_files:
        try:
            os.remove(file_path)
            freed += size
        except OSError:
            continue
        if freed >= bytes_to_free:
            break


def download_radar_data(
    level,
    station_id,
    product,
    lookback_hours,
    base_dir,
    progress_callback=None,
    provider="aws",
    date_from=None,
    date_to=None,
    latest_only=False,
):
    provider = str(provider).lower()
    level_path = str(level).lower().replace(" ", "")

    # Use explicit date range if provided, otherwise lookback from now
    is_archive = bool(date_from and date_to)
    if is_archive:
        start_dt = date_from
        end_dt = date_to
        # Archive downloads go into a separate directory tree
        save_dir = os.path.join(
            base_dir,
            "archive",
            f"radar_{level_path}_downloads",
            product,
            station_id,
        )
    else:
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(hours=float(lookback_hours))
        save_dir = os.path.join(
            base_dir, f"radar_{level_path}_downloads", product, station_id
        )
    os.makedirs(save_dir, exist_ok=True)

    _t_total = _time.perf_counter()
    try:
        _t_list = _time.perf_counter()
        s3_client = get_s3_client() if provider == "aws" else None
        keys = list_nexrad_files(
            s3_client=s3_client,
            level=level,
            station_id=station_id,
            product=product,
            start_dt=start_dt,
            end_dt=end_dt,
            provider=provider,
            latest_only=latest_only,
        )
        _log(
            f"[TIMER] listing took {_time.perf_counter() - _t_list:.2f}s  ({len(keys)} keys, provider={provider})"
        )
    except Exception as e:
        _log(f"[ERROR] NODD list_nexrad_files failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise

    total_files = len(keys)
    if total_files == 0:
        return save_dir, 0, 0

    if latest_only:
        keys = keys[-1:]
        total_files = len(keys)

    if provider == "gcp":
        buckets = (
            [NEXRAD_LEVEL2_GCP_BUCKET]
            if level_path == "level2"
            else [NEXRAD_LEVEL3_GCP_BUCKET]
        )
        requests = importlib.import_module("requests")
    else:
        buckets = [
            NEXRAD_LEVEL2_BUCKET if level_path == "level2" else NEXRAD_LEVEL3_BUCKET
        ]
        requests = None

    downloaded = 0

    def _has_nonempty_file(path):
        try:
            return os.path.exists(path) and os.path.getsize(path) > 0
        except OSError:
            return False

    _t_dl = _time.perf_counter()
    for idx, key in enumerate(keys, start=1):
        if progress_callback:
            progress_callback(idx, total_files)

        filename = os.path.basename(key)
        local_path = os.path.join(save_dir, filename)

        if _has_nonempty_file(local_path):
            continue

        download_succeeded = False
        for attempt in range(1, DOWNLOAD_RETRY_ATTEMPTS + 1):
            try:
                if provider == "gcp":
                    encoded_key = quote(key, safe="/")
                    resp = None
                    for bucket in buckets:
                        url = f"https://storage.googleapis.com/{bucket}/{encoded_key}"
                        candidate = requests.get(url, timeout=60)
                        if candidate.status_code == 200:
                            resp = candidate
                            break
                    if resp is None:
                        raise RuntimeError(
                            f"File not found in any GCP bucket for key={key}"
                        )
                    with open(local_path, "wb") as file_handle:
                        file_handle.write(resp.content)
                else:
                    bucket = buckets[0]
                    s3_client.download_file(bucket, key, local_path)

                if _has_nonempty_file(local_path):
                    downloaded += 1
                    download_succeeded = True
                break
            except (FileExistsError, PermissionError) as e:
                # Concurrent requests can race to write the same file on Windows.
                _time.sleep(DOWNLOAD_RETRY_SLEEP_SECONDS)
                if _has_nonempty_file(local_path):
                    downloaded += 1
                    download_succeeded = True
                    _log(
                        f"[INFO] NODD radar download race-resolved: {type(e).__name__}: {e} | provider={provider} key={key}"
                    )
                    break

                if attempt >= DOWNLOAD_RETRY_ATTEMPTS:
                    _log(
                        f"[WARN] NODD radar download failed after retries: {type(e).__name__}: {e} | provider={provider} key={key}"
                    )
            except Exception as e:
                _log(
                    f"[WARN] NODD radar download failed: {type(e).__name__}: {e} | provider={provider} key={key}"
                )
                break

        if not download_succeeded and _has_nonempty_file(local_path):
            downloaded += 1

    _log(
        f"[TIMER] download loop took {_time.perf_counter() - _t_dl:.2f}s  (downloaded={downloaded}/{total_files})"
    )
    _t_cache = _time.perf_counter()
    _enforce_cache_size(os.path.join(base_dir, f"radar_{level_path}_downloads"))
    _log(f"[TIMER] _enforce_cache_size took {_time.perf_counter() - _t_cache:.2f}s")
    _log(f"[TIMER] download_radar_data TOTAL {_time.perf_counter() - _t_total:.2f}s")
    return save_dir, total_files, downloaded

