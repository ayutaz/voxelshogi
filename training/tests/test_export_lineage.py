"""Independent source roles: conversion never relabels the trained evaluation."""

import copy

import pytest

from training.tests.test_trained_metadata import fixture


def test_explicit_training_source_preserves_old_binding_in_new_clean_export(tmp_path):
    from export.trained import review_evaluation, validate_training_manifest

    folder = fixture(tmp_path / "evaluated", source_commit="a" * 40)
    context = {
        "sourceCommit": "d" * 40,
        "sourceDirty": False,
        "trainingSourceCommit": "a" * 40,
    }
    result = review_evaluation(folder, context=context, seed=314159)
    provenance = result["training"]["export_provenance"]
    assert provenance == {
        "schema": "voxelshogi-export-lineage-v1",
        "training_source_commit": "a" * 40,
        "export_source_commit": "d" * 40,
    }
    assert result["training"]["binding"]["source_commit"] == "a" * 40
    manifest = {
        "trained": True,
        "numericContract": "voxelshogi-trained-numeric-v1",
        "seed": 314159,
        "sourceDirty": False,
        "sourceCommit": "d" * 40,
        "id": result["model_id"],
        "checkpoint": result["weights"],
        "training": result["training"],
    }
    validate_training_manifest(manifest)
    for field in ("schema", "training_source_commit", "export_source_commit"):
        bad = copy.deepcopy(manifest)
        bad["training"]["export_provenance"][field] = "bad"
        with pytest.raises(ValueError):
            validate_training_manifest(bad)


def test_conversion_cannot_infer_or_forge_the_independently_expected_training_source(
    tmp_path,
):
    from export.trained import review_evaluation

    folder = fixture(tmp_path / "evaluated", source_commit="a" * 40)
    for expected in (None, "b" * 40, "bad"):
        context = {"sourceCommit": "d" * 40, "sourceDirty": False}
        if expected is not None:
            context["trainingSourceCommit"] = expected
        with pytest.raises(ValueError):
            review_evaluation(folder, context=context, seed=314159)
