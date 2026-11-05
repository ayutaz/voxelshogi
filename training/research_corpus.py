"""Family-level research corpus admission without weakening historical protection.

Pure metadata selection is safe on Mac. Actual published dataset enumeration,
Rust replay and frozen-root checks require external Linux. This module neither
trains models nor converts cutoff/bootstrap values into terminal draw labels.
"""

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from training.evaluation_v2 import fingerprint, validate_protocol
from training.feature_cache import file_hash

SPLITS = ("train", "val", "test")
PRIORITY = {"train": 0, "val": 1, "test": 2}


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _ids(value, *, nonempty=False):
    return (
        type(value) is set
        and (bool(value) or not nonempty)
        and all(_sha(x) for x in value)
    )


def _linux():
    if sys.platform != "linux":
        raise ValueError("real research corpus audit requires external Linux")


def family_partition(families, *, seed=67011):
    """Keep two val/test families each; remaining whole opening families train."""
    if (
        type(families) not in (list, tuple)
        or not 6 <= len(families) <= 4096
        or any(not _sha(x) for x in families)
        or len(set(families)) != len(families)
        or type(seed) is not int
        or not 0 <= seed < 2**63
    ):
        raise ValueError("nonempty unique research families and integer seed required")
    ranked = sorted(
        families,
        key=lambda x: hashlib.sha256(
            f"p6-family-split-v1:{seed}:{x}".encode()
        ).hexdigest(),
    )
    train_end = len(ranked) - 4
    return {
        family: "train" if i < train_end else "val" if i < train_end + 2 else "test"
        for i, family in enumerate(ranked)
    }


def admit_metadata(
    rows,
    families,
    *,
    protected_inputs,
    final_roots,
    development_inputs=None,
    minimum_rows=None,
):
    development_inputs = set() if development_inputs is None else development_inputs
    minimum_rows = (
        {"train": 256, "val": 64, "test": 64} if minimum_rows is None else minimum_rows
    )
    if (
        type(rows) is not list
        or not 1 <= len(rows) <= 1_000_000
        or type(families) is not dict
        or any(not _sha(k) or v not in SPLITS for k, v in families.items())
        or any(list(families.values()).count(split) < 2 for split in SPLITS)
        or not _ids(protected_inputs, nonempty=True)
        or not _ids(final_roots)
        or len(final_roots) != 12
        or not _ids(development_inputs)
        or type(minimum_rows) is not dict
        or set(minimum_rows) != set(SPLITS)
        or any(
            type(n) is not int or not 1 <= n <= 1_000_000 for n in minimum_rows.values()
        )
    ):
        raise ValueError("invalid research corpus split/protection/count contract")
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"id", "family", "input", "value_kind", "ply"}
            or not isinstance(row["id"], str)
            or not 1 <= len(row["id"]) <= 160
            or not _sha(row["family"])
            or row["family"] not in families
            or not _sha(row["input"])
            or row["value_kind"] not in ("terminal-v1", "bootstrap-v1")
            or type(row["ply"]) is not int
            or not 0 <= row["ply"] <= 20000
        ):
            raise ValueError("invalid research sample metadata")
    if len({r["id"] for r in rows}) != len(rows) or {r["family"] for r in rows} != set(
        families
    ):
        raise ValueError("repeated sample ID or incomplete research family enumeration")
    roles = {
        "legacy": protected_inputs,
        "final_roots": final_roots,
        "development": development_inputs,
    }
    blocked = set.union(*roles.values())
    eligible = [(i, r) for i, r in enumerate(rows) if r["input"] not in blocked]
    priorities = {}
    for _, row in eligible:
        priorities[row["input"]] = max(
            priorities.get(row["input"], -1), PRIORITY[families[row["family"]]]
        )
    selected = {s: [] for s in SPLITS}
    seen, cross_split, repeated = set(), 0, 0
    for i, row in sorted(eligible, key=lambda item: item[1]["id"]):
        split = families[row["family"]]
        if PRIORITY[split] != priorities[row["input"]]:
            cross_split += 1
        elif row["input"] in seen:
            repeated += 1
        else:
            selected[split].append(i)
            seen.add(row["input"])
    counts = {
        "raw_samples": len(rows),
        "retained": len(seen),
        "excluded_protected": len(rows) - len(eligible),
        "excluded_cross_split": cross_split,
        "excluded_repeated_inputs": repeated,
    }
    n_rows = {s: len(indices) for s, indices in selected.items()}
    n_families = {
        s: len({rows[i]["family"] for i in indices}) for s, indices in selected.items()
    }
    ids = {s: [rows[i]["id"] for i in indices] for s, indices in selected.items()}
    selection = [{**rows[i], "split": s} for s in SPLITS for i in selected[s]]
    return {
        "schema": "voxelshogi-research-corpus-admission-v1",
        "indices_by_split": selected,
        "selected_ids": ids,
        "selection_sha256": fingerprint(selection),
        "counts": counts,
        "rows_by_split": n_rows,
        "retained_families_by_split": n_families,
        "assigned_families_by_split": {
            s: list(families.values()).count(s) for s in SPLITS
        },
        "family_partition_sha256": fingerprint(families),
        "input_metadata_sha256": fingerprint(rows),
        "overlaps_by_protection_role": {
            name: sum(r["input"] in protected for r in rows)
            for name, protected in roles.items()
        },
        "protected_set_sha256": {
            name: fingerprint(sorted(protected)) for name, protected in roles.items()
        },
        "value_origins": {
            s: dict(Counter(rows[i]["value_kind"] for i in indices))
            for s, indices in selected.items()
        },
        "absolute_ply_bins": {
            s: dict(
                Counter(
                    "0-64"
                    if rows[i]["ply"] <= 64
                    else "65-160"
                    if rows[i]["ply"] <= 160
                    else "161+"
                    for i in indices
                )
            )
            for s, indices in selected.items()
        },
        "minimum_rows": dict(minimum_rows),
        "usable_for_pilot": all(
            n_rows[s] >= minimum_rows[s] and n_families[s] >= 2 for s in SPLITS
        ),
        "duplicate_policy": "test>val>train; one canonical input, smallest stable sample ID within retained split; no target/outcome selection",
        "verification_scope": "metadata admission only; actual source bytes, complete Rust replay, canonical identities and labels must be independently verified by the Linux producer; counts do not establish teacher quality or playing strength",
    }


def _screen_protection(path, expected_sha256):
    _linux()
    from voxelshogi import Game

    from training.evaluation_v2_runner import position_identity
    from training.research_data import input_identity

    path = Path(path)
    if (
        not _sha(expected_sha256)
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > 16 * 1024**2
        or file_hash(path) != expected_sha256
    ):
        raise ValueError("fixed screen config bytes/hash differ")
    bundle = json.loads(path.read_text())
    if type(bundle) is not dict:
        raise ValueError("screen config must be an object")
    body = {k: v for k, v in bundle.items() if k != "conditions_sha256"}
    if bundle.get("schema") != "voxelshogi-research-screen-v1" or bundle.get(
        "conditions_sha256"
    ) != fingerprint(body):
        raise ValueError("screen frozen conditions differ")
    roots, cases, seen = {s: set() for s in ("development", "holdout")}, set(), set()
    for purpose, protocol in (
        ("development", bundle["protocols"]["legal-argmax-v1"]),
        ("holdout", bundle["holdout_protocol"]),
    ):
        validate_protocol(protocol)
        if protocol["purpose"] != purpose or len(protocol["cases"]) != 12:
            raise ValueError("exact development/final12 roots required")
        for case in protocol["cases"]:
            game = Game.from_record(case["opening"])
            snapshot = game.snapshot()
            actual = {
                "purpose": purpose,
                "position": position_identity(snapshot["vsfen"]),
                "input": input_identity(snapshot),
            }
            if (
                game.record() != case["opening"]
                or snapshot["finished"]
                or actual != bundle["roots"][case["id"]]
                or actual["input"] in seen
            ):
                raise ValueError("frozen root differs from Rust canonical input")
            roots[purpose].add(actual["input"])
            seen.add(actual["input"])
            cases.add(case["id"])
    if (
        cases != set(bundle["roots"])
        or sorted(roots["holdout"]) != bundle["protected_holdout_inputs"]
    ):
        raise ValueError("incomplete frozen root protection")
    return roots


def audit_selfplay_corpus(
    folder, protocol, protection, screen, *, screen_sha256, seed=67011
):
    """Enumerate all verified source samples before any training/feature cache."""
    _linux()
    from voxelshogi import Game

    from training.research_data import input_identity
    from training.selfplay_dataset import _load
    from training.selfplay_generations import _protection

    folder = Path(folder)
    manifest_sha256 = file_hash(folder / "manifest.json")
    protection_sha256 = file_hash(protection)
    protocol_sha256 = fingerprint(protocol)
    m, episodes = _load(folder, protocol)
    if m["run"]["complete"] is not True:
        raise ValueError("all completed published generations required")
    protected = _protection(protection, protocol)
    roots = _screen_protection(screen, screen_sha256)
    metadata = []
    for episode in episodes:
        game = Game.from_record(episode["opening"])
        family = input_identity(game.snapshot())
        for sample in episode["samples"]:
            snapshot = game.snapshot()
            if (
                snapshot["vsfen"] != sample["position"]
                or snapshot["side"] != sample["side"]
                or len(game.record()["moves"]) != sample["ply"]
            ):
                raise ValueError(
                    "sample enumeration differs from verified Rust history"
                )
            metadata.append(
                {
                    "id": episode["episode_id"] + ":" + str(sample["ply"]),
                    "family": family,
                    "input": input_identity(snapshot),
                    "value_kind": sample["value"]["kind"],
                    "ply": sample["ply"],
                }
            )
            game.play(sample["move"])
    partition = family_partition(sorted({row["family"] for row in metadata}), seed=seed)
    result = admit_metadata(
        metadata,
        partition,
        protected_inputs=protected,
        final_roots=roots["holdout"],
        development_inputs=roots["development"],
    )
    if (
        file_hash(folder / "manifest.json") != manifest_sha256
        or file_hash(folder / "episodes.parquet") != m["file"]["sha256"]
        or file_hash(protection) != protection_sha256
        or file_hash(screen) != screen_sha256
        or fingerprint(protocol) != protocol_sha256
    ):
        raise ValueError("research source changed during enumeration")
    return {
        "schema": "voxelshogi-research-selfplay-corpus-audit-v1",
        "source_manifest_sha256": manifest_sha256,
        "source_protocol_sha256": protocol_sha256,
        "source_generations": len(m["run"]["generations"]),
        "source_episodes": len(episodes),
        "source_protection_sha256": protection_sha256,
        "screen_config_sha256": screen_sha256,
        "seed": seed,
        "family_partition": partition,
        "metadata": metadata,
        "admission": result,
        "labels_adopted": 0,
        "scope": "source dataset all-file schema/hash and all-episode Rust/target verification, full-sample canonical identity enumeration, frozen24-root replay and split/protection readiness; no feature cache, training, HF publication or teacher-quality acceptance",
    }
