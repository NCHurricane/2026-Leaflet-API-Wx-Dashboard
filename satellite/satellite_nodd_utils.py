from config.satellite_config import ABI_CHANNELS
from font_utils import register_montserrat_fonts
from datetime import datetime, timedelta, timezone
import importlib
import os
import re
import traceback
from urllib.parse import quote

from listing_cache import cached_call

try:
    from . import satellite_utils as thredds_satellite_utils
except ImportError:
    import satellite_utils as thredds_satellite_utils


register_montserrat_fonts()


GOES_BUCKET_BY_SAT = {
    "goes16": "noaa-goes16",
    "goes17": "noaa-goes17",
    "goes18": "noaa-goes18",
    "goes19": "noaa-goes19",
}

GOES_GCP_BUCKET_BY_SAT = {
    "goes18": "gcp-public-data-goes-18",
    "goes19": "gcp-public-data-goes-19",
}

SECTOR_TO_PRODUCT_SUFFIX = {
    "CONUS": "C",
    "Full Disk": "F",
    "FullDisk": "F",
    "FULLDISK": "F",
    "FULL DISK": "F",
    "full_disk": "F",
    "Meso1": "M1",
    "MESO1": "M1",
    "meso1": "M1",
    "Meso2": "M2",
    "MESO2": "M2",
    "meso2": "M2",
}

SECTOR_TO_SCENE_TAG = {
    "Meso1": "M1",
    "MESO1": "M1",
    "meso1": "M1",
    "Meso2": "M2",
    "MESO2": "M2",
    "meso2": "M2",
}

CACHE_MAX_BYTES = 20 * 1024 * 1024 * 1024


def normalize_sector_name(sector):
    text = str(sector or "CONUS").strip()
    slug = text.lower().replace(" ", "").replace("_", "").replace("-", "")

    if slug == "conus":
        return "CONUS"
    if slug == "fulldisk":
        return "Full Disk"
    if slug in ("meso1", "mesoscale1"):
        return "Meso1"
    if slug in ("meso2", "mesoscale2"):
        return "Meso2"
    return text


# Consolidated S3 client — shared across all NODD modules
from s3_utils import get_s3_client  # noqa: E402


def _extract_channel_number(channel_key):
    match = re.search(r"(\d+)", str(channel_key))
    return int(match.group(1)) if match else None


def _date_partition_dir(base_dir, dt_obj):
    dt_utc = (
        dt_obj.replace(tzinfo=timezone.utc)
        if isinstance(dt_obj, datetime) and dt_obj.tzinfo is None
        else dt_obj.astimezone(timezone.utc)
        if isinstance(dt_obj, datetime)
        else datetime.now(timezone.utc)
    )
    return os.path.join(
        base_dir,
        dt_utc.strftime("%Y"),
        dt_utc.strftime("%m"),
        dt_utc.strftime("%d"),
    )


def _iter_hours(start_dt, end_dt):
    current = start_dt.replace(minute=0, second=0, microsecond=0)
    final = end_dt.replace(minute=0, second=0, microsecond=0)
    while current <= final:
        yield current
        current += timedelta(hours=1)


def _list_gcs_keys_for_prefix(bucket, prefix):
    requests = importlib.import_module("requests")

    def _fetch():
        keys = []
        page_token = None

        while True:
            params = {
                "prefix": prefix,
                "maxResults": 1000,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = requests.get(
                f"https://storage.googleapis.com/storage/v1/b/{bucket}/o",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()

            payload = resp.json()
            for item in payload.get("items", []):
                name = item.get("name")
                if name:
                    keys.append(name)

            page_token = payload.get("nextPageToken")
            if not page_token:
                break

        return keys

    return cached_call(
        namespace="satellite_nodd_gcp_prefix",
        key=(bucket, prefix),
        fetch_fn=_fetch,
        ttl_seconds=20,
    )


def list_goes_files(
    s3_client,
    bucket,
    product_prefix,
    start_dt,
    end_dt,
    channel_num=None,
    scene_tag=None,
    provider="aws",
):
    keys = []
    provider = str(provider).lower()
    paginator = (
        s3_client.get_paginator("list_objects_v2") if provider == "aws" else None
    )

    # When start == end (single-frame request), expand end to cover the full hour
    effective_end = end_dt
    if start_dt == end_dt:
        effective_end = end_dt.replace(minute=59, second=59)

    for hour_dt in _iter_hours(start_dt, effective_end):
        year = hour_dt.year
        jday = hour_dt.timetuple().tm_yday
        hour = hour_dt.hour
        prefix = f"{product_prefix}/{year}/{jday:03d}/{hour:02d}/"

        try:
            if provider == "gcp":
                prefix_keys = _list_gcs_keys_for_prefix(bucket, prefix)
            else:

                def _fetch_aws_prefix():
                    prefix_keys_local = []
                    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                        for obj in page.get("Contents", []):
                            key = obj.get("Key", "")
                            if key:
                                prefix_keys_local.append(key)
                    return prefix_keys_local

                prefix_keys = cached_call(
                    namespace="satellite_nodd_aws_prefix",
                    key=(bucket, prefix),
                    fetch_fn=_fetch_aws_prefix,
                    ttl_seconds=20,
                )

            for key in prefix_keys:
                if not key.endswith(".nc"):
                    continue

                if scene_tag is not None and f"CMIP{scene_tag}-" not in key:
                    continue

                if channel_num is not None:
                    channel_match = re.search(r"-M\dC(\d{2})_", key)
                    if not channel_match or int(channel_match.group(1)) != channel_num:
                        continue

                scan_time = thredds_satellite_utils.parse_goes_time_from_filename(
                    os.path.basename(key)
                )
                if scan_time is None:
                    continue
                if not (start_dt <= scan_time <= effective_end):
                    continue

                keys.append((scan_time, key))
        except Exception as e:
            print(
                f"[WARN] NODD list_goes_files failed for provider={provider} prefix={prefix}: {type(e).__name__}: {e}"
            )

    deduped = sorted(set(keys), key=lambda x: x[0])
    return [key for _, key in deduped]


def get_goes_data(sat_id, sector, channel_key, lookback_hours=2, provider="aws"):
    provider = str(provider).lower()
    sector = normalize_sector_name(sector)
    sat_key = str(sat_id).lower()
    bucket_map = GOES_GCP_BUCKET_BY_SAT if provider == "gcp" else GOES_BUCKET_BY_SAT
    bucket = bucket_map.get(sat_key)
    if bucket is None:
        digits = "".join(filter(str.isdigit, str(sat_id)))
        bucket = bucket_map.get(f"goes{digits}")

    if bucket is None:
        raise ValueError(f"Unsupported satellite id: {sat_id}")

    sector_suffix = SECTOR_TO_PRODUCT_SUFFIX.get(sector, "C")
    scene_tag = SECTOR_TO_SCENE_TAG.get(sector)
    product_suffix = "M" if scene_tag in {"M1", "M2"} else sector_suffix
    product_prefix = f"ABI-L2-CMIP{product_suffix}"

    channels_to_fetch = ABI_CHANNELS[channel_key].get("req", [channel_key])

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(hours=float(lookback_hours))

    s3_client = get_s3_client() if provider == "aws" else None
    results = {}

    for channel in channels_to_fetch:
        channel_num = _extract_channel_number(channel)
        if channel_num is None:
            print(f"[WARN] Could not parse channel number from {channel}, skipping")
            results[channel] = []
            continue

        channel_keys = list_goes_files(
            s3_client=s3_client,
            bucket=bucket,
            product_prefix=product_prefix,
            start_dt=start_dt,
            end_dt=end_dt,
            channel_num=channel_num,
            scene_tag=scene_tag,
            provider=provider,
        )
        results[channel] = channel_keys

    return results


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


def download_goes_data(
    sat_id,
    sector,
    channel_key,
    lookback_hours,
    base_dir,
    progress_callback=None,
    provider="aws",
    latest_only=False,
):
    provider = str(provider).lower()
    sector = normalize_sector_name(sector)
    try:
        data_map = get_goes_data(
            sat_id, sector, channel_key, lookback_hours, provider=provider
        )
    except Exception as e:
        print(f"[ERROR] NODD get_goes_data failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise

    if latest_only:
        data_map = {
            channel: (keys[-1:] if keys else []) for channel, keys in data_map.items()
        }

    total_found = sum(len(keys) for keys in data_map.values())
    if total_found == 0:
        print(
            f"[ERROR] NODD no satellite data found for {sat_id} {sector} {channel_key} in last {lookback_hours}h"
        )
        return None, 0, 0

    sat_key = str(sat_id).lower()
    bucket_map = GOES_GCP_BUCKET_BY_SAT if provider == "gcp" else GOES_BUCKET_BY_SAT
    bucket = bucket_map.get(sat_key)
    if bucket is None:
        digits = "".join(filter(str.isdigit, str(sat_id)))
        bucket = bucket_map.get(f"goes{digits}")

    save_root = os.path.join(base_dir, "satellite_downloads", str(sat_id), str(sector))
    os.makedirs(save_root, exist_ok=True)

    s3_client = get_s3_client() if provider == "aws" else None
    requests = importlib.import_module("requests") if provider == "gcp" else None
    download_count = 0
    processed_count = 0

    for channel, keys in data_map.items():
        channel_root = os.path.join(save_root, channel)
        os.makedirs(channel_root, exist_ok=True)

        for key in keys:
            processed_count += 1
            if progress_callback:
                progress_callback(processed_count, total_found)

            file_name = os.path.basename(key)
            scan_time = thredds_satellite_utils.parse_goes_time_from_filename(file_name)
            day_dir = _date_partition_dir(
                channel_root, scan_time or datetime.now(timezone.utc)
            )
            os.makedirs(day_dir, exist_ok=True)
            local_path = os.path.join(day_dir, file_name)

            if os.path.exists(local_path):
                continue

            try:
                if provider == "gcp":
                    encoded_key = quote(key, safe="/")
                    url = f"https://storage.googleapis.com/{bucket}/{encoded_key}"
                    resp = requests.get(url, timeout=60)
                    resp.raise_for_status()
                    with open(local_path, "wb") as file_handle:
                        file_handle.write(resp.content)
                else:
                    s3_client.download_file(bucket, key, local_path)
                download_count += 1
            except Exception as e:
                print(
                    f"[WARN] NODD download failed: {type(e).__name__}: {e} | provider={provider} bucket={bucket} key={key}"
                )

    _enforce_cache_size(os.path.join(base_dir, "satellite_downloads"))
    return save_root, total_found, download_count


def generate_satellite_animation(*args, **kwargs):
    return thredds_satellite_utils.generate_satellite_animation(*args, **kwargs)
