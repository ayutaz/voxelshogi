"""Known model-contract regressions; only executed failing assertions count."""

import json
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MUTATIONS = [
    ("white-axes", "pieces = pieces[::-1]", "pieces = pieces"),
    ("hand-owner", "counts = counts[::-1]", "counts = counts"),
    ("promotion-label", "+ int(promote)", "+ 0"),
    ("output-tolerance", "if exceeded:", "if False:"),
    ("finite-reference", "not np.isfinite(expected).all() or ", ""),
]


def main():
    output = ROOT / "coverage/python-mutations"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="voxelshogi-python-mutations-") as tmp:
        work = Path(tmp)
        for name in ["pyproject.toml", "uv.lock", ".python-version"]:
            shutil.copy2(ROOT / name, work / name)
        shutil.copytree(
            ROOT / "export",
            work / "export",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        env = {
            **os.environ,
            "UV_PROJECT_ENVIRONMENT": str(ROOT / ".venv"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

        def run(name):
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
                    "export/tests/test_contract.py",
                    f"--junitxml={report}",
                ],
                cwd=work,
                check=False,
                env=env,
                text=True,
                capture_output=True,
                timeout=60,
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
                f"{name}: infrastructure/collection/timeout failure is not a caught mutation"
            )

        assert run("baseline") == "passed"
        path = work / "export/contract.py"
        original = path.read_text()
        for name, before, after in MUTATIONS:
            assert original.count(before) == 1, f"stale mutation: {name}"
            try:
                path.write_text(original.replace(before, after))
                outcome = run(name)
                results.append({"name": name, "outcome": outcome})
                print(f"{name}: {outcome}", flush=True)
                assert outcome == "caught", f"surviving mutation: {name}"
            finally:
                path.write_text(original)
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
