"""Hand-built preservation proofs and fake controller ports; no GPU or network."""

from copy import deepcopy

import pytest

from training.evaluation_v2 import fingerprint
from training.tests.test_research_pilot_workflow import setup


def collection_fixture(tmp_path, monkeypatch):
    value, _, _, _ = setup(tmp_path, monkeypatch)
    source = value["job"]["source_commit"]
    process = {"pid": 7, "create_time": 10.5, "source_commit": source, "running": False}
    initial = {
        "schema": "voxelshogi-state-upload-budget-v1",
        "approved_maximum_new_bytes": 1024**3,
        "reservations": [{"release_sha256": "1" * 64, "maximum_bytes": 17}],
    }
    states, transfers, proofs = {}, {}, {}
    final = deepcopy(initial)
    for index, inputs in enumerate(value["job"]["inputs"]):
        name = inputs["config"]["architecture"]["architecture"]
        binding = {
            "source_commit": source,
            "cache_sha256": str(index + 2) * 64,
            "config": inputs["config"],
            "contract": {
                "schema": "voxelshogi-research-visit-training-v1",
                "admission_sha256": inputs["admission_sha256"],
            },
            "environment": {"device": "cuda"},
        }
        for offset, run in enumerate(("continuous", "interrupted", "restored")):
            states[name + "/" + run] = {
                "binding": binding,
                "history_sha256": "e" * 64,
                "history_events": 10,
                "checkpoints": {
                    role: {
                        "sha256": f"{100 * index + offset * 2 + r + 10:064x}",
                        "progress": {
                            "step": value["job"]["split_step"]
                            if run == "interrupted"
                            else inputs["config"]["total_updates"]
                        },
                    }
                    for r, role in enumerate(("latest", "best"))
                },
            }
        for stage, run in (("intermediate", "interrupted"), ("final", "continuous")):
            state = states[name + "/" + run]
            manifest = {
                "schema": "voxelshogi-research-resume-archive-v1",
                "purpose": "resume-state",
                "complete": True,
                "binding": binding,
                "roles": {
                    role: {
                        "source_checkpoint_sha256": item["sha256"],
                        "progress": item["progress"],
                    }
                    for role, item in state["checkpoints"].items()
                },
            }
            manifest_sha = fingerprint(manifest)
            plan = {
                "schema": 1,
                "source_commit": source,
                "repo_id": "voxelshogi/voxelshogi-research-training-state-v1",
                "repo_type": "model",
                "artifact_role": "research-training-state",
                "private": False,
                "gated": "manual",
                "license": "apache-2.0",
                "license_approved": True,
                "state_publication_approved": True,
                "expected_binding": binding,
                "files": [
                    {"path": "manifest.json", "bytes": 100, "sha256": manifest_sha}
                ],
            }
            receipt = {
                "repo_id": plan["repo_id"],
                "repo_type": "model",
                "hub_commit": "c" * 40,
                "release_sha256": fingerprint(plan),
                "verified": True,
                "community_disabled": True,
                "dry_run": False,
            }
            transfers[name + "/" + stage] = {
                "plan": plan,
                "receipt": receipt,
                "manifest": manifest,
                "manifest_sha256": manifest_sha,
                "archive_verified": True,
                "restored": True,
            }
            final["reservations"].append(
                {"release_sha256": fingerprint(plan), "maximum_bytes": 100}
            )
        full, resumed = states[name + "/continuous"], states[name + "/restored"]
        proofs[name] = {
            "schema": "voxelshogi-research-pilot-cuda-resume-proof-v1",
            "verified": True,
            "source_commit": source,
            "binding_sha256": fingerprint(binding),
            "total_updates": inputs["config"]["total_updates"],
            "history_sha256": full["history_sha256"],
            "history_events": 10,
            "checkpoints": {
                role: {
                    "exact_equal": True,
                    "compared": {"tensors": 2, "scalars": 3},
                    "progress": full["checkpoints"][role]["progress"],
                    "state_sha256": [
                        s["checkpoints"][role]["sha256"] for s in (full, resumed)
                    ],
                }
                for role in ("latest", "best")
            },
        }
    result_manifest = {
        "files": [
            {"path": "development/queries.jsonl", "bytes": 10, "sha256": "f" * 64}
        ],
        "records_parquet_sha256": "d" * 64,
        "pipeline_complete": True,
    }
    result_plan = {
        "schema": 1,
        "source_commit": source,
        "repo_id": "voxelshogi/voxelshogi-research-pilot-results-v1",
        "repo_type": "dataset",
        "private": False,
        "gated": "manual",
        "license": "cc-by-4.0",
        "license_approved": True,
        "files": [{"path": "records.parquet", "bytes": 123, "sha256": "d" * 64}],
    }
    result_receipt = {
        "repo_id": result_plan["repo_id"],
        "repo_type": "dataset",
        "hub_commit": "c" * 40,
        "release_sha256": fingerprint(result_plan),
        "verified": True,
        "community_disabled": True,
        "dry_run": False,
    }
    snapshot = {
        "schema": "voxelshogi-research-pilot-collection-v1",
        "source_commit": source,
        "workflow_sha256": fingerprint(value),
        "process": process,
        "owned_compute": [],
        "unknown_run_paths": [],
        "run_states": states,
        "state_transfers": transfers,
        "resume_proofs": proofs,
        "state_budget": final,
        "query_trace": {"bytes": 10, "sha256": "f" * 64},
        "result_publication": {
            "plan": result_plan,
            "receipt": result_receipt,
            "manifest": result_manifest,
        },
        "records": {
            "workflow-worker-finished.json": {
                "source_commit": source,
                "pipeline_complete": True,
                "observer_stopped": True,
            },
            "workflow-complete.json": {
                "source_commit": source,
                "pipeline_complete": True,
                "workflow_sha256": fingerprint(value),
                "scientific_pilots": 2,
                "games": 48,
                "state_budget_final_sha256": fingerprint(final),
                "publication": {"receipt": result_receipt},
            },
            "state-budget-final.json": final,
        },
    }
    return value, initial, snapshot


def test_all_live_checkpoint_hashes_are_covered_before_retirement(
    tmp_path, monkeypatch
):
    from infrastructure.research.pilot.retirement import review_collection

    value, initial, snapshot = collection_fixture(tmp_path, monkeypatch)
    result = review_collection(
        value, snapshot, expected_process=snapshot["process"], initial_budget=initial
    )
    assert result["job_complete"] is True
    assert result["covered_runs"] == sorted(snapshot["run_states"])
    assert result["state_budget_sha256"] == fingerprint(snapshot["state_budget"])
    assert result["collection_sha256"] == fingerprint(snapshot)
    assert result["phase6_complete"] is False


@pytest.mark.parametrize(
    "mode",
    [
        "running",
        "pid",
        "orphan",
        "unknown-run",
        "ledger-prefix",
        "ledger-unaccounted",
        "receipt",
        "archive",
        "current-checkpoint",
        "parity",
        "best-parity",
        "history",
        "binding",
        "trace",
        "result",
        "finished",
        "source",
    ],
)
def test_missing_current_state_or_unverified_artifact_cannot_authorize_retirement(
    tmp_path, monkeypatch, mode
):
    from infrastructure.research.pilot.retirement import review_collection

    value, initial, snap = collection_fixture(tmp_path, monkeypatch)
    expected = deepcopy(snap["process"])
    if mode == "running":
        snap["process"]["running"] = True
    elif mode == "pid":
        snap["process"]["pid"] += 1
    elif mode == "orphan":
        snap["owned_compute"] = [{"pid": 88}]
    elif mode == "unknown-run":
        snap["unknown_run_paths"] = ["full/extra"]
    elif mode == "ledger-prefix":
        snap["state_budget"]["reservations"][0]["maximum_bytes"] += 1
    elif mode == "ledger-unaccounted":
        snap["state_budget"]["reservations"].append(
            {"release_sha256": "9" * 64, "maximum_bytes": 3}
        )
    elif mode == "receipt":
        snap["state_transfers"]["full/final"]["receipt"]["verified"] = False
    elif mode == "archive":
        snap["state_transfers"]["full/final"]["manifest_sha256"] = "0" * 64
    elif mode == "current-checkpoint":
        snap["run_states"]["full/continuous"]["checkpoints"]["latest"]["sha256"] = (
            "0" * 64
        )
    elif mode == "parity":
        snap["resume_proofs"]["full"]["verified"] = False
    elif mode == "best-parity":
        snap["resume_proofs"]["full"]["checkpoints"]["best"]["exact_equal"] = False
    elif mode == "history":
        snap["run_states"]["full/restored"]["history_sha256"] = "0" * 64
    elif mode == "binding":
        snap["run_states"]["full/restored"]["binding"] = {
            **snap["run_states"]["full/restored"]["binding"],
            "cache_sha256": "0" * 64,
        }
    elif mode == "trace":
        snap["query_trace"]["sha256"] = "0" * 64
    elif mode == "result":
        snap["result_publication"]["receipt"]["verified"] = False
    elif mode == "finished":
        snap["records"]["workflow-worker-finished.json"]["observer_stopped"] = False
    elif mode == "source":
        snap["source_commit"] = "b" * 40
    if mode in ("ledger-prefix", "ledger-unaccounted"):
        snap["records"]["workflow-complete.json"]["state_budget_final_sha256"] = (
            fingerprint(snap["state_budget"])
        )
    with pytest.raises(ValueError):
        review_collection(
            value, snap, expected_process=expected, initial_budget=initial
        )


def test_failure_before_learning_can_retire_after_small_records_and_unchanged_ledger(
    tmp_path, monkeypatch
):
    from infrastructure.research.pilot.retirement import review_collection

    value, initial, snap = collection_fixture(tmp_path, monkeypatch)
    snap.update(
        run_states={},
        state_transfers={},
        resume_proofs={},
        state_budget=initial,
        result_publication=None,
        query_trace=None,
    )
    snap["records"] = {
        "workflow-worker-finished.json": {
            "source_commit": value["job"]["source_commit"],
            "pipeline_complete": False,
            "observer_stopped": True,
        },
        "workflow-failure.json": {
            "pipeline_complete": False,
            "error_type": "ReadTimeout",
        },
        "state-budget-final.json": initial,
    }
    result = review_collection(
        value, snap, expected_process=snap["process"], initial_budget=initial
    )
    assert result["job_complete"] is False and result["covered_runs"] == []


@pytest.mark.parametrize("mode", ["complete", "persist-failed", "delete-unconfirmed"])
def test_collection_and_durable_ledger_precede_one_owned_deletion(
    tmp_path, monkeypatch, mode
):
    from infrastructure.research.pilot.retirement import watch_pilot

    value, initial, snap = collection_fixture(tmp_path, monkeypatch)
    events, pauses, observations = (
        [],
        [],
        iter([{**snap, "process": {**snap["process"], "running": True}}, snap]),
    )

    def observe():
        events.append("observe")
        return next(observations)

    def collect():
        events.append("collect")
        return snap

    def persist(snapshot, review):
        events.append("persist")
        if mode == "persist-failed":
            raise OSError("disk full")
        return {
            "verified": True,
            "collection_sha256": review["collection_sha256"],
            "state_budget_sha256": review["state_budget_sha256"],
        }

    def retire():
        events.append("retire")
        return {
            "complete": mode != "delete-unconfirmed",
            "instances": [] if mode != "delete-unconfirmed" else [{"id": 1}],
        }

    if mode == "persist-failed":
        with pytest.raises(OSError):
            watch_pilot(
                value,
                expected_process=snap["process"],
                initial_budget=initial,
                observe=observe,
                collect=collect,
                persist=persist,
                retire=retire,
                deadline=1000,
                clock=lambda: 100,
                wait=pauses.append,
            )
        assert "retire" not in events
    else:
        result = watch_pilot(
            value,
            expected_process=snap["process"],
            initial_budget=initial,
            observe=observe,
            collect=collect,
            persist=persist,
            retire=retire,
            deadline=1000,
            clock=lambda: 100,
            wait=pauses.append,
        )
        assert events == [
            "observe",
            "observe",
            "collect",
            "persist",
            "retire",
        ] and pauses == [60]
        assert result["resources_released"] is (mode == "complete")


@pytest.mark.parametrize(
    "mode",
    [
        "complete",
        "already-collected",
        "foreign-ledger",
        "initial-bytes",
        "modified-snapshot",
    ],
)
def test_shared_ledger_collection_is_durable_prefix_preserving_and_reconcilable(
    tmp_path, monkeypatch, mode
):
    import json
    from pathlib import Path

    from infrastructure.research.pilot.retirement import (
        persist_collection,
        review_collection,
    )
    from training.checkpoint import atomic_json

    value, initial, snapshot = collection_fixture(tmp_path, monkeypatch)
    expected = snapshot["process"]
    review = review_collection(
        value, snapshot, expected_process=expected, initial_budget=initial
    )
    control = tmp_path / "control"
    control.mkdir()
    original = Path(value["job"]["base"]) / "state-upload-budget.json"
    (control / "state-upload-budget-initial.json").write_bytes(original.read_bytes())
    atomic_json(control / "job-launch.json", expected)
    shared = tmp_path / "shared-state-budget.json"
    shared.write_bytes(original.read_bytes())
    if mode == "already-collected":
        atomic_json(shared, snapshot["state_budget"])
    elif mode == "foreign-ledger":
        changed = deepcopy(initial)
        changed["reservations"].append({"release_sha256": "9" * 64, "maximum_bytes": 9})
        atomic_json(shared, changed)
    elif mode == "initial-bytes":
        (control / "state-upload-budget-initial.json").write_bytes(
            original.read_bytes() + b"\n"
        )
    elif mode == "modified-snapshot":
        snapshot["run_states"]["full/continuous"]["checkpoints"]["latest"]["sha256"] = (
            "0" * 64
        )
    if mode in ("foreign-ledger", "initial-bytes", "modified-snapshot"):
        before = shared.read_bytes()
        with pytest.raises(ValueError):
            persist_collection(control, shared, value, snapshot, review)
        assert shared.read_bytes() == before
    else:
        receipt = persist_collection(control, shared, value, snapshot, review)
        assert receipt["verified"] is True and receipt[
            "state_budget_sha256"
        ] == fingerprint(snapshot["state_budget"])
        assert json.loads(shared.read_text()) == snapshot["state_budget"]
        assert json.loads((control / "collection-receipt.json").read_text()) == receipt
        assert json.loads((control / "collection.json").read_text()) == snapshot


def test_unresolved_state_transfer_requires_reconciliation_before_retirement(
    tmp_path, monkeypatch
):
    from infrastructure.research.pilot.retirement import review_collection

    value, initial, snapshot = collection_fixture(tmp_path, monkeypatch)
    snapshot["unresolved_transfers"] = ["full/failure-rescue-continuous-transfer"]
    with pytest.raises(ValueError):
        review_collection(
            value,
            snapshot,
            expected_process=snapshot["process"],
            initial_budget=initial,
        )


def test_process_source_is_bound_to_frozen_workflow_even_if_both_pid_records_agree(
    tmp_path, monkeypatch
):
    from infrastructure.research.pilot.retirement import review_collection

    value, initial, snapshot = collection_fixture(tmp_path, monkeypatch)
    snapshot["process"]["source_commit"] = "b" * 40
    with pytest.raises(ValueError):
        review_collection(
            value,
            snapshot,
            expected_process=snapshot["process"],
            initial_budget=initial,
        )


def test_failed_cycle_cannot_discard_a_newer_unpublished_checkpoint(
    tmp_path, monkeypatch
):
    from infrastructure.research.pilot.retirement import review_collection

    value, initial, snapshot = collection_fixture(tmp_path, monkeypatch)
    snapshot["run_states"]["full/continuous"]["checkpoints"]["latest"]["sha256"] = (
        "0" * 64
    )
    snapshot["records"]["workflow-worker-finished.json"]["pipeline_complete"] = False
    del snapshot["records"]["workflow-complete.json"]
    snapshot["records"]["workflow-failure.json"] = {
        "pipeline_complete": False,
        "error_type": "ValueError",
    }
    snapshot.update(query_trace=None, result_publication=None)
    with pytest.raises(ValueError):
        review_collection(
            value,
            snapshot,
            expected_process=snapshot["process"],
            initial_budget=initial,
        )


def test_missing_durable_receipt_cannot_trigger_provider_delete(tmp_path, monkeypatch):
    from infrastructure.research.pilot.retirement import watch_pilot

    value, initial, snapshot = collection_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        watch_pilot(
            value,
            expected_process=snapshot["process"],
            initial_budget=initial,
            observe=lambda: snapshot,
            collect=lambda: snapshot,
            persist=lambda *args: {"verified": False},
            retire=lambda: pytest.fail("delete before verified persistence"),
            deadline=1000,
            clock=lambda: 100,
        )


def test_provider_success_flag_without_absence_is_not_resource_release(
    tmp_path, monkeypatch
):
    from infrastructure.research.pilot.retirement import watch_pilot

    value, initial, snapshot = collection_fixture(tmp_path, monkeypatch)
    result = watch_pilot(
        value,
        expected_process=snapshot["process"],
        initial_budget=initial,
        observe=lambda: snapshot,
        collect=lambda: snapshot,
        persist=lambda snap, review: {
            "verified": True,
            "collection_sha256": review["collection_sha256"],
            "state_budget_sha256": review["state_budget_sha256"],
        },
        retire=lambda: {"complete": True, "instances": [{"id": 123}]},
        deadline=1000,
        clock=lambda: 100,
    )
    assert result["resources_released"] is False


def test_expired_watcher_defers_to_independent_guard_without_read_or_delete():
    from infrastructure.research.pilot.retirement import watch_pilot

    result = watch_pilot(
        {},
        expected_process={},
        initial_budget={},
        observe=lambda: pytest.fail("expired observe"),
        collect=lambda: pytest.fail("expired collect"),
        persist=lambda *a: pytest.fail("expired persist"),
        retire=lambda: pytest.fail("expired delete"),
        deadline=100,
        clock=lambda: 100,
    )
    assert (
        result["independent_guard_required"] is True
        and result["resources_released"] is False
    )
