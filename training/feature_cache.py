"""Hash-bound, disk-backed feature cache and split batches on external Linux."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from training.learning import Batch, epoch_batches
from training.supervision import ROOT, audit_corpus, label_contract, select_target

SCHEMA = "voxelshogi-feature-cache-v1"
FILES = (
    "features.npy",
    "actions.npy",
    "values.npy",
    "offsets.npy",
    "legal.bin",
    "identities.json",
)


def _linux():
    if sys.platform != "linux":
        raise ValueError("feature/data execution requires external Linux")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _provenance(audit, source_commit):
    if audit.get("contract") != label_contract() or not re.fullmatch(
        r"[0-9a-f]{40}", source_commit
    ):
        raise ValueError("cache contract or source commit differs")
    counts = audit["counts"]
    splits = counts["teacher_splits"]
    if (
        set(splits) != {"train", "val", "test"}
        or any(type(n) is not int or n < 1 for n in splits.values())
        or counts["eligible_teachers"] != sum(splits.values())
    ):
        raise ValueError("cache requires nonempty audited teacher splits")


def write_cache(rows, folder, *, audit, source_commit):
    """Low-level streaming writer; production entry point audits pinned files first."""
    _linux()
    _provenance(audit, source_commit)
    import numpy as np
    from voxelshogi import Game

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    count = audit["counts"]["eligible_teachers"]
    features = np.lib.format.open_memmap(
        folder / "features.npy", mode="w+", dtype=np.float32, shape=(count, 729, 43)
    )
    actions = np.lib.format.open_memmap(
        folder / "actions.npy", mode="w+", dtype=np.int64, shape=(count,)
    )
    values = np.lib.format.open_memmap(
        folder / "values.npy", mode="w+", dtype=np.float32, shape=(count,)
    )
    offsets = np.lib.format.open_memmap(
        folder / "offsets.npy", mode="w+", dtype=np.int64, shape=(count + 1,)
    )
    identities, ids, splits = [], set(), Counter()
    current, game, index, offset = None, None, 0, 0
    offsets[0] = 0
    with (folder / "legal.bin").open("xb") as legal_stream:
        for row in rows:
            if row["source"] != "search":
                continue
            if row["game_id"] != current:
                current, game = row["game_id"], Game(row["initial"])
            snapshot = game.snapshot()
            if (
                snapshot["vsfen"] != row["vsfen"]
                or snapshot["hash"] != row["hash"]
                or game.record()["moves"] != row["history"]
                or game.record()["initial"] != row["initial"]
            ):
                raise ValueError("feature replay differs from verified row")
            target = select_target(row)
            if target is not None:
                if index >= count or target.example_id in ids:
                    raise ValueError("cache teacher count or identity differs")
                encoded = game.features()
                if encoded.shape != (729, 43) or not np.isfinite(encoded).all():
                    raise ValueError("invalid encoded features")
                features[index] = encoded
                actions[index], values[index] = target.action, target.value
                legal_stream.write(
                    np.asarray(target.legal_actions, dtype="<i4").tobytes()
                )
                offset += len(target.legal_actions)
                offsets[index + 1] = offset
                identities.append({"id": target.example_id, "split": target.split})
                ids.add(target.example_id)
                splits[target.split] += 1
                index += 1
            if row["played_move"] is not None:
                game.play(row["played_move"])
        legal_stream.flush()
        os.fsync(legal_stream.fileno())
    if index != count or dict(splits) != audit["counts"]["teacher_splits"]:
        raise ValueError("cache split counts differ from audit")
    for array in (features, actions, values, offsets):
        array.flush()
    (folder / "identities.json").write_text(canonical(identities) + "\n")
    inventory = []
    for name in FILES:
        path = folder / name
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
        inventory.append(
            {"file": name, "bytes": path.stat().st_size, "sha256": file_hash(path)}
        )
    manifest = {
        "schema": SCHEMA,
        "complete": True,
        "count": count,
        "source_commit": source_commit,
        "audit": audit,
        "files": inventory,
    }
    temporary = folder / "manifest.tmp"
    with temporary.open("x") as stream:
        stream.write(canonical(manifest) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(folder / "manifest.json")
    return manifest


class FeatureCache:
    def __init__(self, folder):
        _linux()
        import numpy as np

        folder = Path(folder)
        if not (folder / "manifest.json").is_file():
            raise ValueError("incomplete feature cache")
        manifest = json.loads((folder / "manifest.json").read_text())
        _provenance(manifest["audit"], manifest["source_commit"])
        if (
            manifest.get("schema") != SCHEMA
            or manifest.get("complete") is not True
            or manifest["count"] != manifest["audit"]["counts"]["eligible_teachers"]
            or [entry["file"] for entry in manifest["files"]] != list(FILES)
            or {path.name for path in folder.iterdir()} != {*FILES, "manifest.json"}
        ):
            raise ValueError("incomplete or incompatible cache inventory")
        for entry in manifest["files"]:
            path = folder / entry["file"]
            if (
                path.is_symlink()
                or not path.is_file()
                or path.stat().st_size != entry["bytes"]
                or file_hash(path) != entry["sha256"]
            ):
                raise ValueError("cache file size/hash differs")
        self.manifest, self.sha256 = manifest, file_hash(folder / "manifest.json")
        self.features, self.actions, self.values, self.offsets = (
            np.load(folder / name, mmap_mode="r", allow_pickle=False)
            for name in FILES[:4]
        )
        self.legal = np.memmap(folder / "legal.bin", mode="r", dtype="<i4")
        self.identities = json.loads((folder / "identities.json").read_text())
        count = manifest["count"]
        if (
            self.features.shape != (count, 729, 43)
            or self.features.dtype != np.float32
            or self.actions.shape != (count,)
            or self.actions.dtype != np.int64
            or self.values.shape != (count,)
            or self.values.dtype != np.float32
            or self.offsets.shape != (count + 1,)
            or self.offsets.dtype != np.int64
            or self.offsets[0] != 0
            or self.offsets[-1] != len(self.legal)
            or not (np.diff(self.offsets) > 0).all()
            or len(self.identities) != count
            or len({entry["id"] for entry in self.identities}) != count
            or dict(Counter(entry["split"] for entry in self.identities))
            != manifest["audit"]["counts"]["teacher_splits"]
        ):
            raise ValueError("cache array/identity dimensions differ")

    def batches(self, split, *, batch_size, seed, epoch=0, start_batch=0):
        import numpy as np
        import torch

        if split not in ("train", "val", "test"):
            raise ValueError("unknown split")
        selected = [
            i for i, item in enumerate(self.identities) if item["split"] == split
        ]
        if split == "train":
            parts = epoch_batches(
                len(selected),
                batch_size,
                seed=seed,
                epoch=epoch,
                start_batch=start_batch,
            )
        else:
            if (
                type(batch_size) is not int
                or batch_size < 1
                or start_batch != 0
                or epoch != 0
            ):
                raise ValueError("evaluation requires fixed full order")
            parts = (
                range(i, min(i + batch_size, len(selected)))
                for i in range(0, len(selected), batch_size)
            )
        for part in parts:
            indices = [selected[i] for i in part]
            yield Batch(
                torch.from_numpy(np.array(self.features[indices], copy=True)),
                torch.from_numpy(np.array(self.actions[indices], copy=True)),
                torch.from_numpy(np.array(self.values[indices], copy=True)),
                [
                    self.legal[self.offsets[i] : self.offsets[i + 1]].tolist()
                    for i in indices
                ],
                tuple(self.identities[i]["id"] for i in indices),
                split,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    _linux()
    if not args.output.resolve().is_relative_to(ROOT / "runs"):
        parser.error("cache must remain under ignored runs/ on Linux")
    if subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip():
        parser.error("build production cache only from clean source")
    source = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    audit = audit_corpus(args.input)
    import pyarrow.parquet as pq

    generation = json.loads((args.input / "manifest.json").read_text())
    rows = (
        row
        for shard in generation["shards"]
        for row in pq.read_table(args.input / shard["file"]).to_pylist()
    )
    result = write_cache(rows, args.output, audit=audit, source_commit=source)
    print(
        canonical(
            {
                "count": result["count"],
                "teacher_splits": audit["counts"]["teacher_splits"],
                "manifest_sha256": file_hash(args.output / "manifest.json"),
            }
        )
    )


if __name__ == "__main__":
    main()
