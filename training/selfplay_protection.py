"""Build immutable selfplay exclusions without adopting unfinished P5-1 labels."""

import argparse
import hashlib
import re
import sys
from pathlib import Path

from training.checkpoint import atomic_json
from training.feature_cache import file_hash
from training.research_data import SCHEMA, canonical, input_identity, validate_protocol
from training.research_data_runner import (
    ROOT,
    _development_inputs,
    _frozen_inputs,
    _read,
)
from training.supervision import REVISION, RULESET

P51_REPO = "voxelshogi/voxelshogi-search-v1"
P51_REVISION = "1b86f7e83b70a69cdfa3cc0bd4e9b0886623c472"


def history_inputs(protocol, spec, saved, game_factory):
    validate_protocol(protocol)
    if spec not in protocol["games"] or saved["game"] != spec:
        raise ValueError("holdout family differs from frozen protocol")
    game = game_factory()
    record = saved["record"]
    if (
        set(record) != {"ruleset_id", "initial", "moves", "result", "termination"}
        or record["ruleset_id"] != RULESET
        or record["initial"] != game.record()["initial"]
        or type(record["moves"]) is not list
        or len(record["moves"]) > protocol["max_plies"]
    ):
        raise ValueError("invalid holdout game record")
    ids = {input_identity(game.snapshot())}
    for move in record["moves"]:
        game.play(move)  # The production factory is the Rust Game boundary.
        ids.add(input_identity(game.snapshot()))
    expected = game.record()
    natural = game.snapshot()["finished"]
    if not natural:
        if len(record["moves"]) != protocol["max_plies"]:
            raise ValueError("incomplete holdout history")
        expected.update(termination="MaxPlies", result={"Draw": {"reason": "MaxPlies"}})
    if record != expected or saved["termination_kind"] != (
        "natural" if natural else "cutoff"
    ):
        raise ValueError("holdout result differs from Rust replay")
    return ids


def assemble_protection(sources, provenance):
    if (
        set(sources) != {"m4_m6", "p5_evaluation", "p51_holdout"}
        or any(type(ids) is not set or not ids for ids in sources.values())
        or any(
            not isinstance(i, str) or not re.fullmatch(r"[0-9a-f]{64}", i)
            for ids in sources.values()
            for i in ids
        )
        or set(provenance)
        != {"m6_dataset_revision", "p5_evaluation_proof_sha256", "p51_dataset_revision"}
        or provenance["m6_dataset_revision"] != REVISION
        or provenance["p51_dataset_revision"] != P51_REVISION
        or not re.fullmatch(r"[0-9a-f]{64}", provenance["p5_evaluation_proof_sha256"])
    ):
        raise ValueError("nonempty protected sources and fixed provenance required")
    ids = sorted(set.union(*sources.values()))
    return (
        {
            "schema": "voxelshogi-protected-inputs-v1",
            "provenance": provenance,
            "ids": ids,
        },
        {
            "counts": {name: len(value) for name, value in sources.items()},
            "unique_inputs": len(ids),
            "teacher_labels_adopted": 0,
            "scope": "all M4/M6 splits, scored P5-0 continuations and all P5-1 holdout history inputs",
        },
    )


def _p51_release(folder, plan, receipt):
    from training.hub_release import _canonical, plan_release

    if (
        plan is None
        or receipt is None
        or plan["repo_id"] != P51_REPO
        or plan["repo_type"] != "dataset"
        or receipt.get("repo_id") != P51_REPO
        or receipt.get("repo_type") != "dataset"
        or receipt.get("hub_commit") != P51_REVISION
        or receipt.get("verified") is not True
        or receipt.get("dry_run") is not False
        or receipt.get("community_disabled") is not True
        or receipt.get("release_sha256")
        != hashlib.sha256(_canonical(plan).encode()).hexdigest()
    ):
        raise ValueError("verified fixed-revision P5-1 transfer required")
    current = plan_release(
        folder,
        repo_id=P51_REPO,
        repo_type="dataset",
        license_id="cc-by-4.0",
        license_approved=True,
        source_commit=plan["source_commit"],
    )
    if current != plan:
        raise ValueError("P5-1 files changed after HF verification")


def p51_holdout_inputs(folder, game_factory):
    folder = Path(folder)
    m = _read(folder / "manifest.json")
    p = m["protocol"]
    if (
        set(m)
        != {"schema", "protocol", "protocol_sha256", "writer", "games", "complete"}
        or m["schema"] != SCHEMA
        or m["protocol_sha256"] != validate_protocol(p)
        or type(m["complete"]) is not bool
        or not m["complete"]
        or len(m["games"]) != len(p["games"])
    ):
        raise ValueError(
            "complete P5-1 trajectories required; teacher validation is separate"
        )
    ids, counts = set(), {"train": 0, "val": 0, "test": 0}
    for i, saved in enumerate(m["games"]):
        spec, descriptor = p["games"][i], saved["file"]
        if (
            saved["game"] != spec
            or saved["schema"] != SCHEMA
            or saved["protocol_sha256"] != m["protocol_sha256"]
            or descriptor["path"] != f"game-{i:06d}.parquet"
        ):
            raise ValueError("P5-1 game inventory differs")
        path = folder / descriptor["path"]
        if (
            path.is_symlink()
            or path.stat().st_size != descriptor["bytes"]
            or file_hash(path) != descriptor["sha256"]
        ):
            raise ValueError("P5-1 shard bytes/hash differs")
        if spec["split"] in ("val", "test"):
            ids.update(history_inputs(p, spec, saved, game_factory))
        counts[spec["split"]] += 1
    if not ids:
        raise ValueError("P5-1 holdout histories must be nonempty")
    return ids, counts


def build_protection(
    corpus,
    control_run,
    model_run,
    p51_folder,
    output,
    *,
    p51_plan=None,
    p51_receipt=None,
):
    if sys.platform != "linux":
        raise ValueError("protected-input assembly requires external Linux")
    from voxelshogi import Game

    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("new protection output directory required")
    _p51_release(p51_folder, p51_plan, p51_receipt)
    frozen, corpus_proof = _frozen_inputs(corpus)
    proof_path = ROOT / "docs/experiments/p5-evaluation-pilot-2026-10-30.json"
    proof = _read(proof_path)
    evaluation = set()
    for name, folder in (("control", control_run), ("m6", model_run)):
        evaluation.update(_development_inputs(folder, proof["runs"][name]))
    holdout, games = p51_holdout_inputs(p51_folder, Game)
    document, audit = assemble_protection(
        {"m4_m6": frozen, "p5_evaluation": evaluation, "p51_holdout": holdout},
        {
            "m6_dataset_revision": REVISION,
            "p5_evaluation_proof_sha256": file_hash(proof_path),
            "p51_dataset_revision": P51_REVISION,
        },
    )
    audit.update(
        corpus=corpus_proof,
        p51_games=games,
        p51_transfer=p51_receipt,
        p51_manifest_sha256=file_hash(Path(p51_folder) / "manifest.json"),
    )
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "protected.json", document)
    audit["protection_sha256"] = file_hash(output / "protected.json")
    atomic_json(output / "audit.json", audit)
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "corpus",
        "control_run",
        "model_run",
        "p51_folder",
        "p51_plan",
        "p51_receipt",
        "output",
    ):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    report = build_protection(
        args.corpus,
        args.control_run,
        args.model_run,
        args.p51_folder,
        args.output,
        p51_plan=_read(args.p51_plan),
        p51_receipt=_read(args.p51_receipt),
    )
    print(canonical(report))


if __name__ == "__main__":
    main()
