"""External snapshot contract with opaque state/archive ports; no real checkpoints."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.tests.test_research_pilot_retirement import collection_fixture


def disk_fixture(tmp_path, monkeypatch, mode="complete"):
    value, initial, snapshot = collection_fixture(tmp_path, monkeypatch)
    base = Path(value["job"]["base"])
    events = [{"opaque": "verified history port fixture"}]
    for name, state in snapshot["run_states"].items():
        folder = base / name
        folder.mkdir(parents=True)
        atomic_json(
            folder / "run.json",
            {"schema": "voxelshogi-training-run-v1", "binding": state["binding"]},
        )
        (folder / "events.jsonl").write_text(json.dumps(events[0]) + "\n")
        (folder / "checkpoints").mkdir()
        atomic_json(folder / "checkpoints/latest.json", {"best": {"opaque": True}})
        state.update(history_sha256=fingerprint(events), history_events=1)
    for proof in snapshot["resume_proofs"].values():
        proof.update(history_sha256=fingerprint(events), history_events=1)
    snapshot["state_budget"]["reservations"] = list(initial["reservations"])
    for label, item in snapshot["state_transfers"].items():
        name, stage = label.split("/")
        archive = base / name / (stage + "-archive")
        archive.mkdir()
        atomic_json(archive / "manifest.json", item["manifest"])
        item["manifest_sha256"] = file_hash(archive / "manifest.json")
        item["plan"]["files"] = [
            {
                "path": "manifest.json",
                "bytes": (archive / "manifest.json").stat().st_size,
                "sha256": item["manifest_sha256"],
            }
        ]
        item["receipt"]["release_sha256"] = fingerprint(item["plan"])
        control = base / name / (stage + "-transfer")
        control.mkdir()
        for filename, data in (
            ("publication-plan.json", item["plan"]),
            ("publication-receipt.json", item["receipt"]),
            ("complete.json", {"receipt": item["receipt"], "restored": True}),
        ):
            atomic_json(control / filename, data)
        snapshot["state_budget"]["reservations"].append(
            {
                "release_sha256": fingerprint(item["plan"]),
                "maximum_bytes": sum(f["bytes"] for f in item["plan"]["files"]),
            }
        )
    trace = base / "development/queries.jsonl"
    trace.parent.mkdir()
    trace.write_text('{"opaque":"NN query fixture"}\n')
    snapshot["query_trace"] = {
        "bytes": trace.stat().st_size,
        "sha256": file_hash(trace),
    }
    publication = snapshot["result_publication"]
    publication["manifest"]["files"] = [
        {"path": "development/queries.jsonl", **snapshot["query_trace"]}
    ]
    output = base / "publication"
    output.mkdir()
    (output / "records.parquet").write_bytes(
        b"opaque parquet fixture; never real data on Mac"
    )
    publication["manifest"]["records_parquet_sha256"] = file_hash(
        output / "records.parquet"
    )
    atomic_json(output / "manifest.json", publication["manifest"])
    publication["manifest_sha256"] = file_hash(output / "manifest.json")
    publication["plan"]["files"] = [
        {"path": p.name, "bytes": p.stat().st_size, "sha256": file_hash(p)}
        for p in (output / "manifest.json", output / "records.parquet")
    ]
    publication["receipt"]["release_sha256"] = fingerprint(publication["plan"])
    control = base / "results-transfer"
    control.mkdir()
    for filename, data in (
        ("publication-plan.json", publication["plan"]),
        ("publication-receipt.json", publication["receipt"]),
        (
            "complete.json",
            {"receipt": publication["receipt"], "pipeline_complete": True},
        ),
    ):
        atomic_json(control / filename, data)
    snapshot["records"]["workflow-complete.json"]["state_budget_final_sha256"] = (
        fingerprint(snapshot["state_budget"])
    )
    for filename, data in snapshot["records"].items():
        atomic_json(base / filename, data)
    atomic_json(base / "state-upload-budget.json", snapshot["state_budget"])
    for name, proof in snapshot["resume_proofs"].items():
        atomic_json(base / name / "resume-proof.json", proof)
    if mode == "corrupt-archive":
        (base / "full/final-archive/manifest.json").write_text("{}")
    elif mode == "corrupt-result":
        (output / "records.parquet").write_bytes(
            b"x" * (output / "records.parquet").stat().st_size
        )
    elif mode == "unknown-run":
        folder = base / "full/unexpected-fit"
        folder.mkdir()
        atomic_json(
            folder / "run.json",
            {"binding": snapshot["run_states"]["full/continuous"]["binding"]},
        )
    elif mode == "ambiguous":
        (base / "full/final-transfer/complete.json").unlink()
    calls = []

    def source(commit):
        calls.append("source")
        assert commit == value["job"]["source_commit"]
        if mode == "source":
            raise ValueError("changed source")

    def process(expected, folder):
        calls.append("process")
        return {"process": {**expected, "running": mode == "live"}, "owned_compute": []}

    def checkpoint(folder, *, binding, which):
        calls.append("checkpoint")
        if mode == "checkpoint":
            raise ValueError("invalid actual receipt")
        name = folder.parent.relative_to(base).as_posix()
        state = snapshot["run_states"][name]
        assert state["binding"] == binding
        return folder / "opaque.pt", state["checkpoints"][which]

    def archive(folder, *, expected_binding, profile):
        calls.append("archive")
        assert profile == "research"
        manifest = json.loads((folder / "manifest.json").read_text())
        if manifest.get("binding") != expected_binding:
            raise ValueError("bad archive")
        return manifest

    def history(rows, config, progress):
        calls.append("history")
        assert rows == events and config["device"] == "cuda"

    ports = {
        "source": source,
        "process": process,
        "checkpoint": checkpoint,
        "archive": archive,
        "history": history,
    }
    return value, initial, snapshot, ports, calls


@pytest.mark.parametrize(
    "mode",
    [
        "complete",
        "corrupt-archive",
        "corrupt-result",
        "unknown-run",
        "ambiguous",
        "source",
        "checkpoint",
        "live",
        "mac",
    ],
)
def test_collection_checks_production_ports_on_linux_and_exports_only_metadata(
    tmp_path, monkeypatch, mode
):
    from infrastructure.research.pilot.collection import collect_snapshot
    from infrastructure.research.pilot.retirement import review_collection

    value, initial, expected, ports, calls = disk_fixture(tmp_path, monkeypatch, mode)
    with patch("sys.platform", "darwin" if mode == "mac" else "linux"):
        if mode in ("complete", "unknown-run", "ambiguous"):
            actual = collect_snapshot(
                value,
                expected["process"],
                deadline=1000,
                clock=lambda: 100,
                ports=ports,
            )
            assert actual["run_states"] == expected["run_states"]
            assert actual["state_budget"] == expected["state_budget"]
            assert calls.count("checkpoint") == 12 and calls.count("history") == 6
            assert calls.count("archive") == (3 if mode == "ambiguous" else 4)
            assert "content" not in json.dumps(
                actual
            ) and "records.parquet" in json.dumps(actual)
            if mode == "complete":
                proof = review_collection(
                    value,
                    actual,
                    expected_process=expected["process"],
                    initial_budget=initial,
                )
                assert proof["job_complete"] is True
            else:
                with pytest.raises(ValueError):
                    review_collection(
                        value,
                        actual,
                        expected_process=expected["process"],
                        initial_budget=initial,
                    )
        else:
            with pytest.raises(ValueError):
                collect_snapshot(
                    value,
                    expected["process"],
                    deadline=1000,
                    clock=lambda: 100,
                    ports=ports,
                )
            if mode == "mac":
                assert calls == []
            if mode == "live":
                assert "checkpoint" not in calls and "archive" not in calls
