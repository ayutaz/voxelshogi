"""Independent val-origin arithmetic and opaque fixed-root metadata, no models."""

from copy import deepcopy

import pytest

from training.evaluation_v2 import fingerprint


def screen():
    from training.research_screen import screen_definitions
    from training.tests.test_evaluation_v2 import protocol

    spec = protocol()
    spec["search_limits"] = {"max_depth": 3, "max_nodes": 20000, "table_capacity": 4096}
    definitions = screen_definitions("development")
    cases = []
    for definition in definitions:
        case = deepcopy(definition["case"])
        case["opening"] = {
            "ruleset_id": "voxelshogi-standard-v1",
            "initial": "opaque-" + case["id"],
            "moves": [],
            "result": None,
            "termination": None,
        }
        cases.append(case)
    spec["cases"] = cases
    families = {d["case"]["id"]: d["family"] for d in definitions}
    return {"protocol": spec, "families": families}


def test_development_reuses_all_12_frozen_roots_and_limits_without_holdout():
    from infrastructure.research.pilot.validation import development_protocol

    frozen = screen()
    original = deepcopy(frozen)
    p = development_protocol(
        frozen,
        expected_sha256=fingerprint(frozen),
        source_commit="e" * 40,
        weights_sha256="f" * 64,
    )
    assert p["cases"] == original["protocol"]["cases"]
    assert p["search_limits"] == {
        "max_depth": 3,
        "max_nodes": 20000,
        "table_capacity": 4096,
    }
    assert p["source_commit"] == "e" * 40 and p["purpose"] == "development"
    assert p["participants"]["model"] == {
        "backend": "torch-cuda",
        "policy": "legal-argmax-v1",
        "artifact_sha256": "f" * 64,
    }
    assert frozen == original
    assert len(p["cases"]) * 2 == 24
    assert not any(c["seed"] >= 65000 for c in p["cases"])


@pytest.mark.parametrize(
    "change",
    [
        "hash",
        "holdout",
        "cases",
        "root",
        "seed",
        "limit",
        "search",
        "family",
        "source",
        "weight",
    ],
)
def test_development_refuses_changed_conditions(change):
    from infrastructure.research.pilot.validation import development_protocol

    value = screen()
    expected = fingerprint(value)
    source, weight = "e" * 40, "f" * 64
    if change == "hash":
        expected = "0" * 64
    elif change == "holdout":
        value["protocol"]["purpose"] = "holdout"
    elif change == "cases":
        value["protocol"]["cases"].pop()
    elif change == "root":
        value["protocol"]["cases"][0]["id"] = "final-seed-65000"
    elif change == "seed":
        value["protocol"]["cases"][0]["seed"] = 65000
    elif change == "limit":
        value["protocol"]["cases"][0]["max_additional_plies"] += 1
    elif change == "search":
        value["protocol"]["search_limits"]["max_nodes"] = 100
    elif change == "family":
        value["families"]["dev-mate-black-6"] = "made-up-independent-family"
    elif change == "source":
        source = "main"
    elif change == "weight":
        weight = "f" * 63
    if change not in ("hash", "source", "weight"):
        expected = fingerprint(value)  # Hash alone must not approve another workload.
    with pytest.raises(ValueError):
        development_protocol(
            value, expected_sha256=expected, source_commit=source, weights_sha256=weight
        )


def val_data():
    from training.selfplay_training import Samples

    kinds = ["terminal-v1", "bootstrap-v1", "terminal-v1"]
    return Samples(
        ["f0", "f1", "f2"],
        [{"id": str(i), "value": {"kind": kind}} for i, kind in enumerate(kinds)],
        {"split": "val", "admission_sha256": "a" * 64},
    )


def test_origins_are_evaluated_separately_and_weighted_by_actual_rows(monkeypatch):
    from infrastructure.research.pilot import validation as module

    monkeypatch.setattr(module.sys, "platform", "linux")
    data = val_data()
    seen = []

    def evaluate(model, part, config):
        assert model == "selected-best" and config == "frozen-config"
        seen.append([r["id"] for r in part.rows])
        assert part.provenance["split"] == "val" and len(part.rows) == len(
            part.features
        )
        if part.kinds == ["terminal-v1", "terminal-v1"]:
            assert part.features == ["f0", "f2"]
            return {
                "policy_ce": 3.0,
                "value_mse": 1.0,
                "loss": 4.0,
                "examples": 2,
                "value_origins": {"terminal-v1": 2},
            }
        assert part.kinds == ["bootstrap-v1"] and part.features == ["f1"]
        return {
            "policy_ce": 6.0,
            "value_mse": 4.0,
            "loss": 10.0,
            "examples": 1,
            "value_origins": {"bootstrap-v1": 1},
        }

    result = module.origin_metrics(
        "selected-best", data, "frozen-config", evaluate=evaluate
    )
    assert seen == [["0", "2"], ["1"]]
    assert result["aggregate"] == {
        "policy_ce": 4.0,
        "value_mse": 2.0,
        "loss": 6.0,
        "examples": 3,
    }
    assert result["by_origin"]["terminal-v1"]["examples"] == 2
    assert result["by_origin"]["bootstrap-v1"]["examples"] == 1
    assert result["bootstrap_is_observed_outcome"] is False
    assert data.features == ["f0", "f1", "f2"]


@pytest.mark.parametrize(
    "mode",
    [
        "train",
        "test",
        "empty",
        "count",
        "unknown",
        "duplicate",
        "stop",
        "bad-metrics",
        "bad-count",
        "bad-origins",
        "nonfinite",
        "invalid-loss",
    ],
)
def test_origin_metrics_refuse_unreviewed_split_or_false_counts(monkeypatch, mode):
    from infrastructure.research.pilot import validation as module

    monkeypatch.setattr(module.sys, "platform", "linux")
    data = val_data()
    if mode in ("train", "test"):
        data.provenance["split"] = mode
    elif mode == "empty":
        data.rows.clear()
        data.features.clear()
    elif mode == "count":
        data.features.pop()
    elif mode == "unknown":
        data.rows[0]["value"]["kind"] = "draw-from-cutoff"
    elif mode == "duplicate":
        data.rows[1]["id"] = "0"

    def evaluate(*args):
        if mode not in (
            "bad-metrics",
            "bad-count",
            "bad-origins",
            "nonfinite",
            "invalid-loss",
        ):
            pytest.fail("invalid inputs must fail before evaluation")
        part = args[1]
        result = {
            "policy_ce": 1.0,
            "value_mse": 0.5,
            "loss": 1.5,
            "examples": len(part.rows),
            "value_origins": {part.kinds[0]: len(part.rows)},
        }
        if mode in ("bad-metrics", "bad-count"):
            result["examples"] = 999
        if mode in ("bad-metrics", "bad-origins"):
            result["value_origins"] = {"terminal-v1": 999}
        if mode == "nonfinite":
            result.update(policy_ce=float("inf"), loss=float("inf"))
        if mode == "invalid-loss":
            result["loss"] = 100.0
        return result

    with pytest.raises((ValueError, InterruptedError)):
        module.origin_metrics(
            None, data, None, evaluate=evaluate, stop_requested=lambda: mode == "stop"
        )


def test_origin_metrics_reject_Mac_before_numerical_evaluation(monkeypatch):
    from infrastructure.research.pilot import validation as module

    monkeypatch.setattr(module.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="external Linux"):
        module.origin_metrics(None, None, None)


def pair_ports(tmp_path, mode="complete"):
    import json

    from training.tests.test_evaluation_v2 import rows

    frozen = screen()
    calls = []

    def selection(folder, expected, source):
        name = folder.name
        calls.append(("selection", name))
        return {
            "path": str(folder / "model.safetensors"),
            "sha256": (
                "c"
                if mode == "changed-selection" and calls.count(("selection", name)) == 2
                else "a"
                if name == "full"
                else "b"
            )
            * 64,
            "seed": 67004 if mode == "different-seed" and name == "geometry" else 67003,
            "source_commit": "a" * 40,
            "export_source_commit": "e" * 40,
            "architecture": name,
            "common_training_sha256": (
                "8" if mode == "different-training" and name == "geometry" else "9"
            )
            * 64,
        }

    def corpus(folder):
        calls.append(("corpus", str(folder)))

    def replay(role, game):
        assert role == "model" and game == "opaque-Rust-query-port"
        calls.append(("query", role))
        return {
            "role": role,
            "physical_id": "c" * 64,
            "input_id": "d" * 64,
            "record": {"opaque": "replayed by real port"},
        }

    def run(protocol, artifacts, folder, **kwargs):
        calls.append(("run", folder.name))
        assert artifacts == {"model": str(tmp_path / folder.name / "model.safetensors")}
        assert callable(kwargs["stop_requested"])
        if mode == "failure" and folder.name == "geometry":
            raise InterruptedError("retained partial execution")
        if mode != "missing-queries" and not (
            mode == "missing-candidate-queries" and folder.name == "geometry"
        ):
            kwargs["observe_input"]("model", "opaque-Rust-query-port")
        folder.mkdir()
        (folder / "protocol.json").write_text(json.dumps(protocol))
        scores = (
            [("win", "win")] * 4 + [("loss", "loss")] * 4 + [("cutoff", "cutoff")] * 4
            if mode == "family"
            else [("win", "cutoff")] * 12
        )
        values = rows(protocol, scores)
        for row in values:
            row["model_sha256"] = protocol["participants"]["model"]["artifact_sha256"]
            row["opponent_sha256"] = protocol["participants"]["opponent"][
                "artifact_sha256"
            ]
        if mode == "partial":
            values.pop()
        for row in values:
            (folder / f"{row['case_id']}-{row['model_side']}.json").write_text(
                json.dumps(row)
            )
        result = {
            "overall": {"games": len(values)},
            "protocol_sha256": fingerprint(protocol),
        }
        (folder / "run.json").write_text(json.dumps(result))
        return result

    def verify(folder):
        calls.append(("verify", folder.name))
        return json.loads((folder / "run.json").read_text())

    def audit(folders, corpus, selfplay, **kwargs):
        calls.append(("audit", sorted(folders)))
        assert sorted(folders) == ["full", "geometry"]
        inventories = kwargs["observed_inputs"]
        assert set(inventories) == (
            {"neural-query/full/model"}
            if mode == "missing-candidate-queries"
            else {
                "neural-query/full/model",
                "neural-query/geometry/model",
            }
        )
        assert all(
            g == {"positions": {"c" * 64}, "inputs": {"d" * 64}}
            for g in inventories.values()
        )
        return {
            "schema": "voxelshogi-generation-input-audit-v1",
            "passed": mode != "overlap",
            "observed_input_counts": {
                n: {k: 0 if mode == "audit-queries" else len(v) for k, v in g.items()}
                for n, g in inventories.items()
            },
            "runs": {
                name: {
                    "games": 24,
                    "protocol_sha256": "0" * 64
                    if mode == "audit-protocol"
                    else json.loads((folder / "run.json").read_text())[
                        "protocol_sha256"
                    ],
                    "run_sha256": __import__("hashlib")
                    .sha256((folder / "run.json").read_bytes())
                    .hexdigest(),
                }
                for name, folder in folders.items()
            },
        }

    return (
        {
            "selection": selection,
            "corpus": corpus,
            "query": replay,
            "run": run,
            "verify": verify,
            "audit": audit,
        },
        calls,
        frozen,
    )


@pytest.mark.parametrize(
    "mode",
    [
        "complete",
        "partial",
        "failure",
        "missing-queries",
        "overlap",
        "deadline",
        "duplicate",
        "family",
        "different-training",
        "different-seed",
        "changed-selection",
        "missing-candidate-queries",
        "audit-protocol",
        "audit-queries",
    ],
)
def test_pair_runs_exact_48_and_audits_actual_queries_before_completion(
    monkeypatch, tmp_path, mode
):
    import json

    from infrastructure.research.pilot import validation as module

    monkeypatch.setattr(module.sys, "platform", "linux")
    ports, calls, frozen = pair_ports(tmp_path, mode)
    selected = {
        name: {"folder": tmp_path / name, "selection_sha256": "e" * 64}
        for name in ("full", "geometry")
    }
    out = tmp_path / "development"
    if mode == "duplicate":
        out.mkdir()
    args = dict(
        expected_sha256=fingerprint(frozen),
        source_commit="f" * 40,
        corpus=tmp_path / "M4",
        selfplay=tmp_path / "selfplay",
        selfplay_protocol={"fixed": "source"},
        protection=tmp_path / "protection",
        deadline=200,
        clock=lambda: 201 if mode == "deadline" else 100,
        ports=ports,
    )
    if mode not in ("complete", "family"):
        with pytest.raises((ValueError, InterruptedError)):
            module.run_development_pair(frozen, selected, out, **args)
        assert not (out / "complete.json").exists()
        if mode not in ("deadline", "duplicate"):
            assert (out / "failure.json").exists()
        return
    result = module.run_development_pair(frozen, selected, out, **args)
    assert result["games"] == 48 and result["leakage_free"] is True
    assert result["final_holdout_evaluated"] is False
    assert result["source_commit"] == "f" * 40
    assert result["selected_weights"]["full"]["source_commit"] == "a" * 40
    assert result["selected_weights"]["full"]["export_source_commit"] == "e" * 40
    assert result["queries"] == 2
    assert calls.index(("corpus", str(tmp_path / "M4"))) < calls.index(("run", "full"))
    assert (
        calls.count(("selection", "full"))
        == calls.count(("selection", "geometry"))
        == 2
    )
    assert ("verify", "full") in calls and ("verify", "geometry") in calls
    assert calls[-1] == ("selection", "geometry")
    assert result["by_architecture"]["full"]["family_score_bounds"] == pytest.approx(
        [1 / 6, 5 / 6] if mode == "family" else [0.5, 1.0]
    )
    assert json.loads((out / "complete.json").read_text()) == result
    assert len((out / "queries.jsonl").read_text().splitlines()) == 2


def selected_package(tmp_path):
    import json

    from training.feature_cache import file_hash
    from training.tests.test_research_selection import records
    from training.tests.test_research_weights import header

    binding, latest, best, _, metadata = records()
    metadata["training_binding_sha256"] = fingerprint(binding)
    folder = tmp_path / "full"
    folder.mkdir()
    path = header(folder / "model.safetensors", metadata)
    receipt = {
        "schema": "voxelshogi-research-selection-v1",
        "binding": binding,
        "export_provenance": {
            "schema": "voxelshogi-export-lineage-v1",
            "export_source_commit": "a" * 40,
            "training_source_commit": "a" * 40,
        },
        "weights": {
            "path": "model.safetensors",
            "bytes": path.stat().st_size,
            "sha256": file_hash(path),
            "metadata": metadata,
        },
        "latest_receipt": latest,
        "selected_receipt": best,
    }
    (folder / "selection.json").write_text(json.dumps(receipt))
    return folder, receipt


def test_real_metadata_port_binds_selected_weight_bytes_and_common_training(tmp_path):
    from infrastructure.research.pilot.validation import _selected
    from training.feature_cache import file_hash

    folder, receipt = selected_package(tmp_path)
    result = _selected(folder, file_hash(folder / "selection.json"), "a" * 40)
    assert result["sha256"] == receipt["weights"]["sha256"]
    assert result["architecture"] == "full" and result["seed"] == 67003
    assert result["common_training_sha256"] == fingerprint(
        {
            **receipt["binding"],
            "config": {
                k: v
                for k, v in receipt["binding"]["config"].items()
                if k != "architecture"
            },
        }
    )


@pytest.mark.parametrize(
    "change",
    ["bytes", "metadata", "latest", "best", "binding", "lineage", "best-progress"],
)
def test_selection_metadata_port_refuses_wrong_bytes_schedule_and_lineage(
    tmp_path, change
):
    import json

    from infrastructure.research.pilot.validation import _selected
    from training.feature_cache import file_hash

    folder, receipt = selected_package(tmp_path)
    if change == "bytes":
        (folder / "model.safetensors").write_bytes(b"wrong bytes")
    elif change == "metadata":
        receipt["weights"]["metadata"]["step"] = 4
    elif change == "latest":
        receipt["latest_receipt"]["step"] = 3
    elif change == "best":
        receipt["selected_receipt"]["step"] = 4
    elif change == "binding":
        receipt["binding"]["cache_sha256"] = "e" * 64
    elif change == "lineage":
        receipt["export_provenance"]["training_source_commit"] = "e" * 40
    elif change == "best-progress":
        receipt["selected_receipt"]["progress"]["step"] = 4
    (folder / "selection.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        _selected(folder, file_hash(folder / "selection.json"), "a" * 40)


def test_visit_validation_checks_stop_before_terms_and_after_inflight_batch(
    monkeypatch,
):
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace

    import training.research_visit_fit as module

    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(no_grad=nullcontext))
    model = SimpleNamespace(eval=lambda: None)
    data = SimpleNamespace(kinds=["terminal-v1"], rows=[{}])
    config = SimpleNamespace(batch_size=1)
    calls = []

    def terms(*args):
        calls.append("terms")
        return {
            name: SimpleNamespace(item=lambda value=value: value)
            for name, value in (("policy", 0.75), ("value", 0.25), ("total", 1.0))
        }

    monkeypatch.setattr(module, "_terms", terms)
    with pytest.raises(InterruptedError):
        module.evaluate_visits(model, data, config, stop_requested=lambda: True)
    assert not calls
    ticks = iter([False, True])
    with pytest.raises(InterruptedError):
        module.evaluate_visits(model, data, config, stop_requested=lambda: next(ticks))
    assert calls == ["terms"]


def test_absent_value_origin_is_unavailable_and_not_zero_accuracy(monkeypatch):
    from infrastructure.research.pilot import validation as module

    monkeypatch.setattr(module.sys, "platform", "linux")
    data = val_data()
    data.rows = [data.rows[1]]
    data.features = [data.features[1]]

    def evaluate(*args):
        return {
            "policy_ce": 2.0,
            "value_mse": 1.0,
            "loss": 3.0,
            "examples": 1,
            "value_origins": {"bootstrap-v1": 1},
        }

    result = module.origin_metrics(None, data, None, evaluate=evaluate)
    assert result["by_origin"]["terminal-v1"] == {"available": False, "examples": 0}
    assert result["aggregate"]["loss"] == 3.0


def test_selected_training_and_export_lineage_can_precede_evaluation_source(tmp_path):
    from infrastructure.research.pilot.validation import _selected
    from training.feature_cache import file_hash

    folder, _ = selected_package(tmp_path)
    selected = _selected(folder, file_hash(folder / "selection.json"), "e" * 40)
    assert selected["source_commit"] == "a" * 40
    assert selected["export_source_commit"] == "a" * 40


def test_query_and_development_refuse_Mac_before_any_native_port(monkeypatch, tmp_path):
    import sys

    from infrastructure.research.pilot import validation as module

    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "voxelshogi", None)
    with pytest.raises(ValueError, match="external Linux"):
        module._query("model", None)
    with pytest.raises(ValueError, match="external Linux"):
        module.run_development_pair(
            None,
            None,
            tmp_path / "out",
            expected_sha256=None,
            source_commit=None,
            corpus=None,
            selfplay=None,
            selfplay_protocol=None,
            protection=None,
            deadline=0,
        )
