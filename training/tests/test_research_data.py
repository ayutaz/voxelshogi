"""Independent label/identity expectations and fake ports; no Rust or tensors."""

import hashlib
import math
from copy import deepcopy

import pytest

SOURCE = "a" * 40
RULESET = "voxelshogi-standard-v1"


class GamePort:
    def __init__(self, initial=None):
        self.seed = int(initial or 0)
        self.moves = []

    def record(self):
        return {
            "ruleset_id": RULESET,
            "initial": str(self.seed),
            "moves": list(self.moves),
            "result": None,
            "termination": None,
        }

    def snapshot(self):
        ply = len(self.moves)
        board = [0] * 729
        board[(self.seed + ply) % 729] = 1
        return {
            "ruleset_id": RULESET,
            "vsfen": f"fake-{self.seed}-{ply} b - {ply + 1}",
            "side": "b",
            "finished": False,
            "result": None,
            "board": board,
            "hands": [0] * 14,
        }

    def legal_actions(self):
        return {10: "111211", 20: "111311"}

    def play(self, move):
        assert move in self.legal_actions().values()
        self.moves.append(move)

    def search(self, **limits):
        deep = limits["max_depth"] == 3
        return {
            "best_move": "111311" if deep else "111211",
            "score": 300 if deep else 100,
            "completed_depth": limits["max_depth"],
            "nodes": 10,
            "last_iteration_nodes": 5,
            "tt_hits": 0,
            "stop_reason": "depth",
        }


def small_protocol():
    from training.research_data import pilot_protocol

    p = pilot_protocol(SOURCE)
    p.update(opening_plies=1, max_plies=100, sample_plies=[1, 3, 96])
    p["games"] = [
        {"id": "g000000", "seed": 9300, "split": "train"},
        {"id": "g000001", "seed": 9305, "split": "val"},
        {"id": "g000002", "seed": 9307, "split": "test"},
    ]
    return p


def generated():
    from training.research_data import generate_game

    p = small_protocol()
    return p, generate_game(p, p["games"][0], GamePort)


def test_preregistered_pilot_has_paired_teachers_and_fixed_family_splits():
    from training.research_data import pilot_protocol, validate_protocol

    p = pilot_protocol(SOURCE)
    assert (
        validate_protocol(p)
        == hashlib.sha256(
            __import__("json").dumps(p, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    assert [(g["seed"], g["split"]) for g in p["games"]] == [
        (9300, "train"),
        (9301, "train"),
        (9302, "train"),
        (9303, "train"),
        (9304, "train"),
        (9305, "val"),
        (9306, "val"),
        (9307, "test"),
    ]
    assert p["max_plies"] == 512 and p["opening_plies"] == 16
    assert p["sample_plies"] == [16, 48, 96, 160, 256, 384, 480]
    assert p["teachers"]["deep"] == {
        "max_depth": 3,
        "minimum_depth": 3,
        "max_nodes": 100000,
        "table_capacity": 4096,
    }
    assert p["acceptance"] == {
        "minimum_per_cell": 2,
        "minimum_deep_completion_fraction": 0.8,
    }
    assert pilot_protocol(SOURCE) == p  # No shared mutable preset.


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_commit", "main"),
        ("max_plies", True),
        ("opening_plies", 513),
        ("sample_plies", [16, 16]),
        ("sample_plies", [513]),
        ("schema", "old"),
        ("extra", 1),
    ],
)
def test_protocol_rejects_ambiguous_or_unbounded_configuration(field, value):
    from training.research_data import pilot_protocol, validate_protocol

    p = pilot_protocol(SOURCE)
    p[field] = value
    with pytest.raises(ValueError):
        validate_protocol(p)


def test_protocol_rejects_repeated_seed_family_or_unknown_search_budget():
    from training.research_data import pilot_protocol, validate_protocol

    for mutate in (
        lambda p: p["games"][1].update(seed=9300),
        lambda p: p["games"][1].update(id="g000000"),
        lambda p: p["games"][1].update(split="development"),
        lambda p: p["teachers"]["deep"].update(minimum_depth=4),
        lambda p: p["teachers"]["deep"].update(max_nodes=True),
        lambda p: p["teachers"]["deep"].update(max_time=1),
        lambda p: p["acceptance"].update(minimum_deep_completion_fraction=0),
    ):
        p = pilot_protocol(SOURCE)
        mutate(p)
        with pytest.raises(ValueError):
            validate_protocol(p)


def test_canonical_identity_matches_rotated_owner_swapped_inputs_not_history():
    from training.research_data import input_identity

    b = GamePort().snapshot()
    b["board"][0], b["board"][400] = 8, 16
    b["hands"] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    w = deepcopy(b)
    w.update(side="w", vsfen="other w - 99")
    w["board"] = [0] * 729
    # Black code8 becomes White code22 at the opposite square; code16 ->2.
    w["board"][728], w["board"][328] = 22, 2
    w["hands"] = b["hands"][7:] + b["hands"][:7]
    assert input_identity(b) == input_identity(w)
    w["hands"][0] += 1
    assert input_identity(b) != input_identity(w)
    for field, value in (
        ("board", [0] * 728),
        ("side", "x"),
        ("hands", [False] * 14),
        ("ruleset_id", "other"),
    ):
        invalid = deepcopy(b)
        invalid[field] = value
        with pytest.raises(ValueError):
            input_identity(invalid)


def test_both_teachers_annotate_same_root_without_changing_trajectory():
    from training.research_data import validate_game

    p, game = generated()
    assert len(game["record"]["moves"]) == 100
    assert game["record"]["termination"] == "MaxPlies"
    assert [row["ply"] for row in game["samples"]] == [1, 3, 96]
    # Trajectory uses depth3/20k, regardless of shallow annotation's different move.
    assert set(game["record"]["moves"][1:]) == {"111311"}
    for row in game["samples"]:
        assert len(row["history"]) == row["ply"]
        shallow, deep = row["teachers"]["shallow"], row["teachers"]["deep"]
        assert shallow["target"]["policy"] == {"kind": "best-move-v1", "action": 10}
        assert deep["target"]["policy"] == {"kind": "best-move-v1", "action": 20}
        assert shallow["target"]["value"]["value"] == math.tanh(0.1)
        assert deep["target"]["value"]["value"] == math.tanh(0.3)
    validate_game(p, p["games"][0], game, GamePort, recompute=True)


def test_seeded_prefix_has_fixed_sha256_residues_before_trajectory_search():
    from training.research_data import generate_game

    p = small_protocol()
    p.update(opening_plies=3, sample_plies=[3, 96])
    game = generate_game(p, p["games"][0], GamePort)
    # Independently calculated SHA-256 residues for seed9300, ply0..2: 1,1,0.
    assert game["record"]["moves"][:3] == ["111311", "111311", "111211"]


def test_incomplete_deep_teacher_is_preserved_but_has_no_training_target():
    from training.research_data import generate_game, validate_game

    class Incomplete(GamePort):
        def search(self, **limits):
            r = super().search(**limits)
            if limits["max_nodes"] == 100000:
                r.update(completed_depth=2, stop_reason="nodes")
            return r

    p = small_protocol()
    game = generate_game(p, p["games"][0], Incomplete)
    assert all(row["teachers"]["deep"]["target"] is None for row in game["samples"])
    assert all(row["teachers"]["shallow"]["target"] for row in game["samples"])
    validate_game(p, p["games"][0], game, Incomplete, recompute=True)


@pytest.mark.parametrize(
    "mutation",
    ["history", "input", "teacher", "target", "trajectory", "split", "missing"],
)
def test_independent_replay_rejects_modified_metadata_and_labels(mutation):
    from training.research_data import validate_game

    p, game = generated()
    row = game["samples"][0]
    if mutation == "history":
        row["history"] = []
    elif mutation == "input":
        row["input_id"] = "f" * 64
    elif mutation == "teacher":
        row["teachers"]["deep"]["search"]["score"] = 301
    elif mutation == "target":
        row["teachers"]["deep"]["target"]["value"]["value"] = 0.0
    elif mutation == "trajectory":
        game["record"]["moves"][50] = "111211"
    elif mutation == "split":
        row["split"] = "val"
    else:
        game["samples"].pop()
    with pytest.raises(ValueError):
        validate_game(p, p["games"][0], game, GamePort, recompute=True)


def test_interrupt_never_returns_completed_game():
    from training.research_data import generate_game

    p = small_protocol()
    with pytest.raises(InterruptedError):
        generate_game(p, p["games"][0], GamePort, stop_requested=lambda: True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("completed_depth", True),
        ("nodes", 100001),
        ("score", False),
        ("stop_reason", "time"),
    ],
)
def test_cached_replay_still_checks_raw_teacher_contract(field, value):
    from training.research_data import validate_game

    p, game = generated()
    game["samples"][0]["teachers"]["deep"]["search"][field] = value
    with pytest.raises(ValueError):
        validate_game(p, p["games"][0], game, GamePort, recompute=False)


def test_boolean_row_index_cannot_impersonate_integer_one():
    from training.research_data import validate_game

    p, game = generated()
    game["samples"][0]["ply"] = True
    with pytest.raises(ValueError):
        validate_game(p, p["games"][0], game, GamePort, recompute=False)


def test_natural_termination_at_cap_wins_over_cutoff_and_missing_late_is_visible():
    from training.research_data import generate_game, validate_game

    class Terminal(GamePort):
        def snapshot(self):
            s = super().snapshot()
            if len(self.moves) == 3:
                s.update(finished=True, result={"Draw": {"reason": "Repetition"}})
            return s

        def record(self):
            r = super().record()
            if len(self.moves) == 3:
                r.update(
                    result={"Draw": {"reason": "Repetition"}}, termination="Natural"
                )
            return r

    p = small_protocol()
    p.update(max_plies=3, sample_plies=[1, 3])
    game = generate_game(p, p["games"][0], Terminal)
    assert game["termination_kind"] == "natural"
    assert [r["ply"] for r in game["samples"]] == [1]
    validate_game(p, p["games"][0], game, Terminal, recompute=True)


def test_audit_excludes_all_cross_split_input_collisions_and_frozen_inputs():
    from training.research_data import audit_samples

    p, game = generated()
    row = game["samples"][0]
    val = deepcopy(row)
    val.update(game_id="g000001", split="val", physical_id="b" * 64)
    frozen = game["samples"][1]
    report = audit_samples(p, [row, val, frozen], protected={frozen["input_id"]})
    assert report["exclusions"] == {"cross_split_input": 2, "protected_input": 1}
    assert report["eligible_rows"] == 0
    assert report["screen_passed"] is False
    assert report["candidate_rows"] == 3
    assert report["selection_splits"] == ["train", "val"]
    same_split = audit_samples(p, [row, deepcopy(row)], protected=set())
    assert same_split["eligible_rows"] == 1
    assert same_split["exclusions"] == {"duplicate_input": 1}


def test_coverage_counts_actual_rows_and_never_selects_from_test():
    from training.research_data import audit_samples

    p, game = generated()
    p["acceptance"]["minimum_per_cell"] = 1
    rows = deepcopy(game["samples"])
    for row in deepcopy(game["samples"]):
        row.update(
            game_id="g000001",
            split="val",
            input_id=hashlib.sha256(row["input_id"].encode()).hexdigest(),
        )
        rows.append(row)
    report = audit_samples(p, rows, protected=set())
    assert report["screen_passed"] is True
    assert report["eligible_rows"] == 6
    assert report["cells"]["val"]["late"]["deep"] == 1
    incomplete = deepcopy(rows)
    incomplete[0]["teachers"]["deep"]["target"] = None
    insufficient = audit_samples(p, incomplete, protected=set())
    assert insufficient["deep_completion_fraction"]["early"] == 0.75
    assert insufficient["screen_passed"] is False
    for row in deepcopy(game["samples"]):
        row.update(
            game_id="g000002",
            split="test",
            input_id=hashlib.sha256((row["input_id"] + "test").encode()).hexdigest(),
        )
        row["teachers"]["deep"]["target"] = None
        rows.append(row)
    with_test = audit_samples(p, rows, protected=set())
    assert with_test["screen_passed"] is True
    assert with_test["deep_completion_fraction"] == {"early": 1, "late": 1}
    # Missing late samples or no valid deep teacher must fail the preregistered screen.
    assert not audit_samples(p, rows[:2], protected=set())["screen_passed"]
