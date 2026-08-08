import json

from radar import radar_chunks_utils
from tools.validate_fci_native import chunk_paths_from_manifest


def test_l2_diagnostic_public_chunk_contracts():
    chunks = [
        {"scan_prefix": "KRAX/207/20260808-120000-", "seq": 2, "ctype": "E"},
        {"scan_prefix": "KRAX/207/20260808-120000-", "seq": 1, "ctype": "S"},
    ]

    grouped = radar_chunks_utils.group_chunks_by_scan(chunks)

    assert [item["seq"] for item in grouped["KRAX/207/20260808-120000-"]] == [1, 2]
    assert radar_chunks_utils.scan_is_complete(chunks)
    assert (
        radar_chunks_utils.assembled_scan_filename("KRAX/207/20260808-120000-")
        == "KRAX20260808_120000_V06"
    )


def test_fci_validator_requires_a_complete_manifest(tmp_path):
    first = tmp_path / "BODY-001-CHK-BODY.nc"
    second = tmp_path / "BODY-002-CHK-BODY.nc"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"chunks": [first.name, second.name]}), encoding="utf-8"
    )

    assert chunk_paths_from_manifest(manifest) == [first, second]
