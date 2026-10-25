//! Players and piece kinds.

use std::fmt;

/// The side to move. Black (先手, ☗) moves first and moves towards decreasing `y`.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug, PartialOrd, Ord)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum Color {
    Black = 0,
    White = 1,
}

/// Alias used in the public API to match the project specification.
pub type Player = Color;

impl Color {
    pub const ALL: [Color; 2] = [Color::Black, Color::White];

    #[inline]
    pub const fn opponent(self) -> Color {
        match self {
            Color::Black => Color::White,
            Color::White => Color::Black,
        }
    }

    #[inline]
    pub const fn index(self) -> usize {
        self as usize
    }

    /// The `y` direction this side moves "forward".
    #[inline]
    pub const fn forward(self) -> i32 {
        match self {
            Color::Black => -1,
            Color::White => 1,
        }
    }

    /// Distance (0-based) from this side's far edge, i.e. 0 for the last rank.
    /// Black's last rank is `y = 0`, White's is `y = 8`.
    #[inline]
    pub const fn relative_rank(self, y: u8) -> u8 {
        match self {
            Color::Black => y,
            Color::White => 8 - y,
        }
    }
}

/// All 14 piece kinds (8 base kinds and 6 promoted kinds).
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug, PartialOrd, Ord)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum PieceKind {
    Pawn = 0,
    Lance = 1,
    Knight = 2,
    Silver = 3,
    Gold = 4,
    Bishop = 5,
    Rook = 6,
    King = 7,
    Tokin = 8,
    PromotedLance = 9,
    PromotedKnight = 10,
    PromotedSilver = 11,
    Horse = 12,
    Dragon = 13,
}

pub const NUM_PIECE_KINDS: usize = 14;
/// Number of kinds that can be held in hand.
pub const NUM_HAND_KINDS: usize = 7;

impl PieceKind {
    pub const ALL: [PieceKind; NUM_PIECE_KINDS] = [
        PieceKind::Pawn,
        PieceKind::Lance,
        PieceKind::Knight,
        PieceKind::Silver,
        PieceKind::Gold,
        PieceKind::Bishop,
        PieceKind::Rook,
        PieceKind::King,
        PieceKind::Tokin,
        PieceKind::PromotedLance,
        PieceKind::PromotedKnight,
        PieceKind::PromotedSilver,
        PieceKind::Horse,
        PieceKind::Dragon,
    ];

    /// Kinds that can be held in hand and dropped, in hand-index order.
    pub const HAND: [PieceKind; NUM_HAND_KINDS] = [
        PieceKind::Pawn,
        PieceKind::Lance,
        PieceKind::Knight,
        PieceKind::Silver,
        PieceKind::Gold,
        PieceKind::Bishop,
        PieceKind::Rook,
    ];

    #[inline]
    pub const fn index(self) -> usize {
        self as usize
    }

    #[inline]
    pub fn from_index(i: usize) -> Option<PieceKind> {
        PieceKind::ALL.get(i).copied()
    }

    /// Index into the hand array, or `None` for kings and promoted pieces.
    #[inline]
    pub const fn hand_index(self) -> Option<usize> {
        if (self as usize) < NUM_HAND_KINDS { Some(self as usize) } else { None }
    }

    #[inline]
    pub const fn promote(self) -> Option<PieceKind> {
        match self {
            PieceKind::Pawn => Some(PieceKind::Tokin),
            PieceKind::Lance => Some(PieceKind::PromotedLance),
            PieceKind::Knight => Some(PieceKind::PromotedKnight),
            PieceKind::Silver => Some(PieceKind::PromotedSilver),
            PieceKind::Bishop => Some(PieceKind::Horse),
            PieceKind::Rook => Some(PieceKind::Dragon),
            _ => None,
        }
    }

    /// The unpromoted kind (what a captured piece becomes in hand).
    #[inline]
    pub const fn unpromote(self) -> PieceKind {
        match self {
            PieceKind::Tokin => PieceKind::Pawn,
            PieceKind::PromotedLance => PieceKind::Lance,
            PieceKind::PromotedKnight => PieceKind::Knight,
            PieceKind::PromotedSilver => PieceKind::Silver,
            PieceKind::Horse => PieceKind::Bishop,
            PieceKind::Dragon => PieceKind::Rook,
            k => k,
        }
    }

    #[inline]
    pub const fn is_promoted(self) -> bool {
        (self as usize) >= 8
    }

    #[inline]
    pub const fn can_promote(self) -> bool {
        self.promote().is_some()
    }

    /// Moves like a gold general (金, と, 成香, 成桂, 成銀).
    #[inline]
    pub const fn is_gold_like(self) -> bool {
        matches!(
            self,
            PieceKind::Gold
                | PieceKind::Tokin
                | PieceKind::PromotedLance
                | PieceKind::PromotedKnight
                | PieceKind::PromotedSilver
        )
    }

    /// USI-style letter (uppercase) for the base kind, with `+` prefix for promoted kinds.
    pub const fn usi(self) -> &'static str {
        match self {
            PieceKind::Pawn => "P",
            PieceKind::Lance => "L",
            PieceKind::Knight => "N",
            PieceKind::Silver => "S",
            PieceKind::Gold => "G",
            PieceKind::Bishop => "B",
            PieceKind::Rook => "R",
            PieceKind::King => "K",
            PieceKind::Tokin => "+P",
            PieceKind::PromotedLance => "+L",
            PieceKind::PromotedKnight => "+N",
            PieceKind::PromotedSilver => "+S",
            PieceKind::Horse => "+B",
            PieceKind::Dragon => "+R",
        }
    }

    /// Parses a base (unpromoted) letter, case-insensitive.
    pub fn from_letter(c: char) -> Option<PieceKind> {
        Some(match c.to_ascii_uppercase() {
            'P' => PieceKind::Pawn,
            'L' => PieceKind::Lance,
            'N' => PieceKind::Knight,
            'S' => PieceKind::Silver,
            'G' => PieceKind::Gold,
            'B' => PieceKind::Bishop,
            'R' => PieceKind::Rook,
            'K' => PieceKind::King,
            _ => return None,
        })
    }

    /// Japanese name (歩, と, 竜 ...).
    pub const fn japanese(self) -> &'static str {
        match self {
            PieceKind::Pawn => "歩",
            PieceKind::Lance => "香",
            PieceKind::Knight => "桂",
            PieceKind::Silver => "銀",
            PieceKind::Gold => "金",
            PieceKind::Bishop => "角",
            PieceKind::Rook => "飛",
            PieceKind::King => "玉",
            PieceKind::Tokin => "と",
            PieceKind::PromotedLance => "杏",
            PieceKind::PromotedKnight => "圭",
            PieceKind::PromotedSilver => "全",
            PieceKind::Horse => "馬",
            PieceKind::Dragon => "竜",
        }
    }
}

/// A piece on the board.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Piece {
    pub color: Color,
    pub kind: PieceKind,
}

impl Piece {
    #[inline]
    pub const fn new(color: Color, kind: PieceKind) -> Piece {
        Piece { color, kind }
    }

    /// Compact non-zero code: `1 + kind + 14 * color` (1..=28). 0 is reserved for empty.
    #[inline]
    pub const fn code(self) -> u8 {
        1 + self.kind as u8 + 14 * self.color as u8
    }

    #[inline]
    pub fn from_code(code: u8) -> Option<Piece> {
        if code == 0 || code > 28 {
            return None;
        }
        let c = code - 1;
        let color = if c >= 14 { Color::White } else { Color::Black };
        Some(Piece::new(color, PieceKind::from_index((c % 14) as usize)?))
    }
}

impl fmt::Display for Piece {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let s = self.kind.usi();
        match self.color {
            Color::Black => f.write_str(s),
            Color::White => f.write_str(&s.to_ascii_lowercase()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn promotion_roundtrip() {
        for k in PieceKind::ALL {
            if let Some(p) = k.promote() {
                assert!(p.is_promoted());
                assert_eq!(p.unpromote(), k);
            }
            assert!(k.unpromote().hand_index().is_some() || k == PieceKind::King);
        }
        assert_eq!(PieceKind::Gold.promote(), None);
        assert_eq!(PieceKind::King.promote(), None);
    }

    #[test]
    fn promotion_table_is_exact() {
        use PieceKind::*;
        let expected = [
            (Pawn, Some(Tokin)),
            (Lance, Some(PromotedLance)),
            (Knight, Some(PromotedKnight)),
            (Silver, Some(PromotedSilver)),
            (Gold, None),
            (Bishop, Some(Horse)),
            (Rook, Some(Dragon)),
            (King, None),
            (Tokin, None),
            (PromotedLance, None),
            (PromotedKnight, None),
            (PromotedSilver, None),
            (Horse, None),
            (Dragon, None),
        ];
        for (k, p) in expected {
            assert_eq!(k.promote(), p, "{k:?}");
            assert_eq!(k.can_promote(), p.is_some(), "{k:?}");
        }
        let gold_like: Vec<_> = PieceKind::ALL.into_iter().filter(|k| k.is_gold_like()).collect();
        assert_eq!(gold_like, vec![Gold, Tokin, PromotedLance, PromotedKnight, PromotedSilver]);
        let hand: Vec<_> = PieceKind::ALL.into_iter().filter(|k| k.hand_index().is_some()).collect();
        assert_eq!(hand, PieceKind::HAND.to_vec());
    }

    #[test]
    fn color_directions() {
        assert_eq!(Color::Black.forward(), -1);
        assert_eq!(Color::White.forward(), 1);
        assert_eq!(Color::Black.opponent(), Color::White);
        assert_eq!(Color::Black.relative_rank(0), 0);
        assert_eq!(Color::White.relative_rank(8), 0);
        assert_eq!(Color::White.relative_rank(0), 8);
    }

    #[test]
    fn piece_codes() {
        for c in Color::ALL {
            for k in PieceKind::ALL {
                let p = Piece::new(c, k);
                assert_eq!(Piece::from_code(p.code()), Some(p));
            }
        }
        assert_eq!(Piece::from_code(0), None);
        assert_eq!(Piece::from_code(29), None);
    }
}
