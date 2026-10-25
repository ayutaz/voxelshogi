//! Shared test utilities: a deterministic RNG, board builders and an
//! independent *reference* implementation of piece movement written directly
//! from the textual rule definition (docs/RULESET.md). The reference is
//! deliberately naive (brute force over all squares and all blockers) so that
//! it shares no algorithm with the optimized engine.

#![allow(dead_code)]

use std::collections::BTreeSet;
use voxelshogi_core::{Board, Color, Move, Piece, PieceKind, Square};

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

pub fn offsets_from(
    origin: Square,
    v: impl IntoIterator<Item = Square>,
) -> BTreeSet<(i32, i32, i32)> {
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
            let color = if rng.below(2) == 0 {
                Color::Black
            } else {
                Color::White
            };
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
    d != [0, 0, 0] && d.contains(&0)
}

/// Reference attack predicate: could the piece on `from` capture an enemy on `to`?
/// Checks only the single (from, to) pair, so it is cheap enough for full positions.
pub fn reference_attacks(board: &Board, from: Square, to: Square) -> bool {
    let Some(piece) = board.get(from) else {
        return false;
    };
    if from == to {
        return false;
    }
    let ysign = if piece.color == Color::Black { 1 } else { -1 };
    let o = from.v();
    let tv = to.v();
    let d = [tv[0] - o[0], tv[1] - o[1], tv[2] - o[2]];
    if reference_step_offsets(piece.kind).contains(&(d[0], d[1] * ysign, d[2])) {
        return true;
    }
    let occupied = |p: [i32; 3]| p != o && p != tv && !board.is_empty(sq(p[0], p[1], p[2]));
    match piece.kind {
        // 同じz層で、前方へ駒にぶつかるまで
        PieceKind::Lance => {
            d[0] == 0
                && d[2] == 0
                && d[1] * ysign < 0
                && (1..d[1].abs()).all(|i| !occupied([o[0], o[1] + d[1].signum() * i, o[2]]))
        }
        // 始点と終点を対角とする直方体内の駒は飛び越せない
        PieceKind::Rook | PieceKind::Dragon => {
            if !is_rook_geometry(d) {
                return false;
            }
            for x in o[0].min(tv[0])..=o[0].max(tv[0]) {
                for y in o[1].min(tv[1])..=o[1].max(tv[1]) {
                    for z in o[2].min(tv[2])..=o[2].max(tv[2]) {
                        if occupied([x, y, z]) {
                            return false;
                        }
                    }
                }
            }
            true
        }
        PieceKind::Bishop | PieceKind::Horse => {
            is_bishop_geometry(d)
                && reference_bishop_block_region(o, tv)
                    .into_iter()
                    .all(|p| !occupied(p))
        }
        _ => false,
    }
}

/// Reference destination squares (pseudo-legal: own pieces excluded, captures included).
pub fn reference_targets(board: &Board, from: Square) -> BTreeSet<Square> {
    let Some(piece) = board.get(from) else {
        return BTreeSet::new();
    };
    Square::all()
        .filter(|&t| {
            reference_attacks(board, from, t) && board.get(t).is_none_or(|q| q.color != piece.color)
        })
        .collect()
}

pub type Hands = [[u8; 7]; 2];

pub fn reference_in_check(board: &Board, color: Color) -> bool {
    let Some(king) = board.find_king(color) else {
        return false;
    };
    board
        .pieces()
        .any(|(s, p)| p.color != color && reference_attacks(board, s, king))
}

fn in_zone(color: Color, y: u8) -> bool {
    color.relative_rank(y) < 3
}

/// 行き所のない駒: the piece would have no move at all on an empty board from rank `y`.
fn dead_end(kind: PieceKind, color: Color, y: u8) -> bool {
    let rr = color.relative_rank(y);
    match kind {
        PieceKind::Pawn | PieceKind::Lance => rr == 0,
        PieceKind::Knight => rr <= 1,
        _ => false,
    }
}

/// Reference legal moves, written directly from docs/RULESET.md §3–§6.
pub fn reference_legal_moves(board: &Board, hands: &Hands, side: Color) -> Vec<Move> {
    let mut moves = Vec::new();
    let leaves_king_safe = |b: &Board| !reference_in_check(b, side);
    for (from, piece) in board.pieces().filter(|(_, p)| p.color == side) {
        for to in reference_targets(board, from) {
            let can_promote =
                piece.kind.can_promote() && (in_zone(side, from.y()) || in_zone(side, to.y()));
            let must_promote = dead_end(piece.kind, side, to.y());
            for promote in [false, true] {
                if (promote && !can_promote) || (!promote && must_promote) {
                    continue;
                }
                let mut b = board.clone();
                b.set(from, None);
                let kind = if promote {
                    piece.kind.promote().unwrap()
                } else {
                    piece.kind
                };
                b.set(to, Some(Piece::new(side, kind)));
                if leaves_king_safe(&b) {
                    moves.push(Move::Normal { from, to, promote });
                }
            }
        }
    }
    for (hi, kind) in PieceKind::HAND.into_iter().enumerate() {
        if hands[side.index()][hi] == 0 {
            continue;
        }
        for to in Square::all() {
            if !board.is_empty(to) || dead_end(kind, side, to.y()) {
                continue;
            }
            // 二歩: same layer and file = same (x, z) column
            if kind == PieceKind::Pawn
                && (0..9).any(|y| {
                    board.get(sq(to.x() as i32, y, to.z() as i32))
                        == Some(Piece::new(side, PieceKind::Pawn))
                })
            {
                continue;
            }
            let mut b = board.clone();
            b.set(to, Some(Piece::new(side, kind)));
            if !leaves_king_safe(&b) {
                continue;
            }
            // 打ち歩詰め
            if kind == PieceKind::Pawn && reference_in_check(&b, side.opponent()) {
                let mut h = *hands;
                h[side.index()][hi] -= 1;
                if reference_legal_moves(&b, &h, side.opponent()).is_empty() {
                    continue;
                }
            }
            moves.push(Move::Drop { kind, to });
        }
    }
    moves.sort();
    moves
}
