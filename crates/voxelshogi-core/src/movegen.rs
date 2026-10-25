//! Piece movement: pseudo-legal destination squares and attack queries.
//!
//! See docs/RULESET.md for the movement rules. Offsets below are written for
//! Black (forward = -y); White mirrors the `y` component.
//!
//! Sliding pieces use incremental dynamic programming instead of testing every
//! blocker against every target:
//!
//! * Rook (3D 飛車): a target sharing at least one coordinate with the origin is
//!   reachable iff the axis-aligned rectangle spanned by origin and target holds
//!   no piece other than the two endpoints.
//! * Bishop (3D 角): for a target `(a, a, b)` (two axes moved `a`, the third
//!   `b <= a`) the blocking region is the "trapezoid" `{(m, m, k) : 1 <= m <= a,
//!   0 <= k <= min(m, b)}` minus the target. A space-diagonal target (`b == a`)
//!   needs all three trapezoids (one per pair of equal axes) to be clear.

use crate::board::Board;
use crate::coord::{SIZE, Square};
use crate::piece::{Color, Piece, PieceKind};

type Offset = [i32; 3];

const fn neighbours() -> [Offset; 26] {
    let mut out = [[0; 3]; 26];
    let mut n = 0;
    let mut dx = -1;
    while dx <= 1 {
        let mut dy = -1;
        while dy <= 1 {
            let mut dz = -1;
            while dz <= 1 {
                if !(dx == 0 && dy == 0 && dz == 0) {
                    out[n] = [dx, dy, dz];
                    n += 1;
                }
                dz += 1;
            }
            dy += 1;
        }
        dx += 1;
    }
    out
}

/// Gold: the 26 neighbours minus the same-layer diagonal-back pair and the
/// whole back row (3 squares) of the upper and lower layers.
const fn gold() -> [Offset; 18] {
    let all = neighbours();
    let mut out = [[0; 3]; 18];
    let mut n = 0;
    let mut i = 0;
    while i < 26 {
        let [dx, dy, dz] = all[i];
        let excluded = dy == 1 && ((dz == 0 && dx != 0) || dz != 0);
        if !excluded {
            out[n] = all[i];
            n += 1;
        }
        i += 1;
    }
    out
}

const KING: [Offset; 26] = neighbours();
const GOLD: [Offset; 18] = gold();
const PAWN: [Offset; 1] = [[0, -1, 0]];
const KNIGHT: [Offset; 4] = [[-1, -2, -1], [-1, -2, 1], [1, -2, -1], [1, -2, 1]];
const SILVER: [Offset; 13] = [
    [-1, -1, -1],
    [-1, -1, 0],
    [-1, -1, 1],
    [0, -1, -1],
    [0, -1, 0],
    [0, -1, 1],
    [1, -1, -1],
    [1, -1, 0],
    [1, -1, 1],
    [-1, 1, -1],
    [-1, 1, 1],
    [1, 1, -1],
    [1, 1, 1],
];

/// Step (non-sliding) offsets for Black.
fn step_offsets(kind: PieceKind) -> &'static [Offset] {
    match kind {
        PieceKind::Pawn => &PAWN,
        PieceKind::Knight => &KNIGHT,
        PieceKind::Silver => &SILVER,
        PieceKind::King | PieceKind::Horse | PieceKind::Dragon => &KING,
        k if k.is_gold_like() => &GOLD,
        _ => &[],
    }
}

#[inline]
fn oriented(o: Offset, color: Color) -> Offset {
    match color {
        Color::Black => o,
        Color::White => [o[0], -o[1], o[2]],
    }
}

/// Number of steps available from coordinate `c` in direction `sign`.
#[inline]
fn room(c: i32, sign: i32) -> i32 {
    if sign > 0 { SIZE as i32 - 1 - c } else { c }
}

#[inline]
fn at(o: Offset) -> Square {
    Square::new(o[0] as u8, o[1] as u8, o[2] as u8)
}

struct Gen<'a> {
    board: &'a Board,
    color: Color,
    out: &'a mut Vec<Square>,
}

impl Gen<'_> {
    #[inline]
    fn empty(&self, p: Offset) -> bool {
        self.board.is_empty(at(p))
    }

    #[inline]
    fn push_if_landable(&mut self, s: Square) {
        if self.board.get(s).is_none_or(|q| q.color != self.color) {
            self.out.push(s);
        }
    }

    fn steps(&mut self, from: Square, offsets: &[Offset]) {
        for &o in offsets {
            let [dx, dy, dz] = oriented(o, self.color);
            if let Some(t) = from.offset(dx, dy, dz) {
                self.push_if_landable(t);
            }
        }
    }

    fn slide(&mut self, from: Square, d: Offset) {
        let mut cur = from;
        while let Some(t) = cur.offset(d[0], d[1], d[2]) {
            self.push_if_landable(t);
            if !self.board.is_empty(t) {
                break;
            }
            cur = t;
        }
    }

    /// Rook targets. With `skip_adjacent`, targets at Chebyshev distance 1 are
    /// omitted (the dragon adds them as unblockable king steps instead).
    fn rook(&mut self, from: Square, skip_adjacent: bool) {
        for axis in 0..3 {
            for sign in [-1, 1] {
                let mut d = [0; 3];
                d[axis] = sign;
                let first = self.out.len();
                self.slide(from, d);
                if skip_adjacent && self.out.len() > first {
                    // the first square of a slide is adjacent; drop it if pushed
                    let adj = from.offset(d[0], d[1], d[2]).unwrap();
                    if self.out[first] == adj {
                        self.out.remove(first);
                    }
                }
            }
        }
        let o = from.v();
        for (s, r) in [(0usize, 1usize), (0, 2), (1, 2)] {
            for ss in [-1, 1] {
                for sr in [-1, 1] {
                    let umax = room(o[s], ss) as usize;
                    let vmax = room(o[r], sr) as usize;
                    if umax == 0 || vmax == 0 {
                        continue;
                    }
                    let point = |u: usize, v: usize| {
                        let mut p = o;
                        p[s] += ss * u as i32;
                        p[r] += sr * v as i32;
                        p
                    };
                    // full[u][v]: every cell of [0..=u]x[0..=v] except the origin is empty.
                    let mut full = [[false; SIZE]; SIZE];
                    full[0][0] = true;
                    for u in 1..=umax {
                        full[u][0] = full[u - 1][0] && self.empty(point(u, 0));
                    }
                    for v in 1..=vmax {
                        full[0][v] = full[0][v - 1] && self.empty(point(0, v));
                    }
                    for u in 1..=umax {
                        for v in 1..=vmax {
                            let clear = full[u - 1][v] && full[u][v - 1];
                            let p = point(u, v);
                            full[u][v] = clear && self.empty(p);
                            if clear && !(skip_adjacent && u == 1 && v == 1) {
                                self.push_if_landable(at(p));
                            }
                        }
                    }
                }
            }
        }
    }

    /// Bishop targets. With `skip_adjacent`, distance-1 targets are omitted (see `rook`).
    fn bishop(&mut self, from: Square, skip_adjacent: bool) {
        let o = from.v();
        // votes[dir][m]: how many of the three trapezoids towards a space-diagonal
        // target are clear. dir encodes the sign of each axis as bits.
        let mut votes = [[0u8; SIZE]; 8];
        for (s, r, c) in [(0usize, 1usize, 2usize), (0, 2, 1), (1, 2, 0)] {
            for ss in [-1, 1] {
                for sr in [-1, 1] {
                    let amax = room(o[s], ss).min(room(o[r], sr)) as usize;
                    for sc in [-1, 1] {
                        let bmax = room(o[c], sc) as usize;
                        let point = |m: usize, k: usize| {
                            let mut p = o;
                            p[s] += ss * m as i32;
                            p[r] += sr * m as i32;
                            p[c] += sc * k as i32;
                            p
                        };
                        let mut dir = 0;
                        for (axis, sign) in [(s, ss), (r, sr), (c, sc)] {
                            if sign > 0 {
                                dir |= 1 << axis;
                            }
                        }
                        // g[b]: all cells {(m', k) : m' < m, k <= min(m', b)} are empty.
                        let mut g = [true; SIZE];
                        for m in 1..=amax {
                            let kmax = m.min(bmax);
                            // pe[k]: cells (m, 0..=k) are all empty
                            let mut pe = [false; SIZE];
                            let mut run = true;
                            for (k, slot) in pe.iter_mut().enumerate().take(kmax + 1) {
                                run = run && self.empty(point(m, k));
                                *slot = run;
                            }
                            for b in 0..=kmax {
                                let clear = g[b] && (b == 0 || pe[b - 1]);
                                if b == m {
                                    if clear {
                                        votes[dir][m] += 1;
                                    }
                                } else if (b > 0 || sc > 0) && clear && !(skip_adjacent && m == 1) {
                                    self.push_if_landable(at(point(m, b)));
                                }
                            }
                            for (b, gb) in g.iter_mut().enumerate().take(bmax + 1) {
                                *gb = *gb && pe[m.min(b)];
                            }
                        }
                    }
                }
            }
        }
        for (dir, row) in votes.iter().enumerate() {
            for (m, &v) in row.iter().enumerate() {
                if v == 3 && !(skip_adjacent && m == 1) {
                    let sign = |axis: usize| if dir & (1 << axis) != 0 { 1 } else { -1 };
                    let t = [o[0] + sign(0) * m as i32, o[1] + sign(1) * m as i32, o[2] + sign(2) * m as i32];
                    self.push_if_landable(at(t));
                }
            }
        }
    }
}

/// Appends the pseudo-legal destination squares of `piece` standing on `from`.
pub(crate) fn push_targets(board: &Board, from: Square, piece: Piece, out: &mut Vec<Square>) {
    let mut g = Gen { board, color: piece.color, out };
    match piece.kind {
        PieceKind::Lance => g.slide(from, [0, piece.color.forward(), 0]),
        PieceKind::Rook => g.rook(from, false),
        PieceKind::Bishop => g.bishop(from, false),
        PieceKind::Dragon => {
            g.rook(from, true);
            g.steps(from, &KING);
        }
        PieceKind::Horse => {
            g.bishop(from, true);
            g.steps(from, &KING);
        }
        k => g.steps(from, step_offsets(k)),
    }
}

/// Pseudo-legal destination squares of the piece on `from` (own pieces excluded,
/// captures included). Returns an empty vector for an empty square.
pub fn targets(board: &Board, from: Square) -> Vec<Square> {
    let mut v = Vec::new();
    if let Some(p) = board.get(from) {
        push_targets(board, from, p, &mut v);
    }
    v
}

/// Whether the rectangle/box spanned by `a` and `b` holds no piece except the endpoints.
fn box_clear(board: &Board, a: Offset, b: Offset) -> bool {
    for x in a[0].min(b[0])..=a[0].max(b[0]) {
        for y in a[1].min(b[1])..=a[1].max(b[1]) {
            for z in a[2].min(b[2])..=a[2].max(b[2]) {
                let p = [x, y, z];
                if p != a && p != b && !board.is_empty(at(p)) {
                    return false;
                }
            }
        }
    }
    true
}

/// Whether every bishop trapezoid from `o` to `t` is clear. Assumes bishop geometry.
fn trapezoids_clear(board: &Board, o: Offset, t: Offset) -> bool {
    let d = [t[0] - o[0], t[1] - o[1], t[2] - o[2]];
    let a = d.iter().map(|v| v.abs()).max().unwrap_or(0);
    for (s, r, c) in [(0usize, 1usize, 2usize), (0, 2, 1), (1, 2, 0)] {
        if d[s].abs() != a || d[r].abs() != a {
            continue;
        }
        let b = d[c].abs();
        for m in 1..=a {
            for k in 0..=m.min(b) {
                let mut p = o;
                p[s] += d[s].signum() * m;
                p[r] += d[r].signum() * m;
                p[c] += d[c].signum() * k;
                if p != t && !board.is_empty(at(p)) {
                    return false;
                }
            }
        }
    }
    true
}

/// Whether the piece on `from` attacks `to`, i.e. could capture an enemy piece
/// standing there. Ignores what actually occupies `to`.
pub fn attacks(board: &Board, from: Square, to: Square) -> bool {
    let Some(piece) = board.get(from) else { return false };
    if from == to {
        return false;
    }
    let (o, t) = (from.v(), to.v());
    let d = [t[0] - o[0], t[1] - o[1], t[2] - o[2]];
    let black_d = oriented(d, piece.color);
    if step_offsets(piece.kind).contains(&black_d) {
        return true;
    }
    match piece.kind {
        PieceKind::Lance => d[0] == 0 && d[2] == 0 && black_d[1] < 0 && box_clear(board, o, t),
        PieceKind::Rook | PieceKind::Dragon => d.contains(&0) && box_clear(board, o, t),
        PieceKind::Bishop | PieceKind::Horse => {
            let a = d.iter().map(|v| v.abs()).max().unwrap();
            d.iter().filter(|v| v.abs() == a).count() >= 2 && trapezoids_clear(board, o, t)
        }
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn offset_tables_have_expected_sizes() {
        assert_eq!(KING.len(), 26);
        assert_eq!(GOLD.len(), 18);
        assert_eq!(SILVER.len(), 13);
        // tables contain no duplicates
        for table in [&KING[..], &GOLD[..], &SILVER[..], &KNIGHT[..]] {
            let mut v = table.to_vec();
            v.sort();
            v.dedup();
            assert_eq!(v.len(), table.len());
        }
    }
}
