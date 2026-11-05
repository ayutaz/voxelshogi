"""Fixed-update research schedules and resume metadata; no tensors on Mac."""

from copy import deepcopy
from dataclasses import replace

import pytest

from export.research_contract import architecture_config


def config():
    from training.research_visit_fit import VisitRunConfig

    return VisitRunConfig(
        architecture=architecture_config("axial"),
        seed=67003,
        total_updates=7,
        batch_size=2,
        validate_every=3,
    )


def test_visit_config_binds_total_updates_architecture_and_full_distribution():
    from training.research_visit_fit import VisitRunConfig, validate_binding

    c = config()
    value = c.value()
    assert value["total_updates"] == 7
    assert value["validate_every"] == 3
    assert value["schema"] == "voxelshogi-research-visit-training-config-v1"
    assert value["policy_target"] == "completed legal visit distribution"
    assert value["selection"] == "fixed val at update intervals and final update"
    assert value["architecture"]["architecture"] == "axial"
    assert value["optimizer"]["foreach"] is False
    assert value["optimizer"]["fused"] is False
    assert VisitRunConfig.from_value(value) == c
    b = {
        "source_commit": "a" * 40,
        "cache_sha256": "b" * 64,
        "config": value,
        "contract": {
            "schema": "voxelshogi-research-visit-training-v1",
            "admission_sha256": "c" * 64,
        },
        "environment": {"device": "cuda"},
    }
    assert validate_binding(b) is None
    from training.research_fit import validate_research_binding

    assert validate_research_binding(b) is None
    for path, bad in (
        (("config", "policy_target"), "argmax"),
        (("config", "total_updates"), True),
        (("config", "architecture", "width"), 5),
        (("contract", "admission_sha256"), "main"),
        (("source_commit",), "main"),
        (("environment", "device"), "cpu"),
    ):
        changed = deepcopy(b)
        parent = changed
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = bad
        with pytest.raises(ValueError):
            validate_binding(changed)


@pytest.mark.parametrize(
    "key,value",
    [
        ("total_updates", 0),
        ("total_updates", True),
        ("validate_every", 0),
        ("batch_size", 65),
    ],
)
def test_invalid_limits_fail_before_execution(key, value):
    with pytest.raises(ValueError):
        replace(config(), **{key: value})


def test_cursor_uses_total_updates_not_attempt_limit_or_whole_epochs():
    from training.research_visit_fit import validate_progress

    kinds = ["terminal-v1", "terminal-v1", "bootstrap-v1"]
    c = config()
    # Each epoch has two homogeneous batches: one size2 and one size1.
    validate_progress(
        {"epoch": 3, "next_batch": 1, "step": 7, "examples": 10, "best_val_loss": 1.2},
        kinds,
        c,
    )
    for epoch, cursor, step, examples in ((3, 1, 8, 10), (3, 0, 7, 10), (3, 1, 7, 11)):
        with pytest.raises(ValueError, match="progress"):
            validate_progress(
                {
                    "epoch": epoch,
                    "next_batch": cursor,
                    "step": step,
                    "examples": examples,
                    "best_val_loss": 1.2,
                },
                kinds,
                c,
            )


def test_real_visit_entrypoint_refuses_mac_before_constructing_model(
    monkeypatch, tmp_path
):
    from training import research_visit_fit as module

    monkeypatch.setattr(module.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="Linux"):
        module.fit_visits(
            object(), tmp_path / "run", config=config(), source_commit="a" * 40
        )


def test_archive_visit_history_requires_contiguous_updates_and_scheduled_val(tmp_path):
    import json

    from training.resume_archive import _history

    c = config().value()
    events = [
        {"event": "train", "step": step, "ids": [str(step)], "loss": 0.7}
        for step in range(1, 4)
    ] + [
        {
            "event": "val",
            "step": 3,
            "policy_ce": 0.6,
            "value_mse": 0.1,
            "loss": 0.7,
            "examples": 2,
            "value_origins": {"bootstrap-v1": 2},
        }
    ]
    path = tmp_path / "events.jsonl"

    def read(entries):
        path.write_text("\n".join(map(json.dumps, entries)) + "\n")
        return _history(path, profile="research", config=c, progress={"step": 3})

    assert read(events)["events"] == events
    for malformed in (
        events[:-1],
        events + [events[-1]],
        events[1:],
        [*events[:-1], {**events[-1], "token": "must not archive"}],
        [*events[:-1], {**events[-1], "value_origins": {"terminal-v1": 1}}],
    ):
        with pytest.raises(ValueError, match="history"):
            read(malformed)
