"""Small metadata-only validation of the external CUDA environment."""

import shutil

import pytest


def fixture_root(tmp_path):
    from training.supervision import ROOT

    for name in ("pyproject.toml", "uv.lock", ".python-version"):
        shutil.copy2(ROOT / name, tmp_path / name)
    shutil.copytree(
        ROOT / "infrastructure/cuda",
        tmp_path / "infrastructure/cuda",
        ignore=shutil.ignore_patterns(".venv", "__pycache__"),
    )
    return tmp_path


def test_cuda_lock_pins_python314_and_official_wheel_without_changing_cpu_ci():
    from training.cuda_preflight import validate_environment_files
    from training.supervision import ROOT

    result = validate_environment_files(ROOT)
    assert result["python"] == "3.14.9" and result["torch"] == "2.14.1+cu130"
    assert result["cuda"] == "13.0" and len(result["lock_sha256"]) == 64
    assert result["setuptools"] == "84.1.0"  # Fixes all reported 78.1.0 advisories.


@pytest.mark.parametrize(
    "file,before,after",
    [
        ("infrastructure/cuda/pyproject.toml", "explicit = true", "explicit = false"),
        ("infrastructure/cuda/pyproject.toml", "numpy==2.5.4", "numpy==2.5.3"),
        (
            "infrastructure/cuda/uv.lock",
            "https://download.pytorch.org/whl/cu130",
            "https://untrusted.invalid/whl/cu130",
        ),
        ("infrastructure/cuda/.python-version", "3.14.9", "3.13.11"),
        ("pyproject.toml", "pytorch-cpu", "pytorch-cu130"),
        ("infrastructure/cuda/uv.lock", 'version = "84.1.0"', 'version = "78.1.0"'),
    ],
)
def test_stale_or_wrong_environment_source_is_rejected(tmp_path, file, before, after):
    from training.cuda_preflight import validate_environment_files

    root = fixture_root(tmp_path)
    path = root / file
    assert before in path.read_text()
    path.write_text(path.read_text().replace(before, after))
    with pytest.raises(ValueError):
        validate_environment_files(root)
