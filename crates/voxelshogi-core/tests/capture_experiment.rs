use voxelshogi_core::capture::{CaptureGame, CaptureRule, Outcome, Reason};
use voxelshogi_core::{Board, Color, Move, Piece, PieceKind, Square};

fn sq(x: u8, y: u8, z: u8) -> Square {
    Square::new(x, y, z)
}
fn position(black: usize, white: usize, rule: CaptureRule, limit: u32) -> CaptureGame {
    let mut b = Board::empty();
    for x in 0..black {
        b.set(
            sq(x as u8, 8, 0),
            Some(Piece::new(Color::Black, PieceKind::King)),
        );
    }
    for x in 0..white {
        b.set(
            sq(x as u8, 0, 0),
            Some(Piece::new(Color::White, PieceKind::King)),
        );
    }
    b.set(sq(4, 1, 0), Some(Piece::new(Color::Black, PieceKind::Rook)));
    CaptureGame::from_parts(b, [[0; 7]; 2], Color::Black, rule, limit).unwrap()
}
fn capture() -> Move {
    Move::Normal {
        from: sq(4, 1, 0),
        to: sq(4, 0, 0),
        promote: false,
    }
}

#[test]
fn nine_identical_layers_have_hand_counted_pieces() {
    let g = CaptureGame::new(CaptureRule::FirstFive, 400).unwrap();
    assert_eq!(g.board().count(), 360);
    for color in Color::ALL {
        for (kind, expected) in [
            (PieceKind::King, 9),
            (PieceKind::Pawn, 81),
            (PieceKind::Gold, 18),
            (PieceKind::Rook, 9),
        ] {
            assert_eq!(
                g.board()
                    .pieces()
                    .filter(|(_, p)| p.color == color && p.kind == kind)
                    .count(),
                expected
            );
        }
    }
    assert_eq!(g.captured(), [0, 0]);
    assert_eq!(g.legal_moves().len(), 554);
}

#[test]
fn fifth_king_wins_without_going_to_hand() {
    let g = position(9, 5, CaptureRule::FirstFive, 2);
    assert_eq!(g.captured(), [4, 0]);
    let g = g.after_move(&capture()).unwrap();
    assert_eq!(g.captured(), [5, 0]);
    assert_eq!(g.hands(), &[[0; 7]; 2]);
    assert_eq!(
        g.outcome(),
        Some(Outcome {
            winner: Some(Color::Black),
            reason: Reason::Target
        })
    );
    assert!(g.legal_moves().is_empty());
    assert!(g.after_move(&capture()).is_err());
    assert!(CaptureGame::new(CaptureRule::FirstFive, 1).is_err());
}

#[test]
fn all_kings_rule_continues_after_fifth_and_ends_after_ninth() {
    let g = position(9, 5, CaptureRule::AllKings, 400)
        .after_move(&capture())
        .unwrap();
    assert_eq!(g.captured(), [5, 0]);
    assert_eq!(g.outcome(), None);
    let mut b = Board::empty();
    b.set(sq(4, 0, 0), Some(Piece::new(Color::White, PieceKind::King)));
    for x in 0..9 {
        b.set(sq(x, 8, 0), Some(Piece::new(Color::Black, PieceKind::King)));
    }
    b.set(sq(4, 1, 0), Some(Piece::new(Color::Black, PieceKind::Rook)));
    let g = CaptureGame::from_parts(b, [[0; 7]; 2], Color::Black, CaptureRule::AllKings, 400)
        .unwrap()
        .after_move(&capture())
        .unwrap();
    assert_eq!(g.captured(), [9, 0]);
    assert_eq!(g.outcome().unwrap().winner, Some(Color::Black));
}

#[test]
fn score_rule_only_uses_kings_at_the_even_move_limit() {
    let g = position(8, 5, CaptureRule::ScoreLimit, 2)
        .after_move(&capture())
        .unwrap();
    assert_eq!(g.captured(), [5, 1]);
    assert_eq!(g.outcome(), None);
    let mv = Move::Normal {
        from: sq(0, 0, 0),
        to: sq(0, 1, 0),
        promote: false,
    };
    let g = g.after_move(&mv).unwrap();
    assert_eq!(
        g.outcome(),
        Some(Outcome {
            winner: Some(Color::Black),
            reason: Reason::ScoreLimit
        })
    );
    let g = position(8, 8, CaptureRule::ScoreLimit, 2);
    let a = Move::Normal {
        from: sq(4, 1, 0),
        to: sq(4, 2, 0),
        promote: false,
    };
    let b = Move::Normal {
        from: sq(0, 0, 0),
        to: sq(0, 1, 0),
        promote: false,
    };
    assert_eq!(
        g.after_move(&a).unwrap().after_move(&b).unwrap().outcome(),
        Some(Outcome {
            winner: None,
            reason: Reason::ScoreLimit
        })
    );
}

#[test]
fn legal_sequences_update_turn_ply_and_hash() {
    let mut g = CaptureGame::new(CaptureRule::AllKings, 400).unwrap();
    let first = g.legal_moves()[0];
    let checked = g.after_move(&first).unwrap();
    assert_eq!(checked.ply(), 1);
    assert_eq!(checked.side(), Color::White);
    // Nonempty legal sequences update state on every ply.
    for _ in 0..25 {
        let moves = g.legal_moves();
        assert!(!moves.is_empty());
        let mv = moves[moves.len() / 2];
        let next = g.after_move(&mv).unwrap();
        assert_ne!(g.hash(), next.hash());
        g = next;
    }
}

#[test]
fn repetition_is_fourfold() {
    let mut g = CaptureGame::new(CaptureRule::AllKings, 400).unwrap();
    let cycle = [
        Move::Normal {
            from: sq(4, 8, 4),
            to: sq(4, 7, 4),
            promote: false,
        },
        Move::Normal {
            from: sq(4, 0, 4),
            to: sq(4, 1, 4),
            promote: false,
        },
        Move::Normal {
            from: sq(4, 7, 4),
            to: sq(4, 8, 4),
            promote: false,
        },
        Move::Normal {
            from: sq(4, 1, 4),
            to: sq(4, 0, 4),
            promote: false,
        },
    ];
    for i in 0..12 {
        g = g.after_move(&cycle[i % 4]).unwrap();
        if i < 11 {
            assert_eq!(g.outcome(), None);
        }
    }
    assert_eq!(
        g.outcome(),
        Some(Outcome {
            winner: None,
            reason: Reason::Repetition
        })
    );
}

#[test]
fn attacked_king_is_legal_and_promoted_capture_returns_base_piece() {
    let mut b = Board::empty();
    for x in 0..9 {
        b.set(sq(x, 8, 0), Some(Piece::new(Color::Black, PieceKind::King)));
        b.set(sq(x, 0, 0), Some(Piece::new(Color::White, PieceKind::King)));
    }
    b.set(sq(4, 6, 0), Some(Piece::new(Color::White, PieceKind::Rook)));
    b.set(sq(0, 6, 1), Some(Piece::new(Color::Black, PieceKind::Rook)));
    b.set(
        sq(0, 5, 1),
        Some(Piece::new(Color::White, PieceKind::PromotedSilver)),
    );
    let g =
        CaptureGame::from_parts(b, [[0; 7]; 2], Color::Black, CaptureRule::AllKings, 400).unwrap();
    assert!(
        g.after_move(&Move::Normal {
            from: sq(4, 8, 0),
            to: sq(4, 7, 0),
            promote: false
        })
        .is_ok()
    );
    let next = g
        .after_move(&Move::Normal {
            from: sq(0, 6, 1),
            to: sq(0, 5, 1),
            promote: false,
        })
        .unwrap();
    assert_eq!(next.hands()[0], [0, 0, 0, 1, 0, 0, 0]);
    assert_eq!(next.captured(), [0, 0]);
    assert_eq!(g.hands()[0], [0; 7]);
}

#[test]
fn white_target_on_last_ply_wins_instead_of_cutoff_and_score_target_continues() {
    let mut b = position(5, 9, CaptureRule::AllKings, 2).board().clone();
    b.set(sq(4, 1, 0), None);
    b.set(sq(4, 7, 0), Some(Piece::new(Color::White, PieceKind::Rook)));
    let quiet = Move::Normal {
        from: sq(0, 8, 0),
        to: sq(0, 7, 0),
        promote: false,
    };
    let take = Move::Normal {
        from: sq(4, 7, 0),
        to: sq(4, 8, 0),
        promote: false,
    };
    let g = CaptureGame::from_parts(b, [[0; 7]; 2], Color::Black, CaptureRule::FirstFive, 2)
        .unwrap()
        .after_move(&quiet)
        .unwrap()
        .after_move(&take)
        .unwrap();
    assert_eq!(g.ply(), 2);
    assert_eq!(
        g.outcome(),
        Some(Outcome {
            winner: Some(Color::White),
            reason: Reason::Target
        })
    );
    let mut b = position(9, 5, CaptureRule::ScoreLimit, 4).board().clone();
    for x in [0, 1, 2, 3] {
        b.set(sq(x, 0, 0), None);
    }
    b.set(sq(8, 2, 1), Some(Piece::new(Color::White, PieceKind::Pawn)));
    let g = CaptureGame::from_parts(b, [[0; 7]; 2], Color::Black, CaptureRule::ScoreLimit, 4)
        .unwrap()
        .after_move(&capture())
        .unwrap();
    assert_eq!(g.captured(), [9, 0]);
    // White still has other pieces in this fixture, so no-moves must not end it.
    assert_eq!(g.outcome(), None);
}

#[test]
fn drops_obey_nifu_and_dead_end_and_inventory_is_bounded() {
    let mut b = position(9, 9, CaptureRule::AllKings, 4).board().clone();
    b.set(sq(3, 4, 2), Some(Piece::new(Color::Black, PieceKind::Pawn)));
    let mut hands = [[0; 7]; 2];
    hands[0][0] = 1;
    hands[0][2] = 1;
    let g =
        CaptureGame::from_parts(b.clone(), hands, Color::Black, CaptureRule::AllKings, 4).unwrap();
    for (kind, to) in [
        (PieceKind::Pawn, sq(3, 3, 2)),
        (PieceKind::Pawn, sq(2, 0, 2)),
        (PieceKind::Knight, sq(2, 1, 2)),
    ] {
        assert!(g.after_move(&Move::Drop { kind, to }).is_err());
    }
    let n = g
        .after_move(&Move::Drop {
            kind: PieceKind::Pawn,
            to: sq(3, 3, 3),
        })
        .unwrap();
    assert_eq!(n.hands()[0][0], 0);
    assert_eq!(
        n.board().get(sq(3, 3, 3)),
        Some(Piece::new(Color::Black, PieceKind::Pawn))
    );
    hands[0][0] = 163;
    assert!(CaptureGame::from_parts(b, hands, Color::Black, CaptureRule::AllKings, 4).is_err());
}

mod common;
#[test]
fn movement_matches_independent_brute_force_geometry() {
    use std::collections::BTreeSet;
    let mut g = CaptureGame::new(CaptureRule::AllKings, 400).unwrap();
    for _ in 0..4 {
        let mut expected = BTreeSet::new();
        for (from, p) in g.board().pieces().filter(|(_, p)| p.color == g.side()) {
            for to in common::reference_targets(g.board(), from) {
                let rr = g.side().relative_rank(to.y());
                let forced = match p.kind {
                    PieceKind::Pawn | PieceKind::Lance => rr == 0,
                    PieceKind::Knight => rr < 2,
                    _ => false,
                };
                if !forced {
                    expected.insert(Move::Normal {
                        from,
                        to,
                        promote: false,
                    });
                }
                if p.kind.can_promote() && (g.side().relative_rank(from.y()) < 3 || rr < 3) {
                    expected.insert(Move::Normal {
                        from,
                        to,
                        promote: true,
                    });
                }
            }
        }
        // These opening fixtures have no hands. The drop restrictions have separate hand-written tests.
        assert_eq!(g.hands(), &[[0; 7]; 2]);
        assert_eq!(
            g.legal_moves().into_iter().collect::<BTreeSet<_>>(),
            expected
        );
        assert!(expected.len() > 400);
        g = g
            .after_move(expected.iter().nth(expected.len() / 3).unwrap())
            .unwrap();
    }
}
