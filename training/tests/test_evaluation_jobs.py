"""Whole-protocol assignments and committed case metadata; no engine on Mac."""

import json
from copy import deepcopy

import pytest

from training.evaluation_jobs import plan_case_jobs, read_case_rows
from training.evaluation_v2 import fingerprint
from training.tests.test_evaluation_v2 import protocol, rows


def test_case_jobs_keep_full_protocol_and_both_colors_with_no_duplicate_work():
    first, second = protocol(), protocol()
    second["participants"]["model"]["artifact_sha256"] = "c" * 64
    plan = plan_case_jobs({"m6": first, "g0": second}, max_workers=4)
    assert plan["games"] == 8 and plan["max_workers"] == 4
    assert [j["job_id"] for j in plan["jobs"]] == [
        "g0--tactic",
        "g0--ending",
        "m6--tactic",
        "m6--ending",
    ]
    assert all(j["sides"] == ["b", "w"] for j in plan["jobs"])
    assert all(len(j["protocol"]["cases"]) == 2 for j in plan["jobs"])
    assert plan["jobs"][0]["protocol_sha256"] == fingerprint(second)
    assert first == protocol()  # assigning jobs cannot shrink/mutate the cohort


@pytest.mark.parametrize("workers", [0, 17, True])
def test_unbounded_parallelism_is_rejected(workers):
    with pytest.raises(ValueError):
        plan_case_jobs({"m6": protocol()}, max_workers=workers)


def test_cohort_names_cannot_collide_with_the_job_separator():
    with pytest.raises(ValueError):
        plan_case_jobs({"a--b": protocol()}, max_workers=2)


@pytest.mark.parametrize(
    "field", ["cases", "search_limits", "source_commit", "participants"]
)
def test_job_plan_rejects_changed_common_conditions_or_opponent(field):
    a, b = protocol(), protocol()
    if field == "cases":
        b[field][0]["seed"] += 1
    elif field == "search_limits":
        b[field]["max_nodes"] += 1
    elif field == "source_commit":
        b[field] = "e" * 40
    else:
        b[field]["opponent"]["artifact_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        plan_case_jobs({"m6": a, "g0": b}, max_workers=2)


def case_folder(folder, *, case_index=1, complete=True):
    from training.feature_cache import file_hash

    folder.mkdir()
    spec = protocol()
    assigned = spec["cases"][case_index]
    (folder / "protocol.json").write_text(json.dumps(spec))
    games = rows(spec)[2 * case_index : 2 * case_index + (2 if complete else 1)]
    files = []
    for game in games:
        name = assigned["id"] + "-" + game["model_side"] + ".json"
        (folder / name).write_text(json.dumps(game))
        files.append(
            {
                "path": name,
                "bytes": (folder / name).stat().st_size,
                "sha256": file_hash(folder / name),
            }
        )
    receipt = {
        "schema": "voxelshogi-evaluation-case-job-v1",
        "complete": complete,
        "case_id": assigned["id"],
        "protocol_sha256": fingerprint(spec),
        "games": len(games),
        "runtime": {"source_commit": spec["source_commit"]},
        "files": files,
    }
    (folder / "job.json").write_text(json.dumps(receipt))
    return spec, receipt, games


def test_case_receipt_accepts_assigned_nonprefix_case_without_rebinding_protocol(
    tmp_path,
):
    spec, receipt, expected = case_folder(tmp_path / "job")
    actual, saved = read_case_rows(tmp_path / "job", spec, case_id="ending")
    assert actual == expected and saved == receipt and len(actual) == 2
    assert actual[0]["case_id"] == "ending" and actual[0]["model_side"] == "b"
    assert all(g["protocol_sha256"] == fingerprint(spec) for g in actual)
    with pytest.raises(ValueError):
        read_case_rows(tmp_path / "job", spec, case_id="tactic")


@pytest.mark.parametrize(
    "change",
    ["hash", "protocol", "extra", "duplicate", "foreign-row", "false-complete"],
)
def test_case_receipt_rejects_torn_or_mislabeled_work(tmp_path, change):
    folder = tmp_path / "job"
    spec, receipt, _ = case_folder(folder)
    if change == "hash":
        (folder / receipt["files"][0]["path"]).write_text("{}")
    elif change == "protocol":
        altered = deepcopy(spec)
        altered["cases"][0]["seed"] += 1
        (folder / "protocol.json").write_text(json.dumps(altered))
    elif change == "extra":
        (folder / "orphan.json").write_text("{}")
    elif change == "duplicate":
        receipt["files"][1] = receipt["files"][0]
    elif change == "foreign-row":
        from training.feature_cache import file_hash

        path = folder / receipt["files"][0]["path"]
        game = json.loads(path.read_text())
        game["model_sha256"] = "c" * 64
        path.write_text(json.dumps(game))
        receipt["files"][0].update(bytes=path.stat().st_size, sha256=file_hash(path))
    else:
        receipt["games"] = 1
        receipt["files"] = receipt["files"][:1]
        (folder / "ending-w.json").unlink()
    (folder / "job.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        read_case_rows(folder, spec, case_id="ending")


def test_interrupted_case_keeps_only_its_first_committed_color(tmp_path):
    spec, receipt, expected = case_folder(tmp_path / "job", complete=False)
    actual, saved = read_case_rows(tmp_path / "job", spec, case_id="ending")
    assert (
        actual == expected
        and len(actual) == 1
        and saved == receipt
        and not saved["complete"]
    )


def test_case_hash_detects_same_length_valid_metadata_changes(tmp_path):
    spec, receipt, _ = case_folder(tmp_path / "job")
    path = tmp_path / "job" / receipt["files"][0]["path"]
    row = json.loads(path.read_text())
    row["elapsed_seconds"] += 1.0
    path.write_text(json.dumps(row))
    assert path.stat().st_size == receipt["files"][0]["bytes"]
    with pytest.raises(ValueError, match="hash"):
        read_case_rows(tmp_path / "job", spec, case_id="ending")


def test_parallel_results_are_ordered_without_rewriting_any_row_binding():
    from training.evaluation_jobs import ordered_case_rows

    spec = protocol()
    original = rows(spec)
    combined = ordered_case_rows(
        spec, {"ending": original[2:][::-1], "tactic": original[:2]}
    )
    assert combined == original
    assert [r["protocol_sha256"] for r in combined] == [fingerprint(spec)] * 4


@pytest.mark.parametrize("change", ["missing", "extra", "incomplete", "misassigned"])
def test_aggregation_requires_each_case_and_both_assigned_colors(change):
    from training.evaluation_jobs import ordered_case_rows

    spec = protocol()
    games = rows(spec)
    parts = {"tactic": games[:2], "ending": games[2:]}
    if change == "missing":
        parts.pop("ending")
    elif change == "extra":
        parts["foreign"] = []
    elif change == "incomplete":
        parts["ending"] = games[2:3]
    else:
        parts["ending"], parts["tactic"] = parts["tactic"], parts["ending"]
    with pytest.raises(ValueError):
        ordered_case_rows(spec, parts)


def fake_execution(monkeypatch, spec):
    """Only supplied fake ports execute here; no Rust, model or tensor import."""
    from types import SimpleNamespace

    from training import evaluation_jobs as jobs
    from training.tests.test_evaluation_v2_runner import FakeGame

    calls = []

    def choose(_):
        calls.append(1)
        return 7

    monkeypatch.setattr(jobs, "_linux", lambda: None, raising=False)
    monkeypatch.setattr(
        jobs,
        "_context",
        lambda *a, **kw: (
            SimpleNamespace(from_record=lambda r: FakeGame(r, mate_after=1)),
            {"model": choose, "opponent": choose},
            {"source_commit": spec["source_commit"], "fake_port": True},
        ),
        raising=False,
    )
    monkeypatch.setattr(jobs, "verify_record", lambda *a: None, raising=False)
    return calls


def test_fake_case_resume_commits_each_color_and_never_reexecutes_saved_games(
    tmp_path, monkeypatch
):
    from training.evaluation_jobs import run_case_assignment

    spec = protocol()
    calls = fake_execution(monkeypatch, spec)
    folder = tmp_path / "case"
    first = folder / "ending-b.json"
    with pytest.raises(InterruptedError):
        run_case_assignment(
            spec, {}, folder, case_id="ending", stop_requested=first.exists
        )
    before = first.read_bytes()
    assert len(calls) == 1
    assert read_case_rows(folder, spec, case_id="ending")[1]["games"] == 1
    result = run_case_assignment(spec, {}, folder, case_id="ending", resume=True)
    assert result["complete"] and result["games"] == 2
    assert first.read_bytes() == before and len(calls) == 2
    assert (
        run_case_assignment(spec, {}, folder, case_id="ending", resume=True) == result
    )
    assert len(calls) == 2
    with pytest.raises(FileExistsError):
        run_case_assignment(spec, {}, folder, case_id="ending")


def test_fake_case_resume_refuses_changed_environment_without_overwriting_prefix(
    tmp_path, monkeypatch
):
    from training import evaluation_jobs as jobs

    spec = protocol()
    fake_execution(monkeypatch, spec)
    folder = tmp_path / "case"
    first = folder / "ending-b.json"
    with pytest.raises(InterruptedError):
        jobs.run_case_assignment(
            spec, {}, folder, case_id="ending", stop_requested=first.exists
        )
    original = first.read_bytes()
    context = jobs._context
    monkeypatch.setattr(
        jobs, "_context", lambda *a, **kw: (*context(*a, **kw)[:2], {"changed": True})
    )
    with pytest.raises(ValueError, match="runtime"):
        jobs.run_case_assignment(spec, {}, folder, case_id="ending", resume=True)
    assert first.read_bytes() == original and not (folder / "ending-w.json").exists()


def test_fake_case_rejects_duplicate_owner_and_invalid_assignment_before_output(
    tmp_path, monkeypatch
):
    import fcntl

    from training.evaluation_jobs import run_case_assignment

    spec = protocol()
    calls = fake_execution(monkeypatch, spec)
    folder = tmp_path / "case"
    with pytest.raises(ValueError):
        run_case_assignment(spec, {}, folder, case_id="foreign")
    assert not folder.exists() and not calls
    with (tmp_path / ".case.evaluation.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="owner"):
            run_case_assignment(spec, {}, folder, case_id="ending")
    assert not folder.exists() and not calls


def test_bounded_pool_runs_all_assignments_once_and_limits_simultaneous_children():
    from training.evaluation_jobs import bounded_pool

    started, active, peaks = [], set(), []

    class Child:
        def __init__(self, item):
            self.item, self.ticks = item, 0

        def poll(self):
            self.ticks += 1
            if self.ticks < 3:
                return None
            active.discard(self.item)
            return 0

    def start(item):
        started.append(item)
        active.add(item)
        peaks.append(len(active))
        return Child(item)

    bounded_pool(
        list(range(7)),
        max_workers=3,
        start=start,
        retire=lambda *a: None,
        pause=lambda: None,
    )
    assert started == list(range(7)) and max(peaks) == 3 and not active


@pytest.mark.parametrize("interrupt", [False, True])
def test_bounded_pool_stops_owned_children_and_does_not_start_pending_after_failure(
    interrupt,
):
    from training.evaluation_jobs import bounded_pool

    started, stopped = [], []

    class Child:
        def __init__(self, item):
            self.item = item

        def poll(self):
            return 9 if self.item == 0 and not interrupt else None

    def start(item):
        started.append(item)
        return Child(item)

    with pytest.raises(InterruptedError if interrupt else RuntimeError):
        bounded_pool(
            list(range(5)),
            max_workers=2,
            start=start,
            retire=lambda child, failed: stopped.append((child.item, failed)),
            pause=lambda: None,
            stop_requested=lambda: interrupt and bool(started),
        )
    assert started == ([0] if interrupt else [0, 1])
    assert set(stopped) == ({(0, True)} if interrupt else {(0, True), (1, True)})


@pytest.mark.parametrize("change", ["count", "digest", "omit", "duplicate", "workers"])
def test_serialized_plan_cannot_change_assignments_after_freezing(change):
    from training.evaluation_jobs import validate_case_plan

    plan = plan_case_jobs({"m6": protocol()}, max_workers=2)
    assert validate_case_plan(plan) == {"m6": protocol()}
    if change == "count":
        plan["games"] += 2
    elif change == "digest":
        plan["jobs"][0]["protocol_sha256"] = "c" * 64
    elif change == "omit":
        plan["jobs"].pop()
    elif change == "duplicate":
        plan["jobs"][1] = plan["jobs"][0]
    else:
        plan["max_workers"] = 17
    with pytest.raises(ValueError):
        validate_case_plan(plan)


def test_unknown_or_live_previous_launch_cannot_be_restarted(tmp_path):
    from training.evaluation_jobs import check_previous_launch

    path = tmp_path / "launch.json"
    assert check_previous_launch(path, is_live=lambda info: False) is None
    path.write_text(json.dumps({"state": "requested"}))
    with pytest.raises(ValueError, match="unknown"):
        check_previous_launch(path, is_live=lambda info: False)
    running = {"state": "running", "pid": 123, "create_time": 45.0}
    path.write_text(json.dumps(running))
    with pytest.raises(ValueError, match="live"):
        check_previous_launch(path, is_live=lambda info: True)
    assert check_previous_launch(path, is_live=lambda info: False) == running
    terminal = {**running, "state": "terminal", "exit_code": 1}
    path.write_text(json.dumps(terminal))
    assert check_previous_launch(path, is_live=lambda info: True) == terminal


def test_fake_aggregation_preserves_original_bytes_and_rejects_mixed_runtime(
    tmp_path, monkeypatch
):
    from training import evaluation_jobs as jobs

    spec, _, _ = case_folder(tmp_path / "tactic", case_index=0)
    case_folder(tmp_path / "ending")
    fake_execution(monkeypatch, spec)
    monkeypatch.setattr(
        jobs, "verify_run", lambda p: json.loads((p / "summary.json").read_text())
    )
    folders = {name: tmp_path / name for name in ("tactic", "ending")}
    result = jobs.aggregate_case_jobs(spec, folders, tmp_path / "combined")
    assert result["overall"]["games"] == 4
    for folder in folders.values():
        for row in folder.glob("*-b.json"):
            assert (tmp_path / "combined" / row.name).read_bytes() == row.read_bytes()
    path = tmp_path / "ending/job.json"
    receipt = json.loads(path.read_text())
    receipt["runtime"]["python"] = "different"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="runtime"):
        jobs.aggregate_case_jobs(spec, folders, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_case_and_pool_execution_are_rejected_on_mac_before_allocating_or_spawning(
    monkeypatch, tmp_path
):
    from types import SimpleNamespace

    from training import evaluation_jobs as jobs

    monkeypatch.setattr(jobs, "sys", SimpleNamespace(platform="darwin"))
    for call in (
        lambda: jobs.run_case_assignment(
            protocol(), {}, tmp_path / "case", case_id="ending"
        ),
        lambda: jobs.run_case_plan(
            plan_case_jobs({"m6": protocol()}, max_workers=2),
            {"m6": {}},
            tmp_path / "pool",
        ),
    ):
        with pytest.raises(ValueError, match="Linux"):
            call()
    assert not list(tmp_path.iterdir())
