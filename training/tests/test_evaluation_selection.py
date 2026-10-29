"""Pure binding/val-selection validation; no model load or corpus on Mac."""

import copy

import pytest


def metadata():
    from training.fit import RunConfig
    from training.supervision import label_contract

    binding = {
        "source_commit": "a" * 40,
        "cache_sha256": "b" * 64,
        "contract": label_contract(),
        "config": RunConfig(epochs=3, batch_size=2, device="cpu").value(),
    }
    receipt = {
        "binding": binding,
        "progress": {
            "epoch": 2,
            "next_batch": 0,
            "step": 4,
            "examples": 6,
            "best_val_loss": 1.0,
        },
    }
    return binding, receipt


def test_only_completed_val_selected_epochs_from_fixed_input_source_are_evaluated():
    from training.evaluate import validate_selected

    binding, receipt = metadata()
    result = validate_selected(
        binding, receipt, cache_sha256="b" * 64, source_commit="a" * 40, train_count=3
    )
    assert result == receipt["progress"]


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "cache",
        "contract",
        "selection_split",
        "precision",
        "no_val",
        "no_epoch",
        "mid_epoch",
        "step",
        "receipt",
    ],
)
def test_wrong_or_unselected_checkpoint_is_never_a_final_test_candidate(change):
    from training.evaluate import validate_selected

    binding, receipt = copy.deepcopy(metadata())
    if change == "source":
        binding["source_commit"] = "c" * 40
    elif change == "cache":
        binding["cache_sha256"] = "c" * 64
    elif change == "contract":
        binding["contract"]["value_scale"] = 500
    elif change in ("selection_split", "precision"):
        binding["config"][change] = "test" if change == "selection_split" else "float16"
    elif change == "no_val":
        receipt["progress"]["best_val_loss"] = None
    elif change == "no_epoch":
        receipt["progress"].update(epoch=0, step=0, examples=0)
    elif change == "mid_epoch":
        receipt["progress"].update(next_batch=1, step=5, examples=8)
    elif change == "step":
        receipt["progress"]["step"] = 3
    elif change == "receipt":
        receipt["binding"] = {"other": True}
    with pytest.raises(ValueError):
        validate_selected(
            binding,
            receipt,
            cache_sha256="b" * 64,
            source_commit="a" * 40,
            train_count=3,
        )
