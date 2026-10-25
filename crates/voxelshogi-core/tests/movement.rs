//! Piece movement (pseudo-legal destination squares) tests.
//!
//! Expected values come from (a) hand calculation from the rule text and
//! (b) the independent brute-force reference in `common`.

mod common;

use common::*;
use voxelshogi_core::movegen::{attacks, targets};
use voxelshogi_core::{Board, Color, PieceKind, Square};

const C: (i32, i32, i32) = (4, 4, 4);

fn center() -> Square {
    sq(C.0, C.1, C.2)
}

fn lone(kind: PieceKind, color: Color, at: Square) -> Board {
    board_with(&[(at, color, kind)])
}

fn offs(kind: PieceKind, color: Color) -> std::collections::BTreeSet<(i32, i32, i32)> {
    let b = lone(kind, color, center());
    offsets_from(center(), targets(&b, center()))
}

// ---------------------------------------------------------------- step pieces

#[test]
fn pawn_moves_one_forward_in_same_layer() {
    assert_eq!(offs(PieceKind::Pawn, Color::Black), [(0, -1, 0)].into());
    assert_eq!(offs(PieceKind::Pawn, Color::White), [(0, 1, 0)].into());
}

#[test]
fn knight_jumps_two_forward_with_x_and_z_both_shifted() {
    let expected = [(-1, -2, -1), (-1, -2, 1), (1, -2, -1), (1, -2, 1)].into();
    assert_eq!(offs(PieceKind::Knight, Color::Black), expected);
    let white = [(-1, 2, -1), (-1, 2, 1), (1, 2, -1), (1, 2, 1)].into();
    assert_eq!(offs(PieceKind::Knight, Color::White), white);
}

#[test]
fn silver_has_nine_forward_and_four_diagonal_back_in_other_layers() {
    let mut expected = std::collections::BTreeSet::new();
    for dx in -1..=1 {
        for dz in -1..=1 {
            expected.insert((dx, -1, dz));
        }
    }
    for (dx, dz) in [(-1, -1), (-1, 1), (1, -1), (1, 1)] {
        expected.insert((dx, 1, dz));
    }
    let got = offs(PieceKind::Silver, Color::Black);
    assert_eq!(got.len(), 13);
    assert_eq!(got, expected);
    // Explicitly: the ordinary same-layer diagonal back squares are NOT silver moves.
    assert!(!got.contains(&(1, 1, 0)) && !got.contains(&(-1, 1, 0)));
}

#[test]
fn gold_and_gold_like_pieces_have_eighteen_moves() {
    for kind in [
        PieceKind::Gold,
        PieceKind::Tokin,
        PieceKind::PromotedLance,
        PieceKind::PromotedKnight,
        PieceKind::PromotedSilver,
    ] {
        let got = offs(kind, Color::Black);
        assert_eq!(got.len(), 18, "{kind:?}");
        // excluded: same-layer diagonal back
        assert!(
            !got.contains(&(1, 1, 0)) && !got.contains(&(-1, 1, 0)),
            "{kind:?}"
        );
        // excluded: whole back row of the upper and lower layer
        for dx in -1..=1 {
            assert!(
                !got.contains(&(dx, 1, 1)) && !got.contains(&(dx, 1, -1)),
                "{kind:?}"
            );
        }
        // included: straight back, sideways, straight up/down, diagonal forward in other layers
        for o in [
            (0, 1, 0),
            (1, 0, 0),
            (0, 0, 1),
            (0, 0, -1),
            (1, 0, 1),
            (-1, -1, -1),
            (0, -1, 1),
        ] {
            assert!(got.contains(&o), "{kind:?} missing {o:?}");
        }
    }
    let white = offs(PieceKind::Gold, Color::White);
    assert!(
        white.contains(&(0, 1, 0)) && !white.contains(&(1, -1, 0)) && !white.contains(&(0, -1, 1))
    );
}

#[test]
fn king_moves_to_all_26_neighbours() {
    assert_eq!(offs(PieceKind::King, Color::Black).len(), 26);
    assert_eq!(offs(PieceKind::King, Color::White).len(), 26);
}

#[test]
fn step_pieces_are_clipped_at_board_edges() {
    let corner = sq(0, 0, 0);
    assert_eq!(
        targets(&lone(PieceKind::King, Color::Black, corner), corner).len(),
        7
    );
    assert!(targets(&lone(PieceKind::Pawn, Color::Black, corner), corner).is_empty());
    assert!(
        targets(
            &lone(PieceKind::Knight, Color::Black, sq(4, 1, 4)),
            sq(4, 1, 4)
        )
        .is_empty()
    );
    let k = sq(0, 8, 0);
    assert_eq!(
        offsets_from(k, targets(&lone(PieceKind::Knight, Color::Black, k), k)),
        [(1, -2, 1)].into()
    );
}

#[test]
fn knight_jumps_over_pieces() {
    let o = center();
    let mut pieces = vec![(o, Color::Black, PieceKind::Knight)];
    for dx in -1..=1 {
        for dy in -1..=0 {
            for dz in -1..=1 {
                if (dx, dy, dz) != (0, 0, 0) {
                    pieces.push((sq(4 + dx, 4 + dy, 4 + dz), Color::Black, PieceKind::Pawn));
                }
            }
        }
    }
    let b = board_with(&pieces);
    assert_eq!(targets(&b, o).len(), 4);
}

#[test]
fn cannot_move_onto_own_piece_but_can_capture() {
    let o = center();
    let b = board_with(&[
        (o, Color::Black, PieceKind::King),
        (sq(4, 3, 4), Color::Black, PieceKind::Pawn),
        (sq(5, 3, 4), Color::White, PieceKind::Pawn),
    ]);
    let t = set_of(targets(&b, o));
    assert_eq!(t.len(), 25);
    assert!(!t.contains(&sq(4, 3, 4)));
    assert!(t.contains(&sq(5, 3, 4)));
}

// ---------------------------------------------------------------- lance

#[test]
fn lance_slides_forward_until_blocked() {
    assert_eq!(
        offs(PieceKind::Lance, Color::Black),
        [(0, -1, 0), (0, -2, 0), (0, -3, 0), (0, -4, 0)].into()
    );
    let o = center();
    let b = board_with(&[
        (o, Color::Black, PieceKind::Lance),
        (sq(4, 2, 4), Color::White, PieceKind::Pawn),
    ]);
    assert_eq!(
        offsets_from(o, targets(&b, o)),
        [(0, -1, 0), (0, -2, 0)].into()
    );
    let b = board_with(&[
        (o, Color::Black, PieceKind::Lance),
        (sq(4, 2, 4), Color::Black, PieceKind::Pawn),
    ]);
    assert_eq!(offsets_from(o, targets(&b, o)), [(0, -1, 0)].into());
    // pieces in other layers / files do not block
    let b = board_with(&[
        (o, Color::Black, PieceKind::Lance),
        (sq(4, 2, 5), Color::White, PieceKind::Pawn),
    ]);
    assert_eq!(targets(&b, o).len(), 4);
}

// ---------------------------------------------------------------- rook

#[test]
fn rook_on_empty_board_reaches_every_square_sharing_a_coordinate() {
    // three 9x9 planes through the centre: 3*81 - 3*9 + 1 = 217 squares, minus the origin
    assert_eq!(offs(PieceKind::Rook, Color::Black).len(), 216);
    // from a corner: all squares with some coordinate 0 → 729 - 8^3 - 1
    let c = sq(0, 0, 0);
    assert_eq!(
        targets(&lone(PieceKind::Rook, Color::Black, c), c).len(),
        216
    );
}

#[test]
fn rook_two_axis_move_is_blocked_by_any_piece_in_the_rectangle() {
    let o = center();
    // blocker at (+1, 0, 0) blocks every target with dx >= 1 (the rectangle always contains it)
    let b = board_with(&[
        (o, Color::Black, PieceKind::Rook),
        (sq(5, 4, 4), Color::Black, PieceKind::Pawn),
    ]);
    let t = targets(&b, o);
    assert_eq!(t.len(), 216 - 68);
    assert!(t.iter().all(|s| s.x() <= 4));
    let b = board_with(&[
        (o, Color::Black, PieceKind::Rook),
        (sq(5, 4, 4), Color::White, PieceKind::Pawn),
    ]);
    let t = set_of(targets(&b, o));
    assert_eq!(t.len(), 216 - 67);
    assert!(t.contains(&sq(5, 4, 4)));
    // blocker inside the rectangle but not on any axis: (+2, -2, 0)
    let b = board_with(&[
        (o, Color::Black, PieceKind::Rook),
        (sq(6, 2, 4), Color::Black, PieceKind::Pawn),
    ]);
    let t = set_of(targets(&b, o));
    assert!(!t.contains(&sq(7, 1, 4)) && !t.contains(&sq(6, 1, 4)) && !t.contains(&sq(7, 2, 4)));
    assert!(t.contains(&sq(5, 3, 4)) && t.contains(&sq(6, 3, 4)) && t.contains(&sq(5, 2, 4)));
    // ...and rectangles that do not contain it are unaffected
    assert!(t.contains(&sq(8, 3, 4)) && t.contains(&sq(5, 0, 4)));
    // blocked: dx in 2..=4 and dy in -4..=-2 within layer z=4 (3x3 = 9, incl. the own blocker)
    assert_eq!(t.len(), 216 - 9);
}

#[test]
fn plain_rook_diagonal_step_is_blocked_but_dragon_king_step_is_not() {
    let o = center();
    let blockers = [
        (sq(5, 4, 4), Color::Black, PieceKind::Pawn),
        (sq(4, 3, 4), Color::Black, PieceKind::Pawn),
    ];
    let mut pieces = vec![(o, Color::Black, PieceKind::Rook)];
    pieces.extend_from_slice(&blockers);
    let rook = set_of(targets(&board_with(&pieces), o));
    assert!(!rook.contains(&sq(5, 3, 4)));
    pieces[0].2 = PieceKind::Dragon;
    let dragon = set_of(targets(&board_with(&pieces), o));
    assert!(dragon.contains(&sq(5, 3, 4)));
    // the dragon's extra moves are the 8 space-diagonal neighbours
    assert_eq!(offs(PieceKind::Dragon, Color::Black).len(), 224);
}

// ---------------------------------------------------------------- bishop

#[test]
fn bishop_on_empty_board_from_centre_and_corner() {
    // per distance a: 12*(2a-1) squares with exactly two |d|=a plus 8 space diagonals
    assert_eq!(
        offs(PieceKind::Bishop, Color::Black).len(),
        20 + 44 + 68 + 92
    );
    let c = sq(0, 0, 0);
    // corner: per a, 3 pairs * a values of the third axis + 1 → sum(3a+1, a=1..8) = 116
    assert_eq!(
        targets(&lone(PieceKind::Bishop, Color::Black, c), c).len(),
        116
    );
}

#[test]
fn bishop_geometry_two_axes_equal_third_not_larger() {
    let got = offs(PieceKind::Bishop, Color::Black);
    for o in [
        (1, 1, 0),
        (2, -2, 1),
        (3, 1, -3),
        (-4, -4, -4),
        (2, 2, 2),
        (0, 4, -4),
    ] {
        assert!(got.contains(&o), "{o:?}");
    }
    for o in [(1, 0, 0), (2, 1, 0), (3, 2, 1), (1, 2, 2 + 1), (0, 0, 1)] {
        assert!(!got.contains(&o), "{o:?}");
    }
}

#[test]
fn bishop_planar_diagonal_blocker_blocks_the_whole_wedge() {
    let o = center();
    // blocker at (+1,-1,0) blocks every target (a,-a,k) with |k| <= a: sum(2a+1, a=1..4) = 24
    let b = board_with(&[
        (o, Color::Black, PieceKind::Bishop),
        (sq(5, 3, 4), Color::Black, PieceKind::Pawn),
    ]);
    let t = targets(&b, o);
    assert_eq!(t.len(), 224 - 24);
    let b = board_with(&[
        (o, Color::Black, PieceKind::Bishop),
        (sq(5, 3, 4), Color::White, PieceKind::Pawn),
    ]);
    assert_eq!(targets(&b, o).len(), 224 - 23);
}

#[test]
fn bishop_trapezoid_is_asymmetric() {
    // (0,0,0) -> (2,2,1): blocked by (1,1,0), (1,1,1), (2,2,0); not by (0,0,1).
    let from = sq(0, 0, 0);
    let to = sq(2, 2, 1);
    for blocker in [sq(1, 1, 0), sq(1, 1, 1), sq(2, 2, 0)] {
        let b = board_with(&[
            (from, Color::Black, PieceKind::Bishop),
            (blocker, Color::Black, PieceKind::Gold),
        ]);
        assert!(
            !set_of(targets(&b, from)).contains(&to),
            "should be blocked by {blocker:?}"
        );
    }
    for free in [sq(0, 0, 1), sq(1, 0, 0), sq(2, 1, 1), sq(1, 2, 1)] {
        let b = board_with(&[
            (from, Color::Black, PieceKind::Bishop),
            (free, Color::Black, PieceKind::Gold),
        ]);
        assert!(
            set_of(targets(&b, from)).contains(&to),
            "should not be blocked by {free:?}"
        );
    }
    // the reverse move (2,2,1) -> (0,0,0) is blocked by (0,0,1) but not by (2,2,0).
    let b = board_with(&[
        (to, Color::Black, PieceKind::Bishop),
        (sq(0, 0, 1), Color::Black, PieceKind::Gold),
    ]);
    assert!(!set_of(targets(&b, to)).contains(&from));
    let b = board_with(&[
        (to, Color::Black, PieceKind::Bishop),
        (sq(2, 2, 0), Color::Black, PieceKind::Gold),
    ]);
    assert!(set_of(targets(&b, to)).contains(&from));
}

#[test]
fn bishop_space_diagonal_needs_all_three_trapezoids_clear() {
    let from = sq(0, 0, 0);
    let to = sq(1, 1, 1);
    for blocker in [sq(1, 1, 0), sq(1, 0, 1), sq(0, 1, 1)] {
        let b = board_with(&[
            (from, Color::Black, PieceKind::Bishop),
            (blocker, Color::White, PieceKind::Gold),
        ]);
        assert!(!set_of(targets(&b, from)).contains(&to), "{blocker:?}");
    }
    for free in [sq(1, 0, 0), sq(0, 1, 0), sq(0, 0, 1)] {
        let b = board_with(&[
            (from, Color::Black, PieceKind::Bishop),
            (free, Color::White, PieceKind::Gold),
        ]);
        assert!(set_of(targets(&b, from)).contains(&to), "{free:?}");
    }
    // (0,0,0) -> (2,2,2): exactly these 10 squares block.
    let to = sq(2, 2, 2);
    let blocking: Vec<Square> = [
        (1, 1, 0),
        (1, 0, 1),
        (0, 1, 1),
        (1, 1, 1),
        (2, 2, 0),
        (2, 2, 1),
        (2, 0, 2),
        (2, 1, 2),
        (0, 2, 2),
        (1, 2, 2),
    ]
    .iter()
    .map(|&(x, y, z)| sq(x, y, z))
    .collect();
    for s in Square::all() {
        if s == from || s == to || s.x() > 2 || s.y() > 2 || s.z() > 2 {
            continue;
        }
        let b = board_with(&[
            (from, Color::Black, PieceKind::Bishop),
            (s, Color::White, PieceKind::Gold),
        ]);
        let reaches = set_of(targets(&b, from)).contains(&to);
        assert_eq!(reaches, !blocking.contains(&s), "blocker {s:?}");
    }
}

#[test]
fn horse_has_unblockable_king_steps() {
    assert_eq!(offs(PieceKind::Horse, Color::Black).len(), 230);
    let o = sq(0, 0, 0);
    let b = board_with(&[
        (o, Color::Black, PieceKind::Horse),
        (sq(1, 1, 0), Color::Black, PieceKind::Pawn),
        (sq(1, 0, 1), Color::Black, PieceKind::Pawn),
    ]);
    // (1,1,1) is a king step for the horse: reachable even though bishop trapezoids are occupied
    assert!(set_of(targets(&b, o)).contains(&sq(1, 1, 1)));
    let b = board_with(&[
        (o, Color::Black, PieceKind::Bishop),
        (sq(1, 1, 0), Color::Black, PieceKind::Pawn),
    ]);
    assert!(!set_of(targets(&b, o)).contains(&sq(1, 1, 1)));
}

// ---------------------------------------------------------------- shogitter's own examples

/// The blocking diagrams on shogitter's 駒の動き page: a Black piece at (5,5,5) on 9×9×9
/// with White pawns as blockers. We check against the reference implementation.
#[test]
fn shogitter_blocking_diagrams_match_reference() {
    let origin = Square::from_display(5, 5, 5).unwrap();
    type Case<'a> = (PieceKind, &'a [(u8, u8, u8)]);
    let cases: [Case; 2] = [
        (PieceKind::Rook, &[(7, 7, 5), (3, 5, 5)]),
        (PieceKind::Bishop, &[(7, 4, 3), (3, 5, 3), (7, 7, 7)]),
    ];
    for (kind, blockers) in cases {
        let mut pieces = vec![(origin, Color::Black, kind)];
        for &(f, r, l) in blockers {
            pieces.push((
                Square::from_display(f, r, l).unwrap(),
                Color::White,
                PieceKind::Pawn,
            ));
        }
        let b = board_with(&pieces);
        assert_eq!(
            set_of(targets(&b, origin)),
            reference_targets(&b, origin),
            "{kind:?}"
        );
    }
}

// ---------------------------------------------------------------- property tests vs reference

#[test]
fn every_piece_kind_matches_reference_on_random_boards() {
    let mut rng = Rng(0x5EED_0001);
    let mut checked = 0;
    for round in 0..300 {
        let density = [3, 10, 25, 50][round % 4];
        let mut b = random_board(&mut rng, density);
        for _ in 0..6 {
            let from = Square::from_index(rng.below(729) as usize).unwrap();
            let color = if rng.below(2) == 0 {
                Color::Black
            } else {
                Color::White
            };
            let kind = PieceKind::ALL[rng.below(14) as usize];
            b.set(from, Some(voxelshogi_core::Piece::new(color, kind)));
            let got = set_of(targets(&b, from));
            let want = reference_targets(&b, from);
            assert_eq!(got, want, "round {round} {color:?} {kind:?} at {from:?}");
            checked += 1;
        }
    }
    assert_eq!(checked, 1800);
}

#[test]
fn attacks_agrees_with_targets_including_own_occupied_squares() {
    // attacks(from, to) is true iff a piece at `from` could capture an enemy on `to`.
    let mut rng = Rng(0x5EED_0002);
    for _ in 0..60 {
        let mut b = random_board(&mut rng, 15);
        let from = Square::from_index(rng.below(729) as usize).unwrap();
        let color = if rng.below(2) == 0 {
            Color::Black
        } else {
            Color::White
        };
        let kind = PieceKind::ALL[rng.below(14) as usize];
        b.set(from, Some(voxelshogi_core::Piece::new(color, kind)));
        for to in Square::all() {
            if to == from {
                continue;
            }
            // Replace the target with an enemy piece and compare with the reference.
            let mut b2 = b.clone();
            b2.set(
                to,
                Some(voxelshogi_core::Piece::new(
                    color.opponent(),
                    PieceKind::Gold,
                )),
            );
            let want = reference_targets(&b2, from).contains(&to);
            assert_eq!(
                attacks(&b, from, to),
                want,
                "{color:?} {kind:?} {from:?} -> {to:?}"
            );
        }
    }
}
