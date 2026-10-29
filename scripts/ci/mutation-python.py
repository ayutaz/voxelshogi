"""Known model-contract regressions; only executed failing assertions count."""

import json
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_MUTATIONS = [
    ("white-axes", "pieces = pieces[::-1]", "pieces = pieces"),
    ("hand-owner", "counts = counts[::-1]", "counts = counts"),
    ("promotion-label", "+ int(promote)", "+ 0"),
    ("output-tolerance", "if exceeded:", "if False:"),
    ("finite-reference", "not np.isfinite(expected).all() or ", ""),
]
MUTATIONS = [
    (name, "contract.py", before, after, "test_contract.py")
    for name, before, after in CONTRACT_MUTATIONS
] + [
    (
        "fp16-storage-dtype",
        "variants.py",
        "values.astype(np.float16)",
        "values.astype(np.float32)",
        "test_fp16_weights.py",
    ),
    (
        "fp16-storage-cast",
        "variants.py",
        "to=TensorProto.FLOAT",
        "to=TensorProto.FLOAT16",
        "test_fp16_weights.py",
    ),
    (
        "fp16-storage-overflow",
        "variants.py",
        "np.any(np.abs(values) > 65504)",
        "False",
        "test_fp16_weights.py",
    ),
    (
        "trained-policy-bound",
        "numeric.py",
        "return 1e-4, 1e-4",
        "return 1e-3, 1e-4",
        "test_trained_numeric.py",
    ),
    (
        "trained-value-isolation",
        "numeric.py",
        'and output == "policy"',
        "and True",
        "test_trained_numeric.py",
    ),
    (
        "trained-default-isolation",
        "numeric.py",
        "numeric_contract == TRAINED_NUMERIC_CONTRACT",
        "True",
        "test_trained_numeric.py",
    ),
    (
        "trained-unknown-contract",
        "numeric.py",
        "if numeric_contract not in (None, TRAINED_NUMERIC_CONTRACT):",
        "if False:",
        "test_trained_numeric.py",
    ),
    (
        "attention-axis",
        "model.py",
        "scores.softmax(dim=-1)",
        "scores.softmax(dim=-2)",
        "test_model.py",
    ),
    (
        "policy-layout",
        "model.py",
        "pair.permute(0, 2, 3, 1)",
        "pair.permute(0, 2, 1, 3)",
        "test_model.py",
    ),
    (
        "model-seed",
        "model.py",
        "torch.manual_seed(seed)",
        "torch.manual_seed(SEED)",
        "test_model.py",
    ),
    (
        "unused-block-weights",
        "model.py",
        "self.blocks(self.input(features) + self.position)",
        "self.input(features) + self.position",
        "test_model.py",
    ),
    (
        "package-hash",
        "generate.py",
        'or digest(path) != file.get("sha256")',
        "or False",
        "test_generate.py",
    ),
    ("quant-rounding", "variants.py", "np.rint(", "np.floor(", "test_variants.py"),
    (
        "quant-scale",
        "variants.py",
        "maximum / 127",
        "maximum / 128",
        "test_variants.py",
    ),
    (
        "quant-zero-point",
        "variants.py",
        "return quantized, scale, np.int8(0)",
        "return quantized, scale, np.int8(1)",
        "test_variants.py",
    ),
    (
        "quant-missing-dequant",
        "variants.py",
        '[weight.name],\n                name=prefix + "__dequantize",',
        '[prefix + "__unused"],\n                name=prefix + "__dequantize",',
        "test_variants.py",
    ),
    (
        "fp16-io-types",
        "variants.py",
        "keep_io_types=True",
        "keep_io_types=False",
        "test_variants.py",
    ),
    (
        "quant-extra-approximation",
        "generate.py",
        'if precision == "int8"\n        else',
        "if False\n        else",
        "test_generate.py",
    ),
]


def main():
    output = ROOT / "coverage/python-mutations"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="voxelshogi-python-mutations-") as tmp:
        work = Path(tmp)
        for name in ["pyproject.toml", "uv.lock", ".python-version"]:
            shutil.copy2(ROOT / name, work / name)
        # uv verifies workspace members even when using the existing environment.
        shutil.copytree(
            ROOT / "crates/voxelshogi-python",
            work / "crates/voxelshogi-python",
            ignore=shutil.ignore_patterns("__pycache__", "*.so", "target"),
        )
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
                    f"export/tests/{tests}",
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
        for name, file, before, after, tests in MUTATIONS:
            path = work / "export" / file
            original = path.read_text()
            assert original.count(before) == 1, f"stale mutation: {name}"
            try:
                path.write_text(original.replace(before, after))
                outcome = run(name, tests)
                results.append({"name": name, "outcome": outcome})
                print(f"{name}: {outcome}", flush=True)
                assert outcome == "caught", f"surviving mutation: {name}"
            finally:
                path.write_text(original)
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
