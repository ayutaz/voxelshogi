"""Tiny real Parquet roundtrip on Linux CI; never execute numerical work on Mac."""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="external Linux only")


def test_real_result_parquet_keeps_metadata_unicode_and_newlines(tmp_path):
    import pyarrow.parquet as pq

    from infrastructure.research.pilot.results import fingerprint_bytes, write_records

    text = '{"note":"日本語","step":1}\n'
    rows = [
        {
            "path": "full/continuous/events.jsonl",
            "line": 0,
            "content": text,
            "sha256": fingerprint_bytes(text.encode()),
        }
    ]
    target = tmp_path / "records.parquet"
    write_records(rows, target)
    table = pq.read_table(target)
    assert table.to_pylist() == rows
    assert table.schema.metadata == {b"schema": b"voxelshogi-research-pilot-records-v1"}
