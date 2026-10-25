//! Moves and their compact ASCII notation (docs/RULESET.md §7).

use crate::coord::Square;
use crate::piece::PieceKind;

/// A move: either a board move (with optional promotion) or a drop from hand.
#[derive(
    Clone, Copy, PartialEq, Eq, Hash, Debug, PartialOrd, Ord, serde::Serialize, serde::Deserialize,
)]
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

/// `577567`, `533523+` (promotion) or `P*565` (drop). See docs/RULESET.md §7.
impl std::fmt::Display for Move {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match *self {
            Move::Normal { from, to, promote } => {
                write!(
                    f,
                    "{}{}{}",
                    from.to_ascii(),
                    to.to_ascii(),
                    if promote { "+" } else { "" }
                )
            }
            Move::Drop { kind, to } => write!(f, "{}*{}", kind.usi(), to.to_ascii()),
        }
    }
}
