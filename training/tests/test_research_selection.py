"""Handwritten validation histories and opaque checkpoint ports; no Mac tensors."""

from copy import deepcopy

import pytest


def records(name="full"):
    from dataclasses import asdict

    from export.research_contract import architecture_config
    from training.research_visit_fit import VisitRunConfig

    config = VisitRunConfig(
        architecture=architecture_config(name),
        total_updates=4,
        validate_every=2,
        batch_size=2,
    )
    binding = {
        "source_commit": "a" * 40,
        "cache_sha256": "b" * 64,
        "config": config.value(),
        "contract": {
            "schema": "voxelshogi-research-visit-training-v1",
            "admission_sha256": "c" * 64,
        },
        "environment": {"device": "cuda"},
    }
    events = []
    for step in range(1, 5):
        events.append(
            {"event": "train", "step": step, "ids": ["one", "two"], "loss": 2.0}
        )
        if step % 2 == 0:
            events.append(
                {
                    "event": "val",
                    "step": step,
                    "policy_ce": 0.75,
                    "value_mse": 0.25,
                    "loss": 1.0,
                    "examples": 2,
                    "value_origins": {"terminal-v1": 1, "bootstrap-v1": 1},
                }
            )

    def receipt(step):
        return {
            "schema": "voxelshogi-checkpoint-v1",
            "verified": True,
            "step": step,
            "binding": deepcopy(binding),
            "bytes": 123,
            "sha256": "d" * 64,
            "progress": {
                "epoch": 0,
                "next_batch": step,
                "step": step,
                "examples": step * 2,
                "best_val_loss": 1.0,
            },
        }

    expected = {
        "schema": "voxelshogi-research-weights-v1",
        "architecture": asdict(architecture_config(name)),
        "seed": 67003,
        "source_commit": "a" * 40,
        "checkpoint_role": "best",
        "step": 2,
    }
    return binding, receipt(4), receipt(2), events, expected


@pytest.mark.parametrize("name", ["full", "axial", "geometry", "cnn"])
def test_fixed_M_selects_first_minimum_validation_and_binds_full_training(name):
    from training.evaluation_v2 import fingerprint
    from training.research_selection import review_selection

    binding, latest, best, events, expected = records(name)
    value = review_selection(binding, latest, best, events)
    assert value == expected | {"training_binding_sha256": fingerprint(binding)}
    # A strictly better final validation changes selection to the final checkpoint.
    events[-1].update(policy_ce=0.25, value_mse=0.25, loss=0.5)
    latest["progress"]["best_val_loss"] = 0.5
    assert review_selection(binding, latest, latest, events)["step"] == 4


@pytest.mark.parametrize(
    "change",
    [
        "partial",
        "wrong-best",
        "tie-later",
        "bad-loss",
        "best-binding",
        "latest-binding",
        "receipt-step",
        "missing-val",
        "missing-final-val",
        "empty",
        "toy",
        "boolean",
        "unverified",
        "examples",
        "unscheduled",
        "best-progress",
        "binding-hash-source",
    ],
)
def test_incomplete_or_unselected_checkpoint_is_rejected(change):
    from training.research_selection import review_selection

    b, latest, best, events, _ = records()
    if change == "partial":
        latest["progress"]["step"] = latest["step"] = 3
        latest["progress"]["examples"] = 6
        events = events[:-2]
    elif change == "wrong-best":
        events[-1].update(policy_ce=0.25, value_mse=0.25, loss=0.5)
        latest["progress"]["best_val_loss"] = 0.5
    elif change == "tie-later":
        best = deepcopy(latest)
    elif change == "bad-loss":
        best["progress"]["best_val_loss"] = 3.0
    elif change == "best-binding":
        best["binding"]["cache_sha256"] = "e" * 64
    elif change == "latest-binding":
        latest["binding"]["source_commit"] = "e" * 40
    elif change == "receipt-step":
        best["progress"]["step"] = 3
    elif change == "missing-val":
        events.pop(2)
    elif change == "missing-final-val":
        events.pop()
    elif change == "empty":
        events = []
    elif change == "toy":
        b["config"]["architecture"]["side"] = 2
    elif change == "boolean":
        best["step"] = best["progress"]["step"] = True
    elif change == "unverified":
        best["verified"] = False
    elif change == "examples":
        best["progress"]["examples"] = 1
    elif change == "unscheduled":
        events[2]["step"] = 1
    elif change == "best-progress":
        best["progress"]["best_val_loss"] = float("nan")
    elif change == "binding-hash-source":
        b["source_commit"] = "main"
    with pytest.raises(ValueError):
        review_selection(b, latest, best, events)


def test_export_refuses_Mac_before_checkpoint_or_numeric_imports(monkeypatch, tmp_path):
    import training.research_selection as module

    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setitem(module.sys.modules, "torch", None)
    with pytest.raises(ValueError, match="external Linux"):
        module.export_selected_weights(
            tmp_path / "absent", tmp_path / "out", expected_binding={}
        )


def export_ports(monkeypatch, tmp_path):
    import json
    import sys
    from types import SimpleNamespace

    import training.research_selection as module
    from training.feature_cache import file_hash

    b, latest, best, events, _ = records()
    run = tmp_path / "run"
    run.mkdir()
    (run / "checkpoints").mkdir()
    state = run / "checkpoints" / "opaque-state"
    state.write_bytes(b"opaque checkpoint port, no tensors")
    best["sha256"] = file_hash(state)
    (run / "run.json").write_text(
        json.dumps({"schema": "voxelshogi-training-run-v1", "binding": b})
    )
    (run / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    payload = {
        "model": {"weight": "opaque-state"},
        "optimizer": {},
        "rng": {},
        "binding": deepcopy(b),
        "progress": deepcopy(best["progress"]),
    }
    seen = []

    def read_checkpoint(folder, *, binding, which="latest"):
        assert folder == run / "checkpoints" and binding == b
        seen.append(which)
        return state, latest if which == "latest" else best

    def load(path, *, map_location, weights_only):
        assert path == state and map_location == "cpu" and weights_only is True
        seen.append("decode")
        return payload

    def make(config, *, seed):
        assert config.architecture == "full" and seed == 67003

        def strict(state, *, strict):
            assert strict is True and state == {"weight": "opaque-state"}
            seen.append("strict")

        return SimpleNamespace(load_state_dict=strict)

    def write(state, path, *, metadata):
        assert state == payload["model"] and metadata["step"] == 2
        seen.append("write")
        path.write_bytes(b"opaque exported weight port")
        return {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": file_hash(path),
            "metadata": metadata,
        }

    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setattr(module, "source_commit", lambda: "e" * 40)
    monkeypatch.setattr(module, "checkpoint_receipt", read_checkpoint)
    monkeypatch.setattr(module, "write_research_weights", write)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(load=load))
    monkeypatch.setitem(
        sys.modules, "export.research_model", SimpleNamespace(make_research_model=make)
    )
    return module, run, b, payload, seen


def test_export_decodes_verified_best_and_keeps_relative_lineage(monkeypatch, tmp_path):
    import json

    module, run, b, _, seen = export_ports(monkeypatch, tmp_path)
    out = tmp_path / "out"
    receipt = module.export_selected_weights(run, out, expected_binding=b)
    assert seen == ["latest", "best", "decode", "strict", "write"]
    assert receipt["weights"]["path"] == "model.safetensors"
    assert receipt["weights"]["metadata"]["checkpoint_role"] == "best"
    assert receipt["selected_receipt"]["step"] == 2
    assert receipt["latest_receipt"]["step"] == 4
    assert receipt["export_provenance"]["export_source_commit"] == "e" * 40
    assert receipt["export_provenance"]["training_source_commit"] == "a" * 40
    assert receipt["inference_publication_approved"] is False
    assert json.loads((out / "selection.json").read_text()) == receipt
    with pytest.raises(ValueError, match="fresh"):
        module.export_selected_weights(run, out, expected_binding=b)
    assert seen.count("write") == 1


@pytest.mark.parametrize(
    "change",
    [
        "payload-binding",
        "payload-progress",
        "payload-fields",
        "run-binding",
        "state-race",
        "history-race",
        "run-race",
        "checkpoint-symlink",
    ],
)
def test_export_rejects_changed_or_ambiguous_source_without_writing(
    monkeypatch, tmp_path, change
):
    module, run, b, payload, seen = export_ports(monkeypatch, tmp_path)
    if change == "payload-binding":
        payload["binding"]["cache_sha256"] = "e" * 64
    elif change == "payload-progress":
        payload["progress"]["step"] = 4
    elif change == "payload-fields":
        payload["unknown"] = True
    elif change == "run-binding":
        (run / "run.json").write_text("{}")
    elif change == "checkpoint-symlink":
        (run / "checkpoints").rename(run / "other")
        (run / "checkpoints").symlink_to(run / "other", target_is_directory=True)
    else:
        import sys
        from types import SimpleNamespace

        original = sys.modules["torch"].load

        def racing(*args, **kwargs):
            value = original(*args, **kwargs)
            path = {
                "state-race": run / "checkpoints/opaque-state",
                "history-race": run / "events.jsonl",
                "run-race": run / "run.json",
            }[change]
            path.write_text("{}")
            return value

        monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(load=racing))
    with pytest.raises(ValueError):
        module.export_selected_weights(run, tmp_path / "out", expected_binding=b)
    assert "write" not in seen and not (tmp_path / "out").exists()


def test_export_records_source_and_requires_clean_immutable_checkout(monkeypatch):
    import training.research_selection as module

    answers = iter(["e" * 40 + "\n", ""])
    monkeypatch.setattr(
        module.subprocess, "check_output", lambda *a, **k: next(answers)
    )
    assert module.source_commit() == "e" * 40
    for commit, dirty in [
        ("e" * 40, " M training/research_selection.py\n"),
        ("main", ""),
    ]:
        answers = iter([commit, dirty])
        with pytest.raises(ValueError, match="clean immutable"):
            module.source_commit()


def test_export_source_change_during_decode_never_writes(monkeypatch, tmp_path):
    module, run, binding, _, seen = export_ports(monkeypatch, tmp_path)
    answers = iter(["e" * 40, "f" * 40])
    monkeypatch.setattr(module, "source_commit", lambda: next(answers))
    with pytest.raises(ValueError, match="source changed"):
        module.export_selected_weights(run, tmp_path / "out", expected_binding=binding)
    assert "write" not in seen and not (tmp_path / "out").exists()
