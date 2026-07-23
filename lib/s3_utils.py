"""
Shared AWS S3 client utilities for all NODD data access.

Provides a single unsigned S3 client factory with retry/timeout configuration
used by satellite, radar, MRMS, and lightning modules.  Also includes an HTTP-
based S3 prefix lister for environments where boto3 is not required.
"""

import importlib
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from app_core.upstream_ledger import (
    record_upstream_request,
    requests,
    upstream_operation,
)


class _TrackedPaginator:
    def __init__(self, paginator, operation_name):
        self._paginator = paginator
        self._operation_name = operation_name

    def paginate(self, **kwargs):
        bucket = str(kwargs.get("Bucket") or "unknown")
        prefix = str(kwargs.get("Prefix") or "")
        iterator = iter(self._paginator.paginate(**kwargs))
        page_number = 0
        while True:
            page_number += 1
            resource_key = f"s3://{bucket}/{prefix}#page-{page_number}"
            started = time.perf_counter()
            try:
                page = next(iterator)
            except StopIteration:
                return
            except Exception:
                record_upstream_request(
                    provider="noaa-nodd",
                    resource_key=resource_key,
                    method=self._operation_name,
                    status=None,
                    bytes_transferred=0,
                    duration_seconds=time.perf_counter() - started,
                    outcome="error",
                )
                raise
            byte_count = len(
                json.dumps(page, default=str, separators=(",", ":")).encode()
            )
            record_upstream_request(
                provider="noaa-nodd",
                resource_key=resource_key,
                method=self._operation_name,
                status=(page.get("ResponseMetadata") or {}).get(
                    "HTTPStatusCode", "ok"
                ),
                bytes_transferred=byte_count,
                duration_seconds=time.perf_counter() - started,
                retry_state=(
                    f"transport_retries:{(page.get('ResponseMetadata') or {}).get('RetryAttempts')}"
                    if (page.get("ResponseMetadata") or {}).get("RetryAttempts")
                    else "none"
                ),
            )
            yield page


class _TrackedS3Client:
    def __init__(self, client):
        self._client = client

    def get_paginator(self, operation_name):
        return _TrackedPaginator(
            self._client.get_paginator(operation_name), operation_name
        )

    def download_file(self, bucket, key, filename, *args, **kwargs):
        with upstream_operation(
            provider="noaa-nodd",
            resource_key=f"s3://{bucket}/{key}",
            method="download_file",
        ) as transfer:
            result = self._client.download_file(bucket, key, filename, *args, **kwargs)
            try:
                transfer["bytes"] = Path(filename).stat().st_size
            except OSError:
                pass
            return result

    def head_object(self, *, Bucket, Key, **kwargs):
        with upstream_operation(
            provider="noaa-nodd",
            resource_key=f"s3://{Bucket}/{Key}",
            method="head_object",
        ):
            return self._client.head_object(Bucket=Bucket, Key=Key, **kwargs)

    def get_object(self, *, Bucket, Key, **kwargs):
        started = time.perf_counter()
        resource_key = f"s3://{Bucket}/{Key}"
        try:
            response = self._client.get_object(Bucket=Bucket, Key=Key, **kwargs)
        except Exception:
            record_upstream_request(
                provider="noaa-nodd",
                resource_key=resource_key,
                method="get_object",
                status=None,
                bytes_transferred=0,
                duration_seconds=time.perf_counter() - started,
                outcome="error",
            )
            raise
        expected_bytes = int(response.get("ContentLength") or 0)
        status = (response.get("ResponseMetadata") or {}).get("HTTPStatusCode", "ok")
        retry_count = (response.get("ResponseMetadata") or {}).get("RetryAttempts") or 0
        body = response.get("Body")
        if body is None:
            record_upstream_request(
                provider="noaa-nodd",
                resource_key=resource_key,
                method="get_object",
                status=status,
                bytes_transferred=0,
                duration_seconds=time.perf_counter() - started,
            )
            return response
        response["Body"] = _TrackedStreamingBody(
            body,
            resource_key=resource_key,
            status=status,
            expected_bytes=expected_bytes,
            started=started,
            retry_state=(
                f"transport_retries:{retry_count}" if retry_count else "none"
            ),
        )
        return response

    def __getattr__(self, name):
        return getattr(self._client, name)


class _TrackedStreamingBody:
    def __init__(
        self, body, *, resource_key, status, expected_bytes, started, retry_state
    ):
        self._body = body
        self._resource_key = resource_key
        self._status = status
        self._expected_bytes = expected_bytes
        self._started = started
        self._retry_state = retry_state
        self._bytes = 0
        self._recorded = False

    def _record(self, outcome="success"):
        if self._recorded:
            return
        self._recorded = True
        record_upstream_request(
            provider="noaa-nodd",
            resource_key=self._resource_key,
            method="get_object",
            status=self._status,
            bytes_transferred=self._bytes or self._expected_bytes,
            duration_seconds=time.perf_counter() - self._started,
            retry_state=self._retry_state,
            outcome=outcome,
        )

    def read(self, *args, **kwargs):
        try:
            data = self._body.read(*args, **kwargs)
        except Exception:
            self._record("error")
            raise
        self._bytes += len(data or b"")
        amount = args[0] if args else kwargs.get("amt")
        if amount is None or self._bytes >= self._expected_bytes:
            self._record()
        return data

    def close(self):
        try:
            return self._body.close()
        finally:
            self._record()

    def __getattr__(self, name):
        return getattr(self._body, name)


def track_s3_client(client):
    """Wrap an existing configured S3 client without changing its behavior."""
    if isinstance(client, _TrackedS3Client):
        return client
    return _TrackedS3Client(client)


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

    return track_s3_client(
        boto3.client(
            "s3",
            region_name="us-east-1",
            config=botocore_config.Config(
                signature_version=botocore.UNSIGNED,
                retries={"max_attempts": 6, "mode": "standard"},
                connect_timeout=10,
                read_timeout=60,
            ),
        )
    )


def list_s3_prefix_http(bucket, prefix, timeout=15):
    """List S3 object keys under *prefix* using the public HTTP API.

    This avoids a boto3 dependency for lightweight listing operations
    (e.g., GLM lightning files).  Returns a list of key strings.
    """
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
