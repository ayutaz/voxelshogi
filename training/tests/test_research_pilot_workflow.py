"""Two scientific pilots through bounded workflow ports, no GPU/data/network."""

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.tests.test_research_pilot_job import Hub, bundles, spec
from training.tests.test_research_pilot_validation import screen


def setup(tmp_path, monkeypatch, mode="complete"):
    job = spec()
    job["input_bundles"] = bundles(tmp_path)
    m4 = copy.deepcopy(job["input_bundles"]["selfplay"])
    frozen = screen()
    value = {
        "schema": "voxelshogi-research-pilot-workflow-v1",
        "job": job,
        "m4_bundle": m4,
        "development": frozen,
        "development_sha256": fingerprint(frozen),
    }
    monkeypatch.chdir(tmp_path)
    proof = Path("docs/experiments/m4-production-release-2026-10-29.json")
    proof.parent.mkdir(parents=True)
    atomic_json(proof, {"publication": {**m4, "complete": True}})
    base = Path(job["base"])
    base.mkdir(parents=True)
    ledger = {
        "schema": "voxelshogi-state-upload-budget-v1",
        "approved_maximum_new_bytes": 1024**3,
        "reservations": [{"release_sha256": "1" * 64, "maximum_bytes": 17}],
    }
    atomic_json(base / "state-upload-budget.json", ledger)
    job["state_upload_budget_sha256"] = file_hash(base / "state-upload-budget.json")
    calls = []
    current = [100]

    def acquire(bundle, folder, **kwargs):
        assert bundle == m4 and kwargs["deadline"] == 200
        calls.append("m4")
        folder.mkdir()
        if mode == "m4-failure":
            raise ConnectionError("do not log arbitrary server text")
        return {**m4["receipt"], "verified": mode != "m4-unverified"}

    def learn(value, *, input_admission, **kwargs):
        calls.append("learn")
        assert value == job and kwargs["api"].whoami()["name"] == "ayousanz"
        assert kwargs["stop_requested"]() is False
        folder = base / "input-screen"
        folder.mkdir()
        actual = copy.deepcopy(frozen)
        if mode == "changed-screen":
            actual["protocol"]["cases"][0]["opening"]["initial"] = "changed"
        atomic_json(
            folder / "config.json",
            {
                "protocols": {"legal-argmax-v1": actual["protocol"]},
                "families": actual["families"],
            },
        )
        if mode != "ignored-admission":
            input_admission(folder)
        if mode == "learning-failure":
            raise RuntimeError("unsafe arbitrary exception message")
        if mode == "ledger-rewrite":
            broken = copy.deepcopy(ledger)
            broken["reservations"][0]["maximum_bytes"] = 18
            atomic_json(base / "state-upload-budget.json", broken)
        return {
            "schema": "voxelshogi-research-pilot-learning-result-v1",
            "learning_complete": mode != "partial-learning",
            "scientific_pilots": 2,
            "job_sha256": fingerprint(job),
            "source_commit": job["source_commit"],
            "additional_independent_seeds": 0,
        }

    def post(inputs, run, output, **kwargs):
        name = inputs["config"]["architecture"]["architecture"]
        assert run == base / name / "continuous"
        assert kwargs["deadline"] == 200 and not kwargs["stop_requested"]()
        calls.append("post-" + name)
        if mode == "post-failure" and name == "geometry":
            raise ValueError("invalid checkpoint")
        if mode == "compute-expired" and name == "full":
            current[0] = 200
        return {
            "schema": "voxelshogi-research-pilot-diagnostic-v1",
            "source_commit": "b" * 40
            if mode == "post-source"
            else job["source_commit"],
            "architecture": name,
            "inputs_sha256": fingerprint(inputs),
            "test_features_encoded": 0,
            "final_holdout_evaluated": False,
            "selection": {
                "folder": str(output / "selected"),
                "selection_sha256": "d" * 64,
            },
        }

    def develop(frozen_arg, selected, output, **kwargs):
        calls.append("develop")
        assert frozen_arg == frozen and set(selected) == {"full", "geometry"}
        assert output == base / "development"
        assert kwargs["corpus"] == base / "input-m4/production-64"
        assert kwargs["selfplay"] == base / "input-selfplay"
        assert kwargs["protection"] == base / "input-protection/config.json"
        assert kwargs["selfplay_protocol"] == job["selfplay_protocol"]
        assert kwargs["expected_sha256"] == fingerprint(frozen)
        assert kwargs["deadline"] == 200 and kwargs["source_commit"] == "a" * 40
        return {
            "schema": "voxelshogi-research-pilot-development-v1",
            "games": 47 if mode == "partial-games" else 48,
            "leakage_free": mode != "overlap",
            "source_commit": job["source_commit"],
            "frozen_development_sha256": fingerprint(frozen),
            "final_holdout_evaluated": False,
        }

    def publish(config, folder, *, pipeline_complete, **kwargs):
        calls.append("publish-complete" if pipeline_complete else "publish-partial")
        assert kwargs["deadline"] == 300
        assert config == value and folder == base
        assert (base / "workflow-compute.json").exists()
        assert (base / "state-budget-final.json").exists()
        if mode == "publication-failure":
            raise TimeoutError("ambiguous upload, no blind resend")
        receipt = {
            "verified": mode != "publication-unverified",
            "repo_id": "voxelshogi/voxelshogi-research-pilot-results-v1",
            "hub_commit": "c" * 40,
        }
        return {"pipeline_complete": pipeline_complete, "receipt": receipt}

    ports = {
        "source": lambda source: calls.append("source"),
        "acquire": acquire,
        "learn": learn,
        "post": post,
        "develop": develop,
        "publish": publish,
    }
    return value, ports, calls, current


@pytest.mark.parametrize(
    "mode",
    [
        "complete",
        "m4-failure",
        "m4-unverified",
        "learning-failure",
        "changed-screen",
        "ignored-admission",
        "partial-learning",
        "post-failure",
        "post-source",
        "compute-expired",
        "partial-games",
        "overlap",
        "ledger-rewrite",
        "publication-failure",
        "publication-unverified",
    ],
)
def test_workflow_orders_real_stages_and_publishes_failures_without_claiming_completion(
    tmp_path, monkeypatch, mode
):
    from infrastructure.research.pilot.workflow import run_workflow

    value, ports, calls, current = setup(tmp_path, monkeypatch, mode)
    with patch("sys.platform", "linux"):
        if mode == "complete":
            result = run_workflow(
                value, api=Hub(), fetch=None, ports=ports, clock=lambda: current[0]
            )
            assert calls == [
                "source",
                "m4",
                "learn",
                "post-full",
                "post-geometry",
                "develop",
                "publish-complete",
            ]
            assert result["pipeline_complete"] is True
            assert result["host_retirement_authorized"] is False
            assert result["controller_ledger_collection_required"] is True
            assert result["final_holdout_evaluated"] is False
        else:
            with pytest.raises(
                (
                    ValueError,
                    RuntimeError,
                    InterruptedError,
                    ConnectionError,
                    TimeoutError,
                )
            ):
                run_workflow(
                    value, api=Hub(), fetch=None, ports=ports, clock=lambda: current[0]
                )
            base = Path(value["job"]["base"])
            assert not (base / "workflow-complete.json").exists()
            failure = json.loads((base / "workflow-failure.json").read_text())
            assert failure["pipeline_complete"] is False
            assert "unsafe arbitrary" not in json.dumps(failure)
            assert sum(c.startswith("publish-") for c in calls) == 1
            if mode in (
                "changed-screen",
                "ignored-admission",
                "partial-learning",
                "m4-failure",
                "m4-unverified",
            ):
                assert not any(c.startswith("post-") for c in calls)
            if mode in ("post-failure", "post-source", "compute-expired"):
                assert "develop" not in calls
            if mode not in ("publication-failure", "publication-unverified"):
                assert calls[-1] == "publish-partial"


@pytest.mark.parametrize(
    "mode",
    [
        "hash",
        "m4",
        "candidate",
        "duplicate",
        "linux",
        "stop",
        "source-failed",
        "account",
    ],
)
def test_workflow_admission_fails_without_learning_or_publication(
    tmp_path, monkeypatch, mode
):
    from infrastructure.research.pilot.workflow import run_workflow

    value, ports, calls, _ = setup(tmp_path, monkeypatch)
    if mode == "hash":
        value["development_sha256"] = "0" * 64
    elif mode == "m4":
        value["m4_bundle"]["receipt"]["hub_commit"] = "f" * 40
    elif mode == "candidate":
        value["job"]["inputs"][1]["config"]["architecture"] = value["job"]["inputs"][0][
            "config"
        ]["architecture"]
    elif mode == "duplicate":
        (Path(value["job"]["base"]) / "workflow-request.json").write_text("{}")
    elif mode == "source-failed":
        ports["source"] = lambda _: (_ for _ in ()).throw(
            ValueError("different source")
        )
    with (
        patch("sys.platform", "darwin" if mode == "linux" else "linux"),
        pytest.raises(ValueError),
    ):
        run_workflow(
            value,
            api=Hub(authorized=mode != "account"),
            fetch=None,
            ports=ports,
            clock=lambda: 100,
            stop_requested=lambda: mode == "stop",
        )
    assert not any(
        c in ("m4", "learn", "develop") or c.startswith("publish-") for c in calls
    )


def test_default_learning_port_admits_actual_screen_before_any_fit(
    tmp_path, monkeypatch
):
    from infrastructure.research.pilot import job
    from infrastructure.research.pilot.workflow import load_ports

    calls = []

    def acquire(bundle, folder, **kwargs):
        calls.append(folder.name)
        return {"verified": True}

    def learning(value, **kwargs):
        for label in ("selfplay", "protection", "screen", "diagnosis"):
            kwargs["ports"]["acquire"]({}, tmp_path / ("input-" + label))
        calls.append("fit")

    monkeypatch.setattr(job, "acquire_release", acquire)
    monkeypatch.setattr(job, "run_job", learning)

    def admit(folder):
        assert folder.name == "input-screen"
        calls.append("admission")
        raise ValueError("changed protected root")

    with pytest.raises(ValueError):
        load_ports()["learn"]({}, input_admission=admit, api=None, fetch=None)
    assert calls == ["input-selfplay", "input-protection", "input-screen", "admission"]


@pytest.mark.parametrize("mode", ["stop", "deadline"])
def test_completed_transfer_does_not_hide_late_stop_or_expired_deadline(
    tmp_path, monkeypatch, mode
):
    from infrastructure.research.pilot.workflow import run_workflow

    value, ports, calls, current = setup(tmp_path, monkeypatch)
    original = ports["publish"]
    stopped = [False]

    def publish(*args, **kwargs):
        result = original(*args, **kwargs)
        if mode == "stop":
            stopped[0] = True
        else:
            current[0] = 300
        return result

    ports["publish"] = publish
    with patch("sys.platform", "linux"), pytest.raises(InterruptedError):
        run_workflow(
            value,
            api=Hub(),
            fetch=None,
            ports=ports,
            clock=lambda: current[0],
            stop_requested=lambda: stopped[0],
        )
    base = Path(value["job"]["base"])
    assert not (base / "workflow-complete.json").exists()
    assert (base / "workflow-publication.json").exists()
    assert calls[-1] == "publish-complete"
