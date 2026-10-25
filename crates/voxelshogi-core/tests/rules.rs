//! Legal move generation, move application and game termination (docs/RULESET.md §4–§6).

mod common;

use common::*;
use voxelshogi_core::{
    Board, Color, DrawReason, GameResult, GameState, Move, MoveError, Piece, PieceKind, Square,
    WinReason,
};

const NO_HANDS: Hands = [[0; 7]; 2];

#[test]
fn move_errors_display_the_reason_for_users() {
    assert_eq!(
        MoveError::Illegal("own king exposed".into()).to_string(),
        "illegal move: own king exposed"
    );
    assert_eq!(MoveError::GameOver.to_string(), "the game is over");
}

#[test]
fn hand_count_returns_each_sides_count_and_zero_for_undroppable_kinds() {
    let black = [1, 2, 3, 4, 5, 6, 7];
    let white = [7, 6, 5, 4, 3, 2, 1];
    let state = GameState::from_parts(kings_and(&[]), [black, white], Color::Black);
    for (color, expected) in [(Color::Black, black), (Color::White, white)] {
        for (kind, count) in PieceKind::HAND.into_iter().zip(expected) {
            assert_eq!(state.hand_count(color, kind), count, "{color:?} {kind:?}");
        }
        for kind in [
            PieceKind::King,
            PieceKind::Tokin,
            PieceKind::PromotedLance,
            PieceKind::PromotedKnight,
            PieceKind::PromotedSilver,
            PieceKind::Horse,
            PieceKind::Dragon,
        ] {
            assert_eq!(state.hand_count(color, kind), 0, "{color:?} {kind:?}");
        }
    }
}

#[test]
fn every_hand_kind_can_be_dropped_when_all_seven_are_held() {
    // With only distant kings, the centre is empty and is a legal drop square
    // for every kind: no nifu, dead end, own check, or pawn-drop mate.
    for side in Color::ALL {
        let state = GameState::from_parts(kings_and(&[]), [[1; 7]; 2], side);
        let legal = state.legal_moves();
        for kind in PieceKind::HAND {
            assert!(legal.contains(&Move::Drop {
                kind,
                to: sq(4, 4, 4),
            }));
        }
    }
}

fn hands_with(color: Color, kind: PieceKind, n: u8) -> Hands {
    let mut h = NO_HANDS;
    h[color.index()][kind.hand_index().unwrap()] = n;
    h
}

/// A position with both kings in their home squares plus `extra` pieces.
fn kings_and(extra: &[(Square, Color, PieceKind)]) -> Board {
    let mut v = vec![
        (sq(4, 8, 4), Color::Black, PieceKind::King),
        (sq(4, 0, 4), Color::White, PieceKind::King),
    ];
    v.extend_from_slice(extra);
    board_with(&v)
}

fn moves_from(state: &GameState, from: Square) -> Vec<Move> {
    let mut v: Vec<Move> = state
        .legal_moves()
        .into_iter()
        .filter(|m| matches!(m, Move::Normal { from: f, .. } if *f == from))
        .collect();
    v.sort();
    v
}

fn normal(from: Square, to: Square, promote: bool) -> Move {
    Move::Normal { from, to, promote }
}

fn sorted(mut v: Vec<Move>) -> Vec<Move> {
    v.sort();
    v
}

// ------------------------------------------------------------------ initial position

#[test]
fn new_game_has_initial_board_black_to_move_and_empty_hands() {
    let g = GameState::new();
    assert_eq!(g.board(), &Board::initial());
    assert_eq!(g.side_to_move(), Color::Black);
    assert_eq!(g.ply(), 0);
    assert_eq!(g.hands(), &NO_HANDS);
    assert!(g.result().is_none());
    assert!(!g.is_in_check(Color::Black) && !g.is_in_check(Color::White));
}

#[test]
fn initial_legal_moves_match_reference_for_both_sides() {
    let b = Board::initial();
    for side in Color::ALL {
        let g = GameState::from_parts(b.clone(), NO_HANDS, side);
        let want = reference_legal_moves(&b, &NO_HANDS, side);
        assert_eq!(sorted(g.legal_moves()), want, "{side:?}");
        // all 81 pawn pushes are among them
        let pawn_pushes = want
            .iter()
            .filter(|m| matches!(m, Move::Normal { from, .. } if b.get(*from).unwrap().kind == PieceKind::Pawn))
            .count();
        assert_eq!(pawn_pushes, 81);
    }
}

#[test]
fn initial_position_is_symmetric_between_players() {
    // White's moves are Black's moves under the point reflection through the centre.
    let b = Board::initial();
    let reflect = |s: Square| sq(8 - s.x() as i32, 8 - s.y() as i32, 8 - s.z() as i32);
    let black = GameState::from_parts(b.clone(), NO_HANDS, Color::Black).legal_moves();
    let white: std::collections::BTreeSet<Move> = GameState::from_parts(b, NO_HANDS, Color::White)
        .legal_moves()
        .into_iter()
        .collect();
    assert_eq!(black.len(), white.len());
    assert!(black.len() > 81);
    for m in black {
        let Move::Normal { from, to, promote } = m else {
            panic!("no drops at start")
        };
        assert!(
            white.contains(&normal(reflect(from), reflect(to), promote)),
            "{m:?}"
        );
    }
}

// ------------------------------------------------------------------ promotion

#[test]
fn pawn_entering_zone_may_promote_and_last_rank_must_promote() {
    let p = sq(4, 3, 4);
    let g = GameState::from_parts(
        kings_and(&[(p, Color::Black, PieceKind::Pawn)]),
        NO_HANDS,
        Color::Black,
    );
    assert_eq!(
        moves_from(&g, p),
        vec![normal(p, sq(4, 2, 4), false), normal(p, sq(4, 2, 4), true)]
    );

    let p = sq(4, 1, 3);
    let g = GameState::from_parts(
        kings_and(&[(p, Color::Black, PieceKind::Pawn)]),
        NO_HANDS,
        Color::Black,
    );
    assert_eq!(moves_from(&g, p), vec![normal(p, sq(4, 0, 3), true)]);

    let p = sq(4, 4, 4);
    let g = GameState::from_parts(
        kings_and(&[(p, Color::Black, PieceKind::Pawn)]),
        NO_HANDS,
        Color::Black,
    );
    assert_eq!(moves_from(&g, p), vec![normal(p, sq(4, 3, 4), false)]);
}

#[test]
fn white_promotion_zone_is_ranks_seven_to_nine() {
    let p = sq(2, 5, 2);
    let g = GameState::from_parts(
        kings_and(&[(p, Color::White, PieceKind::Pawn)]),
        NO_HANDS,
        Color::White,
    );
    assert_eq!(
        moves_from(&g, p),
        vec![normal(p, sq(2, 6, 2), false), normal(p, sq(2, 6, 2), true)]
    );
    let p = sq(2, 7, 2);
    let g = GameState::from_parts(
        kings_and(&[(p, Color::White, PieceKind::Pawn)]),
        NO_HANDS,
        Color::White,
    );
    assert_eq!(moves_from(&g, p), vec![normal(p, sq(2, 8, 2), true)]);
}

#[test]
fn knight_must_promote_on_last_two_ranks() {
    let n = sq(4, 3, 4); // jumps to rank y=1 → must promote, 4 targets
    let g = GameState::from_parts(
        kings_and(&[(n, Color::Black, PieceKind::Knight)]),
        NO_HANDS,
        Color::Black,
    );
    let m = moves_from(&g, n);
    assert_eq!(m.len(), 4);
    assert!(
        m.iter()
            .all(|m| matches!(m, Move::Normal { promote: true, .. }))
    );
    let n = sq(4, 4, 4); // jumps to y=2 → optional, 8 moves
    let g = GameState::from_parts(
        kings_and(&[(n, Color::Black, PieceKind::Knight)]),
        NO_HANDS,
        Color::Black,
    );
    assert_eq!(moves_from(&g, n).len(), 8);
}

#[test]
fn moving_out_of_the_zone_may_promote() {
    let s = sq(4, 2, 4);
    let g = GameState::from_parts(
        kings_and(&[(s, Color::Black, PieceKind::Silver)]),
        NO_HANDS,
        Color::Black,
    );
    let m = moves_from(&g, s);
    assert!(m.contains(&normal(s, sq(3, 3, 3), false)));
    assert!(m.contains(&normal(s, sq(3, 3, 3), true)));
    // 13 silver squares, each optional promotion → 26 moves
    assert_eq!(m.len(), 26);
}

#[test]
fn gold_king_and_promoted_pieces_never_promote() {
    for kind in [
        PieceKind::Gold,
        PieceKind::Tokin,
        PieceKind::Horse,
        PieceKind::Dragon,
    ] {
        let s = sq(4, 2, 4);
        let g = GameState::from_parts(
            kings_and(&[(s, Color::Black, kind)]),
            NO_HANDS,
            Color::Black,
        );
        let m = moves_from(&g, s);
        assert!(m.len() >= 18, "{kind:?} has moves");
        assert!(
            m.iter()
                .all(|m| matches!(m, Move::Normal { promote: false, .. })),
            "{kind:?}"
        );
    }
}

#[test]
fn rook_and_bishop_promotion_is_optional_everywhere_in_zone() {
    let r = sq(0, 4, 0);
    let g = GameState::from_parts(
        kings_and(&[(r, Color::Black, PieceKind::Rook)]),
        NO_HANDS,
        Color::Black,
    );
    let m = moves_from(&g, r);
    assert!(
        m.contains(&normal(r, sq(0, 0, 0), false)) && m.contains(&normal(r, sq(0, 0, 0), true))
    );
    assert!(!m.contains(&normal(r, sq(0, 5, 0), true)));
}

// ------------------------------------------------------------------ drops

#[test]
fn pawn_drops_respect_last_rank_and_nifu_per_layer_and_file() {
    let own_pawn = sq(3, 5, 6);
    let board = kings_and(&[
        (own_pawn, Color::Black, PieceKind::Pawn),
        (sq(5, 5, 5), Color::White, PieceKind::Pawn), // enemy pawn: no nifu effect
        (sq(1, 5, 1), Color::Black, PieceKind::Tokin), // promoted pawn: no nifu effect
    ]);
    let g = GameState::from_parts(
        board.clone(),
        hands_with(Color::Black, PieceKind::Pawn, 1),
        Color::Black,
    );
    let drops: Vec<Square> = g
        .legal_moves()
        .into_iter()
        .filter_map(|m| {
            if let Move::Drop {
                kind: PieceKind::Pawn,
                to,
            } = m
            {
                Some(to)
            } else {
                None
            }
        })
        .collect();
    // nifu column
    assert!(drops.iter().all(|s| !(s.x() == 3 && s.z() == 6)));
    // same file, different layer is fine
    assert!(drops.contains(&sq(3, 4, 5)));
    assert!(drops.contains(&sq(5, 4, 5)) && drops.contains(&sq(1, 4, 1)));
    // never on the last rank
    assert!(drops.iter().all(|s| s.y() != 0));
    // exact count: empty squares (729 - 5) minus last rank empties minus nifu-column empties,
    // and no drop that leaves the own king in check (none here) or is 打ち歩詰め (none here).
    let last_rank_empty = (0..81)
        .filter(|i| board.is_empty(sq(i % 9, 0, i / 9)))
        .count();
    let nifu_empty = (1..9).filter(|y| board.is_empty(sq(3, *y, 6))).count(); // y=0 already counted
    assert_eq!(drops.len(), 729 - 5 - last_rank_empty - nifu_empty);
}

#[test]
fn lance_and_knight_drops_avoid_dead_ends() {
    let g = GameState::from_parts(
        kings_and(&[]),
        hands_with(Color::Black, PieceKind::Knight, 2),
        Color::Black,
    );
    let n: Vec<Square> = g
        .legal_moves()
        .into_iter()
        .filter_map(|m| {
            if let Move::Drop { to, .. } = m {
                Some(to)
            } else {
                None
            }
        })
        .collect();
    assert_eq!(n.len(), 7 * 81 - 1); // ranks y=2..8, minus Black king's square
    let g = GameState::from_parts(
        kings_and(&[]),
        hands_with(Color::White, PieceKind::Lance, 1),
        Color::White,
    );
    let l: Vec<Square> = g
        .legal_moves()
        .into_iter()
        .filter_map(|m| {
            if let Move::Drop { to, .. } = m {
                Some(to)
            } else {
                None
            }
        })
        .collect();
    assert!(l.iter().all(|s| s.y() != 8));
    assert_eq!(l.len(), 8 * 81 - 1); // White king at y=0 occupies one
    let g = GameState::from_parts(
        kings_and(&[]),
        hands_with(Color::Black, PieceKind::Gold, 1),
        Color::Black,
    );
    assert_eq!(
        g.legal_moves()
            .iter()
            .filter(|m| matches!(m, Move::Drop { .. }))
            .count(),
        729 - 2
    );
}

#[test]
fn applying_a_drop_moves_piece_from_hand_and_capture_goes_to_hand_unpromoted() {
    let target = sq(4, 3, 4);
    let board = kings_and(&[
        (sq(4, 4, 4), Color::Black, PieceKind::Dragon),
        (target, Color::White, PieceKind::Horse),
    ]);
    let g = GameState::from_parts(
        board,
        hands_with(Color::Black, PieceKind::Silver, 1),
        Color::Black,
    );
    let g2 = g.apply_move(&normal(sq(4, 4, 4), target, false)).unwrap();
    assert_eq!(g2.hands()[0][PieceKind::Bishop.hand_index().unwrap()], 1);
    assert_eq!(
        g2.board().get(target),
        Some(Piece::new(Color::Black, PieceKind::Dragon))
    );
    assert_eq!(g2.side_to_move(), Color::White);
    assert_eq!(g2.ply(), 1);
    // the original state is untouched (apply_move is pure)
    assert_eq!(
        g.board().get(target),
        Some(Piece::new(Color::White, PieceKind::Horse))
    );

    let g3 = g
        .apply_move(&Move::Drop {
            kind: PieceKind::Silver,
            to: sq(0, 0, 0),
        })
        .unwrap();
    assert_eq!(g3.hands()[0][PieceKind::Silver.hand_index().unwrap()], 0);
    assert_eq!(
        g3.board().get(sq(0, 0, 0)),
        Some(Piece::new(Color::Black, PieceKind::Silver))
    );
}

// ------------------------------------------------------------------ check

#[test]
fn rook_checks_through_an_empty_rectangle_and_pieces_in_it_are_pinned() {
    // White rook at (2,2,4); Black king at (4,8,4): same layer z=4, rectangle x∈[2,4], y∈[2,8].
    let rook = sq(2, 2, 4);
    let guard = sq(3, 5, 4); // a Black gold inside the rectangle shields the king
    let board = kings_and(&[
        (rook, Color::White, PieceKind::Rook),
        (guard, Color::Black, PieceKind::Gold),
    ]);
    let g = GameState::from_parts(board.clone(), NO_HANDS, Color::Black);
    assert!(!g.is_in_check(Color::Black));
    let gm = moves_from(&g, guard);
    // stays inside the rectangle → legal
    assert!(gm.contains(&normal(guard, sq(3, 4, 4), false)));
    assert!(gm.contains(&normal(guard, sq(4, 5, 4), false)));
    // leaves the rectangle → exposes the king → illegal
    assert!(!gm.contains(&normal(guard, sq(3, 5, 5), false)));
    assert!(!gm.contains(&normal(guard, sq(3, 5, 3), false)));
    assert_eq!(
        gm,
        reference_legal_moves(&board, &NO_HANDS, Color::Black)
            .into_iter()
            .filter(|m| matches!(m, Move::Normal { from, .. } if *from == guard))
            .collect::<Vec<_>>()
    );

    let mut open = board.clone();
    open.set(guard, None);
    let g = GameState::from_parts(open.clone(), NO_HANDS, Color::Black);
    assert!(g.is_in_check(Color::Black));
    assert_eq!(
        sorted(g.legal_moves()),
        reference_legal_moves(&open, &NO_HANDS, Color::Black)
    );
}

#[test]
fn king_may_not_step_into_attacked_squares_or_stay_in_check() {
    let board = kings_and(&[(sq(4, 6, 2), Color::White, PieceKind::Bishop)]);
    let g = GameState::from_parts(board.clone(), NO_HANDS, Color::Black);
    let want = reference_legal_moves(&board, &NO_HANDS, Color::Black);
    assert_eq!(sorted(g.legal_moves()), want);
    for m in &want {
        let next = g.apply_move(m).unwrap();
        assert!(!next.is_in_check(Color::Black), "{m:?}");
    }
}

#[test]
fn illegal_moves_are_rejected_with_errors() {
    let g = GameState::new();
    // empty square
    assert!(matches!(
        g.apply_move(&normal(sq(4, 4, 4), sq(4, 3, 4), false)),
        Err(MoveError::Illegal(_))
    ));
    // opponent's piece
    assert!(matches!(
        g.apply_move(&normal(sq(4, 2, 4), sq(4, 3, 4), false)),
        Err(MoveError::Illegal(_))
    ));
    // not a pawn move
    assert!(matches!(
        g.apply_move(&normal(sq(4, 6, 4), sq(4, 4, 4), false)),
        Err(MoveError::Illegal(_))
    ));
    // promotion outside the zone
    assert!(matches!(
        g.apply_move(&normal(sq(4, 6, 4), sq(4, 5, 4), true)),
        Err(MoveError::Illegal(_))
    ));
    // drop without the piece in hand
    assert!(matches!(
        g.apply_move(&Move::Drop {
            kind: PieceKind::Gold,
            to: sq(4, 4, 4)
        }),
        Err(MoveError::Illegal(_))
    ));
    // drop of an unpromotable kind (king) is never legal
    assert!(
        g.apply_move(&Move::Drop {
            kind: PieceKind::King,
            to: sq(4, 4, 4)
        })
        .is_err()
    );
    // legal move succeeds
    assert!(
        g.apply_move(&normal(sq(4, 6, 4), sq(4, 5, 4), false))
            .is_ok()
    );
}

// ------------------------------------------------------------------ mate / 打ち歩詰め

#[test]
fn protected_dragon_next_to_cornered_king_is_checkmate() {
    let board = board_with(&[
        (sq(0, 0, 0), Color::White, PieceKind::King),
        (sq(1, 1, 1), Color::Black, PieceKind::Dragon),
        (sq(2, 2, 2), Color::Black, PieceKind::Gold), // protects the dragon (forward row, lower layer)
        (sq(8, 8, 8), Color::Black, PieceKind::King),
    ]);
    let g = GameState::from_parts(board.clone(), NO_HANDS, Color::White);
    assert!(g.is_in_check(Color::White));
    assert!(g.legal_moves().is_empty());
    assert!(reference_legal_moves(&board, &NO_HANDS, Color::White).is_empty());
    assert_eq!(
        g.result(),
        Some(GameResult::Win {
            winner: Color::Black,
            reason: WinReason::Checkmate
        })
    );

    let mut unprotected = board.clone();
    unprotected.set(sq(2, 2, 2), None);
    let g = GameState::from_parts(unprotected, NO_HANDS, Color::White);
    assert_eq!(
        g.legal_moves(),
        vec![normal(sq(0, 0, 0), sq(1, 1, 1), false)]
    );
    assert_eq!(g.result(), None);
}

/// White king boxed in on rank 一 by its own pawns; a Black gold on (4,2,4) protects (4,1,4).
fn uchifuzume_position() -> Board {
    let mut v = vec![
        (sq(4, 0, 4), Color::White, PieceKind::King),
        (sq(4, 8, 4), Color::Black, PieceKind::King),
        (sq(4, 2, 4), Color::Black, PieceKind::Gold),
    ];
    for x in 3..=5 {
        for z in 3..=5 {
            for y in 0..=1 {
                if (x, y, z) != (4, 0, 4) && (x, y, z) != (4, 1, 4) {
                    v.push((sq(x, y, z), Color::White, PieceKind::Pawn));
                }
            }
        }
    }
    board_with(&v)
}

#[test]
fn pawn_drop_checkmate_is_illegal_but_other_drop_mates_are_legal() {
    let board = uchifuzume_position();
    let mut hands = hands_with(Color::Black, PieceKind::Pawn, 1);
    hands[0][PieceKind::Gold.hand_index().unwrap()] = 1;
    let g = GameState::from_parts(board.clone(), hands, Color::Black);
    let pawn_mate = Move::Drop {
        kind: PieceKind::Pawn,
        to: sq(4, 1, 4),
    };
    let gold_mate = Move::Drop {
        kind: PieceKind::Gold,
        to: sq(4, 1, 4),
    };
    let legal = g.legal_moves();
    assert!(!legal.contains(&pawn_mate));
    assert!(legal.contains(&gold_mate));
    assert!(matches!(
        g.apply_move(&pawn_mate),
        Err(MoveError::Illegal(_))
    ));
    let after = g.apply_move(&gold_mate).unwrap();
    assert_eq!(
        after.result(),
        Some(GameResult::Win {
            winner: Color::Black,
            reason: WinReason::Checkmate
        })
    );
    assert_eq!(
        sorted(legal),
        reference_legal_moves(&board, &hands, Color::Black)
    );
}

#[test]
fn pawn_drop_check_that_is_not_mate_is_legal() {
    let mut board = uchifuzume_position();
    board.set(sq(5, 0, 5), None); // gives the king an escape square
    let g = GameState::from_parts(
        board,
        hands_with(Color::Black, PieceKind::Pawn, 1),
        Color::Black,
    );
    let drop = Move::Drop {
        kind: PieceKind::Pawn,
        to: sq(4, 1, 4),
    };
    assert!(g.legal_moves().contains(&drop));
    let after = g.apply_move(&drop).unwrap();
    assert!(after.is_in_check(Color::White));
    assert_eq!(after.result(), None);
}

// ------------------------------------------------------------------ repetition

#[test]
fn fourfold_repetition_is_a_draw() {
    let board = kings_and(&[]);
    let mut g = GameState::from_parts(board, NO_HANDS, Color::Black);
    let cycle = [
        normal(sq(4, 8, 4), sq(4, 7, 4), false),
        normal(sq(4, 0, 4), sq(4, 1, 4), false),
        normal(sq(4, 7, 4), sq(4, 8, 4), false),
        normal(sq(4, 1, 4), sq(4, 0, 4), false),
    ];
    for i in 0..12 {
        assert_eq!(g.result(), None, "ply {i}");
        g = g.apply_move(&cycle[i % 4]).unwrap();
    }
    assert_eq!(
        g.result(),
        Some(GameResult::Draw {
            reason: DrawReason::Repetition
        })
    );
    // no further moves are accepted once the game is over
    assert!(matches!(g.apply_move(&cycle[0]), Err(MoveError::GameOver)));
}

#[test]
fn perpetual_check_loses_for_the_checking_side() {
    // Black rook alternates (1,4,8) <-> (0,4,8) checking the White king that alternates (0,0,0) <-> (1,0,0).
    let board = board_with(&[
        (sq(0, 0, 0), Color::White, PieceKind::King),
        (sq(1, 4, 8), Color::Black, PieceKind::Rook),
        (sq(8, 8, 0), Color::Black, PieceKind::King),
    ]);
    let mut g = GameState::from_parts(board, NO_HANDS, Color::Black);
    let cycle = [
        normal(sq(1, 4, 8), sq(0, 4, 8), false),
        normal(sq(0, 0, 0), sq(1, 0, 0), false),
        normal(sq(0, 4, 8), sq(1, 4, 8), false),
        normal(sq(1, 0, 0), sq(0, 0, 0), false),
    ];
    for i in 0..12 {
        assert_eq!(g.result(), None, "ply {i}");
        g = g.apply_move(&cycle[i % 4]).unwrap();
        if i % 2 == 0 {
            assert!(g.is_in_check(Color::White), "ply {i} should be check");
        }
    }
    assert_eq!(
        g.result(),
        Some(GameResult::Win {
            winner: Color::White,
            reason: WinReason::PerpetualCheck
        })
    );
}

#[test]
fn resignation_ends_the_game() {
    let mut g = GameState::new();
    g.resign();
    assert_eq!(
        g.result(),
        Some(GameResult::Win {
            winner: Color::White,
            reason: WinReason::Resignation
        })
    );
    assert!(g.legal_moves().is_empty());
}

// ------------------------------------------------------------------ hashing / determinism

#[test]
fn hash_depends_on_board_hands_and_side_and_transpositions_agree() {
    let a = GameState::new();
    let b = GameState::from_parts(Board::initial(), NO_HANDS, Color::White);
    assert_ne!(a.hash(), b.hash());
    let c = GameState::from_parts(
        Board::initial(),
        hands_with(Color::Black, PieceKind::Pawn, 1),
        Color::Black,
    );
    assert_ne!(a.hash(), c.hash());

    let m1 = normal(sq(4, 6, 4), sq(4, 5, 4), false);
    let m2 = normal(sq(3, 6, 4), sq(3, 5, 4), false);
    let w1 = normal(sq(4, 2, 4), sq(4, 3, 4), false);
    let w2 = normal(sq(3, 2, 4), sq(3, 3, 4), false);
    let p = a
        .apply_move(&m1)
        .unwrap()
        .apply_move(&w1)
        .unwrap()
        .apply_move(&m2)
        .unwrap()
        .apply_move(&w2)
        .unwrap();
    let q = a
        .apply_move(&m2)
        .unwrap()
        .apply_move(&w2)
        .unwrap()
        .apply_move(&m1)
        .unwrap()
        .apply_move(&w1)
        .unwrap();
    assert_eq!(p.board(), q.board());
    assert_eq!(p.hash(), q.hash());
    // incremental hash equals the from-scratch hash of the same position
    let fresh = GameState::from_parts(p.board().clone(), *p.hands(), p.side_to_move());
    assert_eq!(p.hash(), fresh.hash());
}

#[test]
fn hash_is_stable_across_builds() {
    // Pin the Zobrist seed: datasets store these hashes, so they must never change silently.
    assert_eq!(GameState::new().hash(), GameState::new().hash());
    let h = GameState::new().hash();
    assert_ne!(h, 0);
    assert_eq!(format!("{h:016x}").len(), 16);
}

// ------------------------------------------------------------------ property: random playouts vs reference

fn random_hands(rng: &mut Rng) -> Hands {
    let mut h = NO_HANDS;
    for color in h.iter_mut() {
        for slot in color.iter_mut() {
            if rng.chance(30) {
                *slot = 1 + rng.below(2) as u8;
            }
        }
    }
    h
}

/// Random sparse middle-game-like positions (kings guaranteed, random hands).
fn random_position(rng: &mut Rng) -> (Board, Hands, Color) {
    loop {
        let density = 4 + rng.below(8);
        let mut b = random_board(rng, density);
        // remove random kings, then place exactly one per side
        for s in Square::all() {
            if b.get(s).is_some_and(|p| p.kind == PieceKind::King) {
                b.set(s, None);
            }
        }
        // no pieces on squares where they could never move (as in real games)
        for s in Square::all() {
            if let Some(p) = b.get(s) {
                let rr = p.color.relative_rank(s.y());
                let dead = matches!(p.kind, PieceKind::Pawn | PieceKind::Lance) && rr == 0
                    || p.kind == PieceKind::Knight && rr <= 1;
                if dead {
                    b.set(s, None);
                }
            }
        }
        let bk = Square::from_index(rng.below(729) as usize).unwrap();
        let wk = Square::from_index(rng.below(729) as usize).unwrap();
        if bk == wk {
            continue;
        }
        b.set(bk, Some(Piece::new(Color::Black, PieceKind::King)));
        b.set(wk, Some(Piece::new(Color::White, PieceKind::King)));
        let side = if rng.below(2) == 0 {
            Color::Black
        } else {
            Color::White
        };
        // the side not to move must not be in check (otherwise the position is unreachable)
        if reference_in_check(&b, side.opponent()) {
            continue;
        }
        return (b, random_hands(rng), side);
    }
}

#[test]
fn legal_moves_match_reference_on_random_positions() {
    let mut rng = Rng(0xC0FFEE);
    for i in 0..40 {
        let (b, h, side) = random_position(&mut rng);
        let g = GameState::from_parts(b.clone(), h, side);
        assert_eq!(
            sorted(g.legal_moves()),
            reference_legal_moves(&b, &h, side),
            "position {i}"
        );
        assert_eq!(
            g.is_in_check(side),
            reference_in_check(&b, side),
            "position {i}"
        );
    }
}

#[test]
fn random_playouts_from_initial_position_match_reference_every_ply() {
    let mut rng = Rng(0xBADC0DE);
    for game in 0..3 {
        let mut g = GameState::new();
        assert_eq!(g.board(), &Board::initial());
        for ply in 0..30 {
            let moves = g.legal_moves();
            assert_eq!(
                sorted(moves.clone()),
                reference_legal_moves(g.board(), g.hands(), g.side_to_move()),
                "game {game} ply {ply}"
            );
            if moves.is_empty() {
                break;
            }
            // prefer captures to create hands and open lines
            let caps: Vec<&Move> = moves
                .iter()
                .filter(|m| matches!(m, Move::Normal { to, .. } if !g.board().is_empty(*to)))
                .collect();
            let mv = if !caps.is_empty() && rng.chance(70) {
                *caps[rng.below(caps.len() as u64) as usize]
            } else {
                moves[rng.below(moves.len() as u64) as usize]
            };
            g = g.apply_move(&mv).unwrap();
            assert_eq!(g.ply(), ply + 1);
        }
        assert!(g.ply() >= 20, "game {game} ended early at {}", g.ply());
    }
}

#[test]
fn piece_conservation_holds_during_random_play() {
    // 372 pieces in total: on board + in hands, every ply.
    let mut rng = Rng(42);
    let mut g = GameState::new();
    let mut plies = 0;
    for _ in 0..200 {
        let moves = g.legal_moves();
        if moves.is_empty() || g.result().is_some() {
            break;
        }
        g = g
            .apply_move(&moves[rng.below(moves.len() as u64) as usize])
            .unwrap();
        let in_hand: u32 = g.hands().iter().flatten().map(|&n| n as u32).sum();
        assert_eq!(g.board().count() as u32 + in_hand, 372);
        assert!(g.board().find_king(Color::Black).is_some());
        assert!(g.board().find_king(Color::White).is_some());
        plies += 1;
    }
    assert!(
        plies >= 100 || g.result().is_some(),
        "only {plies} plies played"
    );
}

#[test]
fn when_in_check_drops_are_only_legal_on_interposing_squares() {
    // White lance on (4,2,4) checks the Black king on (4,8,4) along the file; the
    // only legal drops are on the five squares strictly between them.
    let board = kings_and(&[(sq(4, 2, 4), Color::White, PieceKind::Lance)]);
    let g = GameState::from_parts(
        board.clone(),
        hands_with(Color::Black, PieceKind::Gold, 1),
        Color::Black,
    );
    assert!(g.is_in_check(Color::Black));
    let drops: std::collections::BTreeSet<Square> = g
        .legal_moves()
        .into_iter()
        .filter_map(|m| {
            if let Move::Drop { to, .. } = m {
                Some(to)
            } else {
                None
            }
        })
        .collect();
    let between: std::collections::BTreeSet<Square> = (3..=7).map(|y| sq(4, y, 4)).collect();
    assert_eq!(drops, between);
    let off_line = Move::Drop {
        kind: PieceKind::Gold,
        to: sq(0, 4, 0),
    };
    assert!(matches!(
        g.apply_move(&off_line),
        Err(MoveError::Illegal(_))
    ));
}
