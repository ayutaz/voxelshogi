"""Production scheduling and estimates use small, independent numeric examples."""

import pytest


def test_seeded_search_openings_diversify_but_keep_the_teacher_separate():
    from training.production import trajectory_move

    moves = ["999888", "999889", "999898", "999899", "999988", "999989", "999998"]
    # SHA256(move:17:g000002:0) mod 7 = 2; g000005 gives 1.
    assert trajectory_move(17, "g000002", 0, moves, "999888", 8) == "999898"
    assert trajectory_move(17, "g000005", 0, moves, "999888", 8) == "999889"
    assert trajectory_move(17, "g000002", 8, moves, "999888", 8) == "999888"
    assert trajectory_move(17, "g000002", 0, moves, "999888", 0) == "999888"


def test_parallel_merge_marks_duplicates_in_global_game_order():
    from training.production import merge_duplicates

    seen = {}
    first = [{"game_id": "g0", "ply": 0, "vsfen": "board b - 1", "duplicate_of": None}]
    second = [{"game_id": "g1", "ply": 0, "vsfen": "board b - 9", "duplicate_of": None}]
    merge_duplicates(first, seen)
    merge_duplicates(second, seen)
    assert first[0]["duplicate_of"] is None
    assert second[0]["duplicate_of"] == "g0:0"
    assert seen == {"board b -": "g0:0"}


def test_cost_estimate_includes_every_pass_and_setup_without_cpu_linear_scaling():
    from training.production import estimate_production

    # 1000 eligible rows / 0.8 observed yield = 1250 raw rows.
    # generate 125s + validate 250s + regenerate 125s + setup 600s = 1100s.
    report = estimate_production(
        target_eligible=1000,
        measured_rows=100,
        measured_eligible=80,
        generate_seconds=10,
        validate_seconds=20,
        regenerate_seconds=10,
        setup_seconds=600,
        hourly_usd=1,
        contingency=0.2,
    )
    assert report["raw_rows_needed"] == 1250
    assert report["base_seconds"] == 1100
    assert report["budget_seconds"] == 1320
    assert report["estimated_usd"] == pytest.approx(1320 / 3600)
    with pytest.raises(ValueError):
        estimate_production(
            target_eligible=1000,
            measured_rows=100,
            measured_eligible=0,
            generate_seconds=10,
            validate_seconds=20,
            regenerate_seconds=10,
            setup_seconds=600,
            hourly_usd=1,
            contingency=0.2,
        )


def test_production_job_rejects_missing_cost_approval_and_small_success_substitutes():
    from training.production import validate_job

    job = {
        "schema": 1,
        "purpose": "production",
        "provider": "cloudrift",
        "approved": True,
        "approved_seconds": 3600,
        "hourly_usd": 1,
        "max_cost_usd": 2,
        "workers": 2,
        "minimum_eligible_rows": 100000,
        "gpu_model": "rtx5090",
        "config": {"engine_commit": "a" * 40},
    }
    validate_job(job, system="linux", ci=False)
    for change in [
        {"approved": False},
        {"minimum_eligible_rows": 99999},
        {"approved_seconds": 7201},
        {"workers": 5},
    ]:
        with pytest.raises(ValueError):
            validate_job({**job, **change}, system="linux", ci=False)
    with pytest.raises(ValueError, match="Linux"):
        validate_job(job, system="darwin", ci=False)
    with pytest.raises(ValueError):
        validate_job(job, system="linux", ci=True)
