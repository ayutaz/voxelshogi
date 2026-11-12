"""Linux final24 x three actual ONNX formats, replay/query audit and assembly.

The result is evaluation evidence, not a published/staged inference package.
The owning Linux workflow supplies the verified full corpus/selfplay/protection
sources. New training sources must enter that audit before publication.
"""

import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

from export.research_generate import _bounded, _verify
from infrastructure.research.pilot.validation import _query
from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint, summarize_matches, validate_match_rows
from training.feature_cache import file_hash
from training.generation_audit import include_reference_sources
from training.research_inference_release import (
    METADATA_BYTES,
    MODEL_BYTES,
    PRECISIONS,
    _descriptor,
    final_protocol,
)
from training.research_manifest_assembly import _parse, assemble_manifest
from training.research_selection import source_commit


def verify_roots(frozen):
    """Match every preregistered root to actual Rust replay before any model."""
    if sys.platform != "linux":
        raise ValueError("final root replay requires external Linux")
    from voxelshogi import Game

    from training.evaluation_v2_runner import position_identity
    from training.research_data import input_identity

    for case in frozen["protocol"]["cases"]:
        game = Game.from_record(case["opening"])
        snapshot = game.snapshot()
        if (
            game.record() != case["opening"]
            or snapshot["finished"]
            or frozen["roots"][case["id"]]
            != {
                "purpose": "holdout",
                "position": position_identity(snapshot["vsfen"]),
                "input": input_identity(snapshot),
            }
        ):
            raise ValueError("frozen final root differs from actual Rust history")


def load_ports():
    from training.evaluation_v2_runner import run_protocol, verify_run
    from training.generation_audit import audit_generation_runs
    from training.research_development_references import collect_references
    from training.supervision import audit_corpus

    return {
        "source": source_commit,
        "conversion": _verify,
        "roots": verify_roots,
        "corpus": audit_corpus,
        "query": _query,
        "run": run_protocol,
        "verify": verify_run,
        "audit": audit_generation_runs,
        "development": collect_references,
    }


def run_final_formats(
    converted,
    frozen_path,
    output,
    *,
    conversion_sha256,
    frozen_sha256,
    expected_source,
    development_sources,
    development_sources_sha256,
    corpus,
    selfplay,
    selfplay_protocol,
    protection,
    deadline,
    clock=time.time,
    stop_requested=lambda: False,
    ports=None,
):
    if sys.platform != "linux":
        raise ValueError("final M evaluation requires external Linux")
    if (
        type(deadline) not in (int, float)
        or not math.isfinite(deadline)
        or clock() >= deadline
        or stop_requested()
    ):
        raise InterruptedError("fixed final evaluation deadline")
    ports = load_ports() if ports is None else ports
    if (
        set(ports)
        != {
            "source",
            "conversion",
            "roots",
            "corpus",
            "query",
            "run",
            "verify",
            "audit",
            "development",
        }
        or re.fullmatch(r"[0-9a-f]{40}", expected_source or "") is None
        or ports["source"]() != expected_source
    ):
        raise ValueError("complete ports and clean frozen evaluation source required")
    converted, output, frozen_path = Path(converted), Path(output), Path(frozen_path)
    if (
        converted.is_symlink()
        or not converted.is_dir()
        or output.exists()
        or output.is_symlink()
    ):
        raise ValueError("regular conversion and fresh final output required")
    conversion_raw = _bounded(converted / "conversion.json", METADATA_BYTES)
    frozen_raw = _bounded(frozen_path, METADATA_BYTES)
    development_sources = Path(development_sources)
    development_raw = _bounded(development_sources, METADATA_BYTES)
    if (
        hashlib.sha256(conversion_raw).hexdigest() != conversion_sha256
        or hashlib.sha256(frozen_raw).hexdigest() != frozen_sha256
        or hashlib.sha256(development_raw).hexdigest() != development_sources_sha256
    ):
        raise ValueError("frozen conversion/final-protocol bytes differ")
    conversion, frozen = _parse(conversion_raw), _parse(frozen_raw)
    if (
        conversion["schema"] != "voxelshogi-research-conversion-v1"
        or conversion["conversion_complete"] is not True
        or conversion["inference_publication_approved"] is not False
        or conversion["model"]["sourceCommit"] != expected_source
        or [v["precision"] for v in conversion["model"]["variants"]] != list(PRECISIONS)
    ):
        raise ValueError("complete three-format conversion from frozen source required")
    variants = {v["precision"]: v for v in conversion["model"]["variants"]}
    for precision, variant in variants.items():
        _descriptor(variant["model"], precision + ".onnx", MODEL_BYTES)
    protocols = {
        p: final_protocol(
            frozen, model_sha256=v["model"]["sha256"], evaluation_source=expected_source
        )
        for p, v in variants.items()
    }
    payloads = {
        "selection.json": _bounded(converted / "selection.json", METADATA_BYTES),
        "training-history.jsonl": _bounded(
            converted / "training-history.jsonl", 64 * 1024**2
        ),
        "final-protocol.json": frozen_raw,
    }
    ports["conversion"](converted, conversion)
    ports["roots"](frozen)
    ports["corpus"](corpus)
    development_plan = _parse(development_raw)

    def read_development():
        references = ports["development"](
            development_sources.parent,
            development_plan,
            deadline=deadline,
            clock=clock,
            stop_requested=stop_requested,
        )
        include_reference_sources({}, {}, references)
        if references["receipt"].get("plan_sha256") != fingerprint(development_plan):
            raise ValueError("replayed development inventory differs from frozen plan")
        return references

    references = read_development()
    output.mkdir(parents=True, exist_ok=False)
    (output / "evaluation").mkdir()
    stage, total_queries, groups, folders, reports = "evaluation", 0, {}, {}, {}

    def stopping():
        return stop_requested() or clock() >= deadline

    try:
        with (output / "queries.jsonl").open("x") as stream:
            for precision in PRECISIONS:
                stage = "evaluation-" + precision
                if stopping():
                    raise InterruptedError("final format evaluation interrupted")
                before = total_queries

                def observe(role, game, precision=precision):
                    nonlocal total_queries
                    if stopping():
                        raise InterruptedError("final query deadline")
                    row = ports["query"](role, game)
                    if (
                        role != "model"
                        or row["role"] != role
                        or any(
                            re.fullmatch(r"[0-9a-f]{64}", row[k]) is None
                            for k in ("physical_id", "input_id")
                        )
                    ):
                        raise ValueError("actual final neural query identity differs")
                    group = groups.setdefault(
                        f"neural-query/{precision}/model",
                        {"positions": set(), "inputs": set()},
                    )
                    group["positions"].add(row["physical_id"])
                    group["inputs"].add(row["input_id"])
                    stream.write(
                        json.dumps(
                            {"precision": precision, **row},
                            sort_keys=True,
                            allow_nan=False,
                        )
                        + "\n"
                    )
                    total_queries += 1

                spec, variant = protocols[precision], variants[precision]
                model = converted / variant["model"]["path"]
                if (
                    model.is_symlink()
                    or not model.is_file()
                    or model.stat().st_size != variant["model"]["bytes"]
                    or file_hash(model) != variant["model"]["sha256"]
                ):
                    raise ValueError("actual final ONNX bytes differ")
                folder = output / precision
                observed = ports["run"](
                    spec,
                    {"model": model},
                    folder,
                    stop_requested=stopping,
                    observe_input=observe,
                )
                if observed != ports["verify"](folder) or total_queries == before:
                    raise ValueError(
                        "replayed full cohort and actual neural queries required"
                    )
                matches = [
                    json.loads((folder / f"{case['id']}-{side}.json").read_text())
                    for case in spec["cases"]
                    for side in ("b", "w")
                ]
                if len(validate_match_rows(matches, spec)) != 24:
                    raise ValueError("complete final24 cohort required")
                report = {
                    "schema": "voxelshogi-research-format-evaluation-v1",
                    "complete": True,
                    "precision": precision,
                    "evaluation_source_commit": expected_source,
                    "model_sha256": variant["model"]["sha256"],
                    "weights_sha256": conversion["model"]["checkpoint"]["sha256"],
                    "protocol": spec,
                    "games": matches,
                    "summary": summarize_matches(
                        matches,
                        spec,
                        model_sha256=variant["model"]["sha256"],
                        opponent_sha256=spec["participants"]["opponent"][
                            "artifact_sha256"
                        ],
                    ),
                    "run_sha256": file_hash(folder / "run.json"),
                    "actual_neural_queries": total_queries - before,
                }
                reports[precision], folders[precision] = report, folder
                atomic_json(output / "evaluation" / (precision + ".json"), report)
        stage = "all-input-audit"
        if stopping():
            raise InterruptedError("final audit deadline")
        audit = ports["audit"](
            folders,
            corpus,
            selfplay,
            expected_protocol=selfplay_protocol,
            protection=protection,
            observed_inputs=groups,
            reference_sources=references,
        )
        atomic_json(output / "input-audit.json", audit)
        if audit.get("development_references") != references["receipt"] or audit.get(
            "observed_input_counts"
        ) != {
            name: {k: len(ids) for k, ids in group.items()}
            for name, group in groups.items()
        }:
            raise ValueError("audited final neural query inventory differs")
        stage = "final-input-recheck"
        ports["conversion"](converted, conversion)
        if (
            read_development() != references
            or _bounded(development_sources, METADATA_BYTES) != development_raw
        ):
            raise ValueError(
                "development reference sources changed during final evaluation"
            )
        if (
            ports["source"]() != expected_source
            or _bounded(converted / "conversion.json", METADATA_BYTES) != conversion_raw
            or _bounded(frozen_path, METADATA_BYTES) != frozen_raw
        ):
            raise ValueError("source or frozen final inputs changed")
        for name in ("selection.json", "training-history.jsonl"):
            if _bounded(converted / name, 64 * 1024**2) != payloads[name]:
                raise ValueError("selected final input bytes changed")
        payloads.update(
            {
                f"evaluation/{p}.json": (
                    output / "evaluation" / (p + ".json")
                ).read_bytes()
                for p in PRECISIONS
            }
        )
        payloads["input-audit.json"] = (output / "input-audit.json").read_bytes()
        manifest = assemble_manifest(
            conversion_raw,
            payloads,
            conversion_sha256=conversion_sha256,
            final_protocol_sha256=frozen_sha256,
            source_commit=expected_source,
        )
        if stopping():
            raise InterruptedError("final completion deadline")
        atomic_json(output / "assembled-manifest.json", manifest)
        result = {
            "schema": "voxelshogi-research-final-evaluation-v1",
            "complete": True,
            "games": 72,
            "queries": total_queries,
            "source_commit": expected_source,
            "conversion_sha256": conversion_sha256,
            "frozen_sha256": frozen_sha256,
            "development_sources_sha256": development_sources_sha256,
            "development_references_sha256": fingerprint(references["receipt"]),
            "query_trace_sha256": file_hash(output / "queries.jsonl"),
            "input_audit_sha256": file_hash(output / "input-audit.json"),
            "assembled_manifest_sha256": file_hash(output / "assembled-manifest.json"),
            "inference_publication_approved": False,
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
                "completed_formats": len(reports),
                "queries": total_queries,
                "inference_publication_approved": False,
            },
        )
        raise


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("converted", type=Path)
    parser.add_argument("frozen", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--conversion-sha256", required=True)
    parser.add_argument("--frozen-sha256", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--development-sources", type=Path, required=True)
    parser.add_argument("--development-sources-sha256", required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--selfplay", type=Path, required=True)
    parser.add_argument("--selfplay-protocol", type=Path, required=True)
    parser.add_argument("--protection", type=Path, required=True)
    parser.add_argument("--deadline", type=float, required=True)
    args = parser.parse_args()
    result = run_final_formats(
        args.converted,
        args.frozen,
        args.output,
        conversion_sha256=args.conversion_sha256,
        frozen_sha256=args.frozen_sha256,
        expected_source=args.source,
        development_sources=args.development_sources,
        development_sources_sha256=args.development_sources_sha256,
        corpus=args.corpus,
        selfplay=args.selfplay,
        selfplay_protocol=_parse(_bounded(args.selfplay_protocol, METADATA_BYTES)),
        protection=args.protection,
        deadline=args.deadline,
    )
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
