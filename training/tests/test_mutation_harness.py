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


def _module():
    return runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts/ci/mutation-training.py")
    )


def _catalog(count=7):
    return [
        (f"m{i}", "training/value.py", "VALUE = 1", "VALUE = 2", f"test_{i % 3}.py")
        for i in range(count)
    ]


def test_shards_keep_the_manual_partition_and_cover_the_real_catalog_once():
    module = _module()
    select = module["select_mutations"]
    catalog = _catalog()
    assert [[m[0] for m in select(catalog, shard=i, shards=4)] for i in range(4)] == [
        ["m0", "m4"],
        ["m1", "m5"],
        ["m2", "m6"],
        ["m3"],
    ]
    assert select(catalog) == catalog
    actual = module["MUTATIONS"]
    parts = [select(actual, shard=i, shards=4) for i in range(4)]
    names = [m[0] for group in parts for m in group]
    assert len(names) == len(actual) == len(set(names))
    assert set(names) == {m[0] for m in actual}
    assert all(parts)
    assert max(map(len, parts)) - min(map(len, parts)) <= 1


def test_invalid_partial_empty_or_duplicate_partition_is_rejected():
    import pytest

    select = _module()["select_mutations"]
    for settings in [
        {"shard": 0},
        {"shards": 4},
        {"shard": -1, "shards": 4},
        {"shard": 4, "shards": 4},
        {"shard": True, "shards": 4},
        {"shard": 0, "shards": 0},
        {"shard": 0, "shards": True},
        {"shard": 0, "shards": 8},
    ]:
        with pytest.raises(ValueError):
            select(_catalog(), **settings)
    for catalog in ([], [_catalog()[0], _catalog()[0]]):
        with pytest.raises(ValueError):
            select(catalog)


def test_junit_only_accepts_executed_failures_without_skips_or_errors(tmp_path):
    import pytest

    classify = _module()["classify_result"]
    report = tmp_path / "result.xml"
    cases = [
        (0, '<testcase name="ok"/>', "passed"),
        (
            1,
            '<testcase name="bad"><failure type="AssertionError"/></testcase>',
            "caught",
        ),
        (0, "", None),
        (1, "<testcase><error/></testcase>", None),
        (1, "<testcase><failure/></testcase><testcase><skipped/></testcase>", None),
        (0, "<testcase><skipped/></testcase>", None),
        (5, "<testcase><failure/></testcase>", None),
    ]
    for code, body, expected in cases:
        report.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>")
        if expected is None:
            with pytest.raises(RuntimeError):
                classify(code, report, name="fixture")
        else:
            assert classify(code, report, name="fixture") == expected


def test_shard_cli_executes_only_its_baseline_files_and_real_tiny_assertion_failures(
    tmp_path,
    monkeypatch,
):
    import json
    import sys

    module = _module()
    namespace = module["main"].__globals__
    root = tmp_path / "source"
    root.mkdir()
    for name in ("pyproject.toml", "uv.lock", ".python-version", ".gitignore"):
        (root / name).write_text("")
    for name in ("training", "export", "crates", "infrastructure"):
        (root / name).mkdir()
    workflow = (
        Path(__file__).resolve().parents[2] / ".github/workflows/vast-deadline.yml"
    ).read_text()
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/vast-deadline.yml").write_text(workflow)
    (root / "training/tests").mkdir()
    (root / "training/value.py").write_text("VALUE = 1\n")
    # Unassigned files intentionally fail: they must not enter this shard's
    # isolated baseline. The ordinary CI unit job still runs all real tests.
    (root / "training/tests/test_a.py").write_text("assert False\n")
    (root / "training/tests/test_b.py").write_text(
        "from pathlib import Path\n"
        "assert Path('.github/workflows/vast-deadline.yml').read_text() == "
        f"{workflow!r}\n"
        "assert VALUE == 1\n"
    )
    (root / "training/tests/test_c.py").write_text("assert False\n")
    mutations = [
        ("m0", "training/value.py", "VALUE = 1", "VALUE = 2", "test_a.py"),
        ("m1", "training/value.py", "VALUE = 1", "VALUE = 2", "test_b.py"),
        ("m2", "training/value.py", "VALUE = 1", "VALUE = 2", "test_c.py"),
    ]
    monkeypatch.setitem(namespace, "ROOT", root)
    monkeypatch.setitem(namespace, "MUTATIONS", mutations)
    real_run = subprocess.run
    pytest_calls = []
    tiny_tests = """import pathlib,runpy,sys,xml.etree.ElementTree as ET
report=pathlib.Path(sys.argv[1]);suite=ET.Element('testsuite');failed=False
value=runpy.run_path('training/value.py')['VALUE']
for name in sys.argv[2:]:
 case=ET.SubElement(suite,'testcase',name=name)
 try:exec(compile(pathlib.Path(name).read_text(),name,'exec'),{'VALUE':value})
 except AssertionError:
  ET.SubElement(case,'failure',type='AssertionError');failed=True
ET.ElementTree(suite).write(report)
raise SystemExit(1 if failed else 0)
"""

    def run(command, **kwargs):
        if command[0] != "uv":
            return real_run(command, **kwargs)
        targets = [part for part in command if part.startswith("training/tests/")]
        pytest_calls.append((targets, kwargs["timeout"]))
        report = next(
            part.split("=", 1)[1] for part in command if part.startswith("--junitxml=")
        )
        # Actually execute the small assertions in a subprocess and emit their
        # JUnit failures; never run real model, Rust, or data tests on Mac.
        return real_run([sys.executable, "-c", tiny_tests, report, *targets], **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    module["main"](["--shard", "1", "--shards", "2"])
    assert pytest_calls == [
        (["training/tests/test_b.py"], 180),
        (["training/tests/test_b.py"], 60),
    ]
    output = root / "coverage/training-mutations"
    assert json.loads((output / "results.json").read_text()) == [
        {"name": "m1", "outcome": "caught"}
    ]
    assert json.loads((output / "selection.json").read_text()) == {
        "shard": 1,
        "shards": 2,
        "catalog_total": 3,
        "selected": ["m1"],
    }
    assert (root / "training/value.py").read_text() == "VALUE = 1\n"


def test_partial_cli_partition_fails_before_runtime_outputs_or_processes(
    tmp_path, monkeypatch
):
    import pytest

    module = _module()
    monkeypatch.setitem(module["main"].__globals__, "ROOT", tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("must reject before process launch"),
    )
    with pytest.raises(SystemExit) as error:
        module["main"](["--shard", "0"])
    assert error.value.code == 2
    assert not (tmp_path / "coverage").exists()
