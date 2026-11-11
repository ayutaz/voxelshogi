"""Opaque input/ledger files and fake execution ports; no model or network."""

import copy
import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from export.research_contract import architecture_config
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.tests.test_hub_release import release


def spec():
    with patch("sys.platform", "darwin"):
        inputs = runpy.run_path("training/tests/pilot_ports/check-attempt.py")["inputs"]
    base = "runs/p6/research-pilot"
    inputs["paths"] = {
        "selfplay": base + "/input-selfplay",
        "protocol": base + "/selfplay-protocol.json",
        "protection": base + "/input-protection/config.json",
        "screen": base + "/input-screen/config.json",
        "diagnosis_manifest": base + "/input-diagnosis/manifest.json",
    }
    candidate = copy.deepcopy(inputs)
    candidate["config"]["architecture"] = architecture_config("geometry").__dict__
    return {
        "schema": "voxelshogi-research-pilot-job-v1",
        "source_commit": "a" * 40,
        "base": base,
        "inputs": [inputs, candidate],
        "split_step": 3,
        "compute_deadline": 200,
        "transfer_deadline": 300,
        "selfplay_protocol": {"opaque": "reviewed separately by actual attempt"},
        "state_upload_budget_sha256": "b" * 64,
        "maximum_owned_rss_bytes": 32 * 1024**3,
        "input_bundles": {},
    }


def bundles(tmp_path):
    result = {}
    for label in ("selfplay", "protection", "screen", "diagnosis"):
        folder = tmp_path / label
        folder.mkdir()
        plan = release(folder)
        plan.update(repo_id="voxelshogi/opaque-" + label, repo_type="dataset")
        result[label] = {
            "plan": plan,
            "receipt": {
                "repo_id": plan["repo_id"],
                "repo_type": "dataset",
                "release_sha256": fingerprint(plan),
                "hub_commit": "c" * 40,
                "verified": True,
                "community_disabled": True,
                "dry_run": False,
            },
        }
    return result


class Hub:
    def __init__(self, *, authorized=True):
        self.authorized = authorized
        self.calls = []

    def whoami(self):
        self.calls.append("identity")
        return {
            "name": "ayousanz" if self.authorized else "wrong",
            "orgs": [{"name": "voxelshogi"}],
        }

    def repo_info(self, **kwargs):
        return SimpleNamespace(private=False, gated="manual", sha=kwargs["revision"])

    def community_disabled(self, **kwargs):
        return True


@pytest.mark.parametrize(
    "mode",
    [
        "complete",
        "second-failed",
        "unverified-input",
        "wrong-account",
        "duplicate",
        "wrong-cycle",
        "ledger-rewrite",
    ],
)
def test_job_verifies_all_inputs_before_two_cycles_and_collects_ledger_without_retiring(
    tmp_path, monkeypatch, mode
):
    from infrastructure.research.pilot.job import run_job

    value = spec()
    value["input_bundles"] = bundles(tmp_path)
    monkeypatch.chdir(tmp_path)
    base = Path(value["base"])
    base.mkdir(parents=True)
    ledger = {
        "schema": "voxelshogi-state-upload-budget-v1",
        "approved_maximum_new_bytes": 1024**3,
        "reservations": [{"release_sha256": "1" * 64, "maximum_bytes": 17}],
    }
    budget = base / "state-upload-budget.json"
    budget.write_text(json.dumps(ledger))
    value["state_upload_budget_sha256"] = file_hash(budget)
    if mode == "duplicate":
        (base / "job-request.json").write_text("{}")
    api, calls = Hub(authorized=mode != "wrong-account"), []

    def acquire(bundle, destination, **kwargs):
        calls.append(("acquire", destination.name))
        assert kwargs["api"] is api and kwargs["deadline"] == 200
        destination.mkdir()
        return {**bundle["receipt"], "verified": mode != "unverified-input"}

    def cycle(inputs, destination, **kwargs):
        calls.append(("cycle", inputs["config"]["architecture"]["architecture"]))
        assert kwargs["compute_deadline"] == 200 and kwargs["deadline"] == 300
        assert kwargs["split_step"] == 3 and kwargs["upload_budget"] == budget
        assert [c[0] for c in calls[:4]] == ["acquire"] * 4
        if mode == "second-failed" and len(calls) == 6:
            raise RuntimeError("not safe to retain arbitrary exception text")
        changed = json.loads(budget.read_text())
        if mode == "ledger-rewrite":
            changed["reservations"][0]["maximum_bytes"] = 18
        changed["reservations"].append(
            {"release_sha256": str(len(calls)) * 64, "maximum_bytes": 123}
        )
        budget.write_text(json.dumps(changed))
        return {
            "scientific_pilots": 1,
            "additional_independent_seeds": 0,
            "source_commit": inputs["source_commit"],
            "inputs_sha256": "f" * 64 if mode == "wrong-cycle" else fingerprint(inputs),
        }

    ports = {
        "source": lambda source: calls.append(("source", source)),
        "hardware": lambda: {"verified": True},
        "acquire": acquire,
        "cycle": cycle,
    }
    # Keep source observations separate from the four acquisition assertions.
    ports["source"] = lambda source: None
    with patch("sys.platform", "linux"):
        if mode == "complete":
            result = run_job(value, api=api, fetch=None, ports=ports, clock=lambda: 100)
            assert (
                result["learning_complete"] is True and result["scientific_pilots"] == 2
            )
            assert result["additional_independent_seeds"] == 0
            assert [c for c in calls if c[0] == "cycle"] == [
                ("cycle", "full"),
                ("cycle", "geometry"),
            ]
            assert result["development_evaluation_executed"] is False
            assert result["host_retirement_authorized"] is False
        else:
            with pytest.raises((ValueError, RuntimeError, FileExistsError)):
                run_job(value, api=api, fetch=None, ports=ports, clock=lambda: 100)
            assert not (base / "training-complete.json").exists()
            assert not any(c[0] == "cycle" for c in calls) or mode in (
                "second-failed",
                "wrong-cycle",
                "ledger-rewrite",
            )
            if mode in ("duplicate", "wrong-account"):
                assert calls == []
            if mode == "duplicate":
                assert api.calls == []
    if mode in ("complete", "second-failed"):
        collected = json.loads((base / "state-budget-final.json").read_text())
        assert collected == json.loads(budget.read_text())
        assert len(collected["reservations"]) == (3 if mode == "complete" else 2)


@pytest.mark.parametrize(
    "change",
    [
        "same-architecture",
        "changed-data",
        "changed-updates",
        "bad-window",
        "unverified-release",
    ],
)
def test_job_invalid_frozen_conditions_fail_before_execution(change, tmp_path):
    from infrastructure.research.pilot.job import validate_job

    value = spec()
    value["input_bundles"] = bundles(tmp_path)
    if change == "same-architecture":
        value["inputs"][1] = copy.deepcopy(value["inputs"][0])
    if change == "changed-data":
        value["inputs"][1]["paths"]["selfplay"] = "runs/other"
    if change == "changed-updates":
        value["inputs"][1]["config"]["total_updates"] += 1
    if change == "bad-window":
        value["compute_deadline"] = 300
    if change == "unverified-release":
        value["input_bundles"]["diagnosis"]["receipt"]["verified"] = False
    with pytest.raises(ValueError):
        validate_job(value, now=100)


@pytest.mark.parametrize("corrupt", [False, True, "cache-symlink"])
def test_actual_input_acquisition_checks_fixed_hashes_and_copies_only_verified_bytes(
    tmp_path, corrupt
):
    from infrastructure.research.pilot.job import acquire_release

    bundle = bundles(tmp_path)["selfplay"]
    calls = []

    def fetch(**kwargs):
        assert kwargs["revision"] == "c" * 40 and kwargs["repo_type"] == "dataset"
        calls.append(kwargs["filename"])
        return tmp_path / "selfplay" / kwargs["filename"]

    if corrupt == "cache-symlink":
        original = tmp_path / "selfplay/model.onnx"
        blob = tmp_path / "verified-cache-blob"
        original.rename(blob)
        original.symlink_to(blob)
    elif corrupt:
        (tmp_path / "selfplay/model.onnx").write_bytes(b"bad opaque bytes")
    with patch("sys.platform", "linux"):
        if corrupt is True:
            with pytest.raises(ValueError, match="hash"):
                acquire_release(
                    bundle,
                    tmp_path / "download",
                    api=Hub(),
                    fetch=fetch,
                    deadline=200,
                    clock=lambda: 100,
                )
        else:
            proof = acquire_release(
                bundle,
                tmp_path / "download",
                api=Hub(),
                fetch=fetch,
                deadline=200,
                clock=lambda: 100,
            )
            assert proof["verified"] is True and len(calls) == len(
                bundle["plan"]["files"]
            )
            for entry in bundle["plan"]["files"]:
                target = tmp_path / "download" / entry["path"]
                assert (
                    hashlib.sha256(target.read_bytes()).hexdigest() == entry["sha256"]
                )


def test_mac_cannot_start_job_or_acquire_real_input_files():
    from infrastructure.research.pilot.job import acquire_release, run_job

    with (
        patch("sys.platform", "darwin"),
        pytest.raises(ValueError, match="external Linux"),
    ):
        run_job({}, api=None, fetch=None)
    with (
        patch("sys.platform", "darwin"),
        pytest.raises(ValueError, match="external Linux"),
    ):
        acquire_release({}, "opaque", api=None, fetch=None, deadline=1)


def test_resource_observer_sums_owned_children_and_requests_stop_without_remote_calls():
    import threading

    from infrastructure.research.pilot.job import observe_resources

    stop, done, rows = threading.Event(), threading.Event(), []

    def sample():
        done.set()
        return {"summed_owned_rss_bytes": 11, "owned_cpu_seconds": 1.25}

    with patch("sys.platform", "linux"):
        observe_resources(10, stop, done, rows, sample=sample)
    assert stop.is_set() and len(rows) == 1
    assert rows[0]["stop_reason"] == "owned-rss-limit"
    assert rows[0]["owned_cpu_seconds"] == 1.25


def test_observer_errors_retain_type_without_exception_text():
    import threading

    from infrastructure.research.pilot.job import observe_resources

    stop, done, rows = threading.Event(), threading.Event(), []

    def sample():
        done.set()
        raise OSError("opaque credential-like message must not be recorded")

    with patch("sys.platform", "linux"):
        observe_resources(10, stop, done, rows, sample=sample)
    assert rows[0]["observation_error_type"] == "OSError"
    assert "credential-like" not in json.dumps(rows)


def test_resource_sample_includes_parent_and_all_owned_children(monkeypatch):
    import sys

    from infrastructure.research.pilot import job

    child = SimpleNamespace(
        memory_info=lambda: SimpleNamespace(rss=8), cpu_times=lambda: (0.5, 0.25)
    )
    parent = SimpleNamespace(
        memory_info=lambda: SimpleNamespace(rss=4),
        cpu_times=lambda: (0.25, 0.5),
        children=lambda **kw: [child],
    )
    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(Process=lambda: parent))
    monkeypatch.setattr(
        job.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout="30, 123")
    )
    row = job.sample_owned_resources()
    assert row == {
        "summed_owned_rss_bytes": 12,
        "owned_cpu_seconds": 1.5,
        "gpu_utilization_percent": 30,
        "gpu_memory_used_mib": 123,
    }


@pytest.mark.parametrize("mode", ["clean", "wrong-source", "dirty"])
def test_actual_source_checker_requires_exact_clean_head(monkeypatch, mode):
    from infrastructure.research.pilot import job

    def git(args, **kwargs):
        if args == ["git", "rev-parse", "HEAD"]:
            return ("b" if mode == "wrong-source" else "a") * 40 + "\n"
        assert args == ["git", "status", "--porcelain"]
        return " M owned.py" if mode == "dirty" else ""

    monkeypatch.setattr(job.subprocess, "check_output", git)
    if mode == "clean":
        job.check_source("a" * 40)
    else:
        with pytest.raises(ValueError):
            job.check_source("a" * 40)
