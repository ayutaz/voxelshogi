"""The isolated mutation baseline must satisfy the real CLI provenance contract."""

import runpy
import subprocess
from pathlib import Path


def test_isolated_baseline_has_own_clean_commit_and_ignores_only_runtime_outputs(
    tmp_path,
):
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts/ci/mutation-training.py")
    )
    (tmp_path / "example.py").write_text("answer = 42\n")
    (tmp_path / ".gitignore").write_text("/runs/\n__pycache__/\n.pytest_cache/\n")
    commit = module["prepare_baseline_checkout"](tmp_path)
    assert len(commit) == 40 and all(c in "0123456789abcdef" for c in commit)
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs/result.json").write_text("{}\n")
    (tmp_path / "results.xml").write_text("<testsuites/>\n")
    assert (
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=tmp_path, text=True
        )
        == ""
    )
    assert (
        subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=tmp_path, text=True
        ).strip()
        == "mutation-baseline"
    )
    assert subprocess.check_output(["git", "remote"], cwd=tmp_path, text=True) == ""
    (tmp_path / "example.py").write_text("answer = 0\n")
    assert "example.py" in subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=tmp_path, text=True
    )
