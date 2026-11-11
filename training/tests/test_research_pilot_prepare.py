"""Shared feature preparation with handwritten files and fake encoder, no tensors."""

import copy
import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash


def preparation(tmp_path, monkeypatch):
    from infrastructure.research.pilot import attempt

    with patch("sys.platform", "darwin"):
        values = runpy.run_path("training/tests/pilot_ports/check-attempt.py")
    inputs, manifest = (
        copy.deepcopy(values["inputs"]),
        copy.deepcopy(values["manifest"]),
    )
    monkeypatch.chdir(tmp_path)
    paths = {name: Path(p) for name, p in inputs["paths"].items()}
    for p in paths.values():
        p.parent.mkdir(parents=True, exist_ok=True)
    paths["selfplay"].mkdir()
    (paths["selfplay"] / "manifest.json").write_text('{"opaque":"selfplay"}')
    paths["protocol"].write_text('{"opaque":"protocol"}')
    paths["protection"].write_text('{"opaque":"protection"}')
    paths["screen"].write_text('{"opaque":"screen"}')
    (paths["screen"].parent / "manifest.json").write_text('{"opaque":"screen-release"}')
    records = manifest["diagnosis_records"]
    audit, protection = (
        records["admission.json"],
        records["development-protection.json"],
    )
    audit.update(
        source_manifest_sha256=file_hash(paths["selfplay"] / "manifest.json"),
        source_protocol_sha256=fingerprint({"opaque": "protocol"}),
        source_protection_sha256=file_hash(paths["protection"]),
        screen_config_sha256=file_hash(paths["screen"]),
    )
    protection["source_release_manifest_sha256"] = file_hash(
        paths["screen"].parent / "manifest.json"
    )
    inputs.update(
        admission_sha256=fingerprint(audit),
        development_protection_sha256=fingerprint(protection),
        diagnosis_sha256=fingerprint(records["target-diagnosis.json"]),
    )
    inputs["quality_decision"].update(
        {
            k: inputs[k]
            for k in (
                "admission_sha256",
                "development_protection_sha256",
                "diagnosis_sha256",
            )
        }
    )
    paths["diagnosis_manifest"].write_text(json.dumps(manifest))
    seen = []
    corpus = SimpleNamespace(
        train=SimpleNamespace(provenance={"split": "train"}),
        val=SimpleNamespace(provenance={"split": "val"}),
    )

    def digest(config):
        for part in (corpus.train, corpus.val):
            assert (
                part.provenance["full_development_protection_sha256"]
                == inputs["development_protection_sha256"]
            )
            assert part.provenance["teacher_decision_sha256"] == fingerprint(
                inputs["quality_decision"]
            )
        seen.append("digest")
        return "e" * 64

    corpus.digest = digest

    def encode(folder, protocol, protection_path, screen_path, **kwargs):
        assert folder == paths["selfplay"] and protocol == {"opaque": "protocol"}
        assert protection_path == paths["protection"] and screen_path == paths["screen"]
        assert kwargs == {
            "screen_sha256": audit["screen_config_sha256"],
            "expected_audit_sha256": inputs["admission_sha256"],
            "maximum_feature_bytes": 2 * 1024**3,
        }
        seen.append("encode")
        return corpus, {"feature_content_sha256": "old-unprotected-hash"}

    monkeypatch.setattr(attempt.sys, "platform", "linux")
    monkeypatch.setattr(
        attempt.subprocess,
        "check_output",
        lambda args, **kwargs: "a" * 40 if args[1] == "rev-parse" else "",
    )
    monkeypatch.setattr("training.research_visit_data.encode_corpus", encode)
    return attempt, inputs, corpus, seen, paths


def test_fitting_and_diagnostics_share_protected_teacher_data_binding(
    monkeypatch, tmp_path
):
    module, inputs, corpus, seen, _ = preparation(tmp_path, monkeypatch)
    config, decision, actual, record = module.prepare_corpus(inputs)
    assert actual is corpus and config.device == "cuda"
    assert seen == ["encode", "digest"]
    assert decision == fingerprint(inputs["quality_decision"])
    assert record["feature_content_sha256"] == "e" * 64
    assert record["teacher_decision_sha256"] == decision


@pytest.mark.parametrize(
    "mode", ["wrong-source", "dirty", "changed-source", "early-stop", "late-stop"]
)
def test_shared_preparation_refuses_bad_sources_and_fixed_stop(
    monkeypatch, tmp_path, mode
):
    module, inputs, _, seen, paths = preparation(tmp_path, monkeypatch)
    if mode == "wrong-source":
        monkeypatch.setattr(
            module.subprocess,
            "check_output",
            lambda a, **k: "b" * 40 if a[1] == "rev-parse" else "",
        )
    elif mode == "dirty":
        monkeypatch.setattr(
            module.subprocess,
            "check_output",
            lambda a, **k: "a" * 40 if a[1] == "rev-parse" else " M source",
        )
    elif mode == "changed-source":
        paths["protection"].write_text("changed after diagnosis")
    with pytest.raises((ValueError, InterruptedError)):
        module.prepare_corpus(
            inputs,
            stop_requested=lambda: (
                mode == "early-stop" or mode == "late-stop" and "encode" in seen
            ),
        )
    if mode != "late-stop":
        assert "encode" not in seen


def test_shared_preparation_refuses_Mac_before_any_encoder(monkeypatch):
    from infrastructure.research.pilot import attempt

    monkeypatch.setattr(attempt.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="external Linux"):
        attempt.prepare_corpus({})


def test_fit_wrapper_uses_the_same_protected_preparation(monkeypatch, tmp_path):
    module, inputs, corpus, seen, _ = preparation(tmp_path, monkeypatch)
    for key in ("HF_TOKEN", "VAST_API_KEY", "CLOUDRIFT_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(module.signal, "signal", lambda *args: None)
    monkeypatch.setattr(module.time, "time", lambda: 100)
    ticks = iter([10.0, 12.0, 14.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))

    def fit(data, output, **kwargs):
        assert data is corpus and kwargs["config"].device == "cuda"
        assert kwargs["source_commit"] == "a" * 40
        assert kwargs["resume"] is False and kwargs["max_new_steps"] is None
        assert kwargs["stop_requested"]() is False
        seen.append("fit")
        Path(output).mkdir()
        return {"reason": "complete", "opaque": "not actual model training"}

    monkeypatch.setattr("training.research_visit_fit.fit_visits", fit)
    result = module.run(inputs, tmp_path / "fit", deadline=200)
    assert seen == ["encode", "digest", "fit"]
    assert result["encoding"]["feature_content_sha256"] == "e" * 64
    assert result["preparation_seconds"] == result["fitting_call_seconds"] == 2.0
    assert result["whole_attempt_seconds"] == 4.0
