"""Four actual structures, soft-target learning and exact resume on Linux."""

import json
from dataclasses import replace

import pytest

from export.research_contract import ARCHITECTURES
from training.tests.test_research_fit_native import payload
from training.tests.test_research_model_native import tiny


def corpus():
    import numpy as np

    from training.research_targets import visit_policy
    from training.research_visit_fit import VisitCorpus
    from training.selfplay_training import Samples

    def split(start, count):
        rows, features = [], []
        for i in range(start, start + count):
            features.append(np.full((8, 43), i / 100, dtype=np.float32))
            rows.append(
                {
                    "id": str(i),
                    "input_id": f"{i:064x}",
                    "family": f"{start + 100:064x}",
                    "policy": visit_policy([0, 1], {0: 1, 1: 3}),
                    "value": {"kind": "bootstrap-v1", "value": 0.2},
                    "legal_actions": [0, 1],
                }
            )
        return Samples(features, rows, {"fixed_source": "a" * 64})

    return VisitCorpus(split(0, 3), split(3, 2), "b" * 64)


@pytest.mark.parametrize("architecture", ARCHITECTURES)
def test_fixed_updates_mid_epoch_resume_and_validation_are_exact(
    tmp_path, architecture
):
    from training.research_visit_fit import VisitRunConfig, fit_visits
    from training.resume_archive import pack_run, restore_run
    from training.tests.test_checkpoint import assert_state_equal

    c = VisitRunConfig(
        architecture=tiny(architecture),
        seed=67003,
        total_updates=7,
        batch_size=2,
        validate_every=3,
        save_every=2,
        threads=1,
        device="cpu",
        learning_rate=0.003,
    )
    data = corpus()
    full, partial, restored = (
        tmp_path / name for name in ("full", "partial", "restored")
    )
    finished = fit_visits(data, full, config=c, source_commit="a" * 40)
    attempt = fit_visits(
        data, partial, config=c, source_commit="a" * 40, max_new_steps=4
    )
    assert attempt["reason"] == "max_new_steps"
    assert attempt["progress"]["step"] == 4
    initial = payload(partial)
    pack_run(partial, tmp_path / "archive", profile="research")
    restore_run(
        tmp_path / "archive",
        restored,
        expected_binding=initial["binding"],
        profile="research",
    )
    resumed = fit_visits(data, restored, config=c, source_commit="a" * 40, resume=True)
    assert finished["reason"] == resumed["reason"] == "complete"
    assert finished["progress"]["step"] == resumed["progress"]["step"] == 7
    assert_state_equal(payload(full), payload(restored))
    state = payload(restored)
    assert {int(v["step"].item()) for v in state["optimizer"]["state"].values()} == {7}
    for folder in (full, restored):
        events = list(
            map(json.loads, (folder / "events.jsonl").read_text().splitlines())
        )
        assert [e["step"] for e in events if e["event"] == "val"] == [3, 6, 7]
        assert all(
            e["value_origins"] == {"bootstrap-v1": 2}
            for e in events
            if e["event"] == "val"
        )
        assert all(
            set(e["ids"]) <= {"0", "1", "2"} for e in events if e["event"] == "train"
        )
    with pytest.raises(ValueError, match="binding"):
        fit_visits(
            data,
            restored,
            config=replace(c, total_updates=8),
            source_commit="a" * 40,
            resume=True,
        )
    # Holding update count constant, changing full visit probabilities must
    # change actual weights; flattening both targets to argmax would fail this.
    from training.research_targets import visit_policy

    changed = corpus()
    for row in changed.train.rows:
        row["policy"] = visit_policy([0, 1], {0: 2, 1: 3})
    fit_visits(
        changed, tmp_path / "different-soft-target", config=c, source_commit="a" * 40
    )
    assert any(
        not tensor.equal(payload(tmp_path / "different-soft-target")["model"][key])
        for key, tensor in state["model"].items()
    )


def test_validation_retains_full_distribution_and_counts_explicit_value_origins():
    import math

    import torch

    from training.research_visit_fit import VisitRunConfig, evaluate_visits

    class Constant(torch.nn.Module):
        def forward(self, features):
            return torch.zeros((len(features), 184)), torch.zeros((len(features), 1))

    c = VisitRunConfig(architecture=tiny("full"), device="cpu", threads=1)
    report = evaluate_visits(Constant(), corpus().val, c)
    assert report["examples"] == 2
    assert report["value_origins"] == {"bootstrap-v1": 2}
    assert report["policy_ce"] == pytest.approx(math.log(2), abs=1e-6)
    assert report["value_mse"] == pytest.approx(0.04, abs=1e-6)
    assert report["loss"] == pytest.approx(math.log(2) + 0.04, abs=1e-6)


def test_admitted_data_binding_rejects_cross_split_inputs_and_families(tmp_path):
    from training.research_visit_fit import VisitRunConfig, fit_visits

    c = VisitRunConfig(architecture=tiny("full"), device="cpu", threads=1)
    original = corpus()
    digest = original.digest(c)
    changed = corpus()
    changed.train.features[0][0, 0] += 0.01
    assert changed.digest(c) != digest
    for key in ("input_id", "family"):
        bad = corpus()
        bad.val.rows[0][key] = bad.train.rows[0][key]
        with pytest.raises(ValueError, match="isolation"):
            fit_visits(bad, tmp_path / key, config=c, source_commit="a" * 40)
        assert not (tmp_path / key).exists()
