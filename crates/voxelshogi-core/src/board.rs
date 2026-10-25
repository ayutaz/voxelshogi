//! The 729-square board and the initial setup.

use crate::coord::{NUM_SQUARES, SIZE, Square};
use crate::piece::{Color, Piece, PieceKind};

/// Piece placement only (no hands / side to move). One byte per square; 0 = empty.
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct Board {
    cells: [u8; NUM_SQUARES],
}

impl Default for Board {
    fn default() -> Self {
        Board::empty()
    }
}

impl Board {
    pub const fn empty() -> Board {
        Board {
            cells: [0; NUM_SQUARES],
        }
    }

    #[inline]
    pub fn get(&self, sq: Square) -> Option<Piece> {
        Piece::from_code(self.cells[sq.index()])
    }

    #[inline]
    pub fn is_empty(&self, sq: Square) -> bool {
        self.cells[sq.index()] == 0
    }

    #[inline]
    pub fn set(&mut self, sq: Square, piece: Option<Piece>) {
        self.cells[sq.index()] = piece.map_or(0, Piece::code);
    }

    /// Iterates `(square, piece)` for all occupied squares.
    pub fn pieces(&self) -> impl Iterator<Item = (Square, Piece)> + '_ {
        self.cells
            .iter()
            .enumerate()
            .filter(|(_, c)| **c != 0)
            .map(|(i, c)| {
                (
                    Square::from_index(i).unwrap(),
                    Piece::from_code(*c).unwrap(),
                )
            })
    }

    pub fn count(&self) -> usize {
        self.cells.iter().filter(|c| **c != 0).count()
    }

    pub fn find_king(&self, color: Color) -> Option<Square> {
        let code = Piece::new(color, PieceKind::King).code();
        self.cells
            .iter()
            .position(|c| *c == code)
            .and_then(Square::from_index)
    }

    /// The standard initial position of shogitter 三次元将棋 (372 pieces).
    ///
    /// Black (先手) occupies ranks 七..九 (`y = 6..8`):
    /// * rank 七 (`y = 6`): 81 pawns on every `(x, z)`.
    /// * rank 八 (`y = 7`): the 7×7 ring `max(|x-4|,|z-4|) == 3`, 12 rooks on
    ///   `x = 1` (筋2) plus `z = 1` (層II), and 12 bishops on `x = 7` (筋8) plus `z = 7` (層VIII).
    /// * rank 九 (`y = 8`): concentric squares around `(4, 8, 4)` by Chebyshev
    ///   distance `d = max(|x-4|,|z-4|)`: d0 king, d1 gold, d2 silver, d3 knight, d4 lance.
    ///
    /// White's setup is the point reflection through the board centre
    /// (`(x,y,z) -> (8-x, 8-y, 8-z)`).
    pub fn initial() -> Board {
        let mut b = Board::empty();
        let back = [
            PieceKind::King,
            PieceKind::Gold,
            PieceKind::Silver,
            PieceKind::Knight,
            PieceKind::Lance,
        ];
        let put_black = |x: u8, y: u8, z: u8, kind: PieceKind, b: &mut Board| {
            b.set(Square::new(x, y, z), Some(Piece::new(Color::Black, kind)));
            b.set(
                Square::new(8 - x, 8 - y, 8 - z),
                Some(Piece::new(Color::White, kind)),
            );
        };
        for x in 0..SIZE as u8 {
            for z in 0..SIZE as u8 {
                let d = (x as i32 - 4).abs().max((z as i32 - 4).abs()) as usize;
                put_black(x, 8, z, back[d], &mut b);
                put_black(x, 6, z, PieceKind::Pawn, &mut b);
                if d == 3 {
                    let kind = if x == 1 || (z == 1 && x != 7) {
                        PieceKind::Rook
                    } else {
                        PieceKind::Bishop
                    };
                    put_black(x, 7, z, kind, &mut b);
                }
            }
        }
        b
    }
}

impl std::fmt::Debug for Board {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Board({} pieces)", self.count())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn count(b: &Board, color: Color, kind: PieceKind) -> usize {
        b.pieces()
            .filter(|(_, p)| p.color == color && p.kind == kind)
            .count()
    }

    #[test]
    fn initial_piece_counts() {
        let b = Board::initial();
        assert_eq!(b.count(), 372);
        for c in Color::ALL {
            assert_eq!(count(&b, c, PieceKind::Pawn), 81);
            assert_eq!(count(&b, c, PieceKind::Rook), 12);
            assert_eq!(count(&b, c, PieceKind::Bishop), 12);
            assert_eq!(count(&b, c, PieceKind::King), 1);
            assert_eq!(count(&b, c, PieceKind::Gold), 8);
            assert_eq!(count(&b, c, PieceKind::Silver), 16);
            assert_eq!(count(&b, c, PieceKind::Knight), 24);
            assert_eq!(count(&b, c, PieceKind::Lance), 32);
        }
    }

    /// Hand-written placement checks taken directly from the shogitter rule definition
    /// (display coordinates 筋, 段, 層).
    #[test]
    fn initial_specific_squares() {
        let b = Board::initial();
        let at = |f, r, l| b.get(Square::from_display(f, r, l).unwrap());
        let bk = |k| Some(Piece::new(Color::Black, k));
        let wk = |k| Some(Piece::new(Color::White, k));
        assert_eq!(at(5, 9, 5), bk(PieceKind::King));
        assert_eq!(at(5, 1, 5), wk(PieceKind::King));
        assert_eq!(at(4, 9, 4), bk(PieceKind::Gold));
        assert_eq!(at(3, 9, 5), bk(PieceKind::Silver));
        assert_eq!(at(2, 9, 2), bk(PieceKind::Knight));
        assert_eq!(at(1, 9, 1), bk(PieceKind::Lance));
        assert_eq!(at(9, 9, 5), bk(PieceKind::Lance));
        // Black rooks: 筋2 層II..VIII and 層II 筋2..7.
        for l in 2..=8 {
            assert_eq!(at(2, 8, l), bk(PieceKind::Rook), "2八{l}");
            assert_eq!(at(8, 8, l), bk(PieceKind::Bishop), "8八{l}");
        }
        for f in 3..=7 {
            assert_eq!(at(f, 8, 2), bk(PieceKind::Rook), "{f}八II");
            assert_eq!(at(f, 8, 8), bk(PieceKind::Bishop), "{f}八VIII");
        }
        // White: bishops on 筋2 and 層II, rooks on 筋8 and 層VIII.
        for l in 2..=8 {
            assert_eq!(at(2, 2, l), wk(PieceKind::Bishop));
            assert_eq!(at(8, 2, l), wk(PieceKind::Rook));
        }
        for f in 3..=7 {
            assert_eq!(at(f, 2, 2), wk(PieceKind::Bishop));
            assert_eq!(at(f, 2, 8), wk(PieceKind::Rook));
        }
        // Inside of the rank-8 ring is empty.
        assert_eq!(at(5, 8, 5), None);
        assert_eq!(at(1, 8, 1), None);
        for f in 1..=9 {
            for l in 1..=9 {
                assert_eq!(at(f, 7, l), bk(PieceKind::Pawn));
                assert_eq!(at(f, 3, l), wk(PieceKind::Pawn));
                for r in 4..=6 {
                    assert_eq!(at(f, r, l), None);
                }
            }
        }
    }
}
