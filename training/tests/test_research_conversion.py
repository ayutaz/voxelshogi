"""Complete selected histories and opaque converter ports; no model execution."""

import json
from copy import deepcopy

import pytest

from training.feature_cache import file_hash
from training.tests.test_research_selection import records
from training.tests.test_research_weights import header


def inputs(tmp_path):
    from training.evaluation_v2 import fingerprint

    folder = tmp_path / "selected"
    folder.mkdir()
    binding, latest, best, events, metadata = records()
    metadata["training_binding_sha256"] = fingerprint(binding)
    weights = header(folder / "model.safetensors", metadata)
    history = tmp_path / "events.jsonl"
    history.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events)
    )
    selection = {
        "schema": "voxelshogi-research-selection-v1",
        "binding": binding,
        "export_provenance": {
            "schema": "voxelshogi-export-lineage-v1",
            "training_source_commit": "a" * 40,
            "export_source_commit": "e" * 40,
        },
        "latest_receipt": latest,
        "selected_receipt": best,
        "history_sha256": file_hash(history),
        "weights": {
            "path": "model.safetensors",
            "bytes": weights.stat().st_size,
            "sha256": file_hash(weights),
            "metadata": metadata,
        },
        "inference_publication_approved": False,
    }
    (folder / "selection.json").write_text(json.dumps(selection))
    return folder, history, selection


def test_conversion_review_reproduces_the_first_val_minimum_and_preserves_distinct_sources(
    tmp_path,
):
    from export.research_generate import review_inputs

    folder, history, selection = inputs(tmp_path)
    result = review_inputs(selection, history.read_bytes())
    assert result["metadata"]["step"] == 2
    assert result["metadata"]["architecture"]["architecture"] == "full"
    assert result["metadata"]["source_commit"] == "a" * 40
    assert result["selection_export_source"] == "e" * 40
    assert result["total_updates"] == 4
    assert result["weights_sha256"] == file_hash(folder / "model.safetensors")


@pytest.mark.parametrize(
    "change",
    [
        "history",
        "selection",
        "partial",
        "tie",
        "metadata",
        "path",
        "weight-hash",
        "boolean",
        "source",
        "export-source",
        "approval",
        "cpu",
    ],
)
def test_conversion_rejects_unselected_or_unbound_input_metadata(tmp_path, change):
    from export.research_generate import review_inputs

    _, history, selection = inputs(tmp_path)
    raw = history.read_bytes()
    if change == "history":
        raw = raw.replace(b'"loss": 2.0', b'"loss": 3.0', 1)
    elif change == "selection":
        selection["schema"] = "unknown"
    elif change == "partial":
        selection["latest_receipt"]["step"] = 3
    elif change == "tie":
        selection["selected_receipt"] = deepcopy(selection["latest_receipt"])
    elif change == "metadata":
        selection["weights"]["metadata"]["step"] = 4
    elif change == "path":
        selection["weights"]["path"] = "../other.safetensors"
    elif change == "weight-hash":
        selection["weights"]["sha256"] = "bad"
    elif change == "boolean":
        selection["weights"]["bytes"] = True
    elif change == "source":
        selection["export_provenance"]["training_source_commit"] = "e" * 40
    elif change == "export-source":
        selection["export_provenance"]["export_source_commit"] = "main"
    elif change == "approval":
        selection["inference_publication_approved"] = True
    else:
        from training.evaluation_v2 import fingerprint

        selection["binding"]["config"]["device"] = "cpu"
        selection["binding"]["environment"]["device"] = "cpu"
        for key in ("latest_receipt", "selected_receipt"):
            selection[key]["binding"] = deepcopy(selection["binding"])
        selection["weights"]["metadata"]["training_binding_sha256"] = fingerprint(
            selection["binding"]
        )
    with pytest.raises(ValueError):
        review_inputs(selection, raw)


def ports(calls):
    def source():
        calls.append("source")
        return "f" * 40

    def load(path, expected_sha256):
        from training.research_weights import research_metadata

        calls.append("load")
        assert file_hash(path) == expected_sha256
        return "opaque fake network", research_metadata(path)

    def fixtures(output):
        calls.append("fixtures")
        return [{"name": "opaque-fixture-not-a-real-model-test"}]

    def variant(precision, output, *args):
        calls.append(precision)
        path = output / (precision + ".onnx")
        path.write_bytes(b"opaque fake ONNX " + precision.encode())
        return {
            "id": precision,
            "precision": precision,
            "model": {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": file_hash(path),
            },
            "references": {},
        }

    def verify(output, value):
        calls.append("verify")
        assert [v["id"] for v in value["model"]["variants"]] == ["fp32", "fp16", "int8"]

    return {
        "source": source,
        "load": load,
        "fixtures": fixtures,
        "fp32": lambda network, output, fixtures, binding: variant("fp32", output),
        "variant": variant,
        "verify": verify,
    }


def test_Linux_worker_converts_same_selected_weights_to_all_formats_without_claiming_evaluation(
    monkeypatch, tmp_path
):
    import export.research_generate as module

    monkeypatch.setattr(module.sys, "platform", "linux")
    folder, history, selection = inputs(tmp_path)
    calls, output = [], tmp_path / "conversion"
    result = module.generate(
        folder,
        history,
        output,
        selection_sha256=file_hash(folder / "selection.json"),
        expected_source="f" * 40,
        deadline=200,
        clock=lambda: 100,
        ports=ports(calls),
    )
    assert calls == [
        "source",
        "load",
        "fixtures",
        "fp32",
        "fp16",
        "int8",
        "verify",
        "source",
    ]
    assert (
        result["conversion_complete"] is True
        and result["inference_publication_approved"] is False
    )
    assert result["schema"] == "voxelshogi-research-conversion-v1"
    assert result["model"]["checkpoint"]["sha256"] == selection["weights"]["sha256"]
    assert result["model"]["sourceCommit"] == "f" * 40
    assert result["model"]["research"]["trainingSourceCommit"] == "a" * 40
    assert result["model"]["research"]["selectedUpdate"] == 2
    assert (output / "training-history.jsonl").read_bytes() == history.read_bytes()
    assert (output / "model.safetensors").read_bytes() == (
        folder / "model.safetensors"
    ).read_bytes()
    assert not (output / "manifest.json").exists()
    assert not (output / "failure.json").exists()


@pytest.mark.parametrize(
    "change",
    [
        "Mac",
        "source",
        "deadline",
        "selection-hash",
        "weights",
        "metadata",
        "existing",
        "mid-conversion",
        "changed-source",
        "verification",
    ],
)
def test_conversion_refuses_invalid_input_and_preserves_partial_failure(
    monkeypatch, tmp_path, change
):
    import export.research_generate as module

    monkeypatch.setattr(
        module.sys, "platform", "darwin" if change == "Mac" else "linux"
    )
    folder, history, selection = inputs(tmp_path)
    output, calls = tmp_path / "conversion", []
    dependencies = ports(calls)
    expected = file_hash(folder / "selection.json")
    deadline = 99 if change == "deadline" else 200
    if change == "source":
        dependencies["source"] = lambda: "e" * 40
    elif change == "selection-hash":
        expected = "b" * 64
    elif change == "weights":
        with (folder / "model.safetensors").open("ab") as stream:
            stream.write(b"corrupt")
    elif change == "metadata":
        different = deepcopy(selection["weights"]["metadata"])
        different["seed"] += 1
        dependencies["load"] = lambda *args: ("fake", different)
    elif change == "existing":
        output.mkdir()
        (output / "do-not-overwrite").write_text("existing")
    elif change == "mid-conversion":
        dependencies["variant"] = lambda *args: (_ for _ in ()).throw(
            InterruptedError("fake bounded stop")
        )
    elif change == "changed-source":
        remaining = iter(["f" * 40, "e" * 40])
        dependencies["source"] = lambda: next(remaining)
    elif change == "verification":
        dependencies["verify"] = lambda *args: (_ for _ in ()).throw(
            ValueError("fake changed output body")
        )
    with pytest.raises((ValueError, FileExistsError, InterruptedError)):
        module.generate(
            folder,
            history,
            output,
            selection_sha256=expected,
            expected_source="f" * 40,
            deadline=deadline,
            clock=lambda: 100,
            ports=dependencies,
        )
    if change in ("Mac", "deadline", "source"):
        assert calls == []
    if change in ("mid-conversion", "changed-source", "verification"):
        assert json.loads((output / "failure.json").read_text())["complete"] is False
        assert not (output / "conversion.json").exists()
    if change == "existing":
        assert (output / "do-not-overwrite").read_text() == "existing"


def test_conversion_stops_between_formats_and_rechecks_original_history_after_verification(
    monkeypatch, tmp_path
):
    import export.research_generate as module

    monkeypatch.setattr(module.sys, "platform", "linux")
    folder, history, _ = inputs(tmp_path)
    calls, ticks = [], [0]

    def clock():
        ticks[0] += 1
        return 100 if ticks[0] < 5 else 201

    output = tmp_path / "deadline"
    with pytest.raises(InterruptedError):
        module.generate(
            folder,
            history,
            output,
            selection_sha256=file_hash(folder / "selection.json"),
            expected_source="f" * 40,
            deadline=200,
            clock=clock,
            ports=ports(calls),
        )
    assert calls == ["source", "load", "fixtures", "fp32"]
    assert json.loads((output / "failure.json").read_text())["stage"] == "fp16"
    dependencies = ports([])

    def changed_history(*args):
        history.write_bytes(
            history.read_bytes().replace(b'"loss": 2.0', b'"loss": 3.0', 1)
        )

    dependencies["verify"] = changed_history
    output = tmp_path / "history-changed"
    with pytest.raises(ValueError, match="source/input bytes changed"):
        module.generate(
            folder,
            history,
            output,
            selection_sha256=file_hash(folder / "selection.json"),
            expected_source="f" * 40,
            deadline=200,
            clock=lambda: 100,
            ports=dependencies,
        )
    assert not (output / "conversion.json").exists()
