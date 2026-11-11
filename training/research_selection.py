"""Export the first minimum-val M checkpoint for evaluation and conversion.

Metadata review is pure. Reading model tensors and writing weights require
external Linux. The selection receipt is lineage, not inference publication
approval, independent evaluation, or a claim of improved playing strength.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from export.research_contract import architecture_config
from training.checkpoint import SCHEMA as CHECKPOINT_SCHEMA
from training.checkpoint import _progress, atomic_json, checkpoint_receipt
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.research_visit_fit import (
    VisitRunConfig,
    validate_binding,
    validate_history,
)
from training.research_weights import SCHEMA, validate_metadata, write_research_weights


def review_selection(binding, latest, best, events):
    """Require a completed schedule and reproduce strict-< val selection.

    Equal minima retain the earlier checkpoint, exactly as the fitter does.
    No test set, development match result or final holdout chooses the weights.
    """
    try:
        validate_binding(binding)
        config = VisitRunConfig.from_value(binding["config"])
        if config.architecture != architecture_config(config.architecture.architecture):
            raise ValueError("selection requires the fixed M profile")
        for receipt in (latest, best):
            _progress(receipt["progress"])
            if (
                receipt["schema"] != CHECKPOINT_SCHEMA
                or receipt["verified"] is not True
                or receipt["binding"] != binding
                or type(receipt["step"]) is not int
                or receipt["step"] != receipt["progress"]["step"]
            ):
                raise ValueError("selection checkpoint receipt differs")
        if latest["step"] != config.total_updates:
            raise ValueError("selection requires a completed training schedule")
        validate_history(events, binding["config"], latest["progress"])
        validations = [event for event in events if event["event"] == "val"]
        selected = min(validations, key=lambda event: event["loss"])
        if best["step"] != selected["step"] or any(
            receipt["progress"]["best_val_loss"] != selected["loss"]
            for receipt in (latest, best)
        ):
            raise ValueError("checkpoint is not the first minimum-val selection")
        for receipt in (latest, best):
            examples = sum(
                len(event["ids"])
                for event in events
                if event["event"] == "train" and event["step"] <= receipt["step"]
            )
            if receipt["progress"]["examples"] != examples:
                raise ValueError("selection checkpoint example count differs")
        return validate_metadata(
            {
                "schema": SCHEMA,
                "architecture": binding["config"]["architecture"],
                "seed": config.seed,
                "source_commit": binding["source_commit"],
                "training_binding_sha256": fingerprint(binding),
                "checkpoint_role": "best",
                "step": best["step"],
            }
        )
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("incomplete research selection metadata") from error


def source_commit():
    root = Path(__file__).resolve().parents[1]
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=root, text=True
    ).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or dirty:
        raise ValueError("selection export requires a clean immutable checkout")
    return commit


def export_selected_weights(run, output, *, expected_binding):
    if sys.platform != "linux":
        raise ValueError("research selection requires external Linux")
    export_source = source_commit()
    run, output = Path(run), Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("selection requires a fresh output directory")
    if run.is_symlink() or not run.is_dir():
        raise ValueError("selection requires a regular run directory")
    if (run / "checkpoints").is_symlink():
        raise ValueError("selection checkpoint directory must not be a symlink")
    run_path, history_path = run / "run.json", run / "events.jsonl"
    for path in (run_path, history_path):
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > 64 * 1024**2
        ):
            raise ValueError("selection run metadata must be bounded regular files")
    recorded = json.loads(run_path.read_text())
    if recorded != {
        "schema": "voxelshogi-training-run-v1",
        "binding": expected_binding,
    }:
        raise ValueError("selection run binding differs")
    # These ports verify pointer/receipt/state bytes before any tensor decoding.
    _, latest = checkpoint_receipt(run / "checkpoints", binding=expected_binding)
    state_path, best = checkpoint_receipt(
        run / "checkpoints", binding=expected_binding, which="best"
    )
    events = [json.loads(line) for line in history_path.read_text().splitlines()]
    metadata = review_selection(expected_binding, latest, best, events)
    import torch

    from export.research_contract import ResearchConfig
    from export.research_model import make_research_model

    payload = torch.load(state_path, map_location="cpu", weights_only=True)
    if (
        type(payload) is not dict
        or set(payload) != {"model", "optimizer", "rng", "progress", "binding"}
        or payload["binding"] != expected_binding
        or payload["progress"] != best["progress"]
    ):
        raise ValueError("selected payload binding/progress differs from receipt")
    model = make_research_model(
        ResearchConfig(**metadata["architecture"]), seed=metadata["seed"]
    )
    model.load_state_dict(payload["model"], strict=True)
    # Recheck source bytes after decoding; never certify changed input/history.
    if file_hash(state_path) != best["sha256"]:
        raise ValueError("selected checkpoint changed during export")
    if [json.loads(line) for line in history_path.read_text().splitlines()] != events:
        raise ValueError("selection history changed during export")
    if json.loads(run_path.read_text()) != recorded:
        raise ValueError("selection run binding changed during export")
    if source_commit() != export_source:
        raise ValueError("selection export source changed during decoding")
    output.mkdir(parents=True, exist_ok=False)
    weights = write_research_weights(
        payload["model"], output / "model.safetensors", metadata=metadata
    )
    receipt = {
        "schema": "voxelshogi-research-selection-v1",
        "binding": expected_binding,
        "export_provenance": {
            "schema": "voxelshogi-export-lineage-v1",
            "export_source_commit": export_source,
            "training_source_commit": expected_binding["source_commit"],
        },
        "latest_receipt": latest,
        "selected_receipt": best,
        "history_sha256": file_hash(history_path),
        "weights": {**weights, "path": "model.safetensors"},
        "inference_publication_approved": False,
    }
    atomic_json(output / "selection.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--binding", type=Path, required=True)
    args = parser.parse_args()
    export_selected_weights(
        args.run, args.output, expected_binding=json.loads(args.binding.read_text())
    )


if __name__ == "__main__":
    main()
