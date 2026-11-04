"""Literal fixed-loop records retain their order only in the distributed profile."""

import copy
import json

import pytest

from training.resume_archive import _history

CONFIG = {"global_batch": 4, "updates": 4, "warmup_updates": 1}
EVENTS = [
    {
        "global_step": 1,
        "value_kind": "terminal-v1",
        "indices": [3, 1, 0, 2],
        "measured": False,
        "examples": 4,
        "elapsed_seconds": 2.0,
        "policy_loss": 0.5,
        "value_mse": 0.25,
        "loss": 0.75,
        "gradient_norm": 1.0,
    },
    {
        "global_step": 2,
        "value_kind": "bootstrap-v1",
        "indices": [2, 0, 1, 3],
        "measured": True,
        "examples": 4,
        "elapsed_seconds": 4.0,
        "policy_loss": 0.25,
        "value_mse": 0.125,
        "loss": 0.375,
        "gradient_norm": 0.5,
    },
]


def write(path, events):
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    return path


def test_distributed_history_preserves_literal_updates_indices_and_warmup(tmp_path):
    path = write(tmp_path / "events.jsonl", EVENTS)
    assert _history(
        path, profile="distributed", config=CONFIG, progress={"step": 2}
    ) == {"schema": "voxelshogi-training-history-v1", "events": EVENTS}


@pytest.mark.parametrize("profile", ["m6", "selfplay"])
def test_distributed_records_do_not_broaden_existing_history_profiles(
    tmp_path, profile
):
    path = write(tmp_path / "events.jsonl", EVENTS)
    with pytest.raises(ValueError):
        _history(path, profile=profile)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e[0].update(raw_features=[1, 2, 3]),
        lambda e: e[0].update(value_kind="unverified"),
        lambda e: e[0].pop("value_kind"),
        lambda e: e[0].pop("measured"),
        lambda e: e[0].update(global_step=True),
        lambda e: e[0].update(global_step=0),
        lambda e: e[1].update(global_step=3),
        lambda e: e[0].update(indices=[0, 0, 1, 2]),
        lambda e: e[0].update(indices=[-1, 0, 1, 2]),
        lambda e: e[0].update(indices=[True, 0, 1, 2]),
        lambda e: e[0].update(indices=[0.5, 0, 1, 2]),
        lambda e: e[0].update(indices=[0, 1]),
        lambda e: e[0].update(measured=0),
        lambda e: e[0].update(measured=True),
        lambda e: e[0].update(examples=True),
        lambda e: e[0].update(examples=8, indices=list(range(8))),
        lambda e: e[0].update(elapsed_seconds=0),
        lambda e: e[0].update(elapsed_seconds=float("inf")),
        lambda e: e[0].update(loss=float("nan")),
        lambda e: e[0].update(loss=-1),
        lambda e: e[0].update(gradient_norm=True),
    ],
)
def test_malformed_distributed_history_is_rejected(tmp_path, mutate):
    events = copy.deepcopy(EVENTS)
    mutate(events)
    path = write(tmp_path / "events.jsonl", events)
    with pytest.raises(ValueError):
        _history(path, profile="distributed", config=CONFIG, progress={"step": 2})


def test_history_cannot_run_ahead_of_or_behind_checkpoint_cursor(tmp_path):
    path = write(tmp_path / "events.jsonl", EVENTS)
    for step in (1, 3):
        with pytest.raises(ValueError):
            _history(
                path, profile="distributed", config=CONFIG, progress={"step": step}
            )


def test_absent_history_keeps_direct_checkpoint_archive_compatibility(tmp_path):
    assert (
        _history(
            tmp_path / "missing",
            profile="distributed",
            config=CONFIG,
            progress={"step": 2},
        )["events"]
        == []
    )


def test_m6_history_still_requires_known_event_and_fields(tmp_path):
    event = {"event": "train", "step": 1, "ids": ["a"], "loss": 0.5}
    path = write(tmp_path / "events.jsonl", [event])
    assert _history(path)["events"] == [event]
    with pytest.raises(ValueError):
        _history(path, profile="unrecognized")
