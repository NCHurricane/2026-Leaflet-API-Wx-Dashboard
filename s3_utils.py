"""
Shared AWS S3 client utilities for all NODD data access.

Provides a single unsigned S3 client factory with retry/timeout configuration
used by satellite, radar, MRMS, and lightning modules.  Also includes an HTTP-
based S3 prefix lister for environments where boto3 is not required.
"""

import importlib
import xml.etree.ElementTree as ET


def get_s3_client():
    """Create an unsigned S3 client for public NOAA bucket access.

    Uses lazy imports so boto3 is only loaded when actually needed.
    Configured with retries (6 attempts, standard mode) and conservative
    connect/read timeouts suitable for large NODD file downloads.

    Returns:
        boto3 S3 client configured for anonymous (unsigned) requests.
    """
    boto3 = importlib.import_module("boto3")
    botocore = importlib.import_module("botocore")
    botocore_config = importlib.import_module("botocore.config")

    return boto3.client(
        "s3",
        region_name="us-east-1",
        config=botocore_config.Config(
            signature_version=botocore.UNSIGNED,
            retries={"max_attempts": 6, "mode": "standard"},
            connect_timeout=10,
            read_timeout=60,
        ),
    )


def list_s3_prefix_http(bucket, prefix, timeout=15):
    """List S3 object keys under *prefix* using the public HTTP API.

    This avoids a boto3 dependency for lightweight listing operations
    (e.g., GLM lightning files).  Returns a list of key strings.
    """
    requests = importlib.import_module("requests")

    url = f"https://{bucket}.s3.amazonaws.com/?list-type=2&prefix={prefix}"
    try:
        response = requests.get(url, timeout=timeout)
    except Exception as e:
        print(f"S3 HTTP list error for {bucket}/{prefix}: {e}")
        return []

    if response.status_code != 200:
        print(f"S3 HTTP list error: HTTP {response.status_code}")
        return []

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return []

    keys = []
    for elem in root.iter():
        if elem.tag.endswith("Key") and elem.text:
            keys.append(elem.text)
    return keys
