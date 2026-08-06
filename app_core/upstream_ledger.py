"""Credential-safe Phase 0 ledger for application-owned upstream requests.

The ledger is observational only: it does not retry, throttle, cache, or alter
responses. Query strings and credentials are deliberately excluded from the
recorded resource key.
"""

from __future__ import annotations

import json
import hashlib
import os
import threading
import time
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import requests as _requests

from app_core.paths import CACHE_ROOT


_DEFAULT_LEDGER_PATH = Path(CACHE_ROOT) / "metrics" / "upstream_requests.jsonl"
_WRITE_LOCK = threading.Lock()
_PROCESS_IDENTITY = uuid.uuid4().hex
_MEASUREMENT_CONTEXT: ContextVar[dict[str, Any]] = ContextVar(
    "phase0_measurement_context", default={}
)

_PROVIDER_HOSTS = {
    "api.weather.gov": "nws",
    "mapservices.weather.noaa.gov": "nws",
    "aviationweather.gov": "aviationweather",
    "mesonet.agron.iastate.edu": "iem",
    "www.spc.noaa.gov": "spc",
    "www.wpc.ncep.noaa.gov": "wpc",
    "www.nhc.noaa.gov": "nhc",
    "ftp.nhc.noaa.gov": "nhc",
    "api.eumetsat.int": "eumetsat",
    "water.noaa.gov": "nwps",
    "api.tidesandcurrents.noaa.gov": "coops",
    "www.ndbc.noaa.gov": "ndbc",
    "droughtmonitor.unl.edu": "drought-monitor",
    "storage.googleapis.com": "noaa-nodd",
}
_SENSITIVE_QUERY_PARTS = {
    "access_token",
    "api_key",
    "authorization",
    "credential",
    "key",
    "secret",
    "sig",
    "signature",
    "token",
    "x-amz-credential",
    "x-amz-signature",
}


def _enabled() -> bool:
    configured = os.environ.get("WX_UPSTREAM_LEDGER")
    if configured is None:
        return bool(os.environ.get("WX_UPSTREAM_LEDGER_PATH", "").strip())
    return configured.strip().lower() not in {"0", "false", "no", "off"}


def ledger_path() -> Path:
    configured = os.environ.get("WX_UPSTREAM_LEDGER_PATH", "").strip()
    return Path(configured) if configured else _DEFAULT_LEDGER_PATH


def resource_key_for_url(url: str) -> str:
    """Return a stable URL key with only a non-sensitive query fingerprint."""
    parsed = urllib.parse.urlsplit(str(url))
    host = (parsed.hostname or "unknown").lower()
    path = parsed.path or "/"
    base = f"{host}{path}"
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if not pairs:
        return base
    names = {name.strip().lower() for name, _value in pairs}
    if names & _SENSITIVE_QUERY_PARTS:
        return base
    normalized = urllib.parse.urlencode(sorted(pairs))
    fingerprint = hashlib.sha256(normalized.encode()).hexdigest()[:12]
    return f"{base}?query={fingerprint}"


def provider_for_url(url: str) -> str:
    host = (urllib.parse.urlsplit(str(url)).hostname or "unknown").lower()
    if host in _PROVIDER_HOSTS:
        return _PROVIDER_HOSTS[host]
    if host.endswith(".amazonaws.com") or host.endswith(".amazonaws.com.cn"):
        return "noaa-nodd"
    if host.endswith(".weather.gov"):
        return "nws"
    if host.endswith(".noaa.gov"):
        return "noaa"
    return host


def _append(entry: dict[str, Any]) -> None:
    if not _enabled():
        return
    try:
        target = ledger_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        with _WRITE_LOCK:
            with target.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except OSError:
        # Measurement must never make an otherwise-valid upstream call fail.
        return


def record_upstream_request(
    *,
    provider: str,
    resource_key: str,
    method: str,
    status: int | str | None,
    bytes_transferred: int,
    duration_seconds: float,
    cache_result: str = "miss",
    retry_state: str = "none",
    backoff_state: str = "none",
    outcome: str = "success",
) -> None:
    entry = {
            "event": "upstream_request",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            "process_id": _PROCESS_IDENTITY,
            "provider": str(provider),
            "resource_key": str(resource_key),
            "method": str(method).upper(),
            "status": status,
            "bytes": max(0, int(bytes_transferred or 0)),
            "duration_ms": round(max(0.0, duration_seconds) * 1000.0, 3),
            "cache_result": str(cache_result),
            "retry_state": str(retry_state),
            "backoff_state": str(backoff_state),
            "outcome": str(outcome),
        }
    entry.update(_MEASUREMENT_CONTEXT.get())
    _append(entry)


def record_measurement(
    *, stage: str, duration_seconds: float, fields: dict[str, Any] | None = None
) -> None:
    entry: dict[str, Any] = {
        "event": "phase0_measurement",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "process_id": _PROCESS_IDENTITY,
        "stage": str(stage),
        "duration_ms": round(max(0.0, duration_seconds) * 1000.0, 3),
    }
    if fields:
        entry.update(fields)
    entry.update(_MEASUREMENT_CONTEXT.get())
    _append(entry)


@contextmanager
def measurement_context(**fields: Any) -> Iterator[None]:
    merged = dict(_MEASUREMENT_CONTEXT.get())
    merged.update(fields)
    token = _MEASUREMENT_CONTEXT.set(merged)
    try:
        yield
    finally:
        _MEASUREMENT_CONTEXT.reset(token)


@contextmanager
def measure_stage(stage: str, **fields: Any) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        record_measurement(
            stage=stage,
            duration_seconds=time.perf_counter() - started,
            fields=fields,
        )


def _response_bytes(response: Any) -> tuple[int, str]:
    if getattr(response, "_content_consumed", False):
        try:
            return len(response.content or b""), "response_content"
        except Exception:
            pass
    try:
        value = int(response.headers.get("Content-Length") or 0)
        return max(0, value), "content_length"
    except (AttributeError, TypeError, ValueError):
        return 0, "unknown"


def _response_retry_state(response: Any, explicit_state: str) -> str:
    if explicit_state != "none":
        return explicit_state
    try:
        retry_count = len(response.raw.retries.history)
    except (AttributeError, TypeError):
        retry_count = 0
    return f"transport_retries:{retry_count}" if retry_count else "none"


def _track_streaming_response(
    response: Any,
    *,
    provider: str,
    resource_key: str,
    method: str,
    started: float,
    cache_result: str,
    retry_state: str,
    backoff_state: str,
) -> Any:
    state = {"bytes": 0, "recorded": False, "outcome": None}
    original_iter_content = response.iter_content
    original_close = response.close

    def _record(outcome: str | None = None) -> None:
        if state["recorded"]:
            return
        state["recorded"] = True
        byte_count = state["bytes"]
        if not byte_count:
            byte_count, _source = _response_bytes(response)
        status = getattr(response, "status_code", None)
        record_upstream_request(
            provider=provider,
            resource_key=resource_key,
            method=method,
            status=status,
            bytes_transferred=byte_count,
            duration_seconds=time.perf_counter() - started,
            cache_result="revalidated" if status == 304 else cache_result,
            retry_state=retry_state,
            backoff_state=backoff_state,
            outcome=outcome
            or ("success" if getattr(response, "ok", False) else "http_error"),
        )

    def _iter_content(*args, **kwargs):
        try:
            for chunk in original_iter_content(*args, **kwargs):
                state["bytes"] += len(chunk or b"")
                yield chunk
        except Exception:
            _record("error")
            raise
        else:
            _record()

    def _close():
        try:
            return original_close()
        finally:
            _record()

    response.iter_content = _iter_content
    response.close = _close
    return response


class _RequestsProxy:
    """Requests-compatible proxy that records one ledger row per call."""

    def request(self, method: str, url: str, **kwargs):
        provider = kwargs.pop("ledger_provider", None) or provider_for_url(url)
        resource_url = url
        if kwargs.get("params"):
            resource_url = _requests.Request(
                method=method, url=url, params=kwargs["params"]
            ).prepare().url
        resource_key = kwargs.pop("ledger_resource_key", None) or resource_key_for_url(
            resource_url
        )
        cache_result = kwargs.pop("ledger_cache_result", "miss")
        retry_state = kwargs.pop("ledger_retry_state", "none")
        backoff_state = kwargs.pop("ledger_backoff_state", "none")
        started = time.perf_counter()
        try:
            response = _requests.request(method, url, **kwargs)
        except Exception as exc:
            record_upstream_request(
                provider=provider,
                resource_key=resource_key,
                method=method,
                status=getattr(getattr(exc, "response", None), "status_code", None),
                bytes_transferred=0,
                duration_seconds=time.perf_counter() - started,
                cache_result=cache_result,
                retry_state=retry_state,
                backoff_state=backoff_state,
                outcome="error",
            )
            raise
        if kwargs.get("stream"):
            retry_state = _response_retry_state(response, retry_state)
            return _track_streaming_response(
                response,
                provider=provider,
                resource_key=resource_key,
                method=method,
                started=started,
                cache_result=cache_result,
                retry_state=retry_state,
                backoff_state=backoff_state,
            )
        byte_count, _byte_source = _response_bytes(response)
        retry_state = _response_retry_state(response, retry_state)
        record_upstream_request(
            provider=provider,
            resource_key=resource_key,
            method=method,
            status=getattr(response, "status_code", None),
            bytes_transferred=byte_count,
            duration_seconds=time.perf_counter() - started,
            cache_result="revalidated" if response.status_code == 304 else cache_result,
            retry_state=retry_state,
            backoff_state=backoff_state,
            outcome="success" if getattr(response, "ok", False) else "http_error",
        )
        return response

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def head(self, url: str, **kwargs):
        return self.request("HEAD", url, **kwargs)

    def post(self, url: str, data=None, json=None, **kwargs):
        return self.request("POST", url, data=data, json=json, **kwargs)

    def __getattr__(self, name: str):
        return getattr(_requests, name)


requests = _RequestsProxy()


class _TrackedUrlResponse:
    def __init__(
        self,
        response: Any,
        *,
        provider: str,
        resource_key: str,
        method: str,
        started: float,
        cache_result: str,
        retry_state: str,
        backoff_state: str,
    ) -> None:
        self._response = response
        self._provider = provider
        self._resource_key = resource_key
        self._method = method
        self._started = started
        self._cache_result = cache_result
        self._retry_state = retry_state
        self._backoff_state = backoff_state
        self._bytes = 0
        self._recorded = False

    def read(self, *args, **kwargs):
        data = self._response.read(*args, **kwargs)
        self._bytes += len(data or b"")
        return data

    def readinto(self, buffer):
        count = self._response.readinto(buffer)
        self._bytes += max(0, int(count or 0))
        return count

    def __iter__(self):
        for chunk in self._response:
            self._bytes += len(chunk or b"")
            yield chunk

    def _record(self) -> None:
        if self._recorded:
            return
        self._recorded = True
        status = getattr(self._response, "status", None) or getattr(
            self._response, "code", None
        )
        record_upstream_request(
            provider=self._provider,
            resource_key=self._resource_key,
            method=self._method,
            status=status,
            bytes_transferred=self._bytes,
            duration_seconds=time.perf_counter() - self._started,
            cache_result=(
                "revalidated" if status == 304 else self._cache_result
            ),
            retry_state=self._retry_state,
            backoff_state=self._backoff_state,
            outcome="success",
        )

    def close(self):
        try:
            return self._response.close()
        finally:
            self._record()

    def __enter__(self):
        self._response.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            return self._response.__exit__(exc_type, exc, tb)
        finally:
            self._record()

    def __getattr__(self, name: str):
        return getattr(self._response, name)


def urlopen(
    request: str | urllib.request.Request,
    *args,
    ledger_provider: str | None = None,
    ledger_resource_key: str | None = None,
    ledger_cache_result: str = "miss",
    ledger_retry_state: str = "none",
    ledger_backoff_state: str = "none",
    **kwargs,
):
    url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
    method = request.get_method() if isinstance(request, urllib.request.Request) else "GET"
    provider = ledger_provider or provider_for_url(url)
    resource_key = ledger_resource_key or resource_key_for_url(url)
    started = time.perf_counter()
    try:
        response = urllib.request.urlopen(request, *args, **kwargs)
    except Exception as exc:
        status = getattr(exc, "code", None)
        not_modified = status == 304
        record_upstream_request(
            provider=provider,
            resource_key=resource_key,
            method=method,
            status=status,
            bytes_transferred=0,
            duration_seconds=time.perf_counter() - started,
            cache_result="revalidated" if not_modified else ledger_cache_result,
            retry_state=ledger_retry_state,
            backoff_state=ledger_backoff_state,
            outcome="success" if not_modified else "error",
        )
        raise
    return _TrackedUrlResponse(
        response,
        provider=provider,
        resource_key=resource_key,
        method=method,
        started=started,
        cache_result=ledger_cache_result,
        retry_state=ledger_retry_state,
        backoff_state=ledger_backoff_state,
    )


@contextmanager
def upstream_operation(
    *,
    provider: str,
    resource_key: str,
    method: str,
    cache_result: str = "miss",
    retry_state: str = "none",
    backoff_state: str = "none",
) -> Iterator[dict[str, int]]:
    """Track non-HTTP upstream work such as S3 LIST/HEAD/download calls."""
    started = time.perf_counter()
    transfer = {"bytes": 0}
    try:
        yield transfer
    except Exception:
        record_upstream_request(
            provider=provider,
            resource_key=resource_key,
            method=method,
            status=None,
            bytes_transferred=transfer["bytes"],
            duration_seconds=time.perf_counter() - started,
            cache_result=cache_result,
            retry_state=retry_state,
            backoff_state=backoff_state,
            outcome="error",
        )
        raise
    else:
        record_upstream_request(
            provider=provider,
            resource_key=resource_key,
            method=method,
            status="ok",
            bytes_transferred=transfer["bytes"],
            duration_seconds=time.perf_counter() - started,
            cache_result=cache_result,
            retry_state=retry_state,
            backoff_state=backoff_state,
            outcome="success",
        )
