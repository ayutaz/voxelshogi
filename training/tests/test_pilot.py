"""Pilot accounting uses literal expected totals, not a second call to itself."""

import pytest


def test_summary_counts_all_completed_samples_and_keeps_failures_visible():
    from training.pilot import summarize

    samples = [
        {
            "case": "opening",
            "profile": "d2",
            "search_seconds": 2.0,
            "completed_depth": 2,
            "nodes": 100,
            "stop_reason": "depth",
            "score": 0,
        },
        {
            "case": "opening",
            "profile": "d2",
            "search_seconds": 4.0,
            "completed_depth": 1,
            "nodes": 50,
            "stop_reason": "nodes",
            "score": 0,
        },
        {
            "case": "opening",
            "profile": "d2",
            "search_seconds": 1.0,
            "completed_depth": 0,
            "nodes": 1,
            "stop_reason": "nodes",
            "score": None,
        },
        {
            "case": "opening",
            "profile": "d2",
            "search_seconds": 1.0,
            "completed_depth": 0,
            "nodes": 1,
            "stop_reason": "depth",
            "score": 500,
        },
    ]
    result = summarize(samples)
    assert result["sample_count"] == 4
    assert result["total_search_seconds"] == 8.0
    assert result["teacher_count"] == 2
    assert result["unlabelled_count"] == 2
    assert result["samples_per_second"] == pytest.approx(0.5)
    assert result["teacher_samples_per_second"] == pytest.approx(0.25)
    assert result["completed_depths"] == {"0": 2, "1": 1, "2": 1}
    assert result["stop_reasons"] == {"depth": 2, "nodes": 2}


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf")])
def test_summary_rejects_invalid_durations(seconds):
    from training.pilot import summarize

    with pytest.raises(ValueError):
        summarize(
            [
                {
                    "case": "x",
                    "profile": "d1",
                    "search_seconds": seconds,
                    "completed_depth": 1,
                    "nodes": 1,
                    "stop_reason": "depth",
                    "score": 0,
                }
            ]
        )


def test_empty_pilot_is_not_a_successful_measurement():
    from training.pilot import summarize

    with pytest.raises(ValueError):
        summarize([])


def test_gpu_inventory_enforces_single_real_device_and_keeps_driver():
    from training.pilot import parse_gpu_inventory

    assert parse_gpu_inventory("NVIDIA GeForce RTX 4090, 24564, 580.95.05\n") == {
        "name": "NVIDIA GeForce RTX 4090",
        "memory_mib": 24564,
        "driver": "580.95.05",
    }
    for text in (
        "",
        "NVIDIA RTX 4090, 24564, 580.1\nNVIDIA RTX 4090, 24564, 580.1",
        "garbage",
    ):
        with pytest.raises(ValueError):
            parse_gpu_inventory(text)


def test_pilot_refuses_mac_and_no_gpu_outside_ci():
    from training.pilot import check_execution_host

    with pytest.raises(ValueError, match="Linux"):
        check_execution_host("darwin", allow_no_gpu=False, ci=False)
    with pytest.raises(ValueError, match="CI"):
        check_execution_host("linux", allow_no_gpu=True, ci=False)
    check_execution_host("linux", allow_no_gpu=False, ci=False)
    check_execution_host("linux", allow_no_gpu=True, ci=True)
