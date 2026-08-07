"""Shared HTTP payload and validation helpers."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

MAX_ARCHIVE_SPAN_DAYS = {
    "alerts": 7,
    "surface": 7,
    "radar": 2,
    "satellite": 3,
    "spc": 14,
}


def json_safe(value):
    """Convert nested API payload values into FastAPI JSON-compatible types."""

    def encode_numpy_array(array: np.ndarray):
        return json_safe(array.tolist())

    def encode_numpy_scalar(scalar: np.generic):
        return json_safe(scalar.item())

    return jsonable_encoder(
        value,
        custom_encoder={
            np.ndarray: encode_numpy_array,
            np.generic: encode_numpy_scalar,
        },
    )


def error_payload(message: str, *, code: str = "bad_request", details=None):
    payload = {"error": message, "code": code}
    if details is not None:
        payload["details"] = details
    return payload


def parse_utc_datetime(value: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise HTTPException(
            status_code=400,
            detail=error_payload("Invalid empty datetime value.", code="invalid_date"),
        )

    normalized = raw.replace("Z", "+00:00")
    parsed = None
    parse_attempts = ["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"]

    if any(token in normalized for token in ["+", "T"]):
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            parsed = None

    if parsed is None:
        for fmt in parse_attempts:
            try:
                parsed = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        raise HTTPException(
            status_code=400,
            detail=error_payload(
                f"Invalid date format: {value}",
                code="invalid_date",
                details="Use YYYY-MM-DD HH:MM, YYYY-MM-DDTHH:MM, or YYYY-MM-DD",
            ),
        )

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_archive_range(category: str, start_utc: datetime, end_utc: datetime):
    if end_utc < start_utc:
        raise HTTPException(
            status_code=400,
            detail=error_payload(
                "date_to must be greater than or equal to date_from.",
                code="invalid_date_range",
            ),
        )

    max_days = float(MAX_ARCHIVE_SPAN_DAYS.get(category, 7))
    max_delta = timedelta(days=max_days)
    if (end_utc - start_utc) > max_delta:
        raise HTTPException(
            status_code=400,
            detail=error_payload(
                f"Archive range too large for {category}.",
                code="date_range_too_large",
                details=f"Maximum allowed span is {max_days} day(s).",
            ),
        )


def success_payload(
    *,
    message: str,
    image_url: Optional[str],
    source: str,
    data_mode: str,
    request_id: str = "",
    status: str = "success",
):
    payload = {
        "status": status,
        "message": message,
        "image_url": image_url,
        "source": source,
        "data_mode": data_mode,
    }
    if request_id:
        payload["request_id"] = request_id
    return payload


def attach_mode_and_source(payload: dict, data_mode: str):
    if not isinstance(payload, dict):
        return payload
    source_value = payload.get("source") or payload.get("data_source") or "Unknown"
    payload["source"] = source_value
    payload["data_mode"] = data_mode
    return payload
