"""External-Linux exact M inference release staging, without upload.

Copy only the evaluated three formats and their typed evidence. Keep failed
staging separate from the final package; the shared HF harness checks the same
inventory before a later, independently verified publication.
"""

import hashlib
import json
import math
import re
import shutil
import sys
import time
from pathlib import Path

from export.research_generate import _bounded
from training.checkpoint import atomic_json
from training.feature_cache import file_hash
from training.hub_release import artifact_limits, plan_release
from training.research_inference_release import (
    METADATA_BYTES,
    NAMES,
    PRECISIONS,
    ROLE,
    review_manifest,
)
from training.research_manifest_assembly import _parse
from training.research_selection import source_commit

LICENSE = Path(__file__).resolve().parents[1] / "LICENSE"
EVALUATED = {"input-audit.json", *(f"evaluation/{p}.json" for p in PRECISIONS)}
EXPECTED = {
    "README.md",
    "LICENSE",
    "manifest.json",
    "model.safetensors",
    "selection.json",
    "training-history.jsonl",
    "final-protocol.json",
    *EVALUATED,
    *(p + ".onnx" for p in PRECISIONS),
    *("inputs/" + n + ".f32" for n in NAMES),
    *(
        f"reference/{p}/{n}-{o}.f32"
        for p in PRECISIONS
        for n in NAMES
        for o in ("policy", "value")
    ),
}


def _regular(path, root):
    if root.is_symlink() or path.is_symlink():
        raise ValueError("regular release source required")
    relative = path.relative_to(root)
    if any((root / parent).is_symlink() for parent in relative.parents):
        raise ValueError("release source parent must not be a symlink")
    if not path.is_file():
        raise ValueError("complete regular release payload required")


def stage_release(
    converted,
    evaluated,
    card,
    output,
    *,
    frozen,
    manifest_sha256,
    card_sha256,
    expected_source,
    deadline,
    clock=time.time,
    stop_requested=lambda: False,
    ports=None,
):
    if sys.platform != "linux":
        raise ValueError("M release staging requires external Linux")
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("fixed release staging deadline required")

    def boundary():
        if clock() >= deadline or stop_requested():
            raise InterruptedError("fixed release staging deadline")

    boundary()
    ports = (
        {"source": source_commit, "review": review_manifest, "plan": plan_release}
        if ports is None
        else ports
    )
    if (
        set(ports) != {"source", "review", "plan"}
        or re.fullmatch(r"[0-9a-f]{40}", expected_source or "") is None
        or ports["source"]() != expected_source
    ):
        raise ValueError("clean frozen release staging source required")
    converted, evaluated, card, frozen, output = map(
        Path, (converted, evaluated, card, frozen, output)
    )
    if (
        any(p.is_symlink() or not p.is_dir() for p in (converted, evaluated))
        or output.exists()
        or output.is_symlink()
        or any(p.is_symlink() for p in output.parents)
        or any(
            output.resolve().is_relative_to(p.resolve()) for p in (converted, evaluated)
        )
    ):
        raise ValueError("regular sources and fresh separate staging output required")
    manifest_path, completion_path = (
        evaluated / "assembled-manifest.json",
        evaluated / "complete.json",
    )
    manifest_raw = _bounded(manifest_path, METADATA_BYTES)
    completion_raw = _bounded(completion_path, METADATA_BYTES)
    card_raw, license_raw = (
        _bounded(card, METADATA_BYTES),
        _bounded(LICENSE, METADATA_BYTES),
    )
    if (
        hashlib.sha256(manifest_raw).hexdigest() != manifest_sha256
        or hashlib.sha256(card_raw).hexdigest() != card_sha256
    ):
        raise ValueError("frozen manifest or reviewed Model Card bytes differ")
    manifest, completion = _parse(manifest_raw), _parse(completion_raw)
    output.mkdir(parents=True, exist_ok=False)
    pending, package = output / "pending", output / "package"
    stage = "review-evaluation-evidence"
    try:
        pending.mkdir()
        sources = {
            n: (evaluated / n, evaluated)
            if n in EVALUATED
            else (frozen, frozen.parent)
            if n == "final-protocol.json"
            else (converted / n, converted)
            for n in EXPECTED - {"README.md", "LICENSE", "manifest.json"}
        }

        def metadata(name):
            path, root = sources[name]
            _regular(path, root)
            return _bounded(
                path,
                64 * 1024**2 if name == "training-history.jsonl" else METADATA_BYTES,
            )

        audit_raw, frozen_raw = (
            metadata("input-audit.json"),
            metadata("final-protocol.json"),
        )
        if (
            completion.get("schema") != "voxelshogi-research-final-evaluation-v1"
            or completion.get("complete") is not True
            or type(completion.get("games")) is not int
            or completion["games"] != 72
            or type(completion.get("queries")) is not int
            or completion["queries"] < 1
            or completion.get("source_commit") != expected_source
            or completion.get("assembled_manifest_sha256") != manifest_sha256
            or completion.get("input_audit_sha256")
            != hashlib.sha256(audit_raw).hexdigest()
            or completion.get("frozen_sha256") != hashlib.sha256(frozen_raw).hexdigest()
            or completion.get("inference_publication_approved") is not False
        ):
            raise ValueError("same complete final72 evaluation receipt required")
        inventory = ports["review"](
            manifest,
            source_commit=expected_source,
            selection=_parse(metadata("selection.json")),
            history=metadata("training-history.jsonl"),
            frozen=_parse(frozen_raw),
            reports={p: _parse(metadata(f"evaluation/{p}.json")) for p in PRECISIONS},
            audit=_parse(audit_raw),
        )
        if set(inventory) != EXPECTED:
            raise ValueError("exact 42 required M inference files required")

        def verify(name, path, root):
            _regular(path, root)
            descriptor = inventory[name]
            maximum, _ = artifact_limits(ROLE, name)
            if (
                type(descriptor) is not dict
                or set(descriptor) != {"path", "bytes", "sha256"}
                or descriptor["path"] != name
                or type(descriptor["bytes"]) is not int
                or not 0 < descriptor["bytes"] <= maximum
                or path.stat().st_size != descriptor["bytes"]
                or file_hash(path) != descriptor["sha256"]
            ):
                raise ValueError("staged M payload bytes/hash differ")

        stage = "copy-exact-payloads"
        for name, (source, root) in sorted(sources.items()):
            boundary()
            verify(name, source, root)
            target = pending / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            verify(name, target, pending)
            boundary()
        (pending / "README.md").write_bytes(card_raw)
        (pending / "LICENSE").write_bytes(license_raw)
        (pending / "manifest.json").write_bytes(manifest_raw)
        stage = "typed-publication-plan"
        boundary()
        plan = ports["plan"](
            pending,
            repo_id=f"voxelshogi/voxelshogi-research-m-{manifest['research']['architecture']['architecture']}-v1",
            repo_type="model",
            license_id="apache-2.0",
            license_approved=True,
            source_commit=expected_source,
            artifact_role=ROLE,
        )
        stage = "source-and-input-recheck"
        for name, (source, root) in sorted(sources.items()):
            boundary()
            verify(name, source, root)
        if (
            ports["source"]() != expected_source
            or _bounded(manifest_path, METADATA_BYTES) != manifest_raw
            or _bounded(completion_path, METADATA_BYTES) != completion_raw
            or _bounded(card, METADATA_BYTES) != card_raw
            or _bounded(LICENSE, METADATA_BYTES) != license_raw
        ):
            raise ValueError("staging source or original evidence changed")
        boundary()
        atomic_json(output / "release-plan.json", plan)
        pending.rename(package)
        result = {
            "schema": "voxelshogi-research-release-staging-v1",
            "complete": True,
            "files": len(plan["files"]),
            "source_commit": expected_source,
            "manifest_sha256": manifest_sha256,
            "card_sha256": card_sha256,
            "evaluation_completion_sha256": hashlib.sha256(completion_raw).hexdigest(),
            "plan_sha256": file_hash(output / "release-plan.json"),
            "uploaded": False,
            "catalog_registered": False,
        }
        atomic_json(output / "complete.json", result)
        return result
    except BaseException as error:
        atomic_json(
            output / "failure.json",
            {
                "complete": False,
                "stage": stage,
                "error_type": type(error).__name__,
                "uploaded": False,
            },
        )
        raise


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("converted", "evaluated", "card", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--card-sha256", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--deadline", type=float, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            stage_release(
                args.converted,
                args.evaluated,
                args.card,
                args.output,
                frozen=args.frozen,
                manifest_sha256=args.manifest_sha256,
                card_sha256=args.card_sha256,
                expected_source=args.source,
                deadline=args.deadline,
            )
        )
    )


if __name__ == "__main__":
    main()
