"""External-Linux reconstruction of declared development histories and queries.

The reviewed plan enumerates every development source used for the experiment.
Replaying a subset cannot prove that an omitted source was never used. The
owning workflow supplies that complete frozen inventory before final testing.
"""

import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

from export.research_generate import _bounded
from training.evaluation_v2 import (
    NEURAL_POLICIES,
    fingerprint,
    validate_match_rows,
    validate_protocol,
)
from training.feature_cache import file_hash
from training.generation_evaluation import _inventory
from training.research_manifest_assembly import _parse


def load_ports():
    from voxelshogi import Game

    from training.evaluation_v2_runner import (
        position_identity,
        verify_record,
        verify_run,
    )
    from training.generation_cases import replay_scored_identities
    from training.research_data import input_identity

    def parquet(path):
        import pyarrow.parquet as pq

        for batch in pq.ParquetFile(path).iter_batches(batch_size=128):
            yield from batch.to_pylist()

    def played(row, case):
        verify_record(row, case)
        return replay_scored_identities(row["record"], case["opening"])

    def query(record):
        game = Game.from_record(record)
        snapshot = game.snapshot()
        if game.record() != record or snapshot["finished"]:
            raise ValueError("development query must be Rust canonical and unfinished")
        return {
            "physical_id": position_identity(snapshot["vsfen"]),
            "input_id": input_identity(snapshot),
            "vsfen": snapshot["vsfen"],
            "side": snapshot["side"],
        }

    return {"parquet": parquet, "played": played, "query": query, "run": verify_run}


def _case(record, spec, expected=None):
    candidates = [
        c
        for c in spec["cases"]
        if record["ruleset_id"] == c["opening"]["ruleset_id"]
        and record["initial"] == c["opening"]["initial"]
        and record["moves"][: len(c["opening"]["moves"])] == c["opening"]["moves"]
    ]
    if len(candidates) != 1 or (
        expected is not None and candidates[0]["id"] != expected
    ):
        raise ValueError("development query has no unique assigned opening")
    return candidates[0]


def collect_references(
    root, value, *, deadline, clock=time.time, stop_requested=lambda: False, ports=None
):
    if sys.platform != "linux":
        raise ValueError("development reference reconstruction requires external Linux")
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("fixed development reconstruction deadline required")

    def boundary():
        if stop_requested() or clock() >= deadline:
            raise InterruptedError("fixed development reconstruction deadline")

    boundary()
    ports = load_ports() if ports is None else ports
    if set(ports) != {"parquet", "played", "query", "run"}:
        raise ValueError("complete development replay ports required")
    if (
        type(value) is not dict
        or set(value) != {"schema", "screens", "runs", "traces"}
        or value["schema"] != "voxelshogi-development-reference-plan-v1"
        or any(
            type(value[k]) is not list or not 1 <= len(value[k]) <= 128
            for k in ("screens", "runs", "traces")
        )
    ):
        raise ValueError(
            "nonempty frozen screen, run and query-trace inventory required"
        )
    frozen_plan = fingerprint(value)
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("regular acquired development source folder required")
    ids, physical, inputs, sources, checked, protocols = set(), {}, {}, {}, {}, {}
    coverage = {}

    def bind(descriptor, wanted=None):
        boundary()
        if (
            type(descriptor) is not dict
            or set(descriptor) != {"path", "bytes", "sha256"}
            or not isinstance(descriptor["path"], str)
        ):
            raise ValueError("immutable development file descriptor required")
        relative = Path(descriptor["path"])
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or relative.as_posix() != descriptor["path"]
            or (wanted is not None and descriptor["path"] != wanted)
            or type(descriptor["bytes"]) is not int
            or not 0 < descriptor["bytes"] <= 4 * 1024**3
            or re.fullmatch(r"[0-9a-f]{64}", str(descriptor["sha256"])) is None
        ):
            raise ValueError("development source path/size/hash differs")
        path = root / relative
        if (
            path in checked
            or any((root / parent).is_symlink() for parent in relative.parents)
            or path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != descriptor["bytes"]
            or file_hash(path) != descriptor["sha256"]
        ):
            raise ValueError("development source bytes/hash differ")
        checked[path] = dict(descriptor)
        return path

    def source(item):
        name = item.get("id")
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[a-z][a-z0-9-]{0,79}", name) is None
            or name in ids
            or type(item.get("games")) is not int
            or not 1 <= item["games"] <= 1000000
        ):
            raise ValueError(
                "distinct named development source and full game count required"
            )
        ids.add(name)
        key = "development/" + name
        physical[key], inputs[key], sources[key] = (
            set(),
            set(),
            {"games": 0, "queries": 0},
        )
        return name, key

    def include(key, identities):
        if type(identities) is not dict or set(identities) != {"positions", "inputs"}:
            raise ValueError("both actual development identities required")
        _inventory({"played": identities["positions"]})
        _inventory({"played": identities["inputs"]})
        physical[key].update(identities["positions"])
        inputs[key].update(identities["inputs"])

    def neural(key, row, spec, expected=None, *, screen=False):
        boundary()
        role = row["role"]
        if (
            role not in spec["participants"]
            or spec["participants"][role]["policy"] not in NEURAL_POLICIES
        ):
            raise ValueError("development query role is not the assigned neural player")
        _case(row["record"], spec, expected)
        actual = ports["query"](row["record"])
        if (
            actual["physical_id"] != row["physical_id"]
            or actual["input_id"] != row["input_id"]
            or (
                screen
                and (actual["vsfen"] != row["vsfen"] or actual["side"] != row["side"])
            )
        ):
            raise ValueError("development query identity differs from Rust replay")
        include(
            key, {"positions": {actual["physical_id"]}, "inputs": {actual["input_id"]}}
        )
        sources[key]["queries"] += 1

    for item in value["screens"]:
        if (
            type(item) is not dict
            or set(item) != {"id", "files", "games", "queries"}
            or type(item["queries"]) is not int
            or item["queries"] < 1
            or type(item["files"]) is not dict
            or set(item["files"])
            != {"config.json", "manifest.json", "matches.parquet", "queries.parquet"}
        ):
            raise ValueError("complete frozen screen files/counts required")
        name, key = source(item)
        files = {n: bind(d, name + "/" + n) for n, d in item["files"].items()}
        specs = _parse(_bounded(files["config.json"], 1024**2))["protocols"]
        if type(specs) is not dict or not 1 <= len(specs) <= 16:
            raise ValueError("screen development cohorts required")
        for spec in specs.values():
            validate_protocol(spec)
            if spec["purpose"] != "development":
                raise ValueError("final holdout cannot enter development references")
        matches = {arm: [] for arm in specs}
        for row in ports["parquet"](files["matches.parquet"]):
            boundary()
            if row["arm"] not in specs:
                raise ValueError("unexpected development screen arm")
            spec = specs[row["arm"]]
            match = _parse(row["match_json"].encode())
            if (
                row["protocol_sha256"] != validate_protocol(spec)
                or row["case_id"] != match["case_id"]
            ):
                raise ValueError("screen match condition differs")
            case = next(c for c in spec["cases"] if c["id"] == match["case_id"])
            include(key, ports["played"](match, case))
            matches[row["arm"]].append(match)
            sources[key]["games"] += 1
        for arm, rows in matches.items():
            validate_match_rows(rows, specs[arm])
        indices = Counter()
        for row in ports["parquet"](files["queries.parquet"]):
            boundary()
            if row["arm"] not in specs:
                raise ValueError("unexpected query screen arm")
            spec = specs[row["arm"]]
            indices[row["arm"]] += 1
            if (
                row["protocol_sha256"] != validate_protocol(spec)
                or row["query_index"] != indices[row["arm"]]
            ):
                raise ValueError("screen query conditions/index differ")
            neural(
                key,
                {**row, "record": _parse(row["record_json"].encode())},
                spec,
                row["case_id"],
                screen=True,
            )
        if sources[key] != {"games": item["games"], "queries": item["queries"]}:
            raise ValueError("full screen game/query enumeration differs")

    for item in value["runs"]:
        if (
            type(item) is not dict
            or set(item) != {"id", "run", "games", "query_coverage"}
            or item["query_coverage"] not in ("trace", "scored-superset")
        ):
            raise ValueError("bound completed development run required")
        name, key = source(item)
        path = bind(item["run"], name + "/run.json")
        ports["run"](path.parent)
        spec = _parse(_bounded(path.parent / "protocol.json", 1024**2))
        validate_protocol(spec)
        if spec["purpose"] != "development":
            raise ValueError("holdout cannot be a development reference")
        if item["query_coverage"] == "scored-superset" and any(
            p["policy"] == "puct32-v1" for p in spec["participants"].values()
        ):
            raise ValueError("PUCT branches require an actual neural query trace")
        protocols[name] = spec
        coverage[name] = item["query_coverage"]
        rows = []
        for case in spec["cases"]:
            for side in ("b", "w"):
                boundary()
                try:
                    row = _parse(
                        _bounded(path.parent / f"{case['id']}-{side}.json", 4 * 1024**2)
                    )
                except (OSError, ValueError) as error:
                    raise ValueError(
                        "complete scored development records required"
                    ) from error
                include(key, ports["played"](row, case))
                rows.append(row)
                sources[key]["games"] += 1
        validate_match_rows(rows, spec)
        if sources[key]["games"] != item["games"]:
            raise ValueError("complete development run game count differs")

    queried_runs = set()
    for trace in value["traces"]:
        if (
            type(trace) is not dict
            or set(trace) != {"file", "cohort_field", "cohorts", "queries"}
            or trace["cohort_field"]
            not in ("architecture", "arm", "cohort", "precision")
            or type(trace["cohorts"]) is not dict
            or not trace["cohorts"]
            or type(trace["queries"]) is not dict
            or set(trace["queries"]) != set(trace["cohorts"])
            or any(n not in protocols for n in trace["cohorts"].values())
            or any(type(n) is not int or n < 1 for n in trace["queries"].values())
        ):
            raise ValueError("bound nonempty actual query traces and cohorts required")
        path = bind(trace["file"])
        counts = Counter()
        with path.open("rb") as stream:
            while line := stream.readline(4 * 1024**2 + 1):
                boundary()
                if len(line) > 4 * 1024**2:
                    raise ValueError("bounded development query record required")
                row = _parse(line)
                label = row.get(trace["cohort_field"])
                if label not in trace["cohorts"]:
                    raise ValueError("unassigned development query cohort")
                name = trace["cohorts"][label]
                neural("development/" + name, row, protocols[name])
                counts[label] += 1
                queried_runs.add(name)
        if dict(counts) != trace["queries"]:
            raise ValueError("full neural query trace enumeration differs")
    required_runs = {
        name
        for name, spec in protocols.items()
        if coverage[name] == "trace"
        and any(p["policy"] in NEURAL_POLICIES for p in spec["participants"].values())
    }
    if not required_runs <= queried_runs:
        raise ValueError("every neural development run needs its complete query trace")
    for path, descriptor in checked.items():
        boundary()
        if (
            path.is_symlink()
            or path.stat().st_size != descriptor["bytes"]
            or file_hash(path) != descriptor["sha256"]
        ):
            raise ValueError("development source changed during replay")
    for name in protocols:
        boundary()
        ports["run"](root / name)
    if fingerprint(value) != frozen_plan:
        raise ValueError("development reference plan changed")
    boundary()
    _inventory(physical)
    _inventory(inputs)
    return {
        "physical": physical,
        "model_input": inputs,
        "receipt": {
            "schema": "voxelshogi-development-references-v1",
            "verified": True,
            "plan_sha256": frozen_plan,
            "sources": {
                name: {
                    **counts,
                    "query_coverage": "trace"
                    if name.removeprefix("development/") not in coverage
                    else coverage[name.removeprefix("development/")],
                    "query_count_is_exact": name.removeprefix("development/")
                    not in coverage
                    or coverage[name.removeprefix("development/")] == "trace",
                    "positions": len(physical[name]),
                    "inputs": len(inputs[name]),
                    "positions_sha256": fingerprint(sorted(physical[name])),
                    "inputs_sha256": fingerprint(sorted(inputs[name])),
                }
                for name, counts in sources.items()
            },
            "files": [checked[p] for p in sorted(checked)],
        },
    }
