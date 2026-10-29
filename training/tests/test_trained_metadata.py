"""Opaque export metadata fixtures, no game generation, weights, or training."""

import json

import pytest


def fixture(folder, *, source_commit="a" * 40, weights_writer=None):
    from training.feature_cache import canonical, file_hash
    from training.fit import RunConfig
    from training.supervision import evaluation_protocol, label_contract

    folder.mkdir()
    if weights_writer is None:
        (folder / "student.safetensors").write_bytes(
            b"opaque fixture, not real weights"
        )
    else:
        weights_writer(folder / "student.safetensors")
    weights = {
        "path": "student.safetensors",
        "bytes": (folder / "student.safetensors").stat().st_size,
        "sha256": file_hash(folder / "student.safetensors"),
    }
    binding = {
        "source_commit": source_commit,
        "cache_sha256": "b" * 64,
        "contract": label_contract(),
        "config": RunConfig().value(),
    }
    progress = {
        "epoch": 1,
        "next_batch": 0,
        "step": 30000,
        "examples": 30000,
        "best_val_loss": 1.0,
    }
    receipt = {
        "binding": binding,
        "progress": progress,
        "sha256": "c" * 64,
        "verified": True,
    }
    info = {
        "model_id": "voxelshogi-transformer-s-m6-314159-v1",
        "artifact_sha256": weights["sha256"],
        "trained": True,
        "precision": "fp32",
        "backend": "torch-cuda",
    }
    origin = {
        "checkpoint_sha256": "c" * 64,
        "source_commit": source_commit,
        "cache_sha256": "b" * 64,
        "selection_split": "val",
        "selected_progress": progress,
        "binding": binding,
        "receipt": receipt,
    }
    value = {
        "schema": "voxelshogi-final-evaluation-v1",
        "source_commit": source_commit,
        "cache_sha256": "b" * 64,
        "contract": label_contract(),
        "model": info,
        "lineage": {"weights": weights, "lineage": origin},
        "counts": {
            "eligible_teachers": 36894,
            "teacher_splits": {"train": 30000, "val": 3000, "test": 3894},
        },
    }
    (folder / "input.json").write_text(canonical(value))
    test = {
        "input_sha256": file_hash(folder / "input.json"),
        "split": "test",
        "metrics": {
            "examples": 3894,
            "policy_loss": 2.0,
            "value_mse": 0.1,
            "loss": 2.1,
            "value_mae": 0.2,
            "policy_top1": 0.25,
            "policy_top5": 0.5,
            "raw_legal_rate": 0.0,
            "masked_legal_rate": 1.0,
        },
    }
    (folder / "test.json").write_text(canonical(test))
    (folder / "test-receipt.json").write_text(
        canonical({"sha256": file_hash(folder / "test.json")})
    )
    protocol = evaluation_protocol()
    games, files = [], []
    matches = folder / "matches"
    matches.mkdir()
    for opponent, seeds in protocol["opening_seeds"].items():
        for seed in seeds:
            for side in ("b", "w"):
                name = f"{opponent}-{seed}-{side}.json"
                row = {
                    "seed": seed,
                    "opponent": opponent,
                    "model_side": side,
                    "opening_moves": ["opaque"] * 8,
                    "outcome": "cutoff",
                    "plies": 256,
                    "record": {
                        "initial": "opaque",
                        "moves": ["opaque"] * 256,
                        "result": {"Draw": {"reason": "MaxPlies"}},
                        "termination": "MaxPlies",
                    },
                }
                (matches / name).write_text(canonical(row))
                files.append(
                    {
                        "file": name,
                        "bytes": (matches / name).stat().st_size,
                        "sha256": file_hash(matches / name),
                    }
                )
                games.append(row)
    report = {
        **value,
        "complete": True,
        "test": test,
        "matches": {
            "complete": True,
            "production_profile": True,
            "model": info,
            "source_commit": source_commit,
            "protocol": protocol,
            "files": files,
        },
    }
    (folder / "evaluation.json").write_text(canonical(report))
    return folder


def test_export_review_binds_complete_test_games_selected_epoch_and_identical_weight_bytes(
    tmp_path,
):
    from export.trained import review_evaluation

    folder = fixture(tmp_path / "evaluated")
    result = review_evaluation(
        folder, context={"sourceCommit": "a" * 40, "sourceDirty": False}, seed=314159
    )
    assert result["model_id"] == "voxelshogi-transformer-s-m6-314159-v1"
    assert result["training"]["receipt"]["progress"]["step"] == 30000
    assert result["training"]["evaluation_game_count"] == 60
    assert result["training"]["evaluated_weights_sha256"] == result["weights"]["sha256"]


@pytest.mark.parametrize(
    "change",
    [
        "dirty",
        "source",
        "seed",
        "incomplete",
        "weights",
        "test",
        "missing_game",
        "changed_game",
        "trained_flag",
        "lineage",
        "test_count",
        "duplicate_game",
    ],
)
def test_unreviewed_or_changed_evaluated_artifacts_are_rejected(tmp_path, change):
    from export.trained import review_evaluation

    folder = fixture(tmp_path / "evaluated")
    context, seed = {"sourceCommit": "a" * 40, "sourceDirty": False}, 314159
    if change == "dirty":
        context["sourceDirty"] = True
    elif change == "source":
        context["sourceCommit"] = "d" * 40
    elif change == "seed":
        seed = 7
    elif change == "weights":
        (folder / "student.safetensors").write_bytes(b"changed")
    elif change == "test":
        (folder / "test.json").write_text("{}")
    elif change == "missing_game":
        (folder / "matches/random-7000-b.json").unlink()
    elif change == "changed_game":
        (folder / "matches/random-7000-b.json").write_text("{}")
    else:
        path = folder / "evaluation.json"
        report = json.loads(path.read_text())
        if change == "incomplete":
            report["matches"]["complete"] = False
        elif change == "trained_flag":
            report["model"]["trained"] = False
        elif change == "lineage":
            report["lineage"]["lineage"]["selection_split"] = "test"
        elif change == "test_count":
            report["test"]["metrics"]["examples"] = 1
        elif change == "duplicate_game":
            report["matches"]["files"].append(report["matches"]["files"][0])
        path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        review_evaluation(folder, context=context, seed=seed)


def test_trained_manifest_cannot_lose_selected_provenance_or_change_weight_identity(
    tmp_path,
):
    import copy

    from export.trained import review_evaluation, validate_training_manifest

    result = review_evaluation(
        fixture(tmp_path / "evaluated"),
        context={"sourceCommit": "a" * 40, "sourceDirty": False},
        seed=314159,
    )
    manifest = {
        "trained": True,
        "seed": 314159,
        "sourceDirty": False,
        "sourceCommit": "a" * 40,
        "id": result["model_id"],
        "checkpoint": result["weights"],
        "training": result["training"],
    }
    validate_training_manifest(manifest)
    for field in ("missing", "weights", "games", "source"):
        bad = copy.deepcopy(manifest)
        if field == "missing":
            del bad["training"]
        elif field == "weights":
            bad["checkpoint"]["sha256"] = "d" * 64
        elif field == "games":
            bad["training"]["evaluation_game_count"] = 4
        else:
            bad["sourceCommit"] = "d" * 40
        with pytest.raises(ValueError):
            validate_training_manifest(bad)
