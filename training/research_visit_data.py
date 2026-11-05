"""Convert fully audited P5 visits to the P6 train/val consumer, Linux only.

No publication, training, teacher-quality adoption or holdout tuning happens
here. The execution driver must first verify the fixed HF bytes and settings.
"""

import re
import sys
from copy import deepcopy
from pathlib import Path

from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.research_corpus import audit_selfplay_corpus

FEATURE_BYTES = 729 * 43 * 4


def _linux():
    if sys.platform != "linux":
        raise ValueError("research feature encoding requires external Linux")


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def select_training(audit, *, expected_sha256, maximum_feature_bytes=2 * 1024**3):
    """Validate the hash-bound handoff, then return train/val metadata only."""
    if not _sha(expected_sha256) or fingerprint(audit) != expected_sha256:
        raise ValueError("reviewed research audit hash differs")
    if (
        type(maximum_feature_bytes) is not int
        or not 1 <= maximum_feature_bytes <= 32 * 1024**3
    ):
        raise ValueError("invalid explicit feature byte limit")
    try:
        if audit["schema"] != "voxelshogi-research-selfplay-corpus-audit-v1" or any(
            not _sha(audit[k])
            for k in (
                "source_manifest_sha256",
                "source_protocol_sha256",
                "source_protection_sha256",
                "screen_config_sha256",
            )
        ):
            raise ValueError("complete source audit binding required")
        a = audit["admission"]
        rows = audit["metadata"]
        if (
            a["usable_for_pilot"] is not True
            or not rows
            or len({r["id"] for r in rows}) != len(rows)
        ):
            raise ValueError("usable nonempty unique admission required")
        if any(
            set(a[key]) != {"train", "val", "test"}
            for key in ("indices_by_split", "selected_ids", "rows_by_split")
        ):
            raise ValueError("all three admitted roles required")
        result, selected, seen, families = {}, [], set(), set()
        for split in ("train", "val", "test"):
            indices = a["indices_by_split"][split]
            if (
                type(indices) is not list
                or not indices
                or any(type(i) is not int or not 0 <= i < len(rows) for i in indices)
            ):
                raise ValueError("invalid admitted selection indices")
            part = [rows[i] for i in indices]
            current_families = {r["family"] for r in part}
            if (
                [r["id"] for r in part] != a["selected_ids"][split]
                or len(part) != a["rows_by_split"][split]
                or len(current_families) < 2
                or current_families & families
                or any(audit["family_partition"][r["family"]] != split for r in part)
                or any(not _sha(r["input"]) or r["input"] in seen for r in part)
                or len({r["input"] for r in part}) != len(part)
            ):
                raise ValueError(
                    "admitted split counts, identities or family isolation differ"
                )
            selected.extend({**r, "split": split} for r in part)
            seen.update(r["input"] for r in part)
            families.update(current_families)
            if split != "test":
                result[split] = [dict(r) for r in part]
        if fingerprint(selected) != a["selection_sha256"]:
            raise ValueError("admitted ordered selection hash differs")
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError("invalid admitted research metadata") from error
    if sum(map(len, result.values())) * FEATURE_BYTES > maximum_feature_bytes:
        raise ValueError("admitted features exceed explicit byte budget")
    return result


def encode_corpus(
    folder,
    protocol,
    protection,
    screen,
    *,
    screen_sha256,
    expected_audit_sha256,
    seed=67011,
    maximum_feature_bytes=2 * 1024**3,
):
    """Replay immutable complete sources and encode exactly selected train/val.

    Full source/target verification is repeated by the auditor before selection;
    test is checked for disjointness but never features-encoded by this consumer.
    The byte cap covers dense feature arrays, not total process RSS.
    """
    _linux()
    folder = Path(folder)
    audit = audit_selfplay_corpus(
        folder, protocol, protection, screen, screen_sha256=screen_sha256, seed=seed
    )
    selected = select_training(
        audit,
        expected_sha256=expected_audit_sha256,
        maximum_feature_bytes=maximum_feature_bytes,
    )

    import numpy as np
    from voxelshogi import Game

    from training.research_data import input_identity
    from training.research_visit_fit import VisitCorpus, VisitRunConfig
    from training.selfplay_dataset import _load
    from training.selfplay_training import Samples

    def unchanged():
        return (
            file_hash(folder / "manifest.json") == audit["source_manifest_sha256"]
            and file_hash(protection) == audit["source_protection_sha256"]
            and file_hash(screen) == audit["screen_config_sha256"]
            and fingerprint(protocol) == audit["source_protocol_sha256"]
            and fingerprint(audit) == expected_audit_sha256
        )

    if not unchanged():
        raise ValueError("research source changed before feature encoding")
    manifest, episodes = _load(folder, protocol)
    wanted = {r["id"]: r for part in selected.values() for r in part}
    encoded = {}
    for episode in episodes:
        game = Game.from_record(episode["opening"])
        family = input_identity(game.snapshot())
        for sample in episode["samples"]:
            sample_id = episode["episode_id"] + ":" + str(sample["ply"])
            if sample_id in wanted:
                snapshot = game.snapshot()
                actual = {
                    "id": sample_id,
                    "family": family,
                    "input": input_identity(snapshot),
                    "value_kind": sample["value"]["kind"],
                    "ply": len(game.record()["moves"]),
                }
                if (
                    actual != wanted[sample_id]
                    or sample_id in encoded
                    or snapshot["vsfen"] != sample["position"]
                    or snapshot["side"] != sample["side"]
                    or sorted(game.legal_actions()) != sample["legal_actions"]
                ):
                    raise ValueError(
                        "feature history differs from admitted Rust sample"
                    )
                features = game.features()
                if (
                    features.shape != (729, 43)
                    or features.dtype != np.float32
                    or not np.isfinite(features).all()
                ):
                    raise ValueError("invalid admitted float32 feature encoding")
                encoded[sample_id] = (
                    features,
                    {
                        "id": sample_id,
                        "input_id": actual["input"],
                        "family": family,
                        "policy": deepcopy(sample["policy"]),
                        "value": deepcopy(sample["value"]),
                        "legal_actions": list(sample["legal_actions"]),
                    },
                )
            game.play(sample["move"])
    if set(encoded) != set(wanted):
        raise ValueError("not every admitted train/val sample was encoded")
    if (
        not unchanged()
        or file_hash(folder / "episodes.parquet") != manifest["file"]["sha256"]
    ):
        raise ValueError("research source changed during feature encoding")
    parts = {}
    for split, rows in selected.items():
        items = [encoded[r["id"]] for r in rows]
        parts[split] = Samples(
            [x[0] for x in items],
            [x[1] for x in items],
            {
                "schema": "voxelshogi-research-visit-samples-v1",
                "split": split,
                "admission_sha256": expected_audit_sha256,
                "source_manifest_sha256": audit["source_manifest_sha256"],
                "source_protocol_sha256": audit["source_protocol_sha256"],
                "selection_sha256": audit["admission"]["selection_sha256"],
                "selected_ids_sha256": fingerprint([r["id"] for r in rows]),
            },
        )
    corpus = VisitCorpus(parts["train"], parts["val"], expected_audit_sha256)
    evidence = {
        "schema": "voxelshogi-research-visit-features-v1",
        "admission_sha256": expected_audit_sha256,
        "encoded_rows": {s: len(p.rows) for s, p in parts.items()},
        "feature_bytes": len(encoded) * FEATURE_BYTES,
        "test_features_encoded": 0,
        "feature_content_sha256": corpus.digest(VisitRunConfig(device="cpu")),
        "scope": "verified source replay and exact selected train/val features/visits; no teacher-quality adoption, training, HF publication, test evaluation or strength claim",
    }
    return corpus, evidence
