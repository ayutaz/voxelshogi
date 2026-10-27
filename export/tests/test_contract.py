import numpy as np
import pytest

from export.contract import (
    ACTIONS,
    FEATURES,
    INPUT_SCHEMA,
    action_index,
    compare_outputs,
    encode_position,
)


def test_piece_channels_axes_and_hands_have_independent_expected_values():
    board = [0] * 729
    board[0], board[102], board[728] = 1, 14, 28  # x=3,y=2,z=1 => 81+18+3
    features = encode_position(board, [81, 32, 24, 16, 8, 12, 12] + [0] * 7, "b")
    assert INPUT_SCHEMA == "voxelshogi-standard-features-v1"
    assert FEATURES == 43
    assert features.shape == (1, 729, 43)
    assert features.dtype == np.float32
    np.testing.assert_array_equal(features[0, :, :29].sum(axis=1), np.ones(729))
    assert features[0, 0, 1] == 1
    assert features[0, 102, 14] == 1
    assert features[0, 728, 28] == 1
    assert features[0, 103, 0] == 1
    np.testing.assert_array_equal(features[0, :, 29:36], np.full((729, 7), 0.5))
    np.testing.assert_array_equal(features[0, :, 36:], np.zeros((729, 7)))


def test_white_canonical_view_reverses_all_axes_and_swaps_piece_and_hand_owners():
    board = [0] * 729
    board[0], board[102], board[728] = 1, 14, 28
    features = encode_position(board, [0] * 7 + [81, 32, 24, 16, 8, 12, 12], "w")
    assert features[0, 0, 14] == 1
    assert features[0, 626, 28] == 1
    assert features[0, 728, 15] == 1
    np.testing.assert_array_equal(features[0, :, 29:36], np.full((729, 7), 0.5))
    np.testing.assert_array_equal(features[0, :, 36:], np.zeros((729, 7)))


@pytest.mark.parametrize(
    "board,hands,side",
    [
        ([0] * 728, [0] * 14, "b"),
        ([29] + [0] * 728, [0] * 14, "b"),
        ([0.5] + [0] * 728, [0] * 14, "b"),
        ([False] * 729, [0] * 14, "b"),
        ([0] * 729, [0] * 13, "b"),
        ([0] * 729, [0, 65] + [0] * 12, "b"),
        ([0] * 729, [-1] + [0] * 13, "b"),
        ([0] * 729, [0] * 14, "x"),
    ],
)
def test_invalid_feature_inputs_are_rejected(board, hands, side):
    with pytest.raises(ValueError):
        encode_position(board, hands, side)


def test_action_indices_distinguish_promotion_drop_kind_and_canonical_side():
    assert ACTIONS == 1_067_985
    assert action_index(0, 728, "b") == 1456
    assert action_index(0, 728, "b", promote=True) == 1457
    assert action_index(728, 728, "b", promote=True) == 1_062_881
    assert action_index(None, 0, "b", drop_kind=0) == 1_062_882
    assert action_index(None, 728, "b", drop_kind=6) == 1_067_984
    assert action_index(728, 0, "w") == 1456
    assert action_index(None, 728, "w", drop_kind=0) == 1_062_882


@pytest.mark.parametrize(
    "source,destination,side,options",
    [
        (729, 0, "b", {}),
        (-1, 0, "b", {}),
        (True, 0, "b", {}),
        (0, 729, "b", {}),
        (0, 0, "x", {}),
        (None, 0, "b", {}),
        (None, 0, "b", {"drop_kind": 7}),
        (None, 0, "b", {"drop_kind": 0, "promote": True}),
        (0, 1, "b", {"drop_kind": 0}),
    ],
)
def test_invalid_actions_are_rejected(source, destination, side, options):
    with pytest.raises(ValueError):
        action_index(source, destination, side, **options)


def test_numerical_check_uses_all_outputs_and_fixed_absolute_plus_relative_bounds():
    expected = np.array([0.0, 1.0, -2.0], np.float32)
    actual = np.array([0.000009, 1.00009, -2.00019], np.float32)
    report = compare_outputs(expected, actual)
    assert report["elements"] == 3
    assert report["max_abs"] == pytest.approx(0.00019, abs=2e-7)
    with pytest.raises(ValueError, match="tolerance"):
        compare_outputs(expected, np.array([0.000011, 1.0, -2.0], np.float32))
    with pytest.raises(ValueError, match="tolerance"):
        compare_outputs(expected, np.zeros(3, np.float32))


@pytest.mark.parametrize(
    "actual", [np.array([np.nan]), np.array([np.inf]), np.zeros((1, 1)), np.zeros(0)]
)
def test_shape_nonfinite_and_empty_outputs_cannot_pass(actual):
    with pytest.raises(ValueError):
        compare_outputs(np.array([0.0]), actual)


def test_reference_must_be_finite_too():
    with pytest.raises(ValueError):
        compare_outputs(np.array([np.nan]), np.array([0.0]))
