"""Assigned games retain full protocol identity and replay exactly on Linux."""

import json
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="external Linux only")


def test_case_jobs_aggregate_exact_rows_and_match_the_sequential_reference(tmp_path):
    from training.evaluation_jobs import aggregate_case_jobs, run_case_assignment
    from training.evaluation_v2_runner import run_protocol, verify_run
    from training.feature_cache import file_hash
    from training.tests.test_evaluation_v2_native import native_protocol

    spec = native_protocol()
    jobs = {}
    for case in reversed(spec["cases"]):
        folder = tmp_path / case["id"]
        result = run_case_assignment(spec, {}, folder, case_id=case["id"])
        assert result["complete"] and result["games"] == 2
        jobs[case["id"]] = folder
    combined = tmp_path / "combined"
    actual = aggregate_case_jobs(spec, jobs, combined)
    expected = run_protocol(spec, {}, tmp_path / "reference")
    assert [
        actual["overall"][k] for k in ("games", "wins", "losses", "draws", "cutoffs")
    ] == [4, 1, 1, 0, 2]
    assert verify_run(combined) == actual
    for key in ("wins", "losses", "draws", "cutoffs", "score_bounds"):
        assert actual["overall"][key] == expected["overall"][key]
    for case in spec["cases"]:
        for side in ("b", "w"):
            name = case["id"] + "-" + side + ".json"
            assert file_hash(combined / name) == file_hash(jobs[case["id"]] / name)
            assert (
                json.loads((combined / name).read_text())["record"]
                == json.loads((tmp_path / "reference" / name).read_text())["record"]
            )


def test_case_resume_reuses_its_committed_first_color_without_replaying_it(tmp_path):
    from training.evaluation_jobs import read_case_rows, run_case_assignment
    from training.feature_cache import file_hash
    from training.tests.test_evaluation_v2_native import native_protocol

    spec = native_protocol()
    case = spec["cases"][1]
    folder = tmp_path / "interrupted"
    first = folder / (case["id"] + "-b.json")
    with pytest.raises(InterruptedError):
        run_case_assignment(
            spec, {}, folder, case_id=case["id"], stop_requested=first.exists
        )
    original = file_hash(first)
    assert len(read_case_rows(folder, spec, case_id=case["id"])[0]) == 1
    result = run_case_assignment(spec, {}, folder, case_id=case["id"], resume=True)
    assert result["complete"] and result["games"] == 2 and file_hash(first) == original
    assert (
        run_case_assignment(spec, {}, folder, case_id=case["id"], resume=True) == result
    )
    with pytest.raises(FileExistsError):
        run_case_assignment(spec, {}, folder, case_id=case["id"])


def test_real_subprocess_pool_completes_the_full_frozen_cohort_and_resumes_idempotently(
    tmp_path,
):
    from training.evaluation_jobs import plan_case_jobs, run_case_plan
    from training.evaluation_v2_runner import verify_run
    from training.tests.test_evaluation_v2_native import native_protocol

    spec = native_protocol()
    plan = plan_case_jobs({"control": spec}, max_workers=2)
    folder = tmp_path / "pool"
    actual = run_case_plan(plan, {"control": {}}, folder)
    assert actual["control"]["overall"]["games"] == 4
    assert verify_run(folder / "cohorts/control") == actual["control"]
    assert run_case_plan(plan, {"control": {}}, folder, resume=True) == actual
    for job in plan["jobs"]:
        launch = json.loads(
            (folder / "launches" / (job["job_id"] + ".json")).read_text()
        )
        assert launch["state"] == "terminal" and launch["exit_code"] == 0
