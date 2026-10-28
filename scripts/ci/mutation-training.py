"""Known Python boundary/data/resource regressions; require executed failures."""

import json
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "crates/voxelshogi-python/python/voxelshogi"
MUTATIONS = [
    (
        "hub-namespace",
        "training/hub_release.py",
        'r"voxelshogi/[A-Za-z0-9][A-Za-z0-9._-]*"',
        'r"[A-Za-z0-9]+/[A-Za-z0-9][A-Za-z0-9._-]*"',
        "test_hub_release.py",
    ),
    (
        "hub-public-creation",
        "training/hub_release.py",
        "api.create_repo(**destination, private=False)",
        "api.create_repo(**destination, private=True)",
        "test_hub_release.py",
    ),
    (
        "hub-manual-gate",
        "training/hub_release.py",
        'if info.private or info.gated != "manual":',
        "if info.private:",
        "test_hub_release.py",
    ),
    (
        "hub-reviewed-inventory",
        "training/hub_release.py",
        "if current != plan:",
        "if False:",
        "test_hub_release.py",
    ),
    (
        "hub-transfer-hash",
        "training/hub_release.py",
        'digest.hexdigest() != file["sha256"]',
        "False",
        "test_hub_release.py",
    ),
    (
        "pilot-selected-gpu",
        "training/pilot.py",
        'gpu["name"] not in names',
        "False",
        "test_pilot.py",
    ),
    (
        "pilot-vram-boundary",
        "training/pilot.py",
        '"rtx5090": ("RTX 5090", 30000)',
        '"rtx5090": ("RTX 5090", 29999)',
        "test_pilot.py",
    ),
    (
        "pilot-throughput",
        "training/pilot.py",
        '"samples_per_second": len(samples) / total',
        '"samples_per_second": teachers / total',
        "test_pilot.py",
    ),
    (
        "pilot-teacher-depth",
        "training/pilot.py",
        'sample["completed_depth"] >= 1',
        'sample["completed_depth"] >= 0',
        "test_pilot.py",
    ),
    (
        "pilot-single-gpu",
        "training/pilot.py",
        "len(rows) != 1",
        "len(rows) < 1",
        "test_pilot.py",
    ),
    (
        "pilot-linux-only",
        "training/pilot.py",
        'system != "linux"',
        'system not in ("linux", "darwin")',
        "test_pilot.py",
    ),
    (
        "atomic-initial-ownership",
        "training/data.py",
        "(directory / OWNER_FILE).touch(exist_ok=False)",
        "pass",
        "test_data.py",
    ),
    (
        "interrupted-group-cleanup",
        "training/runner.py",
        "if process is not None and not cleaned:",
        "if process is not None and process.poll() is None and not cleaned:",
        "test_runner.py",
    ),
    (
        "teacher-verification",
        "training/data.py",
        'if row["teacher"] != (canonical(teacher) if teacher is not None else None):',
        "if False:",
        "test_data.py",
    ),
    (
        "white-features",
        f"{PACKAGE}/__init__.py",
        "board = board[::-1]",
        "board = board",
        "test_engine.py",
    ),
    (
        "white-actions",
        f"{PACKAGE}/__init__.py",
        "else 728 - index",
        "else index",
        "test_engine.py",
    ),
    (
        "promoted-action",
        f"{PACKAGE}/__init__.py",
        '+ text.endswith("+")',
        "+ 0",
        "test_engine.py",
    ),
    (
        "actor-reward",
        f"{PACKAGE}/env.py",
        "1.0 if winner == actor else -1.0",
        "-1.0 if winner == actor else 1.0",
        "test_engine.py",
    ),
    (
        "resume-config",
        "training/data.py",
        "if old.value() != config.value():",
        "if False:",
        "test_data.py",
    ),
    (
        "shard-hash",
        "training/data.py",
        'if digest(directory / entry["file"]) != entry["sha256"]:',
        "if False:",
        "test_data.py",
    ),
    (
        "duplicate-exclusion",
        "training/data.py",
        'if row["duplicate_of"] != seen.get(key):',
        "if False:",
        "test_data.py",
    ),
    (
        "teacher-eligibility",
        "training/data.py",
        '"teacher_valid": teacher is not None\n                and teacher["completed_depth"] >= 1\n                and teacher["score"] is not None,',
        '"teacher_valid": teacher is not None,',
        "test_data.py",
    ),
    (
        "time-boundary",
        "training/runner.py",
        "if elapsed >= seconds:",
        "if elapsed > seconds:",
        "test_runner.py",
    ),
    (
        "rss-boundary",
        "training/runner.py",
        "if rss >= rss_limit",
        "if rss > rss_limit",
        "test_runner.py",
    ),
    (
        "session-budget",
        "training/runner.py",
        "if remaining <= 0:",
        "if remaining < 0:",
        "test_runner.py",
    ),
    (
        "pressure-stop",
        "training/runner.py",
        'if observation["pressure"]',
        "if False",
        "test_runner.py",
    ),
]


def main():
    output = ROOT / "coverage/training-mutations"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="voxelshogi-training-mutations-") as tmp:
        work = Path(tmp)
        for name in ("pyproject.toml", "uv.lock", ".python-version"):
            shutil.copy2(ROOT / name, work / name)
        for name in ("training", "export", "crates"):
            shutil.copytree(
                ROOT / name,
                work / name,
                ignore=shutil.ignore_patterns("target", "pkg", "__pycache__"),
            )
        env = {
            **os.environ,
            "UV_PROJECT_ENVIRONMENT": str(ROOT / ".venv"),
            "PYTHONPATH": os.pathsep.join(
                [str(work / "crates/voxelshogi-python/python"), str(work)]
            ),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

        def run(name, tests=""):
            report = work / "results.xml"
            report.unlink(missing_ok=True)
            result = subprocess.run(
                [
                    "uv",
                    "run",
                    "--locked",
                    "--no-sync",
                    "pytest",
                    "-q",
                    f"training/tests/{tests}",
                    f"--junitxml={report}",
                ],
                cwd=work,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            (output / f"{name}.log").write_text(result.stdout + result.stderr)
            suites = ET.parse(report).getroot()
            cases = suites.findall(".//testcase")
            failures, errors = suites.findall(".//failure"), suites.findall(".//error")
            if (
                result.returncode == 0
                and cases
                and not failures
                and not errors
                and not suites.findall(".//skipped")
            ):
                return "passed"
            if result.returncode == 1 and failures and not errors:
                return "caught"
            raise RuntimeError(
                f"{name}: collection/infrastructure/timeouts are not caught mutations"
            )

        assert run("baseline") == "passed"
        for name, file, before, after, tests in MUTATIONS:
            path = work / file
            original = path.read_text()
            # Eligibility is deliberately duplicated in the independent verifier;
            # mutate the producer only and let the verifier/tests detect it.
            assert original.count(before) == 1, f"stale/ambiguous mutation: {name}"
            try:
                path.write_text(original.replace(before, after, 1))
                outcome = run(name, tests)
                results.append({"name": name, "outcome": outcome})
                print(f"{name}: {outcome}", flush=True)
                assert outcome == "caught", f"surviving mutation: {name}"
            finally:
                path.write_text(original)
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
