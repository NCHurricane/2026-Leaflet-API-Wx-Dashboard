"""
MRMS NODD Utilities
S3 access for Multi-Radar Multi-Sensor (MRMS) data from noaa-mrms-pds bucket.

Data Source: s3://noaa-mrms-pds
Format: GRIB2
Update Frequency: Every 2 minutes
"""

import os
import sys
import importlib.util
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Callable
from botocore.exceptions import ClientError
from dateutil import tz
from config.mrms_config import MRMS_BUCKET, MRMS_PRODUCTS

# Add parent directory to path for imports
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)


# Cache configuration (check if listing_cache module is available)
CACHE_AVAILABLE = importlib.util.find_spec("listing_cache") is not None


# Consolidated S3 client — shared across all NODD modules
from s3_utils import get_s3_client  # noqa: E402


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

    print(f"[DEBUG] MRMS S3 prefix for {product} on {date_str}: {prefix}")
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
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> List[Tuple[str, datetime]]:
    """
    List MRMS GRIB2 files in S3 bucket within time range.

    Args:
        product: MRMS product key (e.g., "QPE_01H")
        start_time: Start of time range (UTC)
        end_time: End of time range (UTC)
        progress_callback: Optional callback(current_count, total_estimate) for progress updates

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

    total_prefixes = len(date_prefixes)

    # List objects in each date prefix
    for idx, prefix in enumerate(date_prefixes):
        if progress_callback:
            progress_callback(idx + 1, total_prefixes)

        print(f"[DEBUG] Checking S3 prefix: {prefix}")

        try:
            paginator = s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=MRMS_BUCKET, Prefix=prefix)

            page_count = 0
            for page in pages:
                page_count += 1
                if "Contents" not in page:
                    print(
                        f"[DEBUG] No contents in page {page_count} for {prefix}")
                    continue

                for obj in page["Contents"]:
                    key = obj["Key"]

                    # Parse timestamp from filename
                    file_dt = parse_mrms_filename(key)

                    if file_dt and start_time <= file_dt <= end_time:
                        files.append((key, file_dt))

            if page_count == 0:
                print(f"[DEBUG] No pages returned for {prefix}")
            else:
                print(
                    f"[DEBUG] Found {len([f for f in files if prefix in f[0]])} matching files in {prefix}"
                )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code != "NoSuchKey":
                print(f"Error listing S3 prefix {prefix}: {e}")
            continue

    # Sort by datetime
    files.sort(key=lambda x: x[1])

    return files


def download_mrms_file(
    s3_key: str,
    local_dir: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Download MRMS GRIB2 file from S3.

    Args:
        s3_key: S3 key of the file to download
        local_dir: Local directory to save file
        progress_callback: Optional callback for download progress

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
            print(f"[DEBUG] Using cached MRMS file: {local_path}")
            if progress_callback:
                progress_callback(local_size, local_size)
            return local_path
        # Remove empty/partial files so they can be downloaded cleanly.
        try:
            os.remove(local_path)
        except OSError:
            pass

    # Download file
    try:
        # Get file size for progress tracking
        response = s3_client.head_object(Bucket=MRMS_BUCKET, Key=s3_key)
        total_size = response.get("ContentLength", 0)

        # Download with progress tracking
        if progress_callback and total_size > 0:

            def progress_hook(bytes_transferred):
                progress_callback(bytes_transferred, total_size)

            s3_client.download_file(
                MRMS_BUCKET, s3_key, local_path, Callback=progress_hook
            )
        else:
            s3_client.download_file(MRMS_BUCKET, s3_key, local_path)

        return local_path

    except ClientError:
        raise


def download_mrms_data(
    product: str,
    start_time: datetime,
    end_time: datetime,
    local_dir: str,
    max_files: Optional[int] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> List[Tuple[str, datetime]]:
    """
    Download MRMS data files for specified product and time range.

    Args:
        product: MRMS product key
        start_time: Start of time range (UTC)
        end_time: End of time range (UTC)
        local_dir: Local directory to save files
        max_files: Maximum number of files to download (None = no limit)
        progress_callback: Optional callback(stage, current, total) for progress

    Returns:
        List of tuples: (local_file_path, datetime)
        Sorted chronologically
    """
    # List available files
    if progress_callback:
        progress_callback("Listing files", 0, 100)

    print(
        f"[DEBUG] Listing MRMS files for {product} from {start_time} to {end_time}")

    available_files = list_mrms_files(
        product,
        start_time,
        end_time,
        lambda curr, total: (
            progress_callback("Listing files", curr, total)
            if progress_callback
            else None
        ),
    )

    print(f"[DEBUG] Found {len(available_files)} MRMS files for {product}")

    if not available_files:
        return []

    # Limit files if requested
    if max_files and len(available_files) > max_files:
        # Take the most recent files (keep last N files)
        available_files = available_files[-max_files:]
        print(f"[DEBUG] Limited to {max_files} most recent files")

    # Download files
    downloaded_files = []
    total_files = len(available_files)

    for idx, (s3_key, file_dt) in enumerate(available_files):
        if progress_callback:
            progress_callback("Downloading files", idx + 1, total_files)

        try:
            day_dir = os.path.join(
                local_dir,
                file_dt.strftime("%Y"),
                file_dt.strftime("%m"),
                file_dt.strftime("%d"),
            )
            local_path = download_mrms_file(s3_key, day_dir)
            downloaded_files.append((local_path, file_dt))
        except Exception as e:
            print(f"Failed to download {s3_key}: {e}")
            continue

    return downloaded_files


def get_latest_mrms_file(
    product: str, lookback_minutes: int = 30, local_dir: str = None
) -> Optional[Tuple[str, datetime]]:
    """
    Get the most recent MRMS file for a product.

    Args:
        product: MRMS product key
        lookback_minutes: How far back to search (default: 30 minutes)
        local_dir: Local directory to save file (if None, only returns metadata)

    Returns:
        Tuple of (local_file_path, datetime) if found and downloaded, None otherwise
        If local_dir is None, returns (s3_key, datetime)
    """
    end_time = datetime.now(tz.UTC)
    start_time = end_time - timedelta(minutes=lookback_minutes)

    available_files = list_mrms_files(product, start_time, end_time)

    if not available_files:
        return None

    # Get most recent file
    s3_key, file_dt = available_files[-1]

    if local_dir:
        try:
            local_path = download_mrms_file(s3_key, local_dir)
            return (local_path, file_dt)
        except Exception as e:
            print(f"Failed to download latest file {s3_key}: {e}")
            return None
    else:
        return (s3_key, file_dt)
