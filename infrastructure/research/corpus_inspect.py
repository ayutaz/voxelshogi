"""External Linux candidate diagnosis, before any model training or adoption.

The execution wrapper verifies fixed HF plans/receipts for all input bytes and
publishes these small records. This script never downloads data or uses tokens.
"""

import json
import math
import sys
from collections import Counter
from pathlib import Path


def target_diagnosis(episodes, selected_ids):
    """Count origins and policy mass; never reinterpret cutoff as a draw."""
    values, terminations = Counter(), Counter()
    by_split = {s: Counter() for s in ("train", "val", "test")}
    entropies, peaks, support, visits = [], [], [], []
    selected = {i: s for s, ids in selected_ids.items() for i in ids}
    if len(selected) != sum(map(len, selected_ids.values())):
        raise ValueError("repeated selected sample ID")
    observed = set()
    for episode in episodes:
        terminations[episode["termination_kind"]] += 1
        for sample in episode["samples"]:
            sample_id = episode["episode_id"] + ":" + str(sample["ply"])
            if sample_id not in selected:
                continue
            if sample_id in observed:
                raise ValueError("repeated enumerated sample ID")
            observed.add(sample_id)
            kind = sample["value"]["kind"]
            if kind not in ("terminal-v1", "bootstrap-v1"):
                raise ValueError("unknown source value origin")
            values[kind] += 1
            by_split[selected[sample_id]][kind] += 1
            policy = sample["policy"]
            p, v = policy["probabilities"], policy["visits"]
            if (
                not p
                or len(p) != len(v)
                or len(p) != len(policy["actions"])
                or any(
                    type(x) not in (int, float)
                    or not math.isfinite(x)
                    or x <= 0
                    or x > 1
                    for x in p
                )
                or any(type(x) is not int or x < 1 for x in v)
                or not math.isclose(sum(p), 1, abs_tol=1e-9)
                or sum(v) != policy["total_visits"]
                or any(
                    not math.isclose(a, n / sum(v), abs_tol=1e-9)
                    for a, n in zip(p, v, strict=True)
                )
            ):
                raise ValueError("invalid verified sparse visit probabilities")
            entropies.append(-sum(x * math.log(x) for x in p))
            peaks.append(max(p))
            support.append(len(p))
            visits.append(sum(v))
    if observed != set(selected) or not observed:
        raise ValueError("incomplete selected target coverage")
    return {
        "schema": "voxelshogi-research-target-diagnosis-v1",
        "selected_samples": len(observed),
        "value_origins": dict(values),
        "value_origins_by_split": {s: dict(c) for s, c in by_split.items()},
        "all_source_episode_terminations": dict(terminations),
        "policy": {
            "mean_entropy_nats": sum(entropies) / len(entropies),
            "mean_max_probability": sum(peaks) / len(peaks),
            "mean_positive_support": sum(support) / len(support),
            "one_hot_samples": sum(n == 1 for n in support),
            "completed_visits_min": min(visits),
            "completed_visits_max": max(visits),
        },
        "teacher_quality_accepted": False,
        "scope": "Target provenance/distribution diagnosis only. Bootstrap values remain model estimates, cutoff is not draw, no strength or final-test adoption claim.",
    }


def inspect(
    folder, protocol_path, protection, screen_folder, output, *, stop_requested
):
    if sys.platform != "linux":
        raise ValueError("actual corpus and screen replay requires external Linux")
    import pyarrow.parquet as pq
    from voxelshogi import Game

    from training.checkpoint import atomic_json
    from training.evaluation_v2 import fingerprint, validate_protocol
    from training.evaluation_v2_runner import position_identity, verify_record
    from training.feature_cache import file_hash
    from training.generation_cases import replay_scored_identities
    from training.research_corpus import audit_selfplay_corpus
    from training.research_data import input_identity
    from training.selfplay_dataset import _load

    output = Path(output)
    output.mkdir(exist_ok=False)
    folder, screen_folder = Path(folder), Path(screen_folder)
    protocol = json.loads(Path(protocol_path).read_text())
    paths = [
        folder / "manifest.json",
        folder / "episodes.parquet",
        Path(protocol_path),
        Path(protection),
    ]
    paths += [
        screen_folder / p
        for p in (
            "config.json",
            "manifest.json",
            "matches.parquet",
            "queries.parquet",
            "roots.parquet",
        )
    ]
    before = {str(p): file_hash(p) for p in paths}
    screen = screen_folder / "config.json"
    frozen = json.loads(screen.read_text())
    development = set()
    counts = Counter()
    query_indices = Counter()
    manifest, episodes = _load(folder, protocol)
    audit = audit_selfplay_corpus(
        folder, protocol, protection, screen, screen_sha256=file_hash(screen)
    )
    atomic_json(output / "admission.json", audit)
    for row in pq.read_table(screen_folder / "queries.parquet").to_pylist():
        if stop_requested():
            raise InterruptedError("fixed external corpus deadline")
        arm = row["arm"]
        spec = frozen["protocols"][arm]
        query_indices[arm] += 1
        if (
            row["protocol_sha256"] != validate_protocol(spec)
            or row["role"] != "model"
            or row["query_index"] != query_indices[arm]
        ):
            raise ValueError("query protocol/role differs")
        record = json.loads(row["record_json"])
        cases = [
            c["id"]
            for c in spec["cases"]
            if record["ruleset_id"] == c["opening"]["ruleset_id"]
            and record["initial"] == c["opening"]["initial"]
            and record["moves"][: len(c["opening"]["moves"])] == c["opening"]["moves"]
        ]
        if cases != [row["case_id"]]:
            raise ValueError("query case differs from frozen opening")
        game = Game.from_record(record)
        snapshot = game.snapshot()
        if (
            game.record() != record
            or snapshot["finished"]
            or snapshot["vsfen"] != row["vsfen"]
            or snapshot["side"] != row["side"]
            or input_identity(snapshot) != row["input_id"]
            or position_identity(snapshot["vsfen"]) != row["physical_id"]
        ):
            raise ValueError("query canonical replay differs")
        development.add(row["input_id"])
        counts["queries"] += 1
    for row in pq.read_table(screen_folder / "matches.parquet").to_pylist():
        if stop_requested():
            raise InterruptedError("fixed external scored-history deadline")
        spec = frozen["protocols"][row["arm"]]
        case = next(c for c in spec["cases"] if c["id"] == row["case_id"])
        match = json.loads(row["match_json"])
        if row["protocol_sha256"] != validate_protocol(spec):
            raise ValueError("match protocol differs")
        verify_record(match, case)
        development.update(
            replay_scored_identities(match["record"], case["opening"])["inputs"]
        )
        counts["matches"] += 1
    if (
        counts != {"queries": 24579, "matches": 48}
        or len(development) != 18121
        or query_indices != {"legal-argmax-v1": 720, "puct32-v1": 23859}
    ):
        raise ValueError("full development scored/query coverage differs")
    overlap = [r["id"] for r in audit["metadata"] if r["input"] in development]
    development_check = {
        "schema": "voxelshogi-research-full-development-protection-v1",
        "all_source_inputs_checked": len(audit["metadata"]),
        "scored_and_query_inputs": len(development),
        "checked_records": dict(counts),
        "input_set_sha256": fingerprint(sorted(development)),
        "source_release_manifest_sha256": file_hash(screen_folder / "manifest.json"),
        "overlaps": overlap,
        "passed": not overlap,
    }
    atomic_json(output / "development-protection.json", development_check)
    if overlap:
        raise ValueError("source overlaps full development inputs; no pilot permitted")
    diagnosis = target_diagnosis(episodes, audit["admission"]["selected_ids"])
    atomic_json(output / "target-diagnosis.json", diagnosis)
    if any(file_hash(Path(p)) != digest for p, digest in before.items()):
        raise ValueError("candidate or screen source changed during diagnosis")
    result = {
        "schema": "voxelshogi-research-candidate-diagnosis-v1",
        "admission_sha256": fingerprint(audit),
        "development_protection_sha256": fingerprint(development_check),
        "diagnosis_sha256": fingerprint(diagnosis),
        "source_bytes": before,
        "usable_counts": audit["admission"]["usable_for_pilot"],
        "teacher_quality_accepted": False,
        "training_executed": False,
        "source_generations": len(manifest["run"]["generations"]),
        "scope": "Full-source replay/admission and development-input protection/target diagnosis only. Review measured distribution before committing pilot data; final evaluation remains untouched.",
    }
    atomic_json(output / "result.json", result)
    return result
