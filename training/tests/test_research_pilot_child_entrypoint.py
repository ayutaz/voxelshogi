"""Use only standard-library fixture interpreters and fake process ports."""

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest


def test_attempt_module_finds_repo_packages_without_inherited_pythonpath(tmp_path):
    import infrastructure.research.pilot.child as child

    folder = tmp_path / "repo"
    pilot = folder / "infrastructure/research/pilot"
    pilot.mkdir(parents=True)
    copied = pilot / "child.py"
    copied.write_text(Path(child.__file__).read_text())
    (folder / "training").mkdir()
    (folder / "training/__init__.py").write_text("MARKER = 'module-import-ok'\n")
    script = pilot / "attempt.py"
    script.write_text("from training import MARKER\nprint(MARKER)\n")
    module = runpy.run_path(str(copied))
    env = child.child_environment({"PATH": "/usr/bin:/bin"})
    assert "PYTHONPATH" not in env
    # The old file entrypoint cannot see the sibling package, even from repo cwd.
    old = subprocess.run(
        [sys.executable, str(script)],
        cwd=folder,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert old.returncode != 0
    assert "No module named 'training'" in old.stderr
    command, cwd = module["attempt_command"](
        script,
        folder / "inputs.json",
        folder / "output",
        deadline=123,
        resume=True,
        max_new_steps=4,
    )
    assert command[:4] == [
        sys.executable,
        "-m",
        "infrastructure.research.pilot.attempt",
        str(folder / "inputs.json"),
    ]
    assert command[-3:] == ["--resume", "--max-new-steps", "4"]
    assert cwd == folder
    result = subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "module-import-ok\n"


def test_child_diagnostics_preserve_exception_identity_without_raw_log_text(tmp_path):
    from infrastructure.research.pilot.child import child_failure

    path = tmp_path / "attempt.log"
    path.write_text(
        "fake-secret-must-not-be-published\nModuleNotFoundError: No module named 'export'\n"
    )
    value = child_failure(path, 1)
    assert value["schema"] == "voxelshogi-pilot-child-failure-v1"
    assert value["returncode"] == 1
    assert value["exception_type"] == "ModuleNotFoundError"
    assert value["missing_module"] == "export"
    assert value["log_bytes"] == path.stat().st_size
    assert "fake-secret" not in json.dumps(value)
    assert "No module named" not in json.dumps(value)


@pytest.mark.parametrize(
    "line, expected",
    [("RuntimeError: fake-secret\n", "RuntimeError"), ("not a traceback\n", None)],
)
def test_child_diagnostics_handle_other_errors_and_large_logs(tmp_path, line, expected):
    from infrastructure.research.pilot.child import child_failure

    path = tmp_path / "attempt.log"
    path.write_text("x" * 100000 + "\n" + line)
    value = child_failure(path, 2)
    assert value["exception_type"] == expected
    assert value["missing_module"] is None
    assert value["tail_bytes"] <= 32768
    assert "fake-secret" not in json.dumps(value)


def test_entrypoint_rejects_arbitrary_scripts():
    from infrastructure.research.pilot.child import attempt_command

    with pytest.raises(ValueError, match="canonical"):
        attempt_command(Path("elsewhere.py"), "inputs", "output", deadline=100)


def test_run_attempt_uses_canonical_cwd_and_attaches_safe_child_failure(
    tmp_path, monkeypatch
):
    import time

    from infrastructure.research.pilot import child

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("HF_TOKEN", "fake-parent-only-secret")

    class Process:
        returncode = 1

        def poll(self):
            return 1

    def popen(command, **kwargs):
        assert command[1:3] == ["-m", "infrastructure.research.pilot.attempt"]
        assert kwargs.get("cwd") == Path(child.__file__).resolve().parents[3]
        assert "HF_TOKEN" not in kwargs["env"]
        kwargs["stdout"].write("ModuleNotFoundError: No module named 'export'\n")
        return Process()

    monkeypatch.setattr(child.subprocess, "Popen", popen)
    caught = None
    try:
        child.run_attempt(
            Path(child.__file__).with_name("attempt.py"),
            tmp_path / "inputs.json",
            tmp_path / "continuous",
            deadline=time.time() + 60,
        )
    except RuntimeError as error:
        caught = error
    assert isinstance(caught, child.PilotChildError)
    assert caught.diagnostic["missing_module"] == "export"
    assert "fake-parent-only-secret" not in json.dumps(caught.diagnostic)


def test_cycle_persists_child_diagnostic_in_existing_published_failure_record(
    tmp_path, monkeypatch
):
    import time
    from types import SimpleNamespace

    from infrastructure.research.pilot import child, cycle

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        cycle.runpy,
        "run_path",
        lambda _path: {
            "validate_inputs": lambda _inputs: (SimpleNamespace(total_updates=7), None)
        },
    )
    diagnostic = {
        "schema": "voxelshogi-pilot-child-failure-v1",
        "exception_type": "ModuleNotFoundError",
        "missing_module": "export",
    }

    def fail(*args, **kwargs):
        raise child.PilotChildError(diagnostic)

    with pytest.raises(child.PilotChildError):
        cycle.run_cycle(
            {"source_commit": "a" * 40},
            tmp_path / "cycle",
            split_step=3,
            deadline=time.time() + 120,
            compute_deadline=time.time() + 60,
            api=None,
            fetch=None,
            upload_budget=None,
            ports={"launch": fail, "pack": None, "transfer": None, "prove": None},
        )
    failure = json.loads((tmp_path / "cycle/failure.json").read_text())
    assert failure.get("child_failure") == diagnostic
    assert failure["recovery"]["reason"] == "no-checkpoint-evidence"


def test_unknown_missing_module_is_not_published_as_arbitrary_text(tmp_path):
    from infrastructure.research.pilot.child import child_failure

    path = tmp_path / "log"
    path.write_text("ModuleNotFoundError: No module named 'fake_secret_identifier'\n")
    value = child_failure(path, 1)
    assert value["exception_type"] == "ModuleNotFoundError"
    assert value["missing_module"] is None
    assert "fake_secret_identifier" not in json.dumps(value)
