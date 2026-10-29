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
        "supervision-side",
        "training/supervision.py",
        'return index if side == "b" else 728 - index',
        "return index",
        "test_supervision.py",
    ),
    (
        "supervision-value-sign",
        "training/supervision.py",
        "return math.tanh(score / VALUE_SCALE)",
        "return -math.tanh(score / VALUE_SCALE)",
        "test_supervision.py",
    ),
    (
        "supervision-played-move",
        "training/supervision.py",
        'action=move_action(teacher["best_move"], row["side"]),',
        'action=move_action(row["played_move"], row["side"]),',
        "test_supervision.py",
    ),
    (
        "supervision-completed-depth",
        "training/supervision.py",
        'valid = teacher is not None and teacher["completed_depth"] >= 1',
        'valid = teacher is not None and teacher["completed_depth"] >= 0',
        "test_supervision.py",
    ),
    (
        "supervision-duplicate-target",
        "training/supervision.py",
        'if row["duplicate_of"] is not None or row["termination"] is not None or not valid:',
        'if row["termination"] is not None or not valid:',
        "test_supervision.py",
    ),
    (
        "supervision-legal-actions",
        "training/supervision.py",
        'raise ValueError("legal moves and canonical IDs differ")',
        "pass",
        "test_supervision.py",
    ),
    (
        "supervision-source",
        "training/supervision.py",
        'raise ValueError("only search rows may have search teachers")',
        "pass",
        "test_supervision.py",
    ),
    (
        "supervision-leakage",
        "training/supervision.py",
        'raise ValueError("duplicate marker differs; possible cross-split leakage")',
        "pass",
        "test_supervision.py",
    ),
    (
        "supervision-empty-split",
        "training/supervision.py",
        'raise ValueError("every split requires nonduplicate search teachers")',
        "pass",
        "test_supervision.py",
    ),
    (
        "supervision-file-hash",
        "training/supervision.py",
        'raise ValueError("corpus file hash differs")',
        "pass",
        "test_supervision.py",
    ),
    (
        "supervision-manifest-inventory",
        "training/supervision.py",
        'raise ValueError("manifest differs from verified inventory")',
        "pass",
        "test_supervision.py",
    ),
    (
        "rental-small-cpu-quote",
        "training/rental_control.py",
        '"rtx59-3-24-750-xam.1": 86400',
        '"rtx59-3-24-750-xam.1": 43200',
        "test_rental_control.py",
    ),
    (
        "rental-existing-instance",
        "training/rental_control.py",
        'raise ValueError("another VoxelShogi rental is active")',
        "pass",
        "test_rental_control.py",
    ),
    (
        "release-data-contract",
        "training/production_release.py",
        'raise ValueError("production schema or ruleset differs")',
        "pass",
        "test_production_release.py",
    ),
    (
        "release-download-revision",
        "training/production_release.py",
        'revision=receipt["hub_commit"],',
        'revision="main",',
        "test_production_release.py",
    ),
    (
        "release-hub-parent",
        "training/production_release.py",
        'if not kwargs.get("revision") and info.sha != self.parent:',
        "if False:",
        "test_production_release.py",
    ),
    (
        "release-eligible-target",
        "training/production_release.py",
        'validation["eligible_rows"] < 100000',
        "False",
        "test_production_release.py",
    ),
    (
        "release-full-regeneration",
        "training/production_release.py",
        'report.get("regenerated_bytes_match") is not True',
        "False",
        "test_production_release.py",
    ),
    (
        "release-file-bytes",
        "training/production_release.py",
        'raise ValueError("production file hashes differ")',
        "pass",
        "test_production_release.py",
    ),
    (
        "rental-budget",
        "training/rental_control.py",
        "reserved + cap > 100",
        "False",
        "test_rental_control.py",
    ),
    (
        "rental-guardian-first",
        "training/rental_control.py",
        "start_guard()  # Must be alive before the API can create a paid resource.",
        "pass  # Mutation: do not start the independent guardian.",
        "test_rental_control.py",
    ),
    (
        "rental-ownership",
        "training/rental_control.py",
        'raise ValueError("instance ownership differs; refuse to terminate")',
        "pass",
        "test_rental_control.py",
    ),
    (
        "rental-deadline",
        "training/rental_control.py",
        'while self.clock() < limits["stop_at"]:',
        'while self.clock() <= limits["stop_at"]:',
        "test_rental_control.py",
    ),
    (
        "shogitter-hand-owner",
        "training/shogitter.py",
        "amount, side, kind = change",
        "side, amount, kind = change",
        "test_shogitter.py",
    ),
    (
        "shogitter-layer",
        "training/shogitter.py",
        "(packed_y - 1) // 9",
        "(packed_y - 1) // 8",
        "test_shogitter.py",
    ),
    (
        "shogitter-source-board",
        "training/shogitter.py",
        'if actual["board"] != board or actual["hands"] != hands:',
        "if False:",
        "test_shogitter.py",
    ),
    (
        "shogitter-capture-hand",
        "training/shogitter.py",
        "if hands != expected:",
        "if False:",
        "test_shogitter.py",
    ),
    (
        "hub-community-after-upload",
        "training/hub_release.py",
        'if (\n        api.community_disabled(repo_id=plan["repo_id"], repo_type=plan["repo_type"])\n        is not True\n    ):',
        "if False:",
        "test_hub_release.py",
    ),
    (
        "hub-community-disabled",
        "training/hub_release.py",
        "if api.community_disabled(**destination) is not True:",
        "if False:",
        "test_hub_release.py",
    ),
    (
        "hub-dataset-card",
        "training/hub_release.py",
        "if section is None or not section.group(1).strip():",
        "if False:",
        "test_hub_release.py",
    ),
    (
        "mutation-runtime-exclude",
        "scripts/ci/mutation-training.py",
        'stream.write("\\n/results.xml\\n")',
        "pass",
        "test_mutation_harness.py",
    ),
    (
        "production-opening-diversity",
        "training/production.py",
        "ply >= opening_plies",
        "True",
        "test_production.py",
    ),
    (
        "production-global-duplicate",
        "training/production.py",
        'row["duplicate_of"] = seen.get(key)',
        'row["duplicate_of"] = None',
        "test_production.py",
    ),
    (
        "production-regeneration-cost",
        "training/production.py",
        "generate_seconds + validate_seconds + regenerate_seconds",
        "generate_seconds + validate_seconds",
        "test_production.py",
    ),
    (
        "production-cost-approval",
        "training/production.py",
        'if not smoke and job.get("approved") is not True:',
        "if False:",
        "test_production.py",
    ),
    (
        "production-eligible-target",
        "training/production.py",
        '100000 if job["purpose"] == "production" else 1',
        '1 if job["purpose"] == "production" else 1',
        "test_production.py",
    ),
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


def prepare_baseline_checkout(work):
    if (work / ".git").exists():
        raise ValueError("mutation baseline must have its own new Git checkout")

    def git(*args):
        return subprocess.run(
            ["git", *args],
            cwd=work,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()

    git("init", "--quiet", "--initial-branch=mutation-baseline")
    with (work / ".git/info/exclude").open("a") as stream:
        stream.write("\n/results.xml\n")
    git("add", ".")
    git(
        "-c",
        "user.name=VoxelShogi CI",
        "-c",
        "user.email=ci@voxelshogi.invalid",
        "commit",
        "--quiet",
        "-m",
        "Isolated mutation baseline",
    )
    return git("rev-parse", "HEAD")


def main():
    output = ROOT / "coverage/training-mutations"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="voxelshogi-training-mutations-") as tmp:
        work = Path(tmp)
        for name in ("pyproject.toml", "uv.lock", ".python-version", ".gitignore"):
            shutil.copy2(ROOT / name, work / name)
        for name in ("training", "export", "crates"):
            shutil.copytree(
                ROOT / name,
                work / name,
                ignore=shutil.ignore_patterns("target", "pkg", "__pycache__"),
            )
        (work / "scripts/ci").mkdir(parents=True)
        shutil.copy2(Path(__file__), work / "scripts/ci/mutation-training.py")
        prepare_baseline_checkout(work)
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
