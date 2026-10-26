//! Hand-written boundary contracts exposed by the full-core M1 mutation audit.
use voxelshogi_core::capture::{CaptureGame, CaptureRule, Outcome, Reason};
use voxelshogi_core::{Board, Color, Move, Piece, PieceKind, Square};
fn kings() -> Board {
    let mut b = Board::empty();
    for x in 0..9 {
        b.set(
            Square::new(x, 8, 0),
            Some(Piece::new(Color::Black, PieceKind::King)),
        );
        b.set(
            Square::new(x, 0, 0),
            Some(Piece::new(Color::White, PieceKind::King)),
        );
    }
    b
}
#[test]
fn experimental_limits_and_each_inventory_bound_are_enforced() {
    for limit in [2, 2000] {
        assert!(CaptureGame::new(CaptureRule::AllKings, limit).is_ok());
    }
    for limit in [0, 1, 1999, 2001, 2002] {
        assert!(CaptureGame::new(CaptureRule::AllKings, limit).is_err());
    }
    for side in Color::ALL {
        for (index, max) in [162u8, 36, 36, 36, 36, 18, 18].into_iter().enumerate() {
            let mut hands = [[0; 7]; 2];
            hands[side.index()][index] = max;
            assert!(
                CaptureGame::from_parts(kings(), hands, side, CaptureRule::AllKings, 2).is_ok()
            );
            hands[side.opponent().index()][index] = 1;
            assert!(
                CaptureGame::from_parts(kings(), hands, side, CaptureRule::AllKings, 2).is_err()
            );
        }
        let mut b = kings();
        b.set(
            Square::new(0, 4, 1),
            Some(Piece::new(side, PieceKind::King)),
        );
        assert!(CaptureGame::from_parts(b, [[0; 7]; 2], side, CaptureRule::AllKings, 2).is_err());
    }
    let mut hands = [[0; 7]; 2];
    hands[0][0] = 162;
    let mut board = kings();
    board.set(
        Square::new(4, 4, 4),
        Some(Piece::new(Color::Black, PieceKind::Pawn)),
    );
    assert!(CaptureGame::from_parts(board, hands, Color::Black, CaptureRule::AllKings, 2).is_err());
}
#[test]
fn promotion_zone_is_exactly_three_ranks_including_moves_leaving_the_zone() {
    for side in Color::ALL {
        let rank = |y| if side == Color::Black { y } else { 8 - y };
        for (from_y, to_y, allowed) in [(4, 3, false), (3, 4, false), (2, 3, true), (3, 2, true)] {
            let from = Square::new(4, rank(from_y), 4);
            let to = Square::new(4, rank(to_y), 4);
            let mut b = kings();
            b.set(from, Some(Piece::new(side, PieceKind::Rook)));
            let g =
                CaptureGame::from_parts(b, [[0; 7]; 2], side, CaptureRule::AllKings, 4).unwrap();
            let moves = g.legal_moves();
            assert!(moves.contains(&Move::Normal {
                from,
                to,
                promote: false
            }));
            assert_eq!(
                moves.contains(&Move::Normal {
                    from,
                    to,
                    promote: true
                }),
                allowed
            );
        }
    }
}
#[test]
fn forced_promotions_for_both_sides_have_no_unpromoted_alternative() {
    for side in Color::ALL {
        let rank = |y| if side == Color::Black { y } else { 8 - y };
        for (kind, from_y, to_x, to_y, to_z) in [
            (PieceKind::Pawn, 1, 4, 0, 4),
            (PieceKind::Lance, 1, 4, 0, 4),
            (PieceKind::Knight, 2, 5, 0, 5),
            (PieceKind::Knight, 3, 5, 1, 5),
        ] {
            let from = Square::new(4, rank(from_y), 4);
            let to = Square::new(to_x, rank(to_y), to_z);
            let mut b = kings();
            b.set(from, Some(Piece::new(side, kind)));
            let g =
                CaptureGame::from_parts(b, [[0; 7]; 2], side, CaptureRule::AllKings, 4).unwrap();
            assert!(g.legal_moves().contains(&Move::Normal {
                from,
                to,
                promote: true
            }));
            assert!(!g.legal_moves().contains(&Move::Normal {
                from,
                to,
                promote: false
            }));
        }
    }
}
#[test]
fn score_limit_can_award_white_without_a_king_capture_on_the_last_ply() {
    let mut b = kings();
    for x in 0..4 {
        b.set(Square::new(x, 8, 0), None);
    }
    b.set(Square::new(0, 0, 0), None);
    let mut g =
        CaptureGame::from_parts(b, [[0; 7]; 2], Color::Black, CaptureRule::ScoreLimit, 2).unwrap();
    assert_eq!(g.captured(), [1, 4]);
    for (from, to) in [
        (Square::new(8, 8, 0), Square::new(8, 7, 0)),
        (Square::new(8, 0, 0), Square::new(8, 1, 0)),
    ] {
        g = g
            .after_move(&Move::Normal {
                from,
                to,
                promote: false,
            })
            .unwrap();
    }
    assert_eq!(
        g.outcome(),
        Some(Outcome {
            winner: Some(Color::White),
            reason: Reason::ScoreLimit
        })
    );
}

#[test]
fn experimental_drop_set_matches_a_direct_rule_reference_for_all_hands_and_colors() {
    use std::collections::BTreeSet;
    for side in Color::ALL {
        let mut b = kings();
        b.set(
            Square::new(3, 4, 4),
            Some(Piece::new(side, PieceKind::Pawn)),
        );
        let mut hands = [[0; 7]; 2];
        hands[side.index()] = [1; 7];
        let g = CaptureGame::from_parts(b, hands, side, CaptureRule::AllKings, 4).unwrap();
        let mut expected = BTreeSet::new();
        for to in Square::all().filter(|&s| g.board().get(s).is_none()) {
            let rank = if side == Color::Black {
                to.y()
            } else {
                8 - to.y()
            };
            for kind in PieceKind::HAND {
                if matches!(kind, PieceKind::Pawn | PieceKind::Lance) && rank == 0 {
                    continue;
                }
                if kind == PieceKind::Knight && rank < 2 {
                    continue;
                }
                if kind == PieceKind::Pawn && to.x() == 3 && to.z() == 4 {
                    continue;
                }
                expected.insert(Move::Drop { kind, to });
            }
        }
        let actual = g
            .legal_moves()
            .into_iter()
            .filter(|m| matches!(m, Move::Drop { .. }))
            .collect::<BTreeSet<_>>();
        assert!(expected.len() > 3000);
        assert_eq!(actual, expected);
    }
}
#[test]
fn no_moves_in_a_score_game_is_a_draw_with_an_explicit_reason() {
    let mut board = kings();
    for x in 0..9 {
        board.set(Square::new(x, 0, 0), None);
    }
    let g = CaptureGame::from_parts(board, [[0; 7]; 2], Color::White, CaptureRule::ScoreLimit, 2)
        .unwrap();
    assert_eq!(g.board().count(), 9);
    assert_eq!(g.captured(), [9, 0]);
    assert!(g.legal_moves().is_empty());
    assert_eq!(
        g.outcome(),
        Some(Outcome {
            winner: None,
            reason: Reason::NoMoves
        })
    );
    assert!(
        g.after_move(&Move::Drop {
            kind: PieceKind::Pawn,
            to: Square::new(4, 4, 4)
        })
        .is_err()
    );
}

#[test]
fn experiment_rules_have_distinct_fixed_identifiers() {
    assert_eq!(
        CaptureRule::FirstFive.id(),
        "voxelshogi-nine-kings-first5-v0"
    );
    assert_eq!(CaptureRule::AllKings.id(), "voxelshogi-nine-kings-all-v0");
    assert_eq!(
        CaptureRule::ScoreLimit.id(),
        "voxelshogi-nine-kings-score-v0"
    );
}
