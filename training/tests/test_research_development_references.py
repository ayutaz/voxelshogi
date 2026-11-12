"""Handwritten histories and fake replay ports, without Rust or model work."""

import hashlib
import json
from copy import deepcopy

import pytest

from training.evaluation_v2 import fingerprint
from training.tests.test_evaluation_v2 import protocol, rows


def raw(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


def setup(tmp_path, monkeypatch):
    from training import research_development_references as module

    monkeypatch.setattr(module.sys, "platform", "linux")
    root = tmp_path / "references"
    root.mkdir()
    calls = []
    spec = protocol()
    matches = rows(spec)
    query_record = deepcopy(spec["cases"][0]["opening"])
    query_record["moves"].append("off-path-query")

    def write(name, body):
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        return {
            "path": name,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }

    source = {
        "id": "screen",
        "files": {
            n: write(
                "screen/" + n,
                raw({"protocols": {"arm": spec}})
                if n == "config.json"
                else b"opaque parquet or manifest",
            )
            for n in (
                "config.json",
                "manifest.json",
                "matches.parquet",
                "queries.parquet",
            )
        },
        "games": 4,
        "queries": 1,
    }
    runs = [
        {
            "id": name,
            "run": write(
                name + "/run.json", raw({"complete": True, "games": 4, "files": []})
            ),
            "games": 4,
            "query_coverage": "trace",
        }
        for name in ("full", "geometry")
    ]
    for name in ("full", "geometry"):
        write(name + "/protocol.json", raw(spec))
        for match in matches:
            write(name + f"/{match['case_id']}-{match['model_side']}.json", raw(match))
    trace_rows = [
        {
            "architecture": a,
            "role": "model",
            "physical_id": "e" * 64,
            "input_id": "f" * 64,
            "record": query_record,
        }
        for a in ("full", "geometry")
    ]
    trace = {
        "file": write("pilot/queries.jsonl", b"".join(raw(r) for r in trace_rows)),
        "cohort_field": "architecture",
        "cohorts": {"full": "full", "geometry": "geometry"},
        "queries": {"full": 1, "geometry": 1},
    }
    value = {
        "schema": "voxelshogi-development-reference-plan-v1",
        "screens": [source],
        "runs": runs,
        "traces": [trace],
    }
    screen_rows = [
        {
            "arm": "arm",
            "case_id": m["case_id"],
            "protocol_sha256": fingerprint(spec),
            "match_json": json.dumps(m),
        }
        for m in matches
    ]
    screen_queries = [
        {
            "arm": "arm",
            "case_id": spec["cases"][0]["id"],
            "protocol_sha256": fingerprint(spec),
            "role": "model",
            "query_index": 1,
            "record_json": json.dumps(query_record),
            "vsfen": "opaque-query",
            "side": "b",
            "physical_id": "e" * 64,
            "input_id": "f" * 64,
        }
    ]

    def parquet(path):
        calls.append(path.name)
        return iter(screen_rows if path.name == "matches.parquet" else screen_queries)

    def played(row, case):
        assert row["case_id"] == case["id"]
        calls.append("played")
        return {"positions": {"1" * 64}, "inputs": {"2" * 64}}

    def query(record):
        calls.append("query")
        return {
            "physical_id": "e" * 64,
            "input_id": "f" * 64,
            "vsfen": "opaque-query",
            "side": "b",
        }

    def run(folder):
        calls.append("run-" + folder.name)
        for match in matches:
            path = folder / f"{match['case_id']}-{match['model_side']}.json"
            if not path.is_file() or path.read_bytes() != raw(match):
                raise ValueError("replayed source match bytes changed")
        return {"verified": folder.name}

    options = {
        "deadline": 200,
        "clock": lambda: 100,
        "ports": {"parquet": parquet, "played": played, "query": query, "run": run},
    }
    return module, root, value, options, calls


def test_all_scored_and_off_path_query_inputs_are_retained_and_bound(
    tmp_path, monkeypatch
):
    module, root, value, options, calls = setup(tmp_path, monkeypatch)
    result = module.collect_references(root, value, **options)
    assert set(result["physical"]) == {
        "development/screen",
        "development/full",
        "development/geometry",
    }
    assert all(ids == {"1" * 64, "e" * 64} for ids in result["physical"].values())
    assert all(ids == {"2" * 64, "f" * 64} for ids in result["model_input"].values())
    receipt = result["receipt"]
    assert receipt["verified"] is True and receipt["plan_sha256"] == fingerprint(value)
    assert {k: v["games"] for k, v in receipt["sources"].items()} == {
        "development/screen": 4,
        "development/full": 4,
        "development/geometry": 4,
    }
    assert {k: v["queries"] for k, v in receipt["sources"].items()} == {
        "development/screen": 1,
        "development/full": 1,
        "development/geometry": 1,
    }
    assert calls.count("played") == 12 and calls.count("query") == 3
    from training.generation_evaluation import audit_evaluation_inputs

    final = {"only-searched-branch": {"positions": {"a" * 64}, "inputs": {"f" * 64}}}
    audit = audit_evaluation_inputs(result["physical"], result["model_input"], final)
    assert audit["passed"] is False
    assert audit["overlaps_by_source"]["model_input"] == {
        "development/full": 1,
        "development/geometry": 1,
        "development/screen": 1,
    }


def legacy_argmax(tmp_path, monkeypatch):
    module, root, value, options, calls = setup(tmp_path, monkeypatch)
    value["runs"][1]["query_coverage"] = "scored-superset"
    trace = value["traces"][0]
    trace["cohorts"].pop("geometry")
    trace["queries"].pop("geometry")
    path = root / trace["file"]["path"]
    body = raw(json.loads(path.read_text().splitlines()[0]))
    path.write_bytes(body)
    trace["file"].update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    return module, root, value, options, calls


def test_legacy_argmax_can_use_explicit_scored_superset_without_inventing_query_counts(
    tmp_path, monkeypatch
):
    module, root, value, options, calls = legacy_argmax(tmp_path, monkeypatch)
    result = module.collect_references(root, value, **options)
    assert result["model_input"]["development/geometry"] == {"2" * 64}
    row = result["receipt"]["sources"]["development/geometry"]
    assert (
        row["query_coverage"] == "scored-superset"
        and row["query_count_is_exact"] is False
    )
    assert row["queries"] == 0 and calls.count("query") == 2


def test_puct_cannot_substitute_played_paths_for_unrecorded_branches(
    tmp_path, monkeypatch
):
    module, root, value, options, _ = legacy_argmax(tmp_path, monkeypatch)
    folder = root / "geometry"
    path = folder / "protocol.json"
    spec = json.loads(path.read_bytes())
    spec["participants"]["model"]["policy"] = "puct32-v1"
    path.write_bytes(raw(spec))
    for case in spec["cases"]:
        for side in ("b", "w"):
            path = folder / f"{case['id']}-{side}.json"
            row = json.loads(path.read_bytes())
            row["protocol_sha256"] = fingerprint(spec)
            path.write_bytes(raw(row))
    options["ports"]["run"] = lambda folder: {"verified": "consistent handwritten run"}
    with pytest.raises(ValueError, match="PUCT"):
        module.collect_references(root, value, **options)


@pytest.mark.parametrize(
    "fault",
    [
        "empty-screen",
        "empty-runs",
        "missing-trace",
        "incomplete-queries",
        "query-id",
        "query-case",
        "query-role",
        "query-index",
        "run-holdout",
        "screen-holdout",
        "missing-match",
        "file-hash",
        "parent-link",
        "path-escape",
        "duplicate-source",
        "changed-source",
        "changed-match",
        "expired",
        "platform",
    ],
)
def test_omitted_changed_or_unreplayed_references_cannot_pass(
    tmp_path, monkeypatch, fault
):
    module, root, value, options, calls = setup(tmp_path, monkeypatch)
    if fault == "empty-screen":
        value["screens"] = []
    elif fault == "empty-runs":
        value["runs"] = []
    elif fault == "missing-trace":
        value["traces"] = []
    elif fault == "incomplete-queries":
        value["traces"][0]["queries"]["geometry"] = 2
    elif fault in ("query-id", "query-case", "query-role"):
        path = root / "pilot/queries.jsonl"
        records = [json.loads(s) for s in path.read_text().splitlines()]
        if fault == "query-id":
            records[1]["input_id"] = "0" * 64
        elif fault == "query-case":
            records[1]["record"]["initial"] = "unassigned-case"
        else:
            records[1]["role"] = "opponent"
        body = b"".join(raw(r) for r in records)
        path.write_bytes(body)
        value["traces"][0]["file"].update(
            bytes=len(body), sha256=hashlib.sha256(body).hexdigest()
        )
    elif fault == "query-index":
        original = options["ports"]["parquet"]

        def changed(path):
            records = list(original(path))
            if path.name == "queries.parquet":
                records[0]["query_index"] = 2
            return iter(records)

        options["ports"]["parquet"] = changed
    elif fault in ("run-holdout", "screen-holdout"):
        if fault == "run-holdout":
            path = root / "full/protocol.json"
            spec = json.loads(path.read_bytes())
            spec["purpose"] = "holdout"
            path.write_bytes(raw(spec))
        else:
            path = root / "screen/config.json"
            v = json.loads(path.read_bytes())
            v["protocols"]["arm"]["purpose"] = "holdout"
            body = raw(v)
            path.write_bytes(body)
            value["screens"][0]["files"]["config.json"].update(
                bytes=len(body), sha256=hashlib.sha256(body).hexdigest()
            )
    elif fault == "missing-match":
        (root / "geometry" / "ending-w.json").unlink()
    elif fault == "file-hash":
        path = root / "screen/queries.parquet"
        body = path.read_bytes()
        path.write_bytes(bytes([body[0] ^ 1]) + body[1:])
    elif fault == "parent-link":
        folder = root / "screen"
        other = root / "other"
        folder.rename(other)
        folder.symlink_to(other, target_is_directory=True)
    elif fault == "path-escape":
        value["screens"][0]["files"]["queries.parquet"]["path"] = "../queries.parquet"
    elif fault == "duplicate-source":
        value["runs"][1]["id"] = "screen"
    elif fault == "changed-source":
        original = options["ports"]["query"]

        def changed(record):
            result = original(record)
            path = root / "screen/queries.parquet"
            body = path.read_bytes()
            path.write_bytes(b"X" + body[1:])
            return result

        options["ports"]["query"] = changed
    elif fault == "changed-match":
        original = options["ports"]["query"]

        def changed(record):
            result = original(record)
            if "run-full" in calls and "run-geometry" in calls:
                path = root / "full/tactic-b.json"
                path.write_bytes(path.read_bytes() + b" ")
            return result

        options["ports"]["query"] = changed
    elif fault == "expired":
        options["deadline"] = 99
    else:
        monkeypatch.setattr(module.sys, "platform", "darwin")
    expected = InterruptedError if fault == "expired" else ValueError
    with pytest.raises(expected):
        module.collect_references(root, value, **options)
