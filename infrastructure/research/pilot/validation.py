"""Fixed development protocols and separate val-origin diagnostics for M pilots.

Never use the final holdout to select weights or alter a pilot. Real metric
execution is external Linux only. These helpers do not authorize publication,
retirement, general-strength claims, or completion of the two-pilot experiment.
"""

import math
import re
import sys
from copy import deepcopy

from training.evaluation_v2 import fingerprint, validate_protocol
from training.evaluation_v2_runner import rust_policy_identity
from training.generation_cases import SEARCH_LIMITS
from training.research_screen import screen_definitions


def development_protocol(frozen, *, expected_sha256, source_commit, weights_sha256):
    """Rebind only participants/source in a hash-frozen development slice."""
    try:
        if (
            fingerprint(frozen) != expected_sha256
            or not isinstance(source_commit, str)
            or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
            or not isinstance(weights_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", weights_sha256) is None
        ):
            raise ValueError("fixed development/source/weights binding differs")
        protocol = deepcopy(frozen["protocol"])
        validate_protocol(protocol)
        definitions = screen_definitions("development")
        if (
            protocol["purpose"] != "development"
            or protocol["search_limits"] != SEARCH_LIMITS
            or len(protocol["cases"]) != 12
            or frozen["families"] != {d["case"]["id"]: d["family"] for d in definitions}
        ):
            raise ValueError("fixed development cases/families/limits differ")
        for case, definition in zip(protocol["cases"], definitions, strict=True):
            if {k: v for k, v in case.items() if k != "opening"} != {
                k: v for k, v in definition["case"].items() if k != "opening"
            }:
                raise ValueError("fixed development case identity differs")
        protocol["source_commit"] = source_commit
        protocol["participants"] = {
            "model": {
                "backend": "torch-cuda",
                "policy": "legal-argmax-v1",
                "artifact_sha256": weights_sha256,
            },
            "opponent": {
                "backend": "rust",
                "policy": "alphabeta-v1",
                "artifact_sha256": rust_policy_identity(
                    "alphabeta-v1", source_commit, SEARCH_LIMITS
                ),
            },
        }
        validate_protocol(protocol)
        return protocol
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("incomplete development slice") from error


def origin_metrics(model, data, config, *, evaluate=None, stop_requested=lambda: False):
    if sys.platform != "linux":
        raise ValueError("origin validation requires external Linux")
    from training.selfplay_training import Samples

    if (
        type(data) is not Samples
        or data.provenance.get("split") != "val"
        or not data.rows
        or len(data.rows) != len(data.features)
        or len({r["id"] for r in data.rows}) != len(data.rows)
        or any(k not in ("terminal-v1", "bootstrap-v1") for k in data.kinds)
    ):
        raise ValueError("nonempty admitted val samples and distinct IDs required")
    if evaluate is None:
        from training.research_visit_fit import evaluate_visits

        def evaluate(model, part, config):
            return evaluate_visits(model, part, config, stop_requested=stop_requested)

    totals = {"policy_ce": 0.0, "value_mse": 0.0, "loss": 0.0}
    parts = {}
    for kind in ("terminal-v1", "bootstrap-v1"):
        if stop_requested():
            raise InterruptedError("origin validation interrupted")
        indices = [i for i, value in enumerate(data.kinds) if value == kind]
        if not indices:
            parts[kind] = {"available": False, "examples": 0}
            continue
        part = Samples(
            [data.features[i] for i in indices],
            [data.rows[i] for i in indices],
            {**data.provenance, "diagnostic_value_origin": kind},
        )
        metrics = evaluate(model, part, config)
        if stop_requested():
            raise InterruptedError("origin validation interrupted")
        if (
            set(metrics)
            != {"policy_ce", "value_mse", "loss", "examples", "value_origins"}
            or type(metrics["examples"]) is not int
            or metrics["examples"] != len(indices)
            or metrics["value_origins"] != {kind: len(indices)}
            or any(
                type(metrics[k]) not in (int, float)
                or not math.isfinite(metrics[k])
                or metrics[k] < 0
                for k in totals
            )
            or not math.isclose(
                metrics["loss"],
                metrics["policy_ce"] + metrics["value_mse"],
                rel_tol=1e-6,
                abs_tol=1e-7,
            )
        ):
            raise ValueError("origin diagnostic metric/count differs")
        parts[kind] = {"available": True, **metrics}
        for name in totals:
            totals[name] += metrics[name] * len(indices)
    return {
        "schema": "voxelshogi-research-val-origins-v1",
        "split": "val",
        "aggregate": {
            **{k: v / len(data.rows) for k, v in totals.items()},
            "examples": len(data.rows),
        },
        "by_origin": parts,
        "bootstrap_is_observed_outcome": False,
        "scope": "Same selected weights, separate terminal/bootstrap CE and MSE; row-weighted aggregate, no test/holdout, no claim of game-outcome accuracy from bootstrap targets.",
    }


def _selected(folder, expected_sha256, source_commit):
    import json
    from pathlib import Path

    from training.checkpoint import _progress
    from training.feature_cache import file_hash
    from training.research_visit_fit import VisitRunConfig, validate_binding
    from training.research_weights import research_metadata

    if (
        not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
    ):
        raise ValueError("immutable evaluation source required")
    folder = Path(folder)
    path = folder / "selection.json"
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > 1024**2
        or file_hash(path) != expected_sha256
    ):
        raise ValueError("fixed selection receipt differs")
    receipt = json.loads(path.read_text())
    binding = receipt["binding"]
    validate_binding(binding)
    config = VisitRunConfig.from_value(binding["config"])
    for item in (receipt["latest_receipt"], receipt["selected_receipt"]):
        _progress(item["progress"])
        if type(item["step"]) is not int or item["step"] != item["progress"]["step"]:
            raise ValueError("selected receipt cursor differs")
    weights = receipt["weights"]
    model = folder / "model.safetensors"
    metadata = research_metadata(model)
    if (
        receipt["schema"] != "voxelshogi-research-selection-v1"
        or not isinstance(receipt["export_provenance"]["export_source_commit"], str)
        or re.fullmatch(
            r"[0-9a-f]{40}", receipt["export_provenance"]["export_source_commit"]
        )
        is None
        or receipt["export_provenance"]["schema"] != "voxelshogi-export-lineage-v1"
        or receipt["export_provenance"]["training_source_commit"]
        != binding["source_commit"]
        or config.device != "cuda"
        or weights["path"] != "model.safetensors"
        or type(weights["bytes"]) is not int
        or not 0 < weights["bytes"] <= 192 * 1024**2
        or model.stat().st_size != weights["bytes"]
        or file_hash(model) != weights["sha256"]
        or metadata != weights["metadata"]
        or metadata["checkpoint_role"] != "best"
        or metadata["source_commit"] != binding["source_commit"]
        or metadata["training_binding_sha256"] != fingerprint(binding)
        or metadata["architecture"] != binding["config"]["architecture"]
        or metadata["seed"] != config.seed
        or receipt["latest_receipt"]["step"] != config.total_updates
        or receipt["selected_receipt"]["step"] != metadata["step"]
        or any(
            r["verified"] is not True or r["binding"] != binding
            for r in (receipt["latest_receipt"], receipt["selected_receipt"])
        )
    ):
        raise ValueError("best weights and frozen M selection differ")
    return {
        "path": str(model),
        "sha256": weights["sha256"],
        "seed": config.seed,
        "source_commit": binding["source_commit"],
        "export_source_commit": receipt["export_provenance"]["export_source_commit"],
        "architecture": config.architecture.architecture,
        "common_training_sha256": fingerprint(
            {
                **binding,
                "config": {
                    k: v for k, v in binding["config"].items() if k != "architecture"
                },
            }
        ),
    }


def _query(role, game):
    if sys.platform != "linux":
        raise ValueError("query replay requires external Linux")
    from voxelshogi import Game

    from training.evaluation_v2_runner import position_identity
    from training.research_data import input_identity

    record, snapshot = game.record(), game.snapshot()
    replayed = Game.from_record(record)
    if replayed.record() != record or replayed.snapshot() != snapshot:
        raise ValueError("actual neural query history differs from Rust replay")
    return {
        "role": role,
        "physical_id": position_identity(snapshot["vsfen"]),
        "input_id": input_identity(snapshot),
        "record": record,
    }


def load_validation_ports():
    from training.evaluation_v2_runner import run_protocol, verify_run
    from training.generation_audit import audit_generation_runs
    from training.supervision import audit_corpus

    return {
        "selection": _selected,
        "corpus": audit_corpus,
        "query": _query,
        "run": run_protocol,
        "verify": verify_run,
        "audit": audit_generation_runs,
    }


def run_development_pair(
    frozen,
    selected,
    output,
    *,
    expected_sha256,
    source_commit,
    corpus,
    selfplay,
    selfplay_protocol,
    protection,
    deadline,
    clock=None,
    stop_requested=lambda: False,
    ports=None,
):
    """Run Full/Geometry x12 fixed roots x2 colors, replay queries and audit.

    Full M4 bytes are mandatory for the final whole-input audit in addition to
    the four learning bundles. The controller must obtain those directly on
    Linux from the fixed production release; never relay them through Mac.
    """
    if sys.platform != "linux":
        raise ValueError("development evaluation requires external Linux")
    import json
    import time
    from pathlib import Path

    from training.checkpoint import atomic_json
    from training.evaluation_v2 import _counts, summarize_matches, validate_match_rows
    from training.feature_cache import file_hash

    clock = time.time if clock is None else clock
    if (
        type(deadline) not in (int, float)
        or not math.isfinite(deadline)
        or clock() >= deadline
        or stop_requested()
    ):
        raise InterruptedError("fixed development deadline")
    if type(selected) is not dict or set(selected) != {"full", "geometry"}:
        raise ValueError("exact Full/Geometry pilot selections required")
    ports = load_validation_ports() if ports is None else ports
    if set(ports) != {"selection", "corpus", "query", "run", "verify", "audit"}:
        raise ValueError("complete development execution ports required")
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("fresh development output required")
    output.mkdir(parents=True, exist_ok=False)

    def stopping():
        return stop_requested() or clock() >= deadline

    stage, queries, inventories, folders, results, identities = (
        "selection",
        0,
        {},
        {},
        {},
        {},
    )
    try:
        for name in ("full", "geometry"):
            item = selected[name]
            identities[name] = ports["selection"](
                item["folder"], item["selection_sha256"], source_commit
            )
            if (
                identities[name]["architecture"] != name
                or not isinstance(identities[name]["source_commit"], str)
                or re.fullmatch(r"[0-9a-f]{40}", identities[name]["source_commit"])
                is None
            ):
                raise ValueError("pilot structure/source differs")
        if (
            identities["full"]["common_training_sha256"]
            != identities["geometry"]["common_training_sha256"]
        ):
            raise ValueError("pilot common training/data binding differs")
        if identities["full"]["seed"] != identities["geometry"]["seed"]:
            raise ValueError("pilot seeds differ")
        protocols = {
            name: development_protocol(
                frozen,
                expected_sha256=expected_sha256,
                source_commit=source_commit,
                weights_sha256=item["sha256"],
            )
            for name, item in identities.items()
        }
        if stopping():
            raise InterruptedError("development preparation deadline")
        stage = "production-corpus-verification"
        ports["corpus"](corpus)
        trace = output / "queries.jsonl"
        with trace.open("x") as stream:
            for name, protocol in protocols.items():
                stage = "development-" + name
                if stopping():
                    raise InterruptedError("development interrupted")
                count_before = queries

                def observe(role, game, name=name):
                    nonlocal queries
                    if stopping():
                        raise InterruptedError("neural query deadline")
                    row = ports["query"](role, game)
                    if (
                        role != "model"
                        or row["role"] != role
                        or any(
                            re.fullmatch(r"[0-9a-f]{64}", row[k]) is None
                            for k in ("physical_id", "input_id")
                        )
                    ):
                        raise ValueError("actual model query identity differs")
                    key = "neural-query/" + name + "/" + role
                    group = inventories.setdefault(
                        key, {"positions": set(), "inputs": set()}
                    )
                    group["positions"].add(row["physical_id"])
                    group["inputs"].add(row["input_id"])
                    stream.write(
                        json.dumps(
                            {"architecture": name, **row},
                            sort_keys=True,
                            allow_nan=False,
                        )
                        + "\n"
                    )
                    queries += 1

                folder = output / name
                result = ports["run"](
                    protocol,
                    {"model": identities[name]["path"]},
                    folder,
                    stop_requested=stopping,
                    observe_input=observe,
                )
                if (
                    result != ports["verify"](folder)
                    or result["protocol_sha256"] != fingerprint(protocol)
                    or result["overall"]["games"] != 24
                    or queries == count_before
                ):
                    raise ValueError(
                        "complete replayed24 games and actual NN queries required"
                    )
                rows = [
                    json.loads((folder / f"{case['id']}-{side}.json").read_text())
                    for case in protocol["cases"]
                    for side in ("b", "w")
                ]
                validated = validate_match_rows(rows, protocol)
                # Recompute summary from the exact cohort instead of accepting a count.
                summary = summarize_matches(
                    rows,
                    protocol,
                    model_sha256=identities[name]["sha256"],
                    opponent_sha256=protocol["participants"]["opponent"][
                        "artifact_sha256"
                    ],
                )
                families = frozen["families"]
                stats = {
                    family: _counts(
                        [
                            row
                            for row in validated.values()
                            if families[row["case_id"]] == family
                        ]
                    )
                    for family in sorted(set(families.values()))
                }
                results[name] = {
                    "summary": summary,
                    "families": stats,
                    "family_score_bounds": [
                        sum(s["score_bounds"][i] for s in stats.values()) / len(stats)
                        for i in (0, 1)
                    ],
                }
                folders[name] = folder
        if stopping():
            raise InterruptedError("development query-audit deadline")
        stage = "all-played-and-neural-input-audit"
        audit = ports["audit"](
            folders,
            corpus,
            selfplay,
            expected_protocol=selfplay_protocol,
            protection=protection,
            observed_inputs=inventories,
        )
        atomic_json(output / "input-audit.json", audit)
        if (
            audit.get("schema") != "voxelshogi-generation-input-audit-v1"
            or audit.get("passed") is not True
            or any(audit["runs"].get(name, {}).get("games") != 24 for name in folders)
        ):
            raise ValueError("full played/queried input audit failed")
        for name, folder in folders.items():
            if audit["runs"][name]["protocol_sha256"] != fingerprint(
                protocols[name]
            ) or audit["runs"][name]["run_sha256"] != file_hash(folder / "run.json"):
                raise ValueError("audited run/protocol bytes differ")
        expected_observed = {
            name: {kind: len(ids) for kind, ids in group.items()}
            for name, group in inventories.items()
        }
        if audit.get("observed_input_counts") != expected_observed:
            raise ValueError("audited neural-query inventory differs")
        for name, item in selected.items():
            if (
                ports["selection"](
                    item["folder"], item["selection_sha256"], source_commit
                )
                != identities[name]
            ):
                raise ValueError("selected weights changed during development")
        if stopping():
            raise InterruptedError("development completion deadline")
        result = {
            "schema": "voxelshogi-research-pilot-development-v1",
            "source_commit": source_commit,
            "frozen_development_sha256": expected_sha256,
            "games": 48,
            "queries": queries,
            "query_trace_sha256": file_hash(trace),
            "input_audit_sha256": file_hash(output / "input-audit.json"),
            "by_architecture": results,
            "selected_weights": identities,
            "leakage_free": True,
            "final_holdout_evaluated": False,
            "general_strength_improvement_established": False,
        }
        atomic_json(output / "complete.json", result)
        return result
    except BaseException as error:
        atomic_json(
            output / "failure.json",
            {
                "complete": False,
                "stage": stage,
                "error_type": type(error).__name__,
                "completed_cohorts": len(results),
                "queries": queries,
                "final_holdout_evaluated": False,
            },
        )
        raise
