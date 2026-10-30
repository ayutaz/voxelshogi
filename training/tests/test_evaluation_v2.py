"""Hand-counted evaluation v2 metadata; no engine, search, or tensors on Mac."""

from copy import deepcopy

import pytest


def opening(label):
    return {
        "ruleset_id": "voxelshogi-standard-v1",
        "initial": label,
        "moves": ["opaque-prefix"],
        "termination": None,
        "result": None,
    }


def protocol():
    return {
        "schema": "voxelshogi-evaluation-v2",
        "purpose": "development",
        "source_commit": "d" * 40,
        "participants": {
            "model": {
                "artifact_sha256": "a" * 64,
                "backend": "torch-cuda",
                "policy": "legal-argmax-v1",
            },
            "opponent": {
                "artifact_sha256": "b" * 64,
                "backend": "rust",
                "policy": "alphabeta-v1",
            },
        },
        "ruleset_id": "voxelshogi-standard-v1",
        "search_limits": {"max_depth": 3, "max_nodes": 20000, "table_capacity": 4096},
        "bootstrap": {"seed": 314159, "resamples": 10000},
        "sensitivity": {"minimum_pairs": 4, "minimum_termination_rate": 0.5},
        "cases": [
            {
                "id": "tactic",
                "stratum": "tactical",
                "seed": 7,
                "max_additional_plies": 2,
                "opening": opening("hand-tactic"),
            },
            {
                "id": "ending",
                "stratum": "endgame",
                "seed": 8,
                "max_additional_plies": 4,
                "opening": opening("hand-endgame"),
            },
        ],
    }


def rows(spec, outcomes=(("win", "loss"), ("draw", "cutoff"))):
    from training.evaluation_v2 import fingerprint

    result = []
    for case, pair in zip(spec["cases"], outcomes, strict=True):
        for side, outcome in zip(("b", "w"), pair, strict=True):
            reason = {"Draw": {"reason": "Repetition"}}
            if outcome in ("win", "loss"):
                winner = side if outcome == "win" else {"b": "w", "w": "b"}[side]
                reason = {
                    "Win": {
                        "winner": {"b": "Black", "w": "White"}[winner],
                        "reason": "Checkmate",
                    }
                }
            plies = case["max_additional_plies"] if outcome == "cutoff" else 1
            if outcome == "cutoff":
                reason = {"Draw": {"reason": "MaxPlies"}}
            record = {
                **deepcopy(case["opening"]),
                "moves": case["opening"]["moves"] + ["opaque-move"] * plies,
                "termination": "MaxPlies" if outcome == "cutoff" else None,
                "result": reason,
            }
            result.append(
                {
                    "protocol_sha256": fingerprint(spec),
                    "case_id": case["id"],
                    "model_side": side,
                    "model_sha256": "a" * 64,
                    "opponent_sha256": "b" * 64,
                    "seed": case["seed"],
                    "opening_sha256": fingerprint(case["opening"]),
                    "record": record,
                    "outcome": outcome,
                    "elapsed_seconds": float(plies),
                }
            )
    return result


def summarize(games, spec):
    from training.evaluation_v2 import summarize_matches

    return summarize_matches(
        games, spec, model_sha256="a" * 64, opponent_sha256="b" * 64
    )


def test_hand_counted_outcomes_lengths_colors_strata_and_censoring_bounds():
    spec = protocol()
    result = summarize(rows(spec), spec)
    total = result["overall"]
    assert [
        total[k] for k in ("games", "pairs", "wins", "losses", "draws", "cutoffs")
    ] == [4, 2, 1, 1, 1, 1]
    assert total["win_rate"] == 0.25
    assert total["termination_rate"] == 0.75
    # 1 win + 1 half-point draw; cutoff can add anything in [0,1].
    assert total["score_bounds"] == [0.375, 0.625]
    assert total["completed_score_rate"] == 0.5
    assert total["additional_plies"] == {"min": 1, "max": 4, "mean": 1.75}
    assert total["elapsed_seconds"] == {"total": 7.0, "mean": 1.75}
    assert result["by_side"]["b"]["wins"] == 1
    assert result["by_side"]["w"]["cutoffs"] == 1
    assert result["by_stratum"]["tactical"]["losses"] == 1
    assert result["by_stratum"]["endgame"]["draws"] == 1
    assert result["sensitivity"]["sufficient"] is False  # only two pairs


def test_all_cutoffs_remain_unknown_and_do_not_earn_draw_score_or_strength_claim():
    spec = protocol()
    result = summarize(rows(spec, (("cutoff", "cutoff"),) * 2), spec)
    assert result["overall"]["draws"] == 0
    assert result["overall"]["score_bounds"] == [0.0, 1.0]
    assert result["overall"]["completed_score_rate"] is None
    assert result["overall"]["paired_win_rate95"] == [0.0, 0.0]
    assert result["sensitivity"]["sufficient"] is False
    assert "population" in result["interval_limitations"]


def test_bootstrap_keeps_both_colors_together_and_is_order_independent():
    spec = protocol()
    games = rows(spec, (("win", "loss"), ("loss", "win")))
    expected = summarize(games, spec)
    assert expected["overall"]["paired_win_rate95"] == [0.5, 0.5]
    assert summarize(games[::-1], spec) == expected
    assert summarize(rows(spec, (("win", "win"), ("loss", "loss"))), spec)["overall"][
        "paired_win_rate95"
    ] == [0.0, 1.0]


def test_complete_cohort_and_exact_source_bindings_are_required():
    spec = protocol()
    games = rows(spec)
    for invalid in ([], games[:-1], games + games[:1]):
        with pytest.raises(ValueError):
            summarize(invalid, spec)
    for key, value in (
        ("protocol_sha256", "c" * 64),
        ("model_sha256", "c" * 64),
        ("opponent_sha256", "c" * 64),
        ("case_id", "unknown"),
        ("model_side", "x"),
        ("seed", 999),
        ("seed", True),
        ("opening_sha256", "c" * 64),
        ("outcome", "failed"),
        ("elapsed_seconds", float("nan")),
        ("elapsed_seconds", -1),
        ("elapsed_seconds", True),
    ):
        changed = deepcopy(games)
        changed[0][key] = value
        with pytest.raises(ValueError, match="evaluation"):
            summarize(changed, spec)


def test_result_and_record_prefix_limits_are_checked_not_just_claimed_outcome():
    spec = protocol()
    games = rows(spec)
    changes = [
        (0, "initial", "different"),
        (0, "ruleset_id", "nine-kings"),
        (0, "moves", ["different-prefix", "opaque-move"]),
        (0, "result", {"Win": {"winner": "White", "reason": "Checkmate"}}),
        (0, "termination", "Abandoned"),
        (3, "moves", ["opaque-prefix", "opaque-move"]),
        (3, "moves", ["opaque-prefix"] + ["opaque-move"] * 5),
        (3, "termination", None),
    ]
    for index, key, value in changes:
        altered = deepcopy(games)
        altered[index]["record"][key] = value
        with pytest.raises(ValueError):
            summarize(altered, spec)


def test_contract_rejects_duplicate_openings_cases_and_unbounded_or_changed_fields():
    from training.evaluation_v2 import validate_protocol

    spec = protocol()
    assert len(validate_protocol(spec)) == 64
    bad = []
    for key, value in (
        ("schema", "v1"),
        ("purpose", "train"),
        ("ruleset_id", "nine-kings"),
        ("extra", True),
    ):
        changed = deepcopy(spec)
        changed[key] = value
        bad.append(changed)
    for key, value in (
        ("max_depth", 0),
        ("max_nodes", True),
        ("table_capacity", -1),
        ("max_time_ms", 1000),
    ):
        changed = deepcopy(spec)
        changed["search_limits"][key] = value
        bad.append(changed)
    for key, value in (
        ("seed", True),
        ("max_additional_plies", 0),
        ("max_additional_plies", 20001),
        ("stratum", "unknown"),
    ):
        changed = deepcopy(spec)
        changed["cases"][0][key] = value
        bad.append(changed)
    changed = deepcopy(spec)
    changed["cases"] += [deepcopy(changed["cases"][0])]
    bad.append(changed)
    changed = deepcopy(spec)
    changed["cases"][1]["opening"] = deepcopy(changed["cases"][0]["opening"])
    bad.append(changed)
    changed = deepcopy(spec)
    changed["cases"][0]["opening"]["result"] = {"Draw": {"reason": "Repetition"}}
    bad.append(changed)
    for changed in bad:
        with pytest.raises(ValueError):
            validate_protocol(changed)


def test_split_leakage_uses_canonical_positions_even_when_history_ids_differ():
    from training.evaluation_v2 import check_disjoint_positions

    groups = {"train": {"a" * 64}, "development": {"b" * 64}, "holdout": {"c" * 64}}
    assert check_disjoint_positions(groups) == {
        "train": 1,
        "development": 1,
        "holdout": 1,
    }
    for changed in (
        {**groups, "holdout": {"a" * 64}},
        {**groups, "train": set()},
        {**groups, "train": {"not-a-hash"}},
        {"train": {"a" * 64}},
    ):
        with pytest.raises(ValueError):
            check_disjoint_positions(changed)


def test_fingerprint_includes_history_and_rules_and_rejects_nonfinite_json():
    from training.evaluation_v2 import fingerprint

    item = opening("opaque")
    assert fingerprint(item) == fingerprint(dict(reversed(list(item.items()))))
    for field, value in (
        ("moves", []),
        ("ruleset_id", "another"),
        ("initial", "another"),
    ):
        assert fingerprint({**item, field: value}) != fingerprint(item)
    with pytest.raises(ValueError):
        fingerprint({"invalid": float("nan")})


def test_participant_policy_backend_and_source_are_frozen_before_execution():
    from training.evaluation_v2 import validate_protocol

    spec = protocol()
    for path, value in (
        (("source_commit",), "not-a-commit"),
        (("participants", "model", "artifact_sha256"), "bad"),
        (("participants", "model", "backend"), "automatic"),
        (("participants", "model", "policy"), "unknown"),
        (("participants", "model", "backend"), "rust"),
        (("participants", "opponent", "backend"), "torch-cuda"),
    ):
        changed = deepcopy(spec)
        target = changed
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with pytest.raises(ValueError):
            validate_protocol(changed)
    changed = deepcopy(spec)
    changed["participants"]["model"]["artifact_sha256"] = "c" * 64
    with pytest.raises(ValueError):
        summarize(rows(changed), changed)


def test_sensitivity_screen_requires_both_predeclared_size_and_termination():
    spec = protocol()
    for i in range(2):
        case = deepcopy(spec["cases"][i])
        case["id"] += "-extra"
        case["opening"]["initial"] += "-extra"
        spec["cases"].append(case)
    result = summarize(rows(spec, (("win", "loss"),) * 4), spec)
    assert result["sensitivity"]["sufficient"] is True
    assert "not proof of strength" in result["sensitivity"]["meaning"]
    result = summarize(rows(spec, (("cutoff", "cutoff"),) * 4), spec)
    assert result["sensitivity"]["sufficient"] is False
