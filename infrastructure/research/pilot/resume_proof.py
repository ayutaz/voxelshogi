"""Verify whole CUDA checkpoint parity, not just model output or final loss.

This is an external-Linux execution driver. The pure tree comparator also has
handwritten fake-tensor checks that do not execute numerical work on Mac.
"""

import argparse
import json
import sys
from pathlib import Path


def compare_tree(left, right, tensor_type, path="state"):
    counts = {"tensors": 0, "scalars": 0}

    def visit(a, b, where):
        if type(a) is not type(b):
            raise ValueError("state type differs: " + where)
        if isinstance(a, tensor_type):
            if a.dtype != b.dtype or a.shape != b.shape or not a.equal(b):
                raise ValueError("exact tensor state differs: " + where)
            counts["tensors"] += 1
        elif isinstance(a, dict):
            if a.keys() != b.keys():
                raise ValueError("state keys differ: " + where)
            for key in a:
                visit(a[key], b[key], where + "/" + str(key))
            if hasattr(a, "_metadata") or hasattr(b, "_metadata"):
                if hasattr(a, "_metadata") != hasattr(b, "_metadata"):
                    raise ValueError("tensor metadata presence differs: " + where)
                visit(a._metadata, b._metadata, where + "/_metadata")
        elif isinstance(a, (list, tuple)):
            if len(a) != len(b):
                raise ValueError("state length differs: " + where)
            for index, (x, y) in enumerate(zip(a, b, strict=True)):
                visit(x, y, where + "/" + str(index))
        elif type(a) in (str, int, float, bool, type(None)):
            if a != b:
                raise ValueError("scalar state differs: " + where)
            counts["scalars"] += 1
        else:
            raise ValueError("unsupported checkpoint type: " + where)

    visit(left, right, path)
    return counts


def verify_runs(continuous, restored, *, total_updates):
    if sys.platform != "linux":
        raise ValueError("actual CUDA resume proof requires external Linux")
    if type(total_updates) is not int or total_updates < 1:
        raise ValueError("fixed total updates required")
    import torch

    from training.checkpoint import checkpoint_receipt
    from training.evaluation_v2 import fingerprint
    from training.research_visit_fit import (
        VisitRunConfig,
        validate_binding,
        validate_history,
    )

    folders = [Path(continuous), Path(restored)]
    bindings = [json.loads((f / "run.json").read_text())["binding"] for f in folders]
    for binding in bindings:
        validate_binding(binding)
    if bindings[0] != bindings[1]:
        raise ValueError("source/data/config/environment binding differs")
    binding = bindings[0]
    config = VisitRunConfig.from_value(binding["config"])
    if config.device != "cuda" or config.total_updates != total_updates:
        raise ValueError("full CUDA schedule differs")
    events = [
        [json.loads(line) for line in (f / "events.jsonl").read_text().splitlines()]
        for f in folders
    ]
    if events[0] != events[1]:
        raise ValueError("full training/validation history differs")
    proofs = {}
    for which in ("latest", "best"):
        states, receipts = [], []
        for folder in folders:
            path, receipt = checkpoint_receipt(
                folder / "checkpoints", binding=binding, which=which
            )
            state = torch.load(path, map_location="cpu", weights_only=True)
            if (
                set(state) != {"model", "optimizer", "rng", "progress", "binding"}
                or state["binding"] != binding
                or state["progress"] != receipt["progress"]
                or not state["rng"]["cuda"]
            ):
                raise ValueError("incomplete CUDA checkpoint")
            states.append(state)
            receipts.append(receipt)
        counts = compare_tree(*states, torch.Tensor)
        if counts["tensors"] < 1:
            raise ValueError("empty tensor comparison")
        if which == "latest":
            if states[0]["progress"]["step"] != total_updates:
                raise ValueError("partial run is not full-run resume evidence")
            validate_history(events[0], config.value(), states[0]["progress"])
        proofs[which] = {
            "progress": states[0]["progress"],
            "compared": counts,
            "state_sha256": [r["sha256"] for r in receipts],
            "exact_equal": True,
        }
    return {
        "schema": "voxelshogi-research-pilot-cuda-resume-proof-v1",
        "verified": True,
        "binding_sha256": fingerprint(binding),
        "source_commit": binding["source_commit"],
        "total_updates": total_updates,
        "history_events": len(events[0]),
        "history_sha256": fingerprint(events[0]),
        "checkpoints": proofs,
        "scope": "Exact latest/best model, optimizer, Python/NumPy/Torch/CUDA RNG, progress, binding and full train/val events after restored continuation. Artifact byte hashes may differ because checkpoint serialization is not a numerical identity. Archive/HF transfer evidence is separately required.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("continuous", type=Path)
    parser.add_argument("restored", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--total-updates", type=int, required=True)
    args = parser.parse_args()
    proof = verify_runs(
        args.continuous, args.restored, total_updates=args.total_updates
    )
    from training.checkpoint import atomic_json

    atomic_json(args.output, proof)
