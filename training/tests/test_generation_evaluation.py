"""Hand-counted paired differences and inventories; no shogi or tensors."""

from copy import deepcopy

import pytest

from training.tests.test_evaluation_v2 import protocol, rows


def cohort(identity, outcomes):
    from training.evaluation_v2 import fingerprint

    spec = protocol()
    spec["participants"]["model"]["artifact_sha256"] = identity * 64
    games = rows(spec, outcomes)
    for row in games:
        row["model_sha256"] = identity * 64
        row["protocol_sha256"] = fingerprint(spec)
    return {"protocol": spec, "rows": games}


def cohorts():
    return {
        "m6": cohort("a", (("win", "loss"), ("draw", "cutoff"))),
        "g0": cohort("c", (("loss", "win"), ("win", "cutoff"))),
    }


def test_paired_generation_differences_keep_colors_and_censored_score_bounds():
    from training.generation_evaluation import summarize_generations

    result = summarize_generations(cohorts(), baseline="m6")
    assert result["games"] == 8 and result["opening_pairs_per_model"] == 2
    delta = result["differences_from_baseline"]["g0"]
    assert delta["win_rate_difference"] == 0.25
    # Pair differences are 0 and +1 win / two colors. The two draws of a
    # bootstrap sample give 0, .25 or .5; resampling colors alone is wrong.
    assert delta["paired_win_difference95"] == [0.0, 0.5]
    # Child [2,3]/4 minus baseline [1.5,2.5]/4, without inventing cutoff scores.
    assert delta["score_difference_bounds"] == [-0.125, 0.375]
    assert result["comparisons"]["m6"]["overall"]["draws"] == 1
    assert "population" in result["limitations"]
    reverse = {k: {**v, "rows": v["rows"][::-1]} for k, v in cohorts().items()}
    assert summarize_generations(reverse, baseline="m6") == result


def test_censoring_stays_unknown_even_if_observed_win_difference_is_zero():
    from training.generation_evaluation import summarize_generations

    value = {
        name: cohort(i, (("cutoff", "cutoff"),) * 2)
        for name, i in (("m6", "a"), ("g0", "c"))
    }
    delta = summarize_generations(value, baseline="m6")["differences_from_baseline"][
        "g0"
    ]
    assert delta["paired_win_difference95"] == [0.0, 0.0]
    assert delta["score_difference_bounds"] == [-1.0, 1.0]


@pytest.mark.parametrize(
    "field",
    [
        "cases",
        "search_limits",
        "source_commit",
        "participants",
        "purpose",
        "bootstrap",
        "sensitivity",
    ],
)
def test_generation_comparisons_require_same_conditions_and_opponent(field):
    from training.generation_evaluation import summarize_generations

    value = cohorts()
    spec = value["g0"]["protocol"]
    if field == "cases":
        spec[field][0]["seed"] += 1
    elif field == "search_limits":
        spec[field]["max_nodes"] += 1
    elif field == "source_commit":
        spec[field] = "e" * 40
    elif field == "participants":
        spec[field]["opponent"]["artifact_sha256"] = "f" * 64
    elif field == "purpose":
        spec[field] = "holdout"
    elif field == "bootstrap":
        spec[field]["seed"] += 1
    else:
        spec[field]["minimum_termination_rate"] = 0.25
    # Rebind otherwise-valid rows, so removing the cross-model condition check
    # cannot be caught merely by a stale row's single-comparison digest.
    from training.evaluation_v2 import fingerprint

    for row in value["g0"]["rows"]:
        row["protocol_sha256"] = fingerprint(spec)
        row["opponent_sha256"] = spec["participants"]["opponent"]["artifact_sha256"]
        row["seed"] = next(
            c["seed"] for c in spec["cases"] if c["id"] == row["case_id"]
        )
    with pytest.raises(ValueError):
        summarize_generations(value, baseline="m6")


def test_empty_missing_repeated_or_mislabeled_generations_cannot_pass():
    from training.generation_evaluation import summarize_generations

    for value in (
        {},
        {"m6": cohorts()["m6"]},
        {**cohorts(), "duplicate": cohorts()["g0"]},
    ):
        with pytest.raises(ValueError):
            summarize_generations(value, baseline="m6")
    value = cohorts()
    value["g0"]["rows"].pop()
    with pytest.raises(ValueError):
        summarize_generations(value, baseline="m6")
    with pytest.raises(ValueError):
        summarize_generations(cohorts(), baseline="absent")


def test_full_physical_and_canonical_input_audit_reports_later_overlaps():
    from training.generation_evaluation import audit_evaluation_inputs

    physical = {"m4-train": {"a" * 64}, "selfplay": {"b" * 64}}
    inputs = {"protected": {"c" * 64}, "selfplay": {"d" * 64}}
    cases = {"one": {"positions": {"e" * 64, "b" * 64}, "inputs": {"f" * 64, "d" * 64}}}
    result = audit_evaluation_inputs(physical, inputs, cases)
    assert result["passed"] is False
    assert result["overlaps_by_source"] == {
        "physical": {"m4-train": 0, "selfplay": 1},
        "model_input": {"protected": 0, "selfplay": 1},
    }
    assert result["evaluation_counts"] == {"positions": 2, "inputs": 2}
    assert result["cases_with_overlap"] == ["one"]
    clean = {"one": {"positions": {"e" * 64}, "inputs": {"f" * 64}}}
    assert audit_evaluation_inputs(physical, inputs, clean)["passed"] is True
    contaminated = deepcopy(clean)
    contaminated["one"]["inputs"].add("c" * 64)
    assert audit_evaluation_inputs(physical, inputs, contaminated)["passed"] is False


def test_input_audit_rejects_missing_empty_or_invalid_inventories():
    from training.generation_evaluation import audit_evaluation_inputs

    p, i = {"m4": {"a" * 64}}, {"protected": {"b" * 64}}
    c = {"one": {"positions": {"c" * 64}, "inputs": {"d" * 64}}}
    for args in (
        ({}, i, c),
        (p, {}, c),
        (p, i, {}),
        (p, i, {"one": {"positions": set(), "inputs": {"d" * 64}}}),
        (p, {"protected": {"bad"}}, c),
    ):
        with pytest.raises(ValueError):
            audit_evaluation_inputs(*args)


def test_generation_cases_fix_15_comparison_and_two_disjoint_timing_openings():
    from collections import Counter

    from training.generation_cases import generation_definitions

    main = generation_definitions("comparison")
    timing = generation_definitions("timing")
    assert len(main) == 15 and len(timing) == 2
    assert Counter(d["case"]["stratum"] for d in main) == {
        "tactical": 3,
        "endgame": 4,
        "middlegame": 4,
        "opening": 4,
    }
    assert len({d["case"]["id"] for d in main + timing}) == 17
    assert {d["case"]["seed"] for d in main}.isdisjoint(
        d["case"]["seed"] for d in timing
    )
    tactics = [d for d in main if d["case"]["stratum"] == "tactical"]
    assert len({d["family"] for d in tactics}) == 1  # do not invent independence
    assert all(
        d["oracle"]["move"] == "232222" and d["case"]["max_additional_plies"] == 1
        for d in tactics
    )
    assert [
        d["generated_opening"]["plies"]
        for d in main
        if d["case"]["stratum"] == "middlegame"
    ] == [96, 128, 160, 192]
    assert (
        len(
            {
                d["case"]["opening"]["initial"]
                for d in main + timing
                if d["generated_opening"] is None
            }
        )
        == 8
    )
    main[0]["case"]["opening"]["moves"].append("mutated")
    assert generation_definitions("comparison")[0]["case"]["opening"]["moves"] == []
    with pytest.raises(ValueError):
        generation_definitions("holdout")


def test_generation_preparation_and_input_replay_reject_mac_before_engine_import(
    monkeypatch,
):
    from training.generation_cases import (
        prepare_generation_protocol,
        replay_scored_identities,
    )

    monkeypatch.setattr("training.generation_cases.sys.platform", "darwin")
    with pytest.raises(ValueError, match="Linux"):
        prepare_generation_protocol({}, "a" * 40, stage="timing")
    with pytest.raises(ValueError, match="Linux"):
        replay_scored_identities({}, {})
