"""Verified completed selfplay episodes; rules remain in Rust game adapters."""

import fcntl
import hashlib
import json
import math
import re
import sys
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from training.checkpoint import atomic_json
from training.evaluation import classify_result
from training.research_data import canonical, fingerprint
from training.research_targets import visit_policy
from training.selfplay_actor import ActorConfig, _rng, sample_action
from training.selfplay_search import SearchConfig
from training.supervision import RULESET

EPISODE = "voxelshogi-selfplay-episode-v2"


def _int(value, low, high):
    return type(value) is int and low <= value <= high


def _number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _same(a, b):
    return canonical(a) == canonical(b)


def _search_facts(row, config, visits):
    s = row["search"]
    best = max(visits, key=lambda a: (visits[a], -a))
    if (
        type(s) is not dict
        or set(s)
        != {
            "best_action",
            "root_value",
            "completed_simulations",
            "model_evaluations",
            "max_depth_reached",
            "stop_reason",
        }
        or not _int(
            s["completed_simulations"],
            config.search.simulations,
            config.search.simulations,
        )
        or not _int(s["model_evaluations"], 1, config.search.simulations + 1)
        or not _int(s["max_depth_reached"], 1, config.search.max_depth)
        or not _int(s["best_action"], 0, 1_067_984)
        or s["best_action"] != best
        or not _number(s["root_value"], -1, 1)
        or s["stop_reason"] != "simulations"
    ):
        raise ValueError("invalid completed-search metadata")
    return s["model_evaluations"]


def verify_episode(
    e, *, expected_source, expected_model, expected_config, game_from_record=None
):
    """Replay every actual move and recompute label arithmetic, not neural search.

    Expected source/model/config come from the coordinator's frozen workload and
    verified artifact loader, not from the episode itself. PUCT visits are checked
    for legality, completed budget and consistency; they are not re-inferred here.
    """
    if game_from_record is None:
        if sys.platform != "linux":
            raise ValueError("real episode replay requires external Linux")
        from voxelshogi import Game

        game_from_record = Game.from_record
    if (
        not isinstance(expected_source, str)
        or re.fullmatch(r"[0-9a-f]{40}", expected_source) is None
        or not isinstance(expected_model, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_model) is None
        or not isinstance(expected_config, ActorConfig)
        or type(e) is not dict
        or set(e)
        != {
            "schema",
            "episode_id",
            "source_commit",
            "config",
            "opening",
            "model_sha256",
            "complete",
            "bootstrap",
            "bootstrap_evaluations",
            "model_evaluations",
            "termination_kind",
            "record",
            "samples",
        }
        or e["schema"] != EPISODE
        or e["complete"] is not True
        or e["source_commit"] != expected_source
        or e["model_sha256"] != expected_model
        or not _same(e["config"], asdict(expected_config))
    ):
        raise ValueError("episode provenance/config/completion differs")
    conditions = {
        k: e[k] for k in ("source_commit", "config", "opening", "model_sha256")
    }
    if e["episode_id"] != fingerprint(conditions):
        raise ValueError("episode identity differs")
    game = game_from_record(e["opening"])
    if (
        not _same(game.record(), e["opening"])
        or game.snapshot()["finished"]
        or e["opening"]["ruleset_id"] != RULESET
    ):
        raise ValueError("invalid opening or history")
    prefix = len(e["opening"]["moves"])
    moves = e["record"]["moves"]
    rows = e["samples"]
    if (
        type(moves) is not list
        or moves[:prefix] != e["opening"]["moves"]
        or not _int(len(moves) - prefix, 1, expected_config.max_plies)
        or type(rows) is not list
        or len(rows) != len(moves) - prefix
    ):
        raise ValueError("episode sample coverage differs from record")
    calls = 0
    for i, row in enumerate(rows):
        ply, snapshot, legal = prefix + i, game.snapshot(), game.legal_actions()
        if (
            snapshot["finished"]
            or type(row) is not dict
            or set(row)
            != {
                "ply",
                "side",
                "position",
                "legal_actions",
                "policy",
                "action",
                "move",
                "search",
                "value",
            }
            or not _int(row["ply"], ply, ply)
            or row["side"] != snapshot["side"]
            or row["position"] != snapshot["vsfen"]
            or not _same(row["legal_actions"], sorted(legal))
        ):
            raise ValueError("episode row differs from Rust replay")
        policy = row["policy"]
        if type(policy) is not dict or set(policy) != {
            "kind",
            "actions",
            "probabilities",
            "visits",
            "total_visits",
        }:
            raise ValueError("invalid sparse policy metadata")
        if (
            type(policy["actions"]) is not list
            or type(policy["visits"]) is not list
            or len(policy["actions"]) != len(policy["visits"])
        ):
            raise ValueError("invalid sparse policy dimensions")
        visits = dict(zip(policy["actions"], policy["visits"], strict=True))
        if (
            not _same(policy, visit_policy(sorted(legal), visits))
            or policy["total_visits"] != expected_config.search.simulations
        ):
            raise ValueError("sparse policy or completed visits differ")
        calls += _search_facts(row, expected_config, visits)
        temperature = (
            expected_config.temperature if i < expected_config.temperature_plies else 0
        )
        selected = sample_action(
            visits,
            temperature,
            _rng(expected_config, expected_model, game.record(), "action"),
        )
        if (
            not _int(row["action"], 0, 1_067_984)
            or row["action"] != selected
            or row["action"] not in legal
            or row["move"] != legal[row["action"]]
            or row["move"] != moves[ply]
        ):
            raise ValueError("played action/seed/history differs")
        game.play(row["move"])
    final = game.snapshot()
    kind = "natural" if final["finished"] else "cutoff"
    expected_record = game.record()
    if kind == "cutoff":
        if len(rows) != expected_config.max_plies:
            raise ValueError("short unfinished episode")
        expected_record.update(
            termination="MaxPlies", result={"Draw": {"reason": "MaxPlies"}}
        )
    if e["termination_kind"] != kind or not _same(e["record"], expected_record):
        raise ValueError("episode termination differs from Rust replay")
    b = e["bootstrap"]
    if kind == "natural":
        if b is not None:
            raise ValueError("natural episode cannot have bootstrap evidence")
    elif (
        type(b) is not dict
        or set(b) != {"value", "side", "ply"}
        or not _number(b["value"], -1, 1)
        or b["side"] != final["side"]
        or not _int(b["ply"], len(moves), len(moves))
    ):
        raise ValueError("invalid raw bootstrap evidence")
    for row in rows:
        if kind == "natural":
            outcome = classify_result(final["result"], row["side"])
            if outcome == "cutoff":
                raise ValueError("cutoff is not a natural value target")
            target = {
                "kind": "terminal-v1",
                "value": {"win": 1.0, "loss": -1.0, "draw": 0.0}[outcome],
            }
        else:
            horizon = len(moves) - row["ply"]
            sign = 1 if row["side"] == b["side"] else -1
            target = {
                "kind": "bootstrap-v1",
                "value": sign
                * b["value"]
                * expected_config.bootstrap_discount**horizon,
                "bootstrap_side": b["side"],
                "model_sha256": expected_model,
                "remaining_plies": horizon,
                "discount": float(expected_config.bootstrap_discount),
            }
        if not _same(row["value"], target):
            raise ValueError(
                "value target differs from independently computed result/horizon"
            )
    bootstraps = int(kind == "cutoff")
    if not _int(e["bootstrap_evaluations"], bootstraps, bootstraps) or not _int(
        e["model_evaluations"], calls + bootstraps, calls + bootstraps
    ):
        raise ValueError("episode model-call accounting differs")
    return {
        "episode_id": e["episode_id"],
        "samples": len(rows),
        "value_kind": "terminal-v1" if kind == "natural" else "bootstrap-v1",
        "model_evaluations": calls + bootstraps,
    }


def _config(raw):
    try:
        result = ActorConfig(**{**raw, "search": SearchConfig(**raw["search"])})
        if not _same(asdict(result), raw):
            raise ValueError("replay actor config differs")
        return result
    except (KeyError, TypeError) as error:
        raise ValueError("invalid replay actor config") from error


def _read_json(path):
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > 32 * 1024 * 1024
    ):
        raise ValueError("invalid replay metadata file")
    raw = path.read_bytes()
    result = json.loads(raw)
    canonical(result)  # Reject nonfinite values even in fields not used by the caller.
    return raw, result


@contextmanager
def _buffer_lock(folder):
    if folder.is_symlink():
        raise ValueError("refusing symlink replay buffer")
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / ".voxelshogi-replay-v1"
    if not marker.exists():
        if any(folder.iterdir()):
            raise ValueError("refusing unowned nonempty replay buffer")
        marker.touch(exist_ok=False)
    if marker.is_symlink() or not marker.is_file() or marker.stat().st_size:
        raise ValueError("invalid replay ownership marker")
    with marker.open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


class ReplayBuffer:
    """Immutable episodes, an atomic ordered index, and a recent replay window.

    The index is the commit point and next-slot cursor. A complete but unindexed
    file is an orphan, never a training example. Identical retries can reuse it.
    Old committed files remain available for lineage and external backup; capacity
    limits the selected training window, not a claim about disk retention.
    """

    def __init__(
        self, folder, *, source_commit, run_id, capacity, game_from_record=None
    ):
        if game_from_record is None and sys.platform != "linux":
            raise ValueError("real replay storage requires external Linux")
        if (
            not isinstance(source_commit, str)
            or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
            or not isinstance(run_id, str)
            or re.fullmatch(r"[0-9a-f]{64}", run_id) is None
            or not _int(capacity, 1, 100000)
        ):
            raise ValueError("invalid replay binding/capacity")
        self.folder, self._from_record = Path(folder), game_from_record
        self._binding = {
            "source_commit": source_commit,
            "run_id": run_id,
            "capacity": capacity,
        }
        with _buffer_lock(self.folder):
            directory = self.folder / "episodes"
            if directory.is_symlink() or directory.exists() and not directory.is_dir():
                raise ValueError("invalid replay episode directory")
            directory.mkdir(exist_ok=True)
            path = self.folder / "buffer.json"
            if not path.exists():
                if any(directory.iterdir()):
                    raise ValueError(
                        "episode files without an index cannot establish a new buffer"
                    )
                atomic_json(
                    path,
                    {
                        "schema": "voxelshogi-replay-buffer-v1",
                        "binding": self._binding,
                        "entries": [],
                    },
                )
            self._load_index()

    def _load_index(self):
        _, m = _read_json(self.folder / "buffer.json")
        if (
            type(m) is not dict
            or set(m) != {"schema", "binding", "entries"}
            or m["schema"] != "voxelshogi-replay-buffer-v1"
            or not _same(m["binding"], self._binding)
            or type(m["entries"]) is not list
            or len(m["entries"]) > 100000
        ):
            raise ValueError("replay binding or index differs")
        ids, episodes = set(), []
        for i, entry in enumerate(m["entries"]):
            if (
                type(entry) is not dict
                or set(entry)
                != {
                    "slot",
                    "path",
                    "sha256",
                    "bytes",
                    "episode_id",
                    "model_sha256",
                    "config",
                    "samples",
                    "model_evaluations",
                }
                or not _int(entry["slot"], i, i)
                or not isinstance(entry["sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None
                or entry["path"] != f"episodes/{entry['sha256']}.json"
                or not _int(entry["bytes"], 1, 32 * 1024 * 1024)
                or not _int(entry["samples"], 1, 20000)
                or not _int(entry["model_evaluations"], 1, 2**63 - 1)
                or entry["episode_id"] in ids
            ):
                raise ValueError("invalid replay index order/inventory")
            path = self.folder / entry["path"]
            if path.parent.is_symlink():
                raise ValueError("symlink replay episode directory")
            raw, episode = _read_json(path)
            if (
                len(raw) != entry["bytes"]
                or hashlib.sha256(raw).hexdigest() != entry["sha256"]
            ):
                raise ValueError("replay episode hash differs")
            facts = verify_episode(
                episode,
                expected_source=self._binding["source_commit"],
                expected_model=entry["model_sha256"],
                expected_config=_config(entry["config"]),
                game_from_record=self._from_record,
            )
            if any(
                not _same(entry[k], facts[k])
                for k in ("episode_id", "samples", "model_evaluations")
            ):
                raise ValueError("replay index differs from verified episode")
            ids.add(entry["episode_id"])
            episodes.append(episode)
        return m, episodes

    @property
    def next_slot(self):
        with _buffer_lock(self.folder):
            m, _ = self._load_index()
            return len(m["entries"])

    def append(self, slot, episode, *, model_sha256, config):
        if not _int(slot, 0, 99999):
            raise ValueError("invalid replay slot")
        facts = verify_episode(
            episode,
            expected_source=self._binding["source_commit"],
            expected_model=model_sha256,
            expected_config=config,
            game_from_record=self._from_record,
        )
        raw = (canonical(episode) + "\n").encode()
        digest = hashlib.sha256(raw).hexdigest()
        descriptor = {
            "slot": slot,
            "path": f"episodes/{digest}.json",
            "sha256": digest,
            "bytes": len(raw),
            "episode_id": facts["episode_id"],
            "model_sha256": model_sha256,
            "config": asdict(config),
            "samples": facts["samples"],
            "model_evaluations": facts["model_evaluations"],
        }
        with _buffer_lock(self.folder):
            m, _ = self._load_index()
            if slot < len(m["entries"]):
                if not _same(m["entries"][slot], descriptor):
                    raise ValueError("conflicting replay slot retry")
                return descriptor
            if slot != len(m["entries"]) or any(
                entry["episode_id"] == facts["episode_id"] for entry in m["entries"]
            ):
                raise ValueError("replay slot gap or repeated episode identity")
            path = self.folder / descriptor["path"]
            if path.parent.is_symlink() or path.is_symlink():
                raise ValueError("symlink replay episode path")
            if path.exists():
                existing, _ = _read_json(path)
                if existing != raw:
                    raise ValueError("conflicting replay orphan")
            else:
                atomic_json(path, episode)
            m["entries"].append(descriptor)
            atomic_json(self.folder / "buffer.json", m)
            return descriptor

    def episodes(self, *, window=True):
        if type(window) is not bool:
            raise ValueError("window flag must be boolean")
        with _buffer_lock(self.folder):
            _, episodes = self._load_index()
            return episodes[-self._binding["capacity"] :] if window else episodes
