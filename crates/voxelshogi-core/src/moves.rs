//! Moves and their compact ASCII notation (docs/RULESET.md §7).

use crate::coord::Square;
use crate::piece::PieceKind;

/// A move: either a board move (with optional promotion) or a drop from hand.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug, PartialOrd, Ord)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum Move {
    Normal {
        from: Square,
        to: Square,
        promote: bool,
    },
    Drop {
        kind: PieceKind,
        to: Square,
    },
}

impl Move {
    pub fn to(&self) -> Square {
        match *self {
            Move::Normal { to, .. } | Move::Drop { to, .. } => to,
        }
    }
}
