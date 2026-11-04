"""Linux full-corpus/continuation audit for P5-3 generation evaluations."""

import json
import sys
from collections import Counter
from pathlib import Path

from training.evaluation_v2 import fingerprint
from training.evaluation_v2_runner import position_identity, verify_run
from training.feature_cache import file_hash
from training.generation_cases import replay_scored_identities
from training.generation_evaluation import audit_evaluation_inputs
from training.research_data import input_identity
from training.supervision import RULESET


def collect_corpus_identities(rows, *, expected_rows, snapshot_factory):
    """Stream every trusted row; injected snapshots keep metadata tests light."""
    if type(expected_rows) is not int or expected_rows < 1:
        raise ValueError("nonempty expected corpus required")
    physical = {name: set() for name in ("train", "val", "test")}
    inputs = {name: set() for name in physical}
    counts, cache = Counter(), {}
    count = 0
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"vsfen", "split", "ruleset_id"}
            or row["split"] not in physical
            or row["ruleset_id"] != RULESET
        ):
            raise ValueError("invalid corpus enumeration row")
        identity = position_identity(row["vsfen"], ruleset=row["ruleset_id"])
        if identity not in cache:
            cache[identity] = input_identity(snapshot_factory(row["vsfen"]))
        physical[row["split"]].add(identity)
        inputs[row["split"]].add(cache[identity])
        counts[row["split"]] += 1
        count += 1
    if count != expected_rows or any(not ids for ids in physical.values()):
        raise ValueError("incomplete corpus rows or split enumeration")
    return (
        physical,
        inputs,
        {
            "rows": count,
            "unique_physical": len(cache),
            "unique_inputs": len(set(cache.values())),
            "rows_by_split": dict(counts),
        },
    )


def audit_generation_runs(folders, corpus, selfplay, *, expected_protocol, protection):
    """Verify inputs before reporting complete physical/canonical membership."""
    if sys.platform != "linux":
        raise ValueError("full generation/corpus audit requires external Linux")
    import pyarrow.parquet as pq
    from voxelshogi import Game

    from training.selfplay_dataset import _load
    from training.selfplay_generations import _protection
    from training.supervision import audit_corpus

    if type(folders) is not dict or not folders:
        raise ValueError("nonempty verified evaluation runs required")
    protected = _protection(protection, expected_protocol)
    corpus, selfplay = Path(corpus), Path(selfplay)
    source_audit = audit_corpus(corpus)
    manifest = json.loads((corpus / "manifest.json").read_text())

    def rows():
        for shard in manifest["shards"]:
            yield from pq.read_table(
                corpus / shard["file"], columns=["vsfen", "split", "ruleset_id"]
            ).to_pylist()

    physical, inputs, corpus_counts = collect_corpus_identities(
        rows(),
        expected_rows=source_audit["counts"]["rows"],
        snapshot_factory=lambda vsfen: Game(vsfen).snapshot(),
    )
    physical = {"m4-" + name: ids for name, ids in physical.items()}
    inputs = {"m4-" + name: ids for name, ids in inputs.items()}
    inputs["protected"] = protected
    saved, episodes = _load(selfplay, expected_protocol)
    if saved["run"]["complete"] is not True:
        raise ValueError(
            "all committed selfplay generations required for evaluation audit"
        )
    positions, sample_inputs, cache, samples = set(), set(), {}, 0
    for episode in episodes:
        for sample in episode["samples"]:
            identity = position_identity(sample["position"])
            if identity not in cache:
                cache[identity] = input_identity(Game(sample["position"]).snapshot())
            positions.add(identity)
            sample_inputs.add(cache[identity])
            samples += 1
    physical["selfplay-all-published-samples"] = positions
    inputs["selfplay-all-published-samples"] = sample_inputs
    cases, receipts = {}, {}
    for name, folder in sorted(folders.items()):
        folder = Path(folder)
        verify_run(folder)
        spec = json.loads((folder / "protocol.json").read_text())
        receipt = json.loads((folder / "run.json").read_text())
        assigned = {c["id"]: c for c in spec["cases"]}
        for descriptor in receipt["files"]:
            row = json.loads((folder / descriptor["path"]).read_text())
            key = name + "/" + descriptor["path"]
            cases[key] = replay_scored_identities(
                row["record"], assigned[row["case_id"]]["opening"]
            )
        receipts[name] = {
            "run_sha256": file_hash(folder / "run.json"),
            "protocol_sha256": receipt["protocol_sha256"],
            "games": receipt["games"],
        }
    result = audit_evaluation_inputs(physical, inputs, cases)
    return {
        **result,
        "schema": "voxelshogi-generation-input-audit-v1",
        "corpus_contract": source_audit["contract"],
        "corpus_counts": corpus_counts,
        "source_identity_counts": result["corpus_counts"],
        "corpus_inventory_sha256": fingerprint(source_audit["files"]),
        "selfplay_manifest_sha256": file_hash(selfplay / "manifest.json"),
        "selfplay_protocol_sha256": fingerprint(expected_protocol),
        "selfplay_generations": len(saved["run"]["generations"]),
        "selfplay_episodes": len(episodes),
        "selfplay_raw_samples_checked": samples,
        "selfplay_exclusion_scope": "all published raw samples across all generations; conservative superset if any training window/eligibility excluded rows",
        "protected_file_sha256": file_hash(protection),
        "runs": receipts,
        "identity_set_sha256": {
            "physical": {n: fingerprint(sorted(ids)) for n, ids in physical.items()},
            "model_input": {n: fingerprint(sorted(ids)) for n, ids in inputs.items()},
        },
    }
