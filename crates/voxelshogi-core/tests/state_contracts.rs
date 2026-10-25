//! Rule-derived contracts for public state APIs and repetition/hash edge cases.
use voxelshogi_core::{
    Board, Color, GameResult, GameState, Move, MoveError, Piece, PieceKind, Square, WinReason,
};

fn sq(x: u8, y: u8, z: u8) -> Square {
    Square::new(x, y, z)
}

fn normal(from: Square, to: Square, promote: bool) -> Move {
    Move::Normal { from, to, promote }
}

fn kings() -> Board {
    let mut b = Board::empty();
    b.set(sq(8, 8, 8), Some(Piece::new(Color::Black, PieceKind::King)));
    b.set(sq(0, 0, 0), Some(Piece::new(Color::White, PieceKind::King)));
    b
}

#[test]
fn legality_api_accepts_legal_moves_and_rejects_illegal_and_terminal_moves() {
    let mut g = GameState::new();
    // Initial Black pawn: one step forward, backwards, and opponent's pawn.
    let legal = normal(sq(4, 6, 4), sq(4, 5, 4), false);
    let backwards = normal(sq(4, 6, 4), sq(4, 7, 4), false);
    let opponent = normal(sq(4, 2, 4), sq(4, 3, 4), false);
    assert!(g.is_legal(&legal));
    assert!(!g.is_legal(&backwards));
    assert!(!g.is_legal(&opponent));
    g.resign();
    assert!(!g.is_legal(&legal));
}

#[test]
fn checked_application_accepts_optional_promotion_in_each_sides_zone() {
    for (side, from_y, to_y, outside_from, outside_to) in
        [(Color::Black, 2, 1, 5, 4), (Color::White, 6, 7, 3, 4)]
    {
        let mut b = kings();
        b.set(sq(4, from_y, 4), Some(Piece::new(side, PieceKind::Pawn)));
        b.set(
            sq(5, outside_from, 4),
            Some(Piece::new(side, PieceKind::Pawn)),
        );
        let g = GameState::from_parts(b, [[0; 7]; 2], side);
        let promoted = g
            .apply_move(&normal(sq(4, from_y, 4), sq(4, to_y, 4), true))
            .unwrap();
        assert_eq!(
            promoted.board().get(sq(4, to_y, 4)),
            Some(Piece::new(side, PieceKind::Tokin))
        );
        assert!(
            g.check_move(&normal(sq(4, from_y, 4), sq(4, to_y, 4), false))
                .is_ok()
        );
        assert!(
            g.check_move(&normal(sq(5, outside_from, 4), sq(5, outside_to, 4), true))
                .is_err()
        );
    }
}

#[test]
fn checked_application_requires_promotion_for_dead_end_pieces() {
    for side in Color::ALL {
        let rank = |y| if side == Color::Black { y } else { 8 - y };
        for (kind, from_y, to_x, to_y, to_z) in [
            (PieceKind::Pawn, 1, 4, 0, 4),
            (PieceKind::Lance, 1, 4, 0, 4),
            (PieceKind::Knight, 2, 5, 0, 5),
            (PieceKind::Knight, 3, 5, 1, 5),
        ] {
            let mut b = kings();
            let from = sq(4, rank(from_y), 4);
            let to = sq(to_x, rank(to_y), to_z);
            b.set(from, Some(Piece::new(side, kind)));
            let g = GameState::from_parts(b, [[0; 7]; 2], side);
            assert!(
                g.check_move(&normal(from, to, false)).is_err(),
                "{side:?} {kind:?}"
            );
            let next = g.apply_move(&normal(from, to, true)).unwrap();
            assert_eq!(
                next.board().get(to),
                Some(Piece::new(side, kind.promote().unwrap()))
            );
        }
    }
}

#[test]
fn play_updates_capture_promotion_hands_turn_and_ply_and_preserves_errors() {
    let mut b = kings();
    b.set(sq(4, 2, 4), Some(Piece::new(Color::Black, PieceKind::Pawn)));
    b.set(
        sq(4, 1, 4),
        Some(Piece::new(Color::White, PieceKind::Silver)),
    );
    let mut g = GameState::from_parts(b, [[0; 7]; 2], Color::Black);
    let before_hash = g.hash();
    g.play(&normal(sq(4, 2, 4), sq(4, 1, 4), true)).unwrap();
    assert_eq!(g.board().get(sq(4, 2, 4)), None);
    assert_eq!(
        g.board().get(sq(4, 1, 4)),
        Some(Piece::new(Color::Black, PieceKind::Tokin))
    );
    assert_eq!(g.hands(), &[[0, 0, 0, 1, 0, 0, 0], [0; 7]]);
    assert_eq!(g.side_to_move(), Color::White);
    assert_eq!(g.ply(), 1);
    assert_ne!(g.hash(), before_hash);
    let snapshot = (
        g.board().clone(),
        *g.hands(),
        g.side_to_move(),
        g.ply(),
        g.hash(),
        g.result(),
    );
    assert!(matches!(
        g.play(&normal(sq(4, 2, 4), sq(4, 1, 4), false)),
        Err(MoveError::Illegal(_))
    ));
    assert_eq!(
        (
            g.board().clone(),
            *g.hands(),
            g.side_to_move(),
            g.ply(),
            g.hash(),
            g.result()
        ),
        snapshot
    );
    g.resign();
    assert_eq!(
        g.play(&normal(sq(0, 0, 0), sq(0, 1, 0), false)),
        Err(MoveError::GameOver)
    );
}

#[test]
fn perpetual_check_loses_for_either_color_even_with_a_nonrepeating_prefix() {
    for checker in Color::ALL {
        // Flip all axes and colors to exercise White as the checking side too.
        let transform = |x, y, z| {
            if checker == Color::Black {
                sq(x, y, z)
            } else {
                sq(8 - x, 8 - y, 8 - z)
            }
        };
        let mover = checker.opponent();
        let mut b = Board::empty();
        b.set(transform(0, 0, 0), Some(Piece::new(mover, PieceKind::King)));
        b.set(
            transform(2, 4, 8),
            Some(Piece::new(checker, PieceKind::Rook)),
        );
        b.set(
            transform(8, 8, 0),
            Some(Piece::new(checker, PieceKind::King)),
        );
        let mut g = GameState::from_parts(b, [[0; 7]; 2], checker);
        g = g
            .apply_move(&normal(transform(2, 4, 8), transform(0, 4, 8), false))
            .unwrap();
        let cycle = [
            normal(transform(0, 0, 0), transform(1, 0, 0), false),
            normal(transform(0, 4, 8), transform(1, 4, 8), false),
            normal(transform(1, 0, 0), transform(0, 0, 0), false),
            normal(transform(1, 4, 8), transform(0, 4, 8), false),
        ];
        for ply in 0..12 {
            assert_eq!(g.result(), None, "{checker:?} cycle ply {ply}");
            g = g.apply_move(&cycle[ply % 4]).unwrap();
            if ply % 2 == 1 {
                assert!(g.is_in_check(mover));
            }
        }
        assert_eq!(
            g.result(),
            Some(GameResult::Win {
                winner: mover,
                reason: WinReason::PerpetualCheck
            })
        );
    }
}

#[test]
fn independent_hand_slots_combine_by_xor_with_board_and_turn() {
    // Zobrist's documented composition rule, rather than values generated by the
    // engine as expected hashes. A slot must affect the hash for both owners.
    for side in Color::ALL {
        let b = kings();
        let base = GameState::from_parts(b.clone(), [[0; 7]; 2], side).hash();
        for owner in Color::ALL {
            for i in 0..7 {
                let mut hands = [[0; 7]; 2];
                hands[owner.index()][i] = 2;
                let slot = GameState::from_parts(Board::empty(), hands, Color::Black).hash();
                assert_ne!(slot, 0);
                let combined = GameState::from_parts(b.clone(), hands, side).hash();
                assert_eq!(combined, base ^ slot, "{side:?} {owner:?} slot {i}");
            }
        }
    }
}
