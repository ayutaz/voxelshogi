"""Portable resume state as typed JSON + safetensors, no executable pickle."""

import argparse
import json
import math
import re
import sys
from collections import OrderedDict
from pathlib import Path

from training.checkpoint import (
    _progress,
    _save_payload,
    atomic_json,
    checkpoint_receipt,
)
from training.feature_cache import canonical, file_hash
from training.fit import RunConfig
from training.supervision import ROOT, label_contract

SCHEMA = "voxelshogi-resume-archive-v1"
SELFPLAY_SCHEMA = "voxelshogi-selfplay-resume-archive-v1"
PAYLOAD_FIELDS = {"model", "optimizer", "rng", "progress", "binding"}


def _linux():
    if sys.platform != "linux":
        raise ValueError("resume state execution requires external Linux")


def encode_tree(value):
    _linux()
    import torch

    tensors = {}

    def encode(item, depth=0):
        if depth > 128:
            raise ValueError("state tree nesting exceeds limit")
        if type(item) is torch.Tensor:
            if (
                item.dtype
                not in (
                    torch.float32,
                    torch.float64,
                    torch.int64,
                    torch.int32,
                    torch.uint8,
                    torch.bool,
                )
                or item.layout != torch.strided
                or len(tensors) >= 10000
            ):
                raise ValueError("unsupported resume tensor")
            if torch.is_floating_point(item) and not torch.isfinite(item).all():
                raise ValueError("nonfinite resume tensor")
            name = f"t{len(tensors):06d}"
            tensors[name] = item.detach().cpu().contiguous().clone()
            return {"type": "tensor", "name": name}
        if type(item) in (dict, OrderedDict):
            if any(type(key) not in (str, int) for key in item):
                raise ValueError("resume dict requires string/integer keys")
            result = {
                "type": "ordered_dict" if type(item) is OrderedDict else "dict",
                "items": [
                    [encode(key, depth + 1), encode(part, depth + 1)]
                    for key, part in item.items()
                ],
            }
            if type(item) is OrderedDict:
                if set(vars(item)) - {"_metadata"}:
                    raise ValueError("unknown OrderedDict attributes")
                result["has_metadata"] = hasattr(item, "_metadata")
                result["metadata"] = encode(getattr(item, "_metadata", None), depth + 1)
            return result
        if type(item) in (list, tuple):
            return {
                "type": "list" if type(item) is list else "tuple",
                "items": [encode(part, depth + 1) for part in item],
            }
        if item is None:
            return {"type": "none"}
        if type(item) in (str, int, bool, float):
            if type(item) is float and not math.isfinite(item):
                raise ValueError("nonfinite resume scalar")
            return {"type": type(item).__name__, "value": item}
        raise ValueError("state contains an unsupported Python object")

    return encode(value), tensors


def decode_tree(tree, tensors):
    _linux()
    import torch

    used = set()
    nodes = 0

    def decode(item, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 100000 or depth > 128 or not isinstance(item, dict):
            raise ValueError("invalid resume tree dimensions")
        kind = item.get("type")
        if kind == "tensor" and set(item) == {"type", "name"}:
            name = item["name"]
            if (
                not re.fullmatch(r"t[0-9]{6}", name)
                or name in used
                or name not in tensors
            ):
                raise ValueError("missing/repeated resume tensor")
            value = tensors[name]
            if (
                type(value) is not torch.Tensor
                or value.dtype
                not in (
                    torch.float32,
                    torch.float64,
                    torch.int64,
                    torch.int32,
                    torch.uint8,
                    torch.bool,
                )
                or (torch.is_floating_point(value) and not torch.isfinite(value).all())
            ):
                raise ValueError("invalid/nonfinite resume tensor")
            used.add(name)
            return value
        if kind in ("dict", "ordered_dict"):
            expected = {"type", "items"} | (
                {"has_metadata", "metadata"} if kind == "ordered_dict" else set()
            )
            if set(item) != expected or not isinstance(item["items"], list):
                raise ValueError("invalid resume dictionary")
            value = OrderedDict() if kind == "ordered_dict" else {}
            for pair in item["items"]:
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ValueError("invalid resume dictionary entry")
                key, part = decode(pair[0], depth + 1), decode(pair[1], depth + 1)
                if type(key) not in (str, int) or key in value:
                    raise ValueError("invalid/repeated resume dictionary key")
                value[key] = part
            if kind == "ordered_dict":
                if type(item["has_metadata"]) is not bool:
                    raise ValueError("invalid metadata flag")
                metadata = decode(item["metadata"], depth + 1)
                if item["has_metadata"]:
                    value._metadata = metadata
                elif metadata is not None:
                    raise ValueError("unexpected OrderedDict metadata")
            return value
        if (
            kind in ("list", "tuple")
            and set(item) == {"type", "items"}
            and isinstance(item["items"], list)
        ):
            value = [decode(part, depth + 1) for part in item["items"]]
            return value if kind == "list" else tuple(value)
        if kind == "none" and set(item) == {"type"}:
            return None
        types = {"str": str, "int": int, "bool": bool, "float": float}
        if (
            kind in types
            and set(item) == {"type", "value"}
            and type(item["value"]) is types[kind]
        ):
            value = item["value"]
            if kind == "float" and not math.isfinite(value):
                raise ValueError("nonfinite resume scalar")
            return value
        raise ValueError("unknown resume tree node; no dynamic Python types allowed")

    result = decode(tree)
    if used != set(tensors):
        raise ValueError("unused tensors in resume state")
    return result


def _schema(profile):
    if profile not in ("m6", "selfplay"):
        raise ValueError("unknown resume archive profile")
    return SCHEMA if profile == "m6" else SELFPLAY_SCHEMA


def _binding(binding, *, profile="m6"):
    _schema(profile)
    if set(binding) != {
        "source_commit",
        "cache_sha256",
        "config",
        "contract",
        "environment",
    }:
        raise ValueError("resume run binding fields differ")
    config = binding["config"]
    if profile == "selfplay":
        from training.selfplay_training import TrainConfig

        contract = binding["contract"]
        if (
            type(contract) is not dict
            or set(contract)
            != {
                "schema",
                "source_commit",
                "parent_model_sha256",
                "generation",
                "architecture",
            }
            or contract["schema"] != "voxelshogi-selfplay-training-v1"
            or contract["source_commit"] != binding["source_commit"]
            or not re.fullmatch(r"[0-9a-f]{40}", binding["source_commit"])
            or not re.fullmatch(r"[0-9a-f]{64}", binding["cache_sha256"])
            or not isinstance(contract["parent_model_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", contract["parent_model_sha256"])
            or type(contract["generation"]) is not int
            or not 0 <= contract["generation"] < 64
            or not isinstance(contract["architecture"], str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", contract["architecture"])
        ):
            raise ValueError(
                "selfplay resume parent/generation/source contract differs"
            )
        try:
            actual = TrainConfig(
                **{key: config[key] for key in TrainConfig.__dataclass_fields__}
            ).value()
        except (KeyError, TypeError) as error:
            raise ValueError("selfplay resume config differs") from error
        if actual != config:
            raise ValueError("selfplay resume config differs")
        return
    if (
        binding["contract"] != label_contract()
        or not re.fullmatch(r"[0-9a-f]{40}", binding["source_commit"])
        or not re.fullmatch(r"[0-9a-f]{64}", binding["cache_sha256"])
        or RunConfig(
            **{key: config[key] for key in RunConfig.__dataclass_fields__}
        ).value()
        != config
    ):
        raise ValueError("resume run input/config/contract differs")


def _descriptor(folder, path):
    return {
        "path": path.relative_to(folder).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_hash(path),
    }


def _history(path):
    allowed = {
        "event",
        "attempt",
        "step",
        "elapsed_seconds",
        "epoch",
        "ids",
        "examples",
        "policy_loss",
        "value_mse",
        "loss",
        "gradient_norm",
        "value_mae",
        "policy_top1",
        "policy_top5",
        "raw_legal_rate",
        "masked_legal_rate",
        "reason",
    }
    events = []
    if path.exists():
        if path.is_symlink():
            raise ValueError("history must be a regular file")
        for line in path.read_text().splitlines():
            event = json.loads(line)
            if set(event) - allowed or event.get("event") not in (
                "train",
                "validation",
                "finish",
            ):
                raise ValueError("unknown raw log fields cannot enter a resume archive")
            canonical(event)
            events.append(event)
    return {"schema": "voxelshogi-training-history-v1", "events": events}


def pack_run(source, output, *, profile="m6"):
    _linux()
    import torch
    from safetensors.torch import save_file

    source, output = Path(source), Path(output)
    if source.is_symlink() or (source / "run.json").is_symlink():
        raise ValueError("source run must be a real directory")
    run = json.loads((source / "run.json").read_text())
    if run.get("schema") != "voxelshogi-training-run-v1":
        raise ValueError("unsupported training run")
    binding = run["binding"]
    _binding(binding, profile=profile)
    index = json.loads((source / "checkpoints/latest.json").read_text())
    selected = ["latest"] + (["best"] if index.get("best") is not None else [])
    if profile == "selfplay" and "best" in selected:
        raise ValueError("selfplay archive must not contain best selection")
    prepared = {}
    for role in selected:
        path, receipt = checkpoint_receipt(
            source / "checkpoints", binding=binding, which=role
        )
        payload = torch.load(path, map_location="cpu", weights_only=True)
        if (
            set(payload) != PAYLOAD_FIELDS
            or payload["binding"] != binding
            or payload["progress"] != receipt["progress"]
        ):
            raise ValueError("resume payload differs from verified receipt")
        prepared[role] = (payload, receipt)
    history = _history(source / "events.jsonl")
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "config.json", run)
    atomic_json(output / "history.json", history)
    files = [
        _descriptor(output, output / name) for name in ("config.json", "history.json")
    ]
    roles = {}
    for role, (payload, receipt) in prepared.items():
        folder = output / role
        folder.mkdir()
        tree, tensors = encode_tree(payload)
        save_file(tensors, folder / "state.safetensors")
        atomic_json(folder / "config.json", tree)
        descriptors = [
            _descriptor(output, folder / name)
            for name in ("config.json", "state.safetensors")
        ]
        files.extend(descriptors)
        roles[role] = {
            "progress": payload["progress"],
            "source_checkpoint_sha256": receipt["sha256"],
            "files": descriptors,
        }
    manifest = {
        "schema": _schema(profile),
        "purpose": "resume-state",
        "binding": binding,
        "roles": roles,
        "files": files,
        "complete": True,
    }
    atomic_json(output / "manifest.json", manifest)
    return manifest


def verify_archive(folder, *, expected_binding, profile="m6"):
    folder = Path(folder)
    if (
        folder.is_symlink()
        or not (folder / "manifest.json").is_file()
        or (folder / "manifest.json").is_symlink()
    ):
        raise ValueError("incomplete resume archive")
    manifest = json.loads((folder / "manifest.json").read_text())
    _binding(expected_binding, profile=profile)
    if (
        manifest.get("schema") != _schema(profile)
        or manifest.get("purpose") != "resume-state"
        or manifest.get("complete") is not True
        or manifest["binding"] != expected_binding
        or not {"latest"} <= set(manifest["roles"]) <= {"latest", "best"}
    ):
        raise ValueError("resume archive schema/binding differs")
    if profile == "selfplay" and (
        set(manifest["roles"]) != {"latest"}
        or manifest["roles"]["latest"]["progress"]["best_val_loss"] is not None
    ):
        raise ValueError("selfplay archive cannot contain best selection")
    expected = {"config.json", "history.json"} | {
        f"{role}/{name}"
        for role in manifest["roles"]
        for name in ("config.json", "state.safetensors")
    }
    if (
        len(manifest["files"]) != len(expected)
        or {entry["path"] for entry in manifest["files"]} != expected
    ):
        raise ValueError("resume archive inventory differs")
    for entry in manifest["files"]:
        path = folder / entry["path"]
        if (
            any(
                parent.is_symlink()
                for parent in path.parents
                if parent != folder and parent.is_relative_to(folder)
            )
            or not path.resolve().is_relative_to(folder.resolve())
            or path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != entry["bytes"]
            or file_hash(path) != entry["sha256"]
        ):
            raise ValueError("resume archive size/hash differs")
    run = json.loads((folder / "config.json").read_text())
    if run != {"schema": "voxelshogi-training-run-v1", "binding": expected_binding}:
        raise ValueError("archived run binding differs")
    for role, descriptor in manifest["roles"].items():
        _progress(descriptor["progress"])
        if role == "best" and descriptor["progress"]["best_val_loss"] is None:
            raise ValueError("best resume state requires a validation loss")
        if not re.fullmatch(r"[0-9a-f]{64}", descriptor["source_checkpoint_sha256"]):
            raise ValueError("resume source checkpoint hash differs")
        if descriptor["files"] != [
            entry for entry in manifest["files"] if entry["path"].startswith(role + "/")
        ]:
            raise ValueError("resume role files differ")
    return manifest


def restore_run(archive, output, *, expected_binding, profile="m6"):
    _linux()
    from safetensors.torch import load_file

    archive, output = Path(archive), Path(output)
    manifest = verify_archive(
        archive, expected_binding=expected_binding, profile=profile
    )
    decoded = {}
    for role, descriptor in manifest["roles"].items():
        tree = json.loads((archive / role / "config.json").read_text())
        tensors = load_file(archive / role / "state.safetensors", device="cpu")
        state = decode_tree(tree, tensors)
        if (
            set(state) != PAYLOAD_FIELDS
            or state["binding"] != expected_binding
            or state["progress"] != descriptor["progress"]
        ):
            raise ValueError("decoded resume payload binding/progress differs")
        decoded[role] = state
    history = json.loads((archive / "history.json").read_text())
    if history["schema"] != "voxelshogi-training-history-v1" or not isinstance(
        history["events"], list
    ):
        raise ValueError("archive training history differs")
    output.mkdir(parents=True, exist_ok=False)
    for role in ("best", "latest"):
        if role in decoded:
            _save_payload(output / "checkpoints", decoded[role], best=role == "best")
    (output / "events.jsonl").write_text(
        "".join(canonical(event) + "\n" for event in history["events"])
    )
    atomic_json(
        output / "restoration.json",
        {
            "schema": _schema(profile),
            "verified": True,
            "archive_manifest_sha256": file_hash(archive / "manifest.json"),
            "source_checkpoints": {
                role: value["source_checkpoint_sha256"]
                for role, value in manifest["roles"].items()
            },
        },
    )
    # run.json is the commit point; fit cannot resume before all state exists.
    atomic_json(
        output / "run.json",
        {"schema": "voxelshogi-training-run-v1", "binding": expected_binding},
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("pack", "restore"))
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-run", type=Path)
    parser.add_argument("--profile", choices=("m6", "selfplay"), default="m6")
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / "runs"):
        parser.error("keep private archives/restores under runs/ on external Linux")
    if args.operation == "pack":
        result = pack_run(args.source, args.output, profile=args.profile)
    else:
        if args.expected_run is None:
            parser.error("restore requires the reviewed --expected-run binding")
        binding = json.loads(args.expected_run.read_text())["binding"]
        result = restore_run(
            args.source, args.output, expected_binding=binding, profile=args.profile
        )
    print(
        canonical(
            {
                "schema": result["schema"],
                "roles": {
                    role: value["progress"] for role, value in result["roles"].items()
                },
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
