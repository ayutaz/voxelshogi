"""Pinned external CUDA runtime and a hand-computed forward/backward probe."""

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from training.checkpoint import atomic_json, deterministic_runtime
from training.feature_cache import file_hash
from training.supervision import ROOT


def validate_environment_files(root):
    root = Path(root)
    folder = root / "infrastructure/cuda"
    config = tomllib.loads((folder / "pyproject.toml").read_text())
    cpu = tomllib.loads((root / "pyproject.toml").read_text())
    lock = tomllib.loads((folder / "uv.lock").read_text())
    cpu_lock = tomllib.loads((root / "uv.lock").read_text())
    packages = {item["name"]: item for item in lock["package"]}
    cpu_versions = {item["name"]: item["version"] for item in cpu_lock["package"]}
    dependencies = config["project"]["dependencies"]
    names = {
        re.match(r"[a-z0-9-]+", item)[0] for item in cpu["project"]["dependencies"]
    }
    pinned = {
        f"{name}=={cpu_versions[name]}" for name in names - {"torch", "voxelshogi"}
    }
    torch = packages["torch"]
    if (
        (folder / ".python-version").read_text().strip() != "3.14.9"
        or (root / ".python-version").read_text().strip() != "3.14.9"
        or config["project"]["requires-python"] != ">=3.14,<3.15"
        or config["tool"]["uv"].get("package") is not False
        or config["tool"]["uv"].get("environments")
        != ["sys_platform == 'linux' and platform_machine == 'x86_64'"]
        or config["tool"]["uv"]["sources"]
        != {
            "torch": {"index": "pytorch-cu130"},
            "voxelshogi": {"path": "../../crates/voxelshogi-python", "editable": True},
        }
        or config["tool"]["uv"]["index"]
        != [
            {
                "name": "pytorch-cu130",
                "url": "https://download.pytorch.org/whl/cu130",
                "explicit": True,
            }
        ]
        or cpu["tool"]["uv"]["sources"]["torch"]
        != [{"index": "pytorch-cpu", "marker": "sys_platform == 'linux'"}]
        or set(dependencies) != pinned | {"torch==2.14.1", "voxelshogi"}
        or any(
            packages[name]["version"] != cpu_versions[name]
            for name in names - {"torch", "voxelshogi"}
        )
        or torch["version"] != "2.14.1+cu130"
        or torch["source"] != {"registry": "https://download.pytorch.org/whl/cu130"}
        or not any(
            "cp314-cp314-manylinux_2_28_x86_64.whl" in wheel["url"]
            and urlsplit(wheel["url"]).scheme == "https"
            and urlsplit(wheel["url"]).hostname
            in {"download.pytorch.org", "download-r2.pytorch.org"}
            and re.fullmatch(r"sha256:[0-9a-f]{64}", wheel["hash"])
            for wheel in torch["wheels"]
        )
    ):
        raise ValueError(
            "CUDA lock/source differs from pinned CPU-compatible environment"
        )
    return {
        "python": "3.14.9",
        "torch": "2.14.1+cu130",
        "cuda": "13.0",
        "lock_sha256": file_hash(folder / "uv.lock"),
    }


def validate_facts(facts):
    if (
        facts["system"] != "Linux"
        or facts["machine"] != "x86_64"
        or facts["python"] != "3.14.9"
        or facts["torch"] != "2.14.1+cu130"
        or facts["cuda"] != "13.0"
        or facts["cuda_available"] is not True
        or facts["gpu_count"] != 1
        or facts["gpu"] != "NVIDIA GeForce RTX 5090"
        or facts["capability"] != [12, 0]
        or "sm_120" not in facts["compiled_arches"]
        or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", facts["driver"])
        or int(facts["driver"].split(".")[0]) < 580
        or type(facts["vram_mib"]) is not int
        or facts["vram_mib"] < 31000
    ):
        raise ValueError("GPU runtime differs from pinned CUDA/RTX5090 trial")
    return facts


def kernel_probe(device):
    if sys.platform != "linux" or device not in ("cpu", "cuda"):
        raise ValueError("probe only on external Linux CPU/CUDA")
    import torch

    deterministic_runtime()
    left = torch.tensor(
        [[1.0, 2.0], [3.0, 4.0]], device=device, dtype=torch.float32, requires_grad=True
    )
    right = torch.tensor(
        [[5.0, 6.0], [7.0, 8.0]], device=device, dtype=torch.float32, requires_grad=True
    )
    product = left @ right
    product.sum().backward()
    result = {
        "device": device,
        "product": product.detach().cpu().tolist(),
        "left_gradient": left.grad.cpu().tolist(),
        "right_gradient": right.grad.cpu().tolist(),
    }
    if result != {
        "device": device,
        "product": [[19.0, 22.0], [43.0, 50.0]],
        "left_gradient": [[11.0, 15.0], [11.0, 15.0]],
        "right_gradient": [[4.0, 4.0], [6.0, 6.0]],
    }:
        raise ValueError("kernel forward/backward differs from independent arithmetic")
    return result


def collect_facts():
    if sys.platform != "linux":
        raise ValueError("CUDA preflight requires external Linux")
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    rows = (
        subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        .stdout.strip()
        .splitlines()
    )
    if len(rows) != 1:
        raise ValueError("exactly one visible GPU is required")
    name, driver, memory = [part.strip() for part in rows[0].split(",")]
    if not torch.cuda.is_available():
        raise ValueError("Torch CUDA unavailable; no CPU fallback")
    return validate_facts(
        {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "torch": str(torch.__version__),
            "cuda": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "gpu_count": torch.cuda.device_count(),
            "gpu": name,
            "driver": driver,
            "vram_mib": int(memory),
            "capability": list(torch.cuda.get_device_capability(0)),
            "compiled_arches": torch.cuda.get_arch_list(),
        }
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / "runs"):
        parser.error("keep GPU preflight output under ignored runs/")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    environment = validate_environment_files(ROOT)
    report = {
        "schema": "voxelshogi-cuda-preflight-v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "facts": collect_facts(),
        "environment": environment,
        "kernel": kernel_probe("cuda"),
        "cpu_lock_sha256": file_hash(ROOT / "uv.lock"),
        "cuda_lock_sha256": file_hash(ROOT / "infrastructure/cuda/uv.lock"),
        "model_learning_tested": False,
    }
    atomic_json(args.output, report)
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
