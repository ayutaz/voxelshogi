"""Opaque ONNX files and handwritten cohorts; no models/search/native execution."""

import hashlib
import json
from copy import deepcopy

import pytest

from training.evaluation_v2 import fingerprint, summarize_matches
from training.tests.test_evaluation_v2 import rows
from training.tests.test_research_manifest_assembly import arguments, raw


def setup(tmp_path, monkeypatch, fault=None):
    from training import research_final_evaluation as module

    monkeypatch.setattr(module.sys, "platform", "linux")
    conversion, payloads, options = arguments(tmp_path)
    converted = json.loads(conversion)
    folder = tmp_path / "converted"
    folder.mkdir()
    for variant in converted["model"]["variants"]:
        body = ("opaque-" + variant["precision"]).encode()
        (folder / variant["model"]["path"]).write_bytes(body)
        variant["model"].update(
            bytes=len(body), sha256=hashlib.sha256(body).hexdigest()
        )
    conversion = raw(converted)
    (folder / "conversion.json").write_bytes(conversion)
    for name in ("selection.json", "training-history.jsonl"):
        (folder / name).write_bytes(payloads[name])
    frozen_path = tmp_path / "frozen.json"
    frozen_path.write_bytes(payloads["final-protocol.json"])
    development_path = tmp_path / "development-sources.json"
    development_path.write_bytes(raw({"opaque": "frozen development source inventory"}))
    references = {
        "physical": {"development/prior": {"9" * 64}},
        "model_input": {"development/prior": {"8" * 64}},
        "receipt": {
            "schema": "voxelshogi-development-references-v1",
            "verified": True,
            "plan_sha256": fingerprint(json.loads(development_path.read_bytes())),
            "sources": {
                "development/prior": {
                    "games": 48,
                    "queries": 24579,
                    "positions": 1,
                    "inputs": 1,
                    "positions_sha256": fingerprint(["9" * 64]),
                    "inputs_sha256": fingerprint(["8" * 64]),
                }
            },
        },
    }
    output = tmp_path / "final"
    calls, saved = [], {}

    def verify_conversion(path, value):
        assert path == folder and value == converted
        calls.append("conversion")
        if fault == "changed-conversion" and calls.count("conversion") == 2:
            raise ValueError("changed graph")

    def roots(value):
        assert value == json.loads(payloads["final-protocol.json"])
        calls.append("roots")

    def run(protocol, artifacts, target, *, stop_requested, observe_input):
        precision = target.name
        assert artifacts == {"model": folder / (precision + ".onnx")}
        assert protocol["participants"]["model"]["backend"] == "ort-cpu"
        assert (
            protocol["participants"]["model"]["artifact_sha256"]
            == hashlib.sha256(artifacts["model"].read_bytes()).hexdigest()
        )
        assert len(protocol["cases"]) == 12 and not stop_requested()
        calls.append(precision)
        target.mkdir()
        matches = rows(protocol, (("win", "loss"),) * 12)
        for match in matches:
            match["model_sha256"] = protocol["participants"]["model"]["artifact_sha256"]
            match["opponent_sha256"] = protocol["participants"]["opponent"][
                "artifact_sha256"
            ]
            (target / f"{match['case_id']}-{match['model_side']}.json").write_bytes(
                raw(match)
            )
        (target / "run.json").write_bytes(raw({"opaque": precision}))
        if fault != "no-queries" or precision != "int8":
            for _ in range(2):
                observe_input("model", precision)
        summary = summarize_matches(
            matches,
            protocol,
            model_sha256=protocol["participants"]["model"]["artifact_sha256"],
            opponent_sha256=protocol["participants"]["opponent"]["artifact_sha256"],
        )
        saved[precision] = deepcopy(summary)
        if fault == "changed-replay" and precision == "int8":
            saved[precision]["overall"]["games"] = 23
        return summary

    def audit(
        folders,
        corpus,
        selfplay,
        *,
        expected_protocol,
        protection,
        observed_inputs,
        reference_sources,
    ):
        assert set(folders) == {"fp32", "fp16", "int8"}
        assert (corpus, selfplay, protection) == (
            "all-m4",
            "all-selfplay",
            "legacy-protection",
        )
        assert expected_protocol == {"fixed": "selfplay"}
        calls.append("audit")
        assert reference_sources == references
        result = {
            "schema": "voxelshogi-generation-input-audit-v1",
            "passed": fault != "overlap",
            "runs": {},
            "observed_input_counts": {},
            "development_references": deepcopy(references["receipt"]),
        }
        for precision in ("fp32", "fp16", "int8"):
            spec = module.final_protocol(
                json.loads(payloads["final-protocol.json"]),
                model_sha256=hashlib.sha256(
                    (folder / (precision + ".onnx")).read_bytes()
                ).hexdigest(),
                evaluation_source=options["source_commit"],
            )
            result["runs"][precision] = {
                "games": 24,
                "run_sha256": hashlib.sha256(
                    (folders[precision] / "run.json").read_bytes()
                ).hexdigest(),
                "protocol_sha256": fingerprint(spec),
            }
            key = f"neural-query/{precision}/model"
            result["observed_input_counts"][key] = {
                k: len(v) for k, v in observed_inputs[key].items()
            }
        if fault == "audit-binding":
            result["runs"]["int8"]["run_sha256"] = "0" * 64
        elif fault == "audit-queries":
            result["observed_input_counts"]["neural-query/int8/model"]["inputs"] = 2
        elif fault == "changed-frozen":
            frozen_path.write_bytes(b"changed frozen protocol")
        elif fault == "audit-development":
            result.pop("development_references")
        elif fault == "changed-development-plan":
            development_path.write_bytes(b'{"changed":"plan"}\n')
        return result

    def query(role, game):
        assert role == "model" and game in ("fp32", "fp16", "int8")
        return {
            "role": role,
            "physical_id": "1" * 64,
            "input_id": "2" * 64,
            "record": {"opaque": game},
        }

    source_reads = []

    def source():
        source_reads.append(True)
        return (
            "e" * 40
            if fault == "changed-source" and len(source_reads) > 1
            else options["source_commit"]
        )

    ports = {
        "source": source,
        "conversion": verify_conversion,
        "roots": roots,
        "corpus": lambda value: calls.append("corpus"),
        "query": query,
        "run": run,
        "verify": lambda path: saved[path.name],
        "audit": audit,
    }

    def development(root, plan, **limits):
        assert root == tmp_path and plan == {
            "opaque": "frozen development source inventory"
        }
        assert limits["deadline"] == 200 and not limits["stop_requested"]()
        calls.append("development")
        result = deepcopy(references)
        if fault == "changed-development" and calls.count("development") == 2:
            result["receipt"]["plan_sha256"] = "0" * 64
        return result

    ports["development"] = development
    kwargs = {
        "conversion_sha256": hashlib.sha256(conversion).hexdigest(),
        "frozen_sha256": options["final_protocol_sha256"],
        "expected_source": options["source_commit"],
        "development_sources": development_path,
        "development_sources_sha256": hashlib.sha256(
            development_path.read_bytes()
        ).hexdigest(),
        "corpus": "all-m4",
        "selfplay": "all-selfplay",
        "selfplay_protocol": {"fixed": "selfplay"},
        "protection": "legacy-protection",
        "deadline": 200,
        "clock": lambda: 100,
        "ports": ports,
    }
    return module, folder, frozen_path, output, kwargs, calls


def test_final_runner_evaluates_the_three_actual_formats_and_closes_manifest(
    tmp_path, monkeypatch
):
    module, folder, frozen, output, kwargs, calls = setup(tmp_path, monkeypatch)
    result = module.run_final_formats(folder, frozen, output, **kwargs)
    assert result["games"] == 72 and result["queries"] == 6
    assert (
        result["complete"] is True and result["inference_publication_approved"] is False
    )
    assert calls == [
        "conversion",
        "roots",
        "corpus",
        "development",
        "fp32",
        "fp16",
        "int8",
        "audit",
        "conversion",
        "development",
    ]
    assert not (output / "manifest.json").exists()
    assembled = json.loads((output / "assembled-manifest.json").read_text())
    assert [v["evaluation"]["gameCount"] for v in assembled["variants"]] == [24, 24, 24]
    assert len((output / "queries.jsonl").read_text().splitlines()) == 6
    for precision in ("fp32", "fp16", "int8"):
        report = json.loads((output / "evaluation" / (precision + ".json")).read_text())
        assert len(report["games"]) == 24 and report["actual_neural_queries"] == 2
        assert (
            report["model_sha256"]
            == hashlib.sha256((folder / (precision + ".onnx")).read_bytes()).hexdigest()
        )


@pytest.mark.parametrize(
    "fault",
    [
        "no-queries",
        "changed-replay",
        "overlap",
        "audit-binding",
        "audit-queries",
        "changed-conversion",
        "graph-hash",
        "changed-source",
        "changed-frozen",
        "changed-development",
        "audit-development",
        "changed-development-plan",
    ],
)
def test_incomplete_or_changed_evidence_never_emits_success(
    tmp_path, monkeypatch, fault
):
    module, folder, frozen, output, kwargs, _ = setup(tmp_path, monkeypatch, fault)
    if fault == "graph-hash":
        path = folder / "int8.onnx"
        original = path.read_bytes()
        path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    with pytest.raises(ValueError):
        module.run_final_formats(folder, frozen, output, **kwargs)
    assert (output / "failure.json").is_file()
    assert not (output / "complete.json").exists()
    assert not (output / "assembled-manifest.json").exists()


@pytest.mark.parametrize(
    "change",
    [
        "conversion-hash",
        "frozen-hash",
        "expired",
        "source",
        "platform",
        "existing-output",
        "model-path",
        "development-hash",
    ],
)
def test_preflight_rejects_unfrozen_or_unowned_execution(tmp_path, monkeypatch, change):
    module, folder, frozen, output, kwargs, calls = setup(tmp_path, monkeypatch)
    error = ValueError
    if change == "conversion-hash":
        kwargs["conversion_sha256"] = "0" * 64
    elif change == "frozen-hash":
        kwargs["frozen_sha256"] = "0" * 64
    elif change == "development-hash":
        kwargs["development_sources_sha256"] = "0" * 64
    elif change == "expired":
        kwargs["deadline"] = 99
        error = InterruptedError
    elif change == "source":
        kwargs["expected_source"] = "e" * 40
    elif change == "platform":
        monkeypatch.setattr(module.sys, "platform", "darwin")
    elif change == "model-path":
        path = folder / "conversion.json"
        value = json.loads(path.read_bytes())
        value["model"]["variants"][0]["model"]["path"] = "../outside.onnx"
        body = raw(value)
        path.write_bytes(body)
        kwargs["conversion_sha256"] = hashlib.sha256(body).hexdigest()
    else:
        output.mkdir()
    with pytest.raises(error):
        module.run_final_formats(folder, frozen, output, **kwargs)
    assert not any(c in calls for c in ("fp32", "fp16", "int8"))


def test_deadline_during_an_actual_query_preserves_failure_without_success(
    tmp_path, monkeypatch
):
    module, folder, frozen, output, kwargs, _ = setup(tmp_path, monkeypatch)
    ticks = iter((100, 100, 100, 201))
    kwargs["clock"] = lambda: next(ticks)
    with pytest.raises(InterruptedError):
        module.run_final_formats(folder, frozen, output, **kwargs)
    failure = json.loads((output / "failure.json").read_text())
    assert failure["stage"] == "evaluation-fp32" and failure["queries"] == 0
    assert failure["error_type"] == "InterruptedError"
    assert not (output / "complete.json").exists()


@pytest.mark.parametrize("changed", [False, True])
def test_default_root_port_replays_each_frozen_identity(tmp_path, monkeypatch, changed):
    import sys
    from types import SimpleNamespace

    from training import evaluation_v2_runner, research_data
    from training import research_final_evaluation as module

    monkeypatch.setattr(module.sys, "platform", "linux")
    played = []

    class Game:
        @classmethod
        def from_record(cls, record):
            value = cls()
            value.value = record
            played.append(record["initial"])
            return value

        def record(self):
            return self.value

        def snapshot(self):
            return {"finished": False, "vsfen": self.value["initial"]}

    monkeypatch.setitem(sys.modules, "voxelshogi", SimpleNamespace(Game=Game))
    positions = {"one": "1" * 64, "two": "2" * 64}
    inputs = {"one": "3" * 64, "two": "4" * 64}
    monkeypatch.setattr(
        evaluation_v2_runner, "position_identity", lambda value: positions[value]
    )
    monkeypatch.setattr(
        research_data, "input_identity", lambda value: inputs[value["vsfen"]]
    )
    frozen = {
        "protocol": {
            "cases": [
                {"id": name, "opening": {"initial": name}} for name in ("one", "two")
            ]
        },
        "roots": {
            name: {
                "purpose": "holdout",
                "position": positions[name],
                "input": inputs[name],
            }
            for name in ("one", "two")
        },
    }
    if changed:
        frozen["roots"]["two"]["input"] = "0" * 64
        with pytest.raises(ValueError, match="actual Rust history"):
            module.verify_roots(frozen)
    else:
        module.verify_roots(frozen)
    assert played == ["one", "two"]
