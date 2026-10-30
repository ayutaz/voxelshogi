"""Lightweight runner boundary checks; no Parquet or rules on Mac."""

import pytest


def test_research_generation_verification_and_audit_are_linux_only(
    monkeypatch, tmp_path
):
    from training import research_data_runner as runner

    monkeypatch.setattr(runner.sys, "platform", "darwin")
    for function, args in (
        (runner.generate_pilot, (tmp_path, {})),
        (runner.verify_pilot, (tmp_path,)),
        (runner.audit_pilot, (tmp_path, tmp_path, tmp_path, tmp_path)),
    ):
        with pytest.raises(ValueError, match="Linux"):
            function(*args)


def test_directory_claim_does_not_accept_unowned_data_or_symlinks(tmp_path):
    from training.research_data_runner import _lock

    unowned = tmp_path / "unowned"
    unowned.mkdir()
    (unowned / "keep.txt").write_text("unrelated")
    with pytest.raises(ValueError, match="unowned"):
        with _lock(unowned):
            pytest.fail("must not acquire unrelated data")
    assert (unowned / "keep.txt").read_text() == "unrelated"
    linked = tmp_path / "linked"
    linked.symlink_to(unowned, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        with _lock(linked):
            pytest.fail("must not follow link")


def test_generation_source_check_rejects_other_commit_and_dirty_worktree(monkeypatch):
    from training import research_data_runner as runner

    p = {"source_commit": "a" * 40}
    for sha, status in (("b" * 40, ""), ("a" * 40, " M training/research_data.py")):
        monkeypatch.setattr(
            runner.subprocess,
            "check_output",
            lambda cmd, **kw: sha if cmd[1] == "rev-parse" else status,
        )
        with pytest.raises(ValueError, match="clean source"):
            runner._source(p)


def test_preset_creates_only_metadata_under_runs_with_fixed_source(
    monkeypatch, tmp_path
):
    import json

    from training import research_data_runner as runner

    monkeypatch.setattr(runner, "_linux", lambda: None)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda cmd, **kw: "a" * 40 if cmd[1] == "rev-parse" else "",
    )
    out = tmp_path / "runs" / "p5" / "protocol.json"
    monkeypatch.setattr(runner.sys, "argv", ["runner", "preset", str(out)])
    runner.main()
    p = json.loads(out.read_text())
    assert p["source_commit"] == "a" * 40 and len(p["games"]) == 8
