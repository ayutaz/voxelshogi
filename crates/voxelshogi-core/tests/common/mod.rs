//! Shared test utilities: a deterministic RNG, board builders and an
//! independent *reference* implementation of piece movement written directly
//! from the textual rule definition (docs/RULESET.md). The reference is
//! deliberately naive (brute force over all squares and all blockers) so that
//! it shares no algorithm with the optimized engine.

#![allow(dead_code)]

use std::collections::BTreeSet;
use voxelshogi_core::{Board, Color, Piece, PieceKind, Square};

/// SplitMix64 — tiny deterministic RNG for property tests.
pub struct Rng(pub u64);

impl Rng {
    pub fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
    pub fn below(&mut self, n: u64) -> u64 {
        self.next_u64() % n
    }
    pub fn chance(&mut self, p_percent: u64) -> bool {
        self.below(100) < p_percent
    }
}

pub fn sq(x: i32, y: i32, z: i32) -> Square {
    Square::from_i32(x, y, z).expect("square on board")
}

pub fn board_with(pieces: &[(Square, Color, PieceKind)]) -> Board {
    let mut b = Board::empty();
    for &(s, c, k) in pieces {
        b.set(s, Some(Piece::new(c, k)));
    }
    b
}

pub fn set_of(v: impl IntoIterator<Item = Square>) -> BTreeSet<Square> {
    v.into_iter().collect()
}

pub fn offsets_from(origin: Square, v: impl IntoIterator<Item = Square>) -> BTreeSet<(i32, i32, i32)> {
    let o = origin.v();
    v.into_iter()
        .map(|s| {
            let t = s.v();
            (t[0] - o[0], t[1] - o[1], t[2] - o[2])
        })
        .collect()
}

/// A random board: each square occupied with probability `density`% by a random piece.
pub fn random_board(rng: &mut Rng, density: u64) -> Board {
    let mut b = Board::empty();
    for s in Square::all() {
        if rng.chance(density) {
            let color = if rng.below(2) == 0 { Color::Black } else { Color::White };
            let kind = PieceKind::ALL[rng.below(14) as usize];
            b.set(s, Some(Piece::new(color, kind)));
        }
    }
    b
}

// ---------------------------------------------------------------------------
// Reference movement rules (transcribed from the rule text, not optimized).
// ---------------------------------------------------------------------------

/// Step offsets for Black; White mirrors `dy`.
fn reference_step_offsets(kind: PieceKind) -> Vec<(i32, i32, i32)> {
    let f = -1; // Black forward
    let mut v = Vec::new();
    let neighbours = || {
        let mut n = Vec::new();
        for dx in -1..=1 {
            for dy in -1..=1 {
                for dz in -1..=1 {
                    if (dx, dy, dz) != (0, 0, 0) {
                        n.push((dx, dy, dz));
                    }
                }
            }
        }
        n
    };
    match kind {
        // 同じz層で前方へ1マス
        PieceKind::Pawn => v.push((0, f, 0)),
        // 前方2マスに加え、xとzをそれぞれ±1した4マス
        PieceKind::Knight => {
            for dx in [-1, 1] {
                for dz in [-1, 1] {
                    v.push((dx, 2 * f, dz));
                }
            }
        }
        // 前方にあるx方向3×z方向3の9マスと、上下z層の斜め後方4マス
        PieceKind::Silver => {
            for dx in -1..=1 {
                for dz in -1..=1 {
                    v.push((dx, f, dz));
                }
            }
            for dx in [-1, 1] {
                for dz in [-1, 1] {
                    v.push((dx, -f, dz));
                }
            }
        }
        // 周囲26マスから、同じz層の斜め後方2マスと、上下z層の後方各3マスを除いた18マス
        k if k.is_gold_like() => {
            for (dx, dy, dz) in neighbours() {
                let same_layer_diag_back = dy == -f && dz == 0 && dx != 0;
                let other_layer_back = dy == -f && dz != 0;
                if !same_layer_diag_back && !other_layer_back {
                    v.push((dx, dy, dz));
                }
            }
        }
        // 周囲1マスの全26マス (also the extra king-moves of 竜王/竜馬)
        PieceKind::King | PieceKind::Horse | PieceKind::Dragon => v = neighbours(),
        _ => {}
    }
    v
}

fn in_box(h: [i32; 3], a: [i32; 3], b: [i32; 3]) -> bool {
    (0..3).all(|i| a[i].min(b[i]) <= h[i] && h[i] <= a[i].max(b[i]))
}

/// Squares that block a 3D bishop moving from `o` to `t` (trapezoid rule, 10/17 revision).
/// Assumes the geometry is a valid bishop move.
fn reference_bishop_block_region(o: [i32; 3], t: [i32; 3]) -> BTreeSet<[i32; 3]> {
    let d = [t[0] - o[0], t[1] - o[1], t[2] - o[2]];
    let a = d.iter().map(|v| v.abs()).max().unwrap();
    let mut region = BTreeSet::new();
    for (s, r, c) in [(0, 1, 2), (0, 2, 1), (1, 2, 0)] {
        if d[s].abs() != a || d[r].abs() != a {
            continue;
        }
        // Rectangle spanned by the diagonal edge (a steps in plane s-r) and the
        // perpendicular edge up to the target, intersected with the region the
        // move sweeps (|c offset| <= diagonal distance): a trapezoid.
        for m in 1..=a {
            for j in 0..=d[c].abs() {
                if j > m {
                    continue;
                }
                let mut p = o;
                p[s] += d[s].signum() * m;
                p[r] += d[r].signum() * m;
                p[c] += d[c].signum() * j;
                if p != t {
                    region.insert(p);
                }
            }
        }
    }
    region
}

fn is_bishop_geometry(d: [i32; 3]) -> bool {
    let a: Vec<i32> = d.iter().map(|v| v.abs()).collect();
    let m = *a.iter().max().unwrap();
    m > 0 && a.iter().filter(|v| **v == m).count() >= 2
}

fn is_rook_geometry(d: [i32; 3]) -> bool {
    d != [0, 0, 0] && d.iter().any(|v| *v == 0)
}

/// Reference destination squares (pseudo-legal: own pieces excluded, captures included).
pub fn reference_targets(board: &Board, from: Square) -> BTreeSet<Square> {
    let Some(piece) = board.get(from) else { return BTreeSet::new() };
    let o = from.v();
    let ysign = if piece.color == Color::Black { 1 } else { -1 };
    let occupied: Vec<[i32; 3]> = board.pieces().map(|(s, _)| s.v()).collect();
    let mut out = BTreeSet::new();
    let own = |s: Square| board.get(s).is_some_and(|p| p.color == piece.color);

    for (dx, dy, dz) in reference_step_offsets(piece.kind) {
        if let Some(t) = from.offset(dx, dy * ysign, dz) {
            if !own(t) {
                out.insert(t);
            }
        }
    }
    let kind = piece.kind;
    for t in Square::all() {
        if t == from || own(t) || out.contains(&t) {
            continue;
        }
        let tv = t.v();
        let d = [tv[0] - o[0], tv[1] - o[1], tv[2] - o[2]];
        let ok = match kind {
            // 同じz層で、前方へ駒にぶつかるまで
            PieceKind::Lance => {
                d[0] == 0
                    && d[2] == 0
                    && d[1] * ysign < 0
                    && !occupied.iter().any(|h| h[0] == o[0] && h[2] == o[2] && (h[1] - o[1]) * d[1].signum() > 0 && (h[1] - o[1]).abs() < d[1].abs())
            }
            // 始点と終点を対角とする直方体内の駒は飛び越せない
            PieceKind::Rook | PieceKind::Dragon => {
                is_rook_geometry(d) && !occupied.iter().any(|h| *h != o && *h != tv && in_box(*h, o, tv))
            }
            PieceKind::Bishop | PieceKind::Horse => {
                is_bishop_geometry(d) && {
                    let region = reference_bishop_block_region(o, tv);
                    !occupied.iter().any(|h| region.contains(h))
                }
            }
            _ => false,
        };
        if ok {
            out.insert(t);
        }
    }
    out
}
