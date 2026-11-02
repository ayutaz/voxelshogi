"""Portable completed-generation replay, without weights or executable state.

Models and optimizer archives retain their separate Apache-2.0 Hub publication.
This dataset restores at a committed generation boundary; it does not recover an
in-progress optimizer step. The next generation creates a fresh optimizer.
"""

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from training.checkpoint import _progress, atomic_json
from training.feature_cache import file_hash
from training.replay import ReplayBuffer, verify_episode
from training.research_data import canonical
from training.selfplay_generations import (
    SCHEMA as RUN_SCHEMA,
)
from training.selfplay_generations import (
    _lock,
    episode_settings,
    validate_protocol,
    validate_publication,
)

SCHEMA = "voxelshogi-selfplay-dataset-v1"
MAX_BYTES = 512 * 1024**2


def _record(record, protocol):
    if set(record) != {
        "generation",
        "parent_model_sha256",
        "model_sha256",
        "file",
        "training_progress",
        "input_sha256",
        "replay_sha256",
        "encoded_samples",
        "sample_audit",
    }:
        raise ValueError("unknown generation record fields")
    progress, audit = record["training_progress"], record["sample_audit"]
    _progress(progress)
    if (
        type(record["encoded_samples"]) is not int
        or not 1 <= record["encoded_samples"] <= 16384
        or progress["epoch"] != protocol["training"]["epochs"]
        or progress["next_batch"] != 0
        or progress["step"] < 1
        or progress["examples"] != record["encoded_samples"] * progress["epoch"]
        or progress["best_val_loss"] is not None
        or set(audit)
        != {
            "buffer_sha256",
            "protected_sha256",
            "excluded_protected",
            "repeated_train_inputs",
            "duplicate_policy",
        }
        or audit["buffer_sha256"] != record["replay_sha256"]
        or audit["duplicate_policy"]
        != "retain within-train occurrences; exclude protected inputs"
        or any(
            type(audit[k]) is not int or audit[k] < 0
            for k in ("excluded_protected", "repeated_train_inputs")
        )
        or any(
            not re.fullmatch(r"[0-9a-f]{64}", v)
            for v in (
                record["input_sha256"],
                record["replay_sha256"],
                audit["protected_sha256"],
            )
        )
    ):
        raise ValueError("uncommitted or invalid generation training metadata")


def _linux():
    if sys.platform != "linux":
        raise ValueError("selfplay dataset execution requires external Linux")


def _json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024**2:
        raise ValueError("invalid selfplay dataset metadata")
    result = json.loads(path.read_text())
    canonical(result)
    return result


def validate_manifest(m, *, expected_protocol):
    run_id = validate_protocol(expected_protocol)
    try:
        run, replay, f = m["run"], m["replay"], m["file"]
        p, records = run["protocol"], run["generations"]
        if (
            set(m) != {"schema", "run", "replay", "file"}
            or m["schema"] != SCHEMA
            or set(run)
            != {
                "schema",
                "protocol",
                "run_id",
                "generations",
                "publications",
                "complete",
            }
            or run["schema"] != RUN_SCHEMA
            or canonical(p) != canonical(expected_protocol)
            or run["run_id"] != run_id
            or type(records) is not list
            or not 1 <= len(records) <= p["generations"]
            or type(run["complete"]) is not bool
            or run["complete"] != (len(records) == p["generations"])
            or type(run["publications"]) is not list
            or len(run["publications"]) > len(records)
        ):
            raise ValueError("selfplay dataset protocol/boundary differs")
        parent = p["base_model_sha256"]
        parents = []
        for i, r in enumerate(records):
            _record(r, p)
            if (
                type(r["generation"]) is not int
                or r["generation"] != i
                or r["parent_model_sha256"] != parent
                or r["file"] != f"generation-{i:03d}/model.safetensors"
                or not re.fullmatch(r"[0-9a-f]{64}", r["model_sha256"])
            ):
                raise ValueError("selfplay dataset model lineage differs")
            parents.append(parent)
            parent = r["model_sha256"]
        for i, receipt in enumerate(run["publications"]):
            if (
                set(receipt) != {"generation", "dataset", "state"}
                or receipt["generation"] != i
            ):
                raise ValueError("selfplay dataset publication order differs")
            validate_publication({k: receipt[k] for k in ("dataset", "state")})
        count = len(records) * p["episodes_per_generation"]
        if (
            set(replay) != {"schema", "binding", "entries"}
            or replay["schema"] != "voxelshogi-replay-buffer-v1"
            or replay["binding"]
            != {
                "source_commit": p["source_commit"],
                "run_id": run_id,
                "capacity": p["replay_capacity"],
            }
            or type(replay["entries"]) is not list
            or len(replay["entries"]) != count
        ):
            raise ValueError("selfplay dataset replay is not a committed boundary")
        for i, entry in enumerate(replay["entries"]):
            if (
                type(entry["slot"]) is not int
                or entry["slot"] != i
                or entry["model_sha256"] != parents[i // p["episodes_per_generation"]]
            ):
                raise ValueError("selfplay dataset replay lineage differs")
        if (
            set(f) != {"path", "bytes", "sha256", "rows"}
            or f["path"] != "episodes.parquet"
            or type(f["bytes"]) is not int
            or not 0 < f["bytes"] <= MAX_BYTES
            or type(f["rows"]) is not int
            or f["rows"] != count
            or not re.fullmatch(r"[0-9a-f]{64}", f["sha256"])
        ):
            raise ValueError("selfplay dataset file inventory differs")
        canonical(m)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("invalid selfplay dataset manifest") from error
    return m


def _schema():
    import pyarrow as pa

    return pa.schema(
        [("slot", pa.int32()), ("episode_json", pa.string())],
        metadata={b"schema_id": SCHEMA.encode()},
    )


def _facts(episodes):
    return {
        "episodes": len(episodes),
        "samples": sum(len(e["samples"]) for e in episodes),
        "natural": sum(e["termination_kind"] == "natural" for e in episodes),
        "cutoff": sum(e["termination_kind"] == "cutoff" for e in episodes),
    }


def dataset_card(m, counts):
    p = m["run"]["protocol"]
    return f"""---
license: cc-by-4.0
configs:
  - config_name: selfplay-episodes
    data_files:
      - split: train
        path: episodes.parquet
---
# VoxelShogi selfplay episodes

## Generation and provenance

Source `{p["source_commit"]}`; standard single-king rules `{p["ruleset_id"]}`.
{len(m["run"]["generations"])} committed generations; {p["generations"]} planned.
{counts["episodes"]} episodes; {counts["samples"]} samples; {counts["natural"]} natural; {counts["cutoff"]} cutoff.
Base model SHA-256: `{p["base_model_sha256"]}`. All seed families, actor/search
budgets, training settings and protected-input provenance are frozen in manifest.json.
Training only; frozen M6/P5 evaluation inputs are excluded by the learner. Replay
may contain repeated positions; this card reports raw episodes/samples, not unique
training inputs or evidence of stronger play.

## Usage and schema

Download at the verified fixed Hub revision after access approval. Read
`episodes.parquet` with pyarrow.parquet.read_table. Each row has slot (int32) and
episode_json (UTF-8 JSON containing complete history, legal actions, sparse visit
policy, model provenance and value-label provenance). Preserve episode boundaries.
Cutoff bootstrap values are model estimates, not natural draws or observed outcomes.
Use training.selfplay_dataset.restore_dataset with the reviewed protocol and
separately downloaded model artifacts at their declared hashes to continue at the
committed boundary. Base model and protected inputs remain separate verified inputs.

## Verification

Every episode is replayed through Rust; legal actions, history, label arithmetic,
seeded action selection and completed search budgets are checked. Visits are not
re-inferred. All replay entries and generation lineage are retained, including
entries outside the active replay window. No in-progress generation is exported.
Byte/SHA-256 identity is required on download. HF verification receipts establish
publication; producing this local folder alone does not establish HF or another-VM
recovery. Model weights and optimizer archives are separate; no pickle is included.

## Access and license

Public/manual download approval; Community OFF. Synthetic episodes are CC-BY-4.0;
see LICENSE. Attribute ayutaz and VoxelShogi contributors, source and fixed Hub
revision. Model/state artifacts are separately Apache-2.0. No credentials or logs
are part of this dataset.
"""


def pack_dataset(source, output, *, expected_protocol):
    _linux()
    import pyarrow as pa
    import pyarrow.parquet as pq

    source, output = Path(source), Path(output)
    if (
        not source.is_dir()
        or source.is_symlink()
        or output.exists()
        or output.is_symlink()
    ):
        raise ValueError("owned source and new dataset destination required")
    with _lock(source):
        run = _json(source / "run.json")
        p = expected_protocol
        run_id = validate_protocol(p)
        replay = ReplayBuffer(
            source / "replay",
            source_commit=p["source_commit"],
            run_id=run_id,
            capacity=p["replay_capacity"],
        )
        index = _json(source / "replay/buffer.json")
        # Validate before Parquet writing; bytes are replaced after staging.
        m = {
            "schema": SCHEMA,
            "run": run,
            "replay": index,
            "file": {
                "path": "episodes.parquet",
                "bytes": 1,
                "sha256": "0" * 64,
                "rows": len(index["entries"]),
            },
        }
        validate_manifest(m, expected_protocol=p)
        for record in run["generations"]:
            path = source / record["file"]
            if (
                path.parent.is_symlink()
                or path.is_symlink()
                or file_hash(path) != record["model_sha256"]
            ):
                raise ValueError("source generation model hash differs")
        episodes = replay.episodes(window=False)
        rows = [
            {"slot": i, "episode_json": canonical(e) + "\n"}
            for i, e in enumerate(episodes)
        ]
        output.mkdir(parents=True, exist_ok=False)
        f = output / "episodes.parquet"
        pq.write_table(
            pa.Table.from_pylist(rows, schema=_schema()),
            f,
            version="2.6",
            compression="zstd",
            compression_level=3,
            use_dictionary=False,
            write_statistics=False,
            row_group_size=16,
        )
        m["file"].update(bytes=f.stat().st_size, sha256=file_hash(f))
        validate_manifest(m, expected_protocol=p)
        counts = _facts(episodes)
        atomic_json(output / "manifest.json", m)
        atomic_json(
            output / "validation.json",
            {
                "schema": SCHEMA,
                "complete": True,
                **counts,
                "scope": "Rust replay and label consistency; no neural search re-inference or HF transfer proof",
            },
        )
        (output / "README.md").write_text(dataset_card(m, counts))
    return m


def _load(folder, expected_protocol):
    import pyarrow.parquet as pq

    folder = Path(folder)
    if folder.is_symlink():
        raise ValueError("symlink dataset")
    m = validate_manifest(
        _json(folder / "manifest.json"), expected_protocol=expected_protocol
    )
    path = folder / "episodes.parquet"
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size != m["file"]["bytes"]
        or file_hash(path) != m["file"]["sha256"]
    ):
        raise ValueError("selfplay dataset bytes/hash differ")
    table = pq.read_table(path)
    if (
        not table.schema.equals(_schema(), check_metadata=True)
        or len(table) != m["file"]["rows"]
    ):
        raise ValueError("selfplay dataset schema/rows differ")
    episodes = []
    for i, row in enumerate(table.to_pylist()):
        e = json.loads(row["episode_json"])
        generation, offset = divmod(i, expected_protocol["episodes_per_generation"])
        config, _ = episode_settings(expected_protocol, generation, offset)
        entry = m["replay"]["entries"][i]
        facts = verify_episode(
            e,
            expected_source=expected_protocol["source_commit"],
            expected_model=entry["model_sha256"],
            expected_config=config,
        )
        raw = (canonical(e) + "\n").encode()
        expected = {
            "slot": i,
            "path": "episodes/" + hashlib.sha256(raw).hexdigest() + ".json",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "episode_id": facts["episode_id"],
            "model_sha256": entry["model_sha256"],
            "config": e["config"],
            "samples": facts["samples"],
            "model_evaluations": facts["model_evaluations"],
        }
        if row["slot"] != i or canonical(entry) != canonical(expected):
            raise ValueError("selfplay dataset episode/index differs")
        episodes.append(e)
    return m, episodes


def restore_dataset(folder, output, *, expected_protocol, models):
    _linux()
    m, episodes = _load(folder, expected_protocol)
    if set(models) != set(range(len(m["run"]["generations"]))):
        raise ValueError("all committed generation models are required")
    for i, record in enumerate(m["run"]["generations"]):
        path = Path(models[i])
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > 64 * 1024**2
            or file_hash(path) != record["model_sha256"]
        ):
            raise ValueError("restoration model hash differs")
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("restoration requires a new output directory")
    with _lock(output):
        replay = output / "replay"
        replay.mkdir()
        (replay / ".voxelshogi-replay-v1").touch()
        (replay / "episodes").mkdir()
        for entry, e in zip(m["replay"]["entries"], episodes, strict=True):
            atomic_json(replay / entry["path"], e)
        atomic_json(replay / "buffer.json", m["replay"])
        for i, record in enumerate(m["run"]["generations"]):
            path = output / record["file"]
            path.parent.mkdir()
            shutil.copyfile(models[i], path)
            if file_hash(path) != record["model_sha256"]:
                raise ValueError("model changed during restoration")
            atomic_json(path.parent / "generation.json", record)
        # The manifest commits only after complete replay and all model copies.
        atomic_json(output / "run.json", m["run"])
    return m
