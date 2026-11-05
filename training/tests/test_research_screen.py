"""Preregistered screen metadata and hand-counted family statistics, no engine."""

from collections import Counter
from copy import deepcopy

import pytest

from training.tests.test_evaluation_v2 import protocol, rows


def method_cohorts(outcomes=None):
    """Twelve opaque roots; four related tactics, four related endings, four seeds."""
    spec = protocol()
    template = deepcopy(spec["cases"][0])
    spec["cases"] = []
    for i in range(12):
        case = deepcopy(template)
        case.update(id=f"case-{i}", seed=64000 + i)
        case["opening"]["initial"] = f"opaque-{i}"
        spec["cases"].append(case)
    families = {
        f"case-{i}": "mate" if i < 4 else "ending" if i < 8 else f"seed-{i}"
        for i in range(12)
    }
    baseline = (("loss", "loss"),) * 12
    outcomes = outcomes or (("win", "win"),) * 4 + baseline[4:]
    cohorts = {}
    for name, scores in (("legal-argmax-v1", baseline), ("puct32-v1", outcomes)):
        current = deepcopy(spec)
        current["participants"]["model"]["policy"] = name
        cohorts[name] = {"protocol": current, "rows": rows(current, scores)}
    return cohorts, families


def test_screen_definitions_freeze_12_development_and_12_separate_final_roots():
    from training.research_screen import screen_definitions

    development, holdout = (screen_definitions(x) for x in ("development", "holdout"))
    assert len(development) == len(holdout) == 12
    assert Counter(x["case"]["stratum"] for x in development) == {
        "tactical": 4,
        "endgame": 4,
        "middlegame": 4,
    }
    assert Counter(x["family"] for x in development).most_common(2) == [
        ("exposed-rook-gold-mate", 4),
        ("material-offset", 4),
    ]
    assert {x["case"]["seed"] for x in development} == {
        64000,
        64001,
        64002,
        64003,
        64010,
        64011,
        64012,
        64013,
        64020,
        64021,
        64022,
        64023,
    }
    assert {x["case"]["seed"] for x in holdout} == set(range(65000, 65012))
    assert all(x["generated_opening"] is not None for x in holdout)
    assert all(x["oracle"] is None for x in holdout)
    assert [x["oracle"]["move"] for x in development[:4]] == [
        "232222",
        "232222",
        "878888",
        "878888",
    ]
    # Static plan is metadata, not a claim of Rust legality or corpus exclusion.
    development[0]["case"]["opening"]["moves"].append("mutation")
    assert screen_definitions("development")[0]["case"]["opening"]["moves"] == []
    with pytest.raises(ValueError):
        screen_definitions("test")


def test_prepare_requires_linux_before_importing_rust(monkeypatch):
    import training.research_screen as module

    monkeypatch.setattr(module.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="external Linux"):
        module.prepare_screen({}, "d" * 40)


def test_same_weight_method_comparison_counts_48_and_clusters_related_cases():
    from training.research_screen import summarize_screen

    cohorts, families = method_cohorts()
    original = deepcopy(cohorts)
    result = summarize_screen(cohorts, families=families)
    assert result["games"] == 48
    assert result["opening_pairs_per_method"] == 12
    assert result["families"] == 6
    delta = result["puct_minus_argmax"]
    # Four of twelve opening pairs improve by 1. They form one of six families.
    assert delta["case_weighted_win_difference"] == pytest.approx(1 / 3)
    assert delta["family_balanced_win_difference"] == pytest.approx(1 / 6)
    assert delta["family_balanced_win_difference95"] == [0.0, 0.5]
    assert delta["family_balanced_score_difference_bounds"] == pytest.approx(
        [1 / 6] * 2
    )
    assert result["verification_scope"].startswith("metadata only")
    assert "not a population" in result["limitations"]
    assert result["comparisons"]["puct32-v1"]["overall"]["wins"] == 8
    assert cohorts == original
    reversed_rows = {k: {**v, "rows": v["rows"][::-1]} for k, v in cohorts.items()}
    assert summarize_screen(reversed_rows, families=families) == result


def test_cutoffs_remain_unknown_in_both_weightings():
    from training.evaluation_v2 import fingerprint
    from training.research_screen import summarize_screen

    cohorts, families = method_cohorts((("cutoff", "cutoff"),) * 12)
    spec = cohorts["legal-argmax-v1"]["protocol"]
    cohorts["legal-argmax-v1"]["rows"] = rows(spec, (("cutoff", "cutoff"),) * 12)
    assert all(
        r["protocol_sha256"] == fingerprint(spec)
        for r in cohorts["legal-argmax-v1"]["rows"]
    )
    result = summarize_screen(cohorts, families=families)["puct_minus_argmax"]
    assert result["family_balanced_win_difference95"] == [0.0, 0.0]
    assert result["case_weighted_score_difference_bounds"] == [-1.0, 1.0]
    assert result["family_balanced_score_difference_bounds"] == [-1.0, 1.0]


@pytest.mark.parametrize(
    "field", ["weights", "backend", "opponent", "cases", "source", "purpose", "policy"]
)
def test_only_model_policy_may_differ_between_arms(field):
    from training.evaluation_v2 import fingerprint
    from training.research_screen import summarize_screen

    cohorts, families = method_cohorts()
    candidate = cohorts["puct32-v1"]
    spec = candidate["protocol"]
    if field == "weights":
        spec["participants"]["model"]["artifact_sha256"] = "f" * 64
    elif field == "backend":
        spec["participants"]["model"]["backend"] = "torch-cpu"
    elif field == "opponent":
        spec["participants"]["opponent"]["artifact_sha256"] = "f" * 64
    elif field == "cases":
        spec["cases"][0]["seed"] += 1
    elif field == "source":
        spec["source_commit"] = "f" * 40
    elif field == "purpose":
        spec["purpose"] = "holdout"
    else:
        spec["participants"]["model"]["policy"] = "legal-argmax-v1"
    # Rebind row metadata: condition checks must not rely on stale digests.
    for row in candidate["rows"]:
        row["protocol_sha256"] = fingerprint(spec)
        row["model_sha256"] = spec["participants"]["model"]["artifact_sha256"]
        row["opponent_sha256"] = spec["participants"]["opponent"]["artifact_sha256"]
        row["seed"] = next(
            c["seed"] for c in spec["cases"] if c["id"] == row["case_id"]
        )
    with pytest.raises(ValueError):
        summarize_screen(cohorts, families=families)


def test_missing_arms_games_or_family_assignments_cannot_pass():
    from training.research_screen import summarize_screen

    cohorts, families = method_cohorts()
    for invalid in (
        {},
        {"puct32-v1": cohorts["puct32-v1"]},
        {**cohorts, "extra": cohorts["puct32-v1"]},
    ):
        with pytest.raises(ValueError):
            summarize_screen(invalid, families=families)
    for invalid in (
        {},
        {**families, "unexpected": "other"},
        {**families, "case-0": ""},
    ):
        with pytest.raises(ValueError):
            summarize_screen(cohorts, families=invalid)
    cohorts["puct32-v1"]["rows"].pop()
    with pytest.raises(ValueError):
        summarize_screen(cohorts, families=families)


def test_eleven_complete_pairs_cannot_substitute_for_the_planned_twelve():
    from training.evaluation_v2 import fingerprint
    from training.research_screen import summarize_screen

    cohorts, families = method_cohorts()
    families.pop("case-11")
    for value in cohorts.values():
        value["protocol"]["cases"].pop()
        value["rows"] = [r for r in value["rows"] if r["case_id"] != "case-11"]
        for row in value["rows"]:
            row["protocol_sha256"] = fingerprint(value["protocol"])
    with pytest.raises(ValueError):
        summarize_screen(cohorts, families=families)


def test_final_holdout_cannot_be_used_as_a_development_screen():
    from training.evaluation_v2 import fingerprint
    from training.research_screen import summarize_screen

    cohorts, families = method_cohorts()
    for value in cohorts.values():
        value["protocol"]["purpose"] = "holdout"
        for row in value["rows"]:
            row["protocol_sha256"] = fingerprint(value["protocol"])
    with pytest.raises(ValueError):
        summarize_screen(cohorts, families=families)
