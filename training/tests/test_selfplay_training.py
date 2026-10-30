"""Metadata-only sampling and execution boundaries; no arrays or model on Mac."""

import pytest


def test_homogeneous_batches_cover_every_sample_once_and_resume_at_batch_boundary():
    from training.selfplay_training import epoch_indices

    kinds = [
        "terminal-v1",
        "bootstrap-v1",
        "terminal-v1",
        "bootstrap-v1",
        "terminal-v1",
    ]
    batches = epoch_indices(kinds, 2, seed=7, epoch=0)
    assert sorted(i for batch in batches for i in batch) == [0, 1, 2, 3, 4]
    assert sorted(map(len, batches)) == [1, 2, 2]
    assert all(len({kinds[i] for i in batch}) == 1 for batch in batches)
    assert batches == epoch_indices(kinds, 2, seed=7, epoch=0)
    assert epoch_indices(kinds, 2, seed=7, epoch=0, start_batch=1) == batches[1:]
    for args in (([], 2), (["search-score-v1"], 2), (kinds, True)):
        with pytest.raises(ValueError):
            epoch_indices(*args, seed=7, epoch=0)
    with pytest.raises(ValueError):
        epoch_indices(kinds, 2, seed=7, epoch=0, start_batch=4)


def test_selfplay_configuration_does_not_claim_validation_selection():
    from training.selfplay_training import TrainConfig

    c = TrainConfig()
    assert c.epochs == 1 and c.batch_size == 4 and c.learning_rate == 0.0001
    assert c.value()["selection"] == "fixed epochs; no holdout selection"
    assert c.value()["precision"] == "float32"
    assert "selection_split" not in c.value()
    with pytest.raises(ValueError):
        TrainConfig(epochs=True)


def test_real_feature_encoding_and_training_are_linux_only(monkeypatch, tmp_path):
    from training import selfplay_training as training

    monkeypatch.setattr(training.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="Linux"):
        training.replay_samples(None, protected={"a" * 64})
    with pytest.raises(ValueError, match="Linux"):
        training.fit_samples(None, None, None, tmp_path, config=None, input_binding={})
