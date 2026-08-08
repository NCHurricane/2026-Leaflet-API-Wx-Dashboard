"""
MRMS NODD Utilities
S3 access for Multi-Radar Multi-Sensor (MRMS) data from noaa-mrms-pds bucket.

Data Source: s3://noaa-mrms-pds
Format: GRIB2
Update Frequency: Every 2 minutes
"""

import logging

import os
import gzip
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from botocore.exceptions import ClientError
from dateutil import tz
from config.mrms_config import MRMS_BUCKET, MRMS_PRODUCTS
from app_core.atomic_io import atomic_output_path

# Consolidated S3 client — shared across all NODD modules
from lib.s3_utils import get_s3_client  # noqa: E402


def _is_valid_gzip_file(path: str, chunk_size: int = 1024 * 1024) -> bool:
    """Validate gzip integrity by streaming through the full file.

    Reading only the first byte can miss truncated tails and CRC/footer errors,
    which then surface later during cfgrib decode.
    """
    try:
        with gzip.open(path, "rb") as fh:
            while fh.read(chunk_size):
                pass
        return True
    except Exception:
        return False


def construct_s3_prefix(product: str, dt: datetime) -> str:
    """
    Construct S3 prefix for MRMS product at given datetime.

    MRMS S3 structure:
    s3://noaa-mrms-pds/CONUS/{ProductName}_00.00/{YYYYMMDD}/

    Args:
        product: MRMS product key (e.g., "QPE_01H", "PrecipRate")
        dt: datetime object for the target time

    Returns:
        S3 prefix string (e.g., "CONUS/MultiSensor_QPE_01H_Pass2/20260216/")
    """
    if product not in MRMS_PRODUCTS:
        raise ValueError(
            f"Unknown MRMS product: {product}. Available: {list(MRMS_PRODUCTS.keys())}"
        )

    product_info = MRMS_PRODUCTS[product]
    s3_product_prefix = product_info["s3_prefix"]

    # Format: CONUS/{ProductName}/{YYYYMMDD}/
    date_str = dt.strftime("%Y%m%d")
    prefix = f"{s3_product_prefix}/{date_str}/"

    logging.getLogger(__name__).info(f"[DEBUG] MRMS S3 prefix for {product} on {date_str}: {prefix}")
    return prefix


def parse_mrms_filename(key: str) -> Optional[datetime]:
    """
    Parse MRMS GRIB2 filename to extract timestamp.

    MRMS filename format:
    MRMS_{ProductName}_00.00_{YYYYMMDD}-{HHMMSS}.grib2.gz
    Example: MRMS_MultiSensor_QPE_01H_Pass2_00.00_20260216-120000.grib2.gz

    Args:
        key: S3 key or filename

    Returns:
        datetime object if parsed successfully, None otherwise
    """
    try:
        filename = os.path.basename(key)

        # Extract timestamp from filename
        # Format: *_{YYYYMMDD}-{HHMMSS}.grib2.gz
        if "_" not in filename or "-" not in filename:
            return None

        parts = filename.split("_")
        for part in parts:
            if "-" in part and len(part) >= 15:  # YYYYMMDD-HHMMSS
                datetime_str = part.split(".")[0]  # Remove .grib2.gz
                if len(datetime_str) == 15:  # YYYYMMDD-HHMMSS
                    dt = datetime.strptime(datetime_str, "%Y%m%d-%H%M%S")
                    # Make timezone-aware as UTC (MRMS files use UTC timestamps)
                    dt = dt.replace(tzinfo=tz.UTC)
                    return dt

        return None
    except Exception:
        return None


def list_mrms_files(
    product: str,
    start_time: datetime,
    end_time: datetime,
) -> List[Tuple[str, datetime]]:
    """
    List MRMS GRIB2 files in S3 bucket within time range.

    Args:
        product: MRMS product key (e.g., "QPE_01H")
        start_time: Start of time range (UTC)
        end_time: End of time range (UTC)
    Returns:
        List of tuples: (s3_key, datetime)
        Sorted chronologically
    """
    s3_client = get_s3_client()
    files = []

    # Generate list of date prefixes to search
    current_date = start_time.date()
    end_date = end_time.date()
    date_prefixes = []

    while current_date <= end_date:
        dt = datetime.combine(current_date, datetime.min.time())
        prefix = construct_s3_prefix(product, dt)
        date_prefixes.append(prefix)
        current_date += timedelta(days=1)

    # List objects in each date prefix
    for prefix in date_prefixes:
        logging.getLogger(__name__).info(f"[DEBUG] Checking S3 prefix: {prefix}")

        try:
            paginator = s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=MRMS_BUCKET, Prefix=prefix)

            page_count = 0
            for page in pages:
                page_count += 1
                if "Contents" not in page:
                    logging.getLogger(__name__).info(
                        f"[DEBUG] No contents in page {page_count} for {prefix}")
                    continue

                for obj in page["Contents"]:
                    key = obj["Key"]

                    # Parse timestamp from filename
                    file_dt = parse_mrms_filename(key)

                    if file_dt and start_time <= file_dt <= end_time:
                        files.append((key, file_dt))

            if page_count == 0:
                logging.getLogger(__name__).info(f"[DEBUG] No pages returned for {prefix}")
            else:
                logging.getLogger(__name__).info(
                    f"[DEBUG] Found {len([f for f in files if prefix in f[0]])} matching files in {prefix}"
                )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code != "NoSuchKey":
                logging.getLogger(__name__).warning(f"Error listing S3 prefix {prefix}: {type(e).__name__}")
            continue

    # Sort by datetime
    files.sort(key=lambda x: x[1])

    return files


def download_mrms_file(
    s3_key: str,
    local_dir: str,
) -> str:
    """
    Download MRMS GRIB2 file from S3.

    Args:
        s3_key: S3 key of the file to download
        local_dir: Local directory to save file
    Returns:
        Local file path of downloaded file

    Raises:
        ClientError: If download fails
    """
    s3_client = get_s3_client()

    # Create local directory if needed
    os.makedirs(local_dir, exist_ok=True)

    # Construct local filename
    filename = os.path.basename(s3_key)
    local_path = os.path.join(local_dir, filename)

    # Reuse existing local file when present.
    # This prevents unnecessary repeated downloads while testing/rerendering.
    if os.path.exists(local_path):
        local_size = os.path.getsize(local_path)
        if local_size > 0:
            # Validate cached .gz files before reuse; a truncated/corrupt file can
            # otherwise persist forever and trigger decode errors downstream.
            is_valid_cached = True
            if local_path.endswith(".gz"):
                is_valid_cached = _is_valid_gzip_file(local_path)

            if is_valid_cached:
                logging.getLogger(__name__).info(f"[DEBUG] Using cached MRMS file: {local_path}")
                return local_path

            logging.getLogger(__name__).warning(f"[DEBUG] Removing corrupt cached MRMS file: {local_path}")
        # Remove empty/partial files so they can be downloaded cleanly.
        try:
            os.remove(local_path)
        except OSError:
            pass

    # Download file
    try:
        # Download with job-owned atomic replacement to avoid cross-request cleanup.
        with atomic_output_path(local_path, suffix=".part") as temporary:
            s3_client.download_file(MRMS_BUCKET, s3_key, str(temporary))

            if local_path.endswith(".gz") and not _is_valid_gzip_file(str(temporary)):
                raise ValueError(
                    f"Downloaded MRMS gzip failed integrity validation: {s3_key}"
                )

        return local_path

    except ClientError:
        raise


def get_latest_mrms_file(
    product: str, lookback_minutes: int = 30
) -> Optional[Tuple[str, datetime]]:
    """
    Get the most recent MRMS file for a product.

    Args:
        product: MRMS product key
        lookback_minutes: How far back to search (default: 30 minutes)

    Returns:
        Tuple of (s3_key, datetime) if found, otherwise None.
    """
    end_time = datetime.now(tz.UTC)
    start_time = end_time - timedelta(minutes=lookback_minutes)

    available_files = list_mrms_files(product, start_time, end_time)

    if not available_files:
        return None

    # Get most recent file
    s3_key, file_dt = available_files[-1]

    return (s3_key, file_dt)
