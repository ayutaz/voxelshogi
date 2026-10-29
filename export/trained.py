"""Bind trained conversion to a reviewed val-selected evaluation and its bytes."""

import json
import re
import sys
from pathlib import Path

from training.evaluate import validate_selected
from training.feature_cache import file_hash
from training.supervision import evaluation_protocol, label_contract


def _json(path):
    if path.is_symlink():
        raise ValueError("evaluated metadata must be a regular file")
    return json.loads(path.read_text())


def _verify(path, descriptor):
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size != descriptor["bytes"]
        or file_hash(path) != descriptor["sha256"]
    ):
        raise ValueError("evaluated artifact size/hash differs")


def review_evaluation(folder, *, context, seed):
    """Pure metadata/hash boundary. Linux loader separately replays every game."""
    folder = Path(folder)
    try:
        if (
            folder.is_symlink()
            or context.get("sourceDirty") is not False
            or not re.fullmatch(r"[0-9a-f]{40}", context.get("sourceCommit", ""))
            or seed != 314159
        ):
            raise ValueError(
                "trained export requires fixed seed and clean immutable source"
            )
        inputs, report = _json(folder / "input.json"), _json(folder / "evaluation.json")
        origin = inputs["lineage"]["lineage"]
        weights = inputs["lineage"]["weights"]
        counts = inputs["counts"]["teacher_splits"]
        if (
            inputs["schema"] != "voxelshogi-final-evaluation-v1"
            or any(report.get(key) != value for key, value in inputs.items())
            or inputs["source_commit"] != context["sourceCommit"]
            or inputs["contract"] != label_contract()
            or report["complete"] is not True
            or inputs["model"]["trained"] is not True
            or inputs["model"]["precision"] != "fp32"
            or inputs["model"]["backend"] not in ("torch-cpu", "torch-cuda")
            or inputs["model"]["model_id"] != f"voxelshogi-transformer-s-m6-{seed}-v1"
            or origin["selection_split"] != "val"
            or origin["source_commit"] != context["sourceCommit"]
            or origin["cache_sha256"] != inputs["cache_sha256"]
            or origin["receipt"]["verified"] is not True
            or origin["checkpoint_sha256"] != origin["receipt"]["sha256"]
            or origin["selected_progress"] != origin["receipt"]["progress"]
            or origin["binding"]["config"]["seed"] != seed
            or weights["path"] != "student.safetensors"
            or weights["sha256"] != inputs["model"]["artifact_sha256"]
            or set(counts) != {"train", "val", "test"}
            or any(type(n) is not int or n < 1 for n in counts.values())
            or sum(counts.values()) != 36894
            or inputs["counts"]["eligible_teachers"] != 36894
        ):
            raise ValueError("incomplete/unselected or mismatched trained evaluation")
        validate_selected(
            origin["binding"],
            origin["receipt"],
            cache_sha256=inputs["cache_sha256"],
            source_commit=context["sourceCommit"],
            train_count=counts["train"],
        )
        _verify(folder / "student.safetensors", weights)
        test = _json(folder / "test.json")
        if (
            test != report["test"]
            or test["split"] != "test"
            or test["metrics"]["examples"] != counts["test"]
            or test["input_sha256"] != file_hash(folder / "input.json")
            or _json(folder / "test-receipt.json")
            != {"sha256": file_hash(folder / "test.json")}
        ):
            raise ValueError("test evaluation differs from completed audited split")
        matches = report["matches"]
        protocol = evaluation_protocol()
        names = {
            f"{opponent}-{seed}-{side}.json"
            for opponent, seeds in protocol["opening_seeds"].items()
            for seed in seeds
            for side in ("b", "w")
        }
        files = matches["files"]
        if (
            matches["complete"] is not True
            or matches["production_profile"] is not True
            or matches["protocol"] != protocol
            or matches["model"] != inputs["model"]
            or matches["source_commit"] != context["sourceCommit"]
            or len(files) != 60
            or {entry["file"] for entry in files} != names
        ):
            raise ValueError(
                "trained export requires the complete fixed 60-game cohort"
            )
        for entry in files:
            _verify(folder / "matches" / entry["file"], entry)
        training = {
            "binding": origin["binding"],
            "receipt": origin["receipt"],
            "evaluated_weights_sha256": weights["sha256"],
            "evaluation_report_sha256": file_hash(folder / "evaluation.json"),
            "test_report_sha256": file_hash(folder / "test.json"),
            "evaluation_game_count": 60,
            "teacher_splits": counts,
        }
        return {
            "model_id": inputs["model"]["model_id"],
            "weights": weights,
            "training": training,
        }
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("incomplete trained evaluation artifacts") from error


def verify_evaluation_games(folder):
    if sys.platform != "linux":
        raise ValueError("replay evaluated games only on external Linux")
    from training.evaluation import opening_record, summarize_pairs, verify_match

    folder = Path(folder)
    report = _json(folder / "evaluation.json")
    matches = report["matches"]
    protocol = evaluation_protocol()
    for opponent, seeds in protocol["opening_seeds"].items():
        rows = []
        for seed in seeds:
            opening = opening_record(seed, plies=protocol["opening_plies"])
            for side in ("b", "w"):
                row = _json(folder / "matches" / f"{opponent}-{seed}-{side}.json")
                if (
                    row["seed"] != seed
                    or row["opponent"] != opponent
                    or row["model_side"] != side
                ):
                    raise ValueError("evaluated game identity differs")
                verify_match(row, opening, max_plies=protocol["max_plies"])
                rows.append(row)
        if (
            summarize_pairs(rows, seeds=seeds, opponent=opponent)
            != matches["cohorts"][opponent]
        ):
            raise ValueError("evaluated cohort summary differs from replayed games")


def load_evaluated_weights(folder, *, context, seed):
    if sys.platform != "linux":
        raise ValueError("convert trained weights only on external Linux")
    review = review_evaluation(folder, context=context, seed=seed)
    verify_evaluation_games(folder)
    import torch
    from safetensors.torch import load_file

    state = load_file(Path(folder) / "student.safetensors", device="cpu")
    if not state or any(
        tensor.dtype != torch.float32 or not torch.isfinite(tensor).all()
        for tensor in state.values()
    ):
        raise ValueError("trained weights must be finite FP32 tensors")
    return state, review


def validate_training_manifest(manifest):
    from export.numeric import TRAINED_NUMERIC_CONTRACT

    try:
        training = manifest["training"]
        binding, receipt = training["binding"], training["receipt"]
        if (
            manifest["trained"] is not True
            or manifest.get("numericContract") != TRAINED_NUMERIC_CONTRACT
            or manifest["seed"] != 314159
            or manifest["sourceDirty"] is not False
            or manifest["id"] != "voxelshogi-transformer-s-m6-314159-v1"
            or training["evaluated_weights_sha256"] != manifest["checkpoint"]["sha256"]
            or training["evaluation_game_count"] != 60
            or receipt["verified"] is not True
            or sum(training["teacher_splits"].values()) != 36894
            or any(
                not re.fullmatch(r"[0-9a-f]{64}", training[key])
                for key in ("evaluation_report_sha256", "test_report_sha256")
            )
        ):
            raise ValueError(
                "trained manifest does not prove evaluated selected weights"
            )
        validate_selected(
            binding,
            receipt,
            cache_sha256=binding["cache_sha256"],
            source_commit=manifest["sourceCommit"],
            train_count=training["teacher_splits"]["train"],
        )
    except (KeyError, TypeError) as error:
        raise ValueError("incomplete trained conversion provenance") from error


def export_evaluated(evaluation_folder, output, *, license=None):
    """No model computation during import; called only by external Linux/CI."""
    if sys.platform != "linux":
        raise ValueError("trained conversion requires external Linux")
    from export.generate import generate

    return generate(output, selected_evaluation=evaluation_folder, license=license)
