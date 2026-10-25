//! Board geometry: squares and coordinates of the 9×9×9 board.
//!
//! Internal coordinates are 0-indexed `(x, y, z)`:
//!
//! * `x` — 筋 (file). Display value is `x + 1` (1..9). As in ordinary shogi
//!   notation, file 1 is on Black's (先手) right-hand side.
//! * `y` — 段 (rank). Display value is `y + 1` written as a kanji numeral
//!   (一..九). Rank 一 (`y = 0`) is White's (後手) back rank.
//! * `z` — 層 (layer). Display value is a Roman numeral I..IX (`z + 1`).
//!   `z` is the shared "up/down" axis for both players.
//!
//! Black moves towards decreasing `y`, White towards increasing `y`.
//! This matches the shogitter.com 三次元将棋 coordinate convention.

use std::fmt;

pub const SIZE: usize = 9;
pub const NUM_SQUARES: usize = SIZE * SIZE * SIZE;

/// A square on the board, stored as `z * 81 + y * 9 + x`.
#[derive(Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Square(u16);

impl Square {
    /// Creates a square from 0-indexed coordinates. Panics in debug builds if out of range.
    #[inline]
    pub const fn new(x: u8, y: u8, z: u8) -> Square {
        debug_assert!((x as usize) < SIZE && (y as usize) < SIZE && (z as usize) < SIZE);
        Square(z as u16 * 81 + y as u16 * 9 + x as u16)
    }

    /// Creates a square from signed coordinates, returning `None` when off the board.
    #[inline]
    pub fn from_i32(x: i32, y: i32, z: i32) -> Option<Square> {
        if (0..SIZE as i32).contains(&x) && (0..SIZE as i32).contains(&y) && (0..SIZE as i32).contains(&z) {
            Some(Square::new(x as u8, y as u8, z as u8))
        } else {
            None
        }
    }

    #[inline]
    pub fn from_index(index: usize) -> Option<Square> {
        (index < NUM_SQUARES).then_some(Square(index as u16))
    }

    #[inline]
    pub const fn index(self) -> usize {
        self.0 as usize
    }

    #[inline]
    pub const fn x(self) -> u8 {
        (self.0 % 9) as u8
    }

    #[inline]
    pub const fn y(self) -> u8 {
        ((self.0 / 9) % 9) as u8
    }

    #[inline]
    pub const fn z(self) -> u8 {
        (self.0 / 81) as u8
    }

    #[inline]
    pub const fn xyz(self) -> (u8, u8, u8) {
        (self.x(), self.y(), self.z())
    }

    /// Coordinates as `[i32; 3]` for vector arithmetic.
    #[inline]
    pub const fn v(self) -> [i32; 3] {
        [self.x() as i32, self.y() as i32, self.z() as i32]
    }

    #[inline]
    pub fn offset(self, dx: i32, dy: i32, dz: i32) -> Option<Square> {
        Square::from_i32(self.x() as i32 + dx, self.y() as i32 + dy, self.z() as i32 + dz)
    }

    /// Iterates all 729 squares in index order.
    pub fn all() -> impl Iterator<Item = Square> {
        (0..NUM_SQUARES as u16).map(Square)
    }

    /// Display coordinates `(筋, 段, 層)`, each 1..9.
    pub const fn display(self) -> (u8, u8, u8) {
        (self.x() + 1, self.y() + 1, self.z() + 1)
    }

    /// Creates a square from 1-indexed display coordinates `(筋, 段, 層)`.
    pub fn from_display(file: u8, rank: u8, layer: u8) -> Option<Square> {
        Square::from_i32(file as i32 - 1, rank as i32 - 1, layer as i32 - 1)
    }

    /// Japanese display string such as `5五V`.
    pub fn to_japanese(self) -> String {
        let (f, r, l) = self.display();
        format!("{}{}{}", f, KANJI_DIGITS[r as usize], ROMAN[l as usize])
    }

    /// Compact ASCII notation: three digits `file rank layer`, e.g. `555`.
    pub fn to_ascii(self) -> String {
        let (f, r, l) = self.display();
        format!("{f}{r}{l}")
    }

    /// Parses the compact ASCII notation produced by [`Square::to_ascii`].
    pub fn parse_ascii(s: &str) -> Option<Square> {
        let b = s.as_bytes();
        if b.len() != 3 || !b.iter().all(|c| (b'1'..=b'9').contains(c)) {
            return None;
        }
        Square::from_display(b[0] - b'0', b[1] - b'0', b[2] - b'0')
    }
}

impl fmt::Debug for Square {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Square({},{},{})", self.x(), self.y(), self.z())
    }
}

impl fmt::Display for Square {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.to_ascii())
    }
}

const KANJI_DIGITS: [&str; 10] = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"];
const ROMAN: [&str; 10] = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"];

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_all_squares() {
        for sq in Square::all() {
            let (x, y, z) = sq.xyz();
            assert_eq!(Square::new(x, y, z), sq);
            assert_eq!(Square::parse_ascii(&sq.to_ascii()), Some(sq));
            let (f, r, l) = sq.display();
            assert_eq!(Square::from_display(f, r, l), Some(sq));
        }
        assert_eq!(Square::all().count(), 729);
    }

    #[test]
    fn display_strings() {
        let sq = Square::new(4, 4, 4);
        assert_eq!(sq.to_japanese(), "5五V");
        assert_eq!(sq.to_ascii(), "555");
        assert_eq!(Square::new(0, 8, 8).to_japanese(), "1九IX");
    }

    #[test]
    fn bounds() {
        assert_eq!(Square::from_i32(-1, 0, 0), None);
        assert_eq!(Square::from_i32(0, 9, 0), None);
        assert_eq!(Square::new(8, 8, 8).offset(1, 0, 0), None);
        assert_eq!(Square::parse_ascii("055"), None);
        assert_eq!(Square::parse_ascii("5555"), None);
    }
}
