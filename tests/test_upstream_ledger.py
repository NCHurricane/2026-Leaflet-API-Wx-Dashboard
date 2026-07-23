import json

from app_core import upstream_ledger


class _FakeRequestsResponse:
    status_code = 200
    ok = True
    headers = {"Content-Length": "7"}
    content = b"payload"
    _content_consumed = True


class _FakeUrlResponse:
    status = 200
    code = 200

    def __init__(self):
        self._payload = b"url-data"

    def read(self, *args, **kwargs):
        payload, self._payload = self._payload, b""
        return payload

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamingResponse:
    status_code = 200
    ok = True
    headers = {"Content-Length": "6"}
    _content_consumed = False

    def iter_content(self, *args, **kwargs):
        yield b"abc"
        yield b"def"

    def close(self):
        return None


def _read_rows(path):
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def test_requests_proxy_records_required_fields_without_query_secrets(
    tmp_path, monkeypatch
):
    ledger_path = tmp_path / "requests.jsonl"
    monkeypatch.setenv("WX_UPSTREAM_LEDGER_PATH", str(ledger_path))
    monkeypatch.setattr(
        upstream_ledger._requests,
        "request",
        lambda method, url, **kwargs: _FakeRequestsResponse(),
    )

    response = upstream_ledger.requests.get(
        "https://api.weather.gov/alerts/active?token=do-not-log"
    )

    assert response.status_code == 200
    row = _read_rows(ledger_path)[0]
    assert row["provider"] == "nws"
    assert row["resource_key"] == "api.weather.gov/alerts/active"
    assert "token" not in json.dumps(row)
    assert row["status"] == 200
    assert row["bytes"] == 7
    assert row["cache_result"] == "miss"
    assert row["retry_state"] == "none"
    assert row["backoff_state"] == "none"


def test_urlopen_records_consumed_bytes(tmp_path, monkeypatch):
    ledger_path = tmp_path / "urlopen.jsonl"
    monkeypatch.setenv("WX_UPSTREAM_LEDGER_PATH", str(ledger_path))
    monkeypatch.setattr(
        upstream_ledger.urllib.request,
        "urlopen",
        lambda request, *args, **kwargs: _FakeUrlResponse(),
    )

    with upstream_ledger.urlopen(
        "https://www.nhc.noaa.gov/data/?signature=do-not-log"
    ) as response:
        assert response.read() == b"url-data"

    row = _read_rows(ledger_path)[0]
    assert row["provider"] == "nhc"
    assert row["resource_key"] == "www.nhc.noaa.gov/data/"
    assert row["bytes"] == 8
    assert "signature" not in json.dumps(row)


def test_streaming_request_records_after_download(tmp_path, monkeypatch):
    ledger_path = tmp_path / "stream.jsonl"
    monkeypatch.setenv("WX_UPSTREAM_LEDGER_PATH", str(ledger_path))
    monkeypatch.setattr(
        upstream_ledger._requests,
        "request",
        lambda method, url, **kwargs: _FakeStreamingResponse(),
    )

    response = upstream_ledger.requests.get(
        "https://api.eumetsat.int/data/download/file?access_token=secret",
        stream=True,
    )
    assert not ledger_path.exists()
    assert b"".join(response.iter_content(3)) == b"abcdef"

    row = _read_rows(ledger_path)[0]
    assert row["provider"] == "eumetsat"
    assert row["bytes"] == 6
    assert "access_token" not in json.dumps(row)


def test_measurement_context_adds_run_identity(tmp_path, monkeypatch):
    ledger_path = tmp_path / "measurements.jsonl"
    monkeypatch.setenv("WX_UPSTREAM_LEDGER_PATH", str(ledger_path))

    with upstream_ledger.measurement_context(run_id="run-1", process_pass="warm"):
        with upstream_ledger.measure_stage("alerts.test"):
            pass

    row = _read_rows(ledger_path)[0]
    assert row["event"] == "phase0_measurement"
    assert row["stage"] == "alerts.test"
    assert row["run_id"] == "run-1"
    assert row["process_pass"] == "warm"


def test_resource_key_removes_user_info_query_and_fragment():
    key = upstream_ledger.resource_key_for_url(
        "https://user:secret@example.com/path/file?sig=secret#fragment"
    )
    assert key == "example.com/path/file"


def test_resource_key_fingerprints_non_sensitive_query_without_values():
    first = upstream_ledger.resource_key_for_url(
        "https://api.weather.gov/alerts/active?area=NC"
    )
    second = upstream_ledger.resource_key_for_url(
        "https://api.weather.gov/alerts/active?area=SC"
    )
    assert first != second
    assert first.startswith("api.weather.gov/alerts/active?query=")
    assert "NC" not in first
