"""Replay evidence from handwritten ports; no engine or tensors on Mac."""

import copy

import pytest

from training.tests.test_selfplay_actor import config, root
from training.tests.test_selfplay_search import evaluator


def episode(plies=1):
    from training.selfplay_actor import play_episode

    return play_episode(
        root(),
        evaluator([]),
        config(plies, bootstrap_discount=0.5),
        model_sha256="a" * 64,
        source_commit="1" * 40,
    )


def test_cutoff_retains_raw_final_estimate_for_independent_label_recomputation():
    e = episode()
    assert e["schema"] == "voxelshogi-selfplay-episode-v2"
    assert e["bootstrap"] == {"value": 0.25, "side": "w", "ply": 1}
    # The raw estimate is distinct from the signed/discounted earlier target.
    assert e["samples"][0]["value"]["value"] == -0.125


def test_natural_episode_has_no_bootstrap_evidence():
    e = episode(2)
    assert e["schema"] == "voxelshogi-selfplay-episode-v2"
    assert e["bootstrap"] is None
    assert [s["value"]["value"] for s in e["samples"]] == [-1, 1]


def from_record(record):
    game = root()
    assert record["initial"] == "root"
    for move in record["moves"]:
        game.play(move)
    return game


def verify(e, **kw):
    from training.replay import verify_episode

    return verify_episode(
        e,
        expected_source="1" * 40,
        expected_model="a" * 64,
        expected_config=config(
            1 if e["termination_kind"] == "cutoff" else 2, bootstrap_discount=0.5
        ),
        game_from_record=from_record,
        **kw,
    )


def test_episode_verifier_replays_all_samples_and_independent_value_targets():
    cutoff, natural = verify(episode()), verify(episode(2))
    assert cutoff["samples"] == 1 and cutoff["value_kind"] == "bootstrap-v1"
    assert natural["samples"] == 2 and natural["value_kind"] == "terminal-v1"
    assert cutoff["model_evaluations"] == 3


@pytest.mark.parametrize(
    "kind",
    [
        "source",
        "model",
        "config",
        "identity",
        "missing",
        "position",
        "side",
        "legal",
        "policy",
        "visits",
        "value",
        "horizon",
        "bootstrap",
        "move",
        "search",
        "counter",
        "partial",
    ],
)
def test_replay_rejects_forged_provenance_policy_history_or_value(kind):
    e = episode()
    row = e["samples"][0]
    if kind == "source":
        e["source_commit"] = "2" * 40
    elif kind == "model":
        e["model_sha256"] = "b" * 64
    elif kind == "config":
        e["config"]["noise_fraction"] = 0.5
    elif kind == "identity":
        e["episode_id"] = "f" * 64
    elif kind == "missing":
        e["samples"] = []
    elif kind == "position":
        row["position"] = "other"
    elif kind == "side":
        row["side"] = "w"
    elif kind == "legal":
        row["legal_actions"].append(999)
    elif kind == "policy":
        row["policy"]["probabilities"] = [0.5]
    elif kind == "visits":
        row["policy"]["visits"] = [2]
        row["policy"]["total_visits"] = 2
    elif kind == "value":
        row["value"]["value"] = 0.125
    elif kind == "horizon":
        row["value"]["remaining_plies"] = 0
    elif kind == "bootstrap":
        e["bootstrap"]["value"] = 0.5
    elif kind == "move":
        row["action"] = 99
    elif kind == "search":
        row["search"]["stop_reason"] = "interrupted"
    elif kind == "counter":
        e["model_evaluations"] += 1
    else:
        e["complete"] = False
    with pytest.raises(ValueError):
        verify(e)


def test_prefix_and_natural_win_viewpoints_are_verified_without_resetting_history():
    from training.selfplay_actor import play_episode

    game = root()
    game.play("3")
    cfg = config(1)
    e = play_episode(
        game, evaluator([]), cfg, model_sha256="a" * 64, source_commit="1" * 40
    )
    from training.replay import verify_episode

    report = verify_episode(
        e,
        expected_source="1" * 40,
        expected_model="a" * 64,
        expected_config=cfg,
        game_from_record=from_record,
    )
    assert report["samples"] == 1 and e["samples"][0]["value"]["value"] == 1
    wrong = copy.deepcopy(e)
    wrong["samples"][0]["value"]["value"] = -1
    with pytest.raises(ValueError):
        verify_episode(
            wrong,
            expected_source="1" * 40,
            expected_model="a" * 64,
            expected_config=cfg,
            game_from_record=from_record,
        )


@pytest.mark.parametrize(
    "field,value",
    [("source_commit", "2" * 40), ("model_sha256", "b" * 64), ("config", None)],
)
def test_self_consistent_forged_conditions_still_cannot_replace_expected_binding(
    field, value
):
    from training.research_data import fingerprint

    e = episode()
    if field == "config":
        e["config"]["noise_fraction"] = 0.5
    else:
        e[field] = value
    e["episode_id"] = fingerprint(
        {k: e[k] for k in ("source_commit", "config", "opening", "model_sha256")}
    )
    with pytest.raises(ValueError):
        verify(e)
