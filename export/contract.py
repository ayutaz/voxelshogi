"""Versioned tensor/action encoding; no move generation or rule validation."""

from numbers import Integral

import numpy as np

from export.numeric import output_tolerances

INPUT_SCHEMA = "voxelshogi-standard-features-v1"
SQUARES = 729
FEATURES = 43
NORMAL_ACTIONS = SQUARES * SQUARES * 2
ACTIONS = NORMAL_ACTIONS + 7 * SQUARES
HAND_TOTALS = np.array([162, 64, 48, 32, 16, 24, 24], dtype=np.float32)


def _side(side: str) -> None:
    if side not in ("b", "w"):
        raise ValueError("side must be b or w")


def _integer(value: int, maximum: int) -> bool:
    return (
        isinstance(value, Integral)
        and not isinstance(value, bool)
        and 0 <= value <= maximum
    )


def encode_position(board: list[int], hands: list[int], side: str) -> np.ndarray:
    """[batch=1, z*81+y*9+x, channels], viewed by the side to move.

    White reverses x/y/z and swaps ownership. Channels 0..28 are one-hot
    empty/own14/opponent14; 29..35 own hands, 36..42 opponent hands.
    Counts use the standard set's totals as denominators. Legal positions
    must be validated by Rust before encoding; this checks the tensor contract.
    """
    _side(side)
    pieces = np.asarray(board)
    counts = np.asarray(hands)
    if pieces.shape != (SQUARES,) or pieces.dtype.kind not in "iu":
        raise ValueError("board must contain 729 integer piece codes")
    if np.any(pieces < 0) or np.any(pieces > 28):
        raise ValueError("piece code outside 0..28")
    if counts.shape != (14,) or counts.dtype.kind not in "iu":
        raise ValueError("hands must contain 14 integer counts")
    counts = counts.reshape(2, 7)
    if np.any(counts < 0) or np.any(counts > HAND_TOTALS):
        raise ValueError("hand count outside the standard piece set")
    if side == "w":
        pieces = pieces[::-1]
        pieces = np.where(pieces == 0, 0, (pieces.astype(np.int64) - 1 + 14) % 28 + 1)
        counts = counts[::-1]
    output = np.zeros((1, SQUARES, FEATURES), dtype=np.float32)
    output[0, np.arange(SQUARES), pieces] = 1
    output[0, :, 29:] = (counts / HAND_TOTALS).reshape(14)
    return output


def action_index(
    source: int | None,
    destination: int,
    side: str,
    *,
    promote: bool = False,
    drop_kind: int | None = None,
) -> int:
    """Normal: 2*(from*729+to)+promote. Drops: 1062882+kind*729+to.

    Squares use side-to-move canonical coordinates. Drop order P,L,N,S,G,B,R.
    This is a unique label, not a legality check; only Rust supplies legal moves.
    """
    _side(side)
    if not _integer(destination, 728) or not isinstance(promote, bool):
        raise ValueError("invalid destination or promotion flag")
    to = int(destination) if side == "b" else 728 - int(destination)
    if source is None:
        if not _integer(drop_kind, 6) or promote:
            raise ValueError("drop needs a kind and cannot promote")
        return NORMAL_ACTIONS + int(drop_kind) * SQUARES + to
    if not _integer(source, 728) or drop_kind is not None:
        raise ValueError("normal move needs a source and no drop kind")
    origin = int(source) if side == "b" else 728 - int(source)
    return 2 * (origin * SQUARES + to) + int(promote)


def compare_outputs(
    reference: np.ndarray,
    actual: np.ndarray,
    *,
    precision: str = "fp32",
    output: str = "policy",
    numeric_contract: str | None = None,
) -> dict:
    """Check every finite output, with thresholds fixed before measurement."""
    expected, observed = np.asarray(reference), np.asarray(actual)
    if expected.shape != observed.shape or expected.size == 0:
        raise ValueError("output shape mismatch or empty output")
    if expected.dtype.kind not in "fiu" or observed.dtype.kind not in "fiu":
        raise ValueError("outputs must be numeric")
    if not np.isfinite(expected).all() or not np.isfinite(observed).all():
        raise ValueError("nonfinite output")
    atol, rtol = output_tolerances(precision, output, numeric_contract)
    expected, observed = expected.astype(np.float64), observed.astype(np.float64)
    delta = np.abs(observed - expected)
    exceeded = int(np.count_nonzero(delta > atol + rtol * np.abs(expected)))
    if exceeded:
        raise ValueError(
            f"{exceeded}/{expected.size} outputs exceed {precision} tolerance"
        )
    return {
        "elements": int(expected.size),
        "max_abs": float(delta.max()),
        "max_relative": float(
            (delta / np.maximum(np.abs(expected), np.finfo(np.float32).tiny)).max()
        ),
        "exceeded": exceeded,
        "atol": atol,
        "rtol": rtol,
    }
