"""Attest four physical GPU UUIDs through isolated one-visible-device probes."""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from training.checkpoint import atomic_json
from training.cuda_preflight import ROOT, validate_environment_files, validate_facts

KERNEL = {
    "device": "cuda",
    "product": [[19.0, 22.0], [43.0, 50.0]],
    "left_gradient": [[11.0, 15.0], [11.0, 15.0]],
    "right_gradient": [[4.0, 4.0], [6.0, 6.0]],
}


def validate_inventory(rows):
    if type(rows) is not list or len(rows) != 4:
        raise ValueError("exactly four physical devices required")
    identifiers = []
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"uuid", "name", "driver", "vram_mib"}
            or not isinstance(row["uuid"], str)
            or not re.fullmatch(
                r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", row["uuid"]
            )
            or row["name"] != "NVIDIA GeForce RTX 5090"
            or type(row["vram_mib"]) is not int
            or row["vram_mib"] < 31000
            or not isinstance(row["driver"], str)
            or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", row["driver"])
            or int(row["driver"].split(".")[0]) < 580
        ):
            raise ValueError("unquoted physical device/UUID/runtime")
        identifiers.append(row["uuid"].lower())
    if len(set(identifiers)) != 4:
        raise ValueError("four distinct physical GPU UUIDs required")
    return deepcopy(rows)


def probe_group(rows, *, probe):
    devices = []
    for row in validate_inventory(rows):
        result = probe(deepcopy(row))
        try:
            facts = validate_facts(result["facts"])
            if (
                result["uuid"] != row["uuid"]
                or type(facts["gpu_count"]) is not int
                or facts["gpu"] != row["name"]
                or facts["driver"] != row["driver"]
                or facts["vram_mib"] != row["vram_mib"]
                or result["kernel"] != KERNEL
            ):
                raise ValueError("child UUID/runtime/kernel differs from assignment")
        except KeyError, TypeError:
            raise ValueError("incomplete child GPU attestation") from None
        devices.append(result)
    return {
        "schema": "voxelshogi-four-gpu-preflight-v1",
        "verified": True,
        "physical_gpu_count": 4,
        "devices": devices,
        "scope": "four physical UUIDs, each probed in its own one-visible-device process",
    }


def isolated_probe(row):
    if sys.platform != "linux":
        raise ValueError("GPU probes require external Linux")
    script = """import csv,json,platform,subprocess,sys
import torch
from training.cuda_preflight import kernel_probe,validate_facts
uuid=sys.argv[1]
text=subprocess.check_output(['nvidia-smi','--id='+uuid,'--query-gpu=uuid,name,driver_version,memory.total','--format=csv,noheader,nounits'],text=True)
rows=list(csv.reader(text.splitlines()));assert len(rows)==1
actual,name,driver,memory=[part.strip() for part in rows[0]];assert actual==uuid
assert torch.cuda.is_available() and torch.cuda.device_count()==1
facts=validate_facts({'system':platform.system(),'machine':platform.machine(),'python':platform.python_version(),
 'torch':str(torch.__version__),'cuda':torch.version.cuda,'cuda_available':torch.cuda.is_available(),
 'gpu_count':torch.cuda.device_count(),'gpu':torch.cuda.get_device_name(0),'driver':driver,'vram_mib':int(memory),
 'capability':list(torch.cuda.get_device_capability(0)),'compiled_arches':torch.cuda.get_arch_list()})
print(json.dumps({'uuid':actual,'facts':facts,'kernel':kernel_probe('cuda')}))
"""
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "HF_TOKEN",
            "HUGGING_FACE_HUB_TOKEN",
            "HUGGINGFACE_HUB_TOKEN",
            "VAST_API_KEY",
            "CLOUDRIFT_API_KEY",
        }
    }
    env.update(CUDA_VISIBLE_DEVICES=row["uuid"], CUBLAS_WORKSPACE_CONFIG=":4096:8")
    result = subprocess.run(
        [sys.executable, "-c", script, row["uuid"]],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return json.loads(result.stdout)


def collect_four_gpu():
    if sys.platform != "linux":
        raise ValueError("GPU inventory requires external Linux")
    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True):
        raise ValueError("GPU preflight requires clean source")
    environment = validate_environment_files(ROOT)
    text = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=uuid,name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        timeout=30,
    )
    rows = []
    for values in csv.reader(text.splitlines()):
        if len(values) != 4:
            raise ValueError("invalid physical GPU inventory")
        uuid, name, driver, memory = [part.strip() for part in values]
        rows.append(
            {"uuid": uuid, "name": name, "driver": driver, "vram_mib": int(memory)}
        )
    result = probe_group(rows, probe=isolated_probe)
    result["environment"] = environment
    result["source_commit"] = source
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / "runs"):
        parser.error("keep preflight output under ignored runs/")
    result = collect_four_gpu()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output, result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
