"""Pure configuration validation; safe metadata checks on Mac."""

import pytest


def test_initial_training_config_is_explicit_fp32_adamw_without_test_selection():
    from training.fit import RunConfig

    config = RunConfig()
    assert config.seed == 314159 and config.epochs == 1 and config.batch_size == 1
    assert config.device == "cuda" and config.learning_rate == 0.0003
    assert config.value()["precision"] == "float32"
    assert config.value()["selection_split"] == "val"
    assert config.value()["optimizer"] == {
        "name": "AdamW",
        "betas": [0.9, 0.999],
        "eps": 1e-8,
        "foreach": False,
        "fused": False,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"epochs": 0},
        {"batch_size": 0},
        {"batch_size": True},
        {"seed": -1},
        {"learning_rate": float("nan")},
        {"learning_rate": 0},
        {"weight_decay": -1},
        {"save_every": 0},
        {"threads": 0},
        {"device": "mps"},
    ],
)
def test_invalid_or_mac_training_config_is_rejected(change):
    from training.fit import RunConfig

    with pytest.raises(ValueError):
        RunConfig(**change)


def test_resume_cursor_counts_partial_batches_and_completed_epochs():
    from training.fit import RunConfig, _check_cursor

    config = RunConfig(epochs=2, batch_size=3)
    # Seven examples => 3 batches per epoch; epoch1/batch1 means step4/10 examples.
    good = {"epoch": 1, "next_batch": 1, "step": 4, "examples": 10}
    _check_cursor(good, 7, config)
    _check_cursor({"epoch": 2, "next_batch": 0, "step": 6, "examples": 14}, 7, config)
    for change in ({"step": 3}, {"next_batch": 4}, {"examples": 9}, {"epoch": 3}):
        with pytest.raises(ValueError, match="cursor"):
            _check_cursor({**good, **change}, 7, config)
