"""Selected-best diagnostic stage through opaque CUDA/data ports, no tensors."""

import copy
import json
from types import SimpleNamespace

import pytest

from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.tests.test_research_pilot_job import spec


def ports_for(tmp_path, mode="complete"):
    inputs = spec()["inputs"][0]
    c = inputs["config"]
    binding = {
        "source_commit": inputs["source_commit"],
        "cache_sha256": "e" * 64,
        "config": copy.deepcopy(c),
        "contract": {
            "schema": "voxelshogi-research-visit-training-v1",
            "admission_sha256": inputs["admission_sha256"],
        },
        "environment": {"device": "cuda", "opaque": "same-runtime"},
    }
    run = tmp_path / "continuous"
    run.mkdir()
    (run / "run.json").write_text(
        json.dumps({"schema": "voxelshogi-training-run-v1", "binding": binding})
    )
    if mode == "binding":
        binding["cache_sha256"] = "f" * 64
        (run / "run.json").write_text(
            json.dumps({"schema": "voxelshogi-training-run-v1", "binding": binding})
        )
    if mode in ("source", "admission", "config"):
        if mode == "source":
            binding["source_commit"] = "b" * 40
        elif mode == "admission":
            binding["contract"]["admission_sha256"] = "0" * 64
        else:
            binding["config"]["seed"] += 1
        (run / "run.json").write_text(
            json.dumps({"schema": "voxelshogi-training-run-v1", "binding": binding})
        )
    calls = []

    def prepare(value, **kwargs):
        from infrastructure.research.pilot.attempt import validate_inputs

        assert value == inputs and callable(kwargs["stop_requested"])
        calls.append("prepare")
        corpus = SimpleNamespace(
            val=SimpleNamespace(rows=[{"id": "one"}, {"id": "two"}]),
            digest=lambda config: (
                ("f" if mode == "data-race" and "metrics" in calls else "e") * 64
            ),
        )
        config, decision = validate_inputs(value)
        return (
            config,
            decision,
            corpus,
            {
                "feature_content_sha256": "e" * 64,
                "test_features_encoded": 1 if mode == "encoded-test" else 0,
            },
        )

    def environment(config):
        calls.append("environment")
        return {
            "device": "cuda",
            "opaque": "other-runtime" if mode == "environment" else "same-runtime",
        }

    def export(folder, target, *, expected_binding):
        assert folder == run and expected_binding == binding
        calls.append("export")
        target.mkdir()
        (target / "model.safetensors").write_bytes(b"opaque model port, not tensors")
        metadata = {
            "architecture": c["architecture"],
            "checkpoint_role": "best",
            "step": 128,
        }
        result = {
            "weights": {
                "sha256": file_hash(target / "model.safetensors"),
                "metadata": metadata,
            },
            "selected_receipt": {"step": 128},
        }
        (target / "selection.json").write_text(json.dumps(result))
        return result

    def network(path, **kwargs):
        assert kwargs == {"expected_sha256": file_hash(path), "device": "cuda"}
        calls.append("network")
        from export.research_contract import ResearchConfig

        return SimpleNamespace(
            config=ResearchConfig(**c["architecture"]), training=mode == "training-mode"
        ), {
            "architecture": c["architecture"],
            "checkpoint_role": "best",
            "step": 129 if mode == "metadata" else 128,
        }

    def metrics(model, data, config, **kwargs):
        assert len(data.rows) == 2 and callable(kwargs["stop_requested"])
        calls.append("metrics")
        if mode == "weight-race":
            (tmp_path / "post/selected/model.safetensors").write_text(
                "changed during diagnostic"
            )
        return {
            "schema": "voxelshogi-research-val-origins-v1",
            "split": "test" if mode == "test-metrics" else "val",
            "aggregate": {
                "examples": 2,
                "policy_ce": 1.0,
                "value_mse": 0.5,
                "loss": 1.5,
            },
            "bootstrap_is_observed_outcome": False,
        }

    return (
        inputs,
        run,
        {
            "prepare": prepare,
            "environment": environment,
            "export": export,
            "network": network,
            "metrics": metrics,
        },
        calls,
    )


@pytest.mark.parametrize(
    "mode",
    [
        "complete",
        "binding",
        "environment",
        "training-mode",
        "metadata",
        "weight-race",
        "early-stop",
        "late-stop",
        "duplicate",
        "test-metrics",
        "data-race",
        "workspace",
        "source",
        "admission",
        "config",
        "encoded-test",
    ],
)
def test_diagnostic_reuses_training_binding_and_selected_weights(
    monkeypatch, tmp_path, mode
):
    from infrastructure.research.pilot.post import run_post

    inputs, run, ports, calls = ports_for(tmp_path, mode)
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv(
        "CUBLAS_WORKSPACE_CONFIG", "wrong" if mode == "workspace" else ":4096:8"
    )
    out = tmp_path / "post"
    if mode == "duplicate":
        out.mkdir()

    def stop():
        return mode == "early-stop" or mode == "late-stop" and "metrics" in calls

    if mode != "complete":
        with pytest.raises((ValueError, InterruptedError)):
            run_post(
                inputs,
                run,
                out,
                deadline=200,
                clock=lambda: 100,
                stop_requested=stop,
                ports=ports,
            )
        assert not (out / "complete.json").exists()
        if mode not in ("early-stop", "duplicate", "workspace"):
            assert (out / "failure.json").exists()
        return
    result = run_post(inputs, run, out, deadline=200, clock=lambda: 100, ports=ports)
    assert calls == ["prepare", "environment", "export", "network", "metrics"]
    assert result["source_commit"] == inputs["source_commit"]
    assert result["inputs_sha256"] == fingerprint(inputs)
    assert result["selected_step"] == 128 and result["test_features_encoded"] == 0
    assert result["final_holdout_evaluated"] is False
    assert result["origins"]["aggregate"]["examples"] == 2
    assert result["selection"]["selection_sha256"] == file_hash(
        out / "selected/selection.json"
    )
    assert json.loads((out / "complete.json").read_text()) == result


def test_post_refuses_Mac_before_data_or_model_ports(monkeypatch, tmp_path):
    from infrastructure.research.pilot.post import run_post

    monkeypatch.setattr("sys.platform", "darwin")
    with pytest.raises(ValueError, match="external Linux"):
        run_post({}, tmp_path / "absent", tmp_path / "out", deadline=200)
