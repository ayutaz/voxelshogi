//! Zobrist hashing of positions (board, hands, side to move).
//!
//! Keys are generated from a fixed SplitMix64 seed so that hashes are identical
//! on every platform and build. Datasets store these hashes, so the seed and the
//! generation order must never change within a `ruleset_id`.

use std::sync::OnceLock;

use crate::board::Board;
use crate::coord::NUM_SQUARES;
use crate::piece::{Color, NUM_HAND_KINDS};

const SEED: u64 = 0x766F_7865_6C73_6867; // "voxelshg"
/// Maximum number of pieces of one kind a player can hold (all 162 pawns).
const MAX_HAND: usize = 162;

struct Keys {
    piece: Vec<[u64; 29]>, // per square, per piece code (0 unused)
    hand: [[[u64; MAX_HAND + 1]; NUM_HAND_KINDS]; 2],
    white_to_move: u64,
}

fn splitmix(state: &mut u64) -> u64 {
    *state = state.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = *state;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

fn keys() -> &'static Keys {
    static KEYS: OnceLock<Keys> = OnceLock::new();
    KEYS.get_or_init(|| {
        let mut s = SEED;
        let mut piece = vec![[0u64; 29]; NUM_SQUARES];
        for row in piece.iter_mut() {
            for k in row.iter_mut().skip(1) {
                *k = splitmix(&mut s);
            }
        }
        let mut hand = [[[0u64; MAX_HAND + 1]; NUM_HAND_KINDS]; 2];
        for color in hand.iter_mut() {
            for kind in color.iter_mut() {
                // count 0 hashes to 0 so that empty hands contribute nothing
                for k in kind.iter_mut().skip(1) {
                    *k = splitmix(&mut s);
                }
            }
        }
        Keys {
            piece,
            hand,
            white_to_move: splitmix(&mut s),
        }
    })
}

/// Full (non-incremental) hash of a position.
pub fn hash_position(board: &Board, hands: &[[u8; NUM_HAND_KINDS]; 2], side: Color) -> u64 {
    let k = keys();
    let mut h = 0u64;
    for (sq, p) in board.pieces() {
        h ^= k.piece[sq.index()][p.code() as usize];
    }
    for (c, color_hands) in hands.iter().enumerate() {
        for (i, &n) in color_hands.iter().enumerate() {
            h ^= k.hand[c][i][(n as usize).min(MAX_HAND)];
        }
    }
    if side == Color::White {
        h ^= k.white_to_move;
    }
    h
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keys_are_distinct_and_nonzero() {
        let k = keys();
        let mut all: Vec<u64> = k
            .piece
            .iter()
            .flat_map(|r| r[1..].iter().copied())
            .collect();
        for c in &k.hand {
            for kind in c {
                all.extend_from_slice(&kind[1..]);
            }
        }
        all.push(k.white_to_move);
        assert!(all.iter().all(|&v| v != 0));
        let n = all.len();
        all.sort_unstable();
        all.dedup();
        assert_eq!(all.len(), n);
    }

    /// Golden value: changing this means every published dataset hash changes.
    #[test]
    fn initial_position_hash_is_pinned() {
        let h = hash_position(&Board::initial(), &[[0; NUM_HAND_KINDS]; 2], Color::Black);
        assert_eq!(format!("{h:016x}"), INITIAL_HASH);
    }

    const INITIAL_HASH: &str = "043b66e12f6b84fd";
}
