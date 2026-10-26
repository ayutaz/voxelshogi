//! Hand-counted evaluation and an independent, full-width minimax oracle.
use voxelshogi_core::search::{evaluate, piece_value};
use voxelshogi_core::{Board, Color, GameState, Piece, PieceKind, Square};

fn kings() -> Board {
    let mut board = Board::empty();
    board.set(
        Square::new(8, 8, 8),
        Some(Piece::new(Color::Black, PieceKind::King)),
    );
    board.set(
        Square::new(0, 0, 0),
        Some(Piece::new(Color::White, PieceKind::King)),
    );
    board
}

#[test]
fn material_values_and_side_perspective_are_hand_counted() {
    let expected = [
        100, 300, 320, 450, 550, 800, 1000, 0, 550, 550, 550, 550, 1100, 1300,
    ];
    for (kind, value) in PieceKind::ALL.into_iter().zip(expected) {
        assert_eq!(piece_value(kind), value, "{kind:?}");
    }
    assert_eq!(evaluate(&GameState::new()), 0);
    let mut board = kings();
    board.set(
        Square::new(4, 4, 4),
        Some(Piece::new(Color::Black, PieceKind::Dragon)),
    );
    board.set(
        Square::new(4, 3, 4),
        Some(Piece::new(Color::White, PieceKind::Tokin)),
    );
    let mut hands = [[0; 7]; 2];
    hands[0][0] = 2; // two Black pawns = 200
    hands[1][3] = 1; // one White silver = 450
    for (side, expected) in [(Color::Black, 500), (Color::White, -500)] {
        let game = GameState::from_parts(board.clone(), hands, side);
        assert_eq!(evaluate(&game), expected); // 1300 - 550 + 200 - 450
    }
}

use std::time::Duration;
use voxelshogi_core::search::{
    MATE_SCORE, SearchLimits, SearchOptions, StopReason, search, search_with_clock,
};
use voxelshogi_core::{GameResult, Move, WinReason};

fn limits(depth: u8) -> SearchLimits {
    SearchLimits {
        max_depth: depth,
        max_nodes: None,
        max_time: None,
        max_game_ply: None,
    }
}
fn basic() -> SearchOptions {
    SearchOptions {
        iterative_deepening: false,
        move_ordering: false,
        transposition_table: false,
        table_capacity: 0,
    }
}
fn static_reference(g: &GameState) -> i32 {
    // Literal rule-independent expected material; no call to the production evaluator.
    let values = [
        100, 300, 320, 450, 550, 800, 1000, 0, 550, 550, 550, 550, 1100, 1300,
    ];
    let mut value = 0;
    for (_, p) in g.board().pieces() {
        value += if p.color == Color::Black {
            values[p.kind as usize]
        } else {
            -values[p.kind as usize]
        };
    }
    for c in Color::ALL {
        for (i, kind) in PieceKind::HAND.into_iter().enumerate() {
            value += (if c == Color::Black { 1 } else { -1 })
                * i32::from(g.hands()[c.index()][i])
                * values[kind as usize];
        }
    }
    if g.side_to_move() == Color::Black {
        value
    } else {
        -value
    }
}
fn oracle(g: &GameState, depth: u8, max_ply: Option<u32>) -> (i32, Vec<Move>) {
    if let Some(result) = g.result() {
        return (
            match result {
                GameResult::Draw { .. } => 0,
                GameResult::Win { winner, .. } => {
                    if winner == g.side_to_move() {
                        1_000_000
                    } else {
                        -1_000_000
                    }
                }
            },
            vec![],
        );
    }
    if max_ply.is_some_and(|limit| g.ply() >= limit) {
        return (0, vec![]);
    }
    if depth == 0 {
        return (static_reference(g), vec![]);
    }
    let mut best = i32::MIN;
    let mut best_moves = vec![];
    for mv in g.legal_moves() {
        let score = -oracle(&g.apply_move(&mv).unwrap(), depth - 1, max_ply).0;
        if score > best {
            best = score;
            best_moves.clear();
        }
        if score == best {
            best_moves.push(mv);
        }
    }
    (best, best_moves)
}

#[test]
fn alpha_beta_matches_independent_full_width_oracle_depths_one_to_three() {
    for side in Color::ALL {
        let mut b = kings();
        b.set(
            Square::new(4, 3, 4),
            Some(Piece::new(Color::Black, PieceKind::Pawn)),
        );
        b.set(
            Square::new(5, 5, 5),
            Some(Piece::new(Color::White, PieceKind::Pawn)),
        );
        let game = GameState::from_parts(b, [[0; 7]; 2], side);
        for depth in 1..=3 {
            let expected = oracle(&game, depth, None);
            for flags in 0..8 {
                let options = SearchOptions {
                    iterative_deepening: flags & 1 != 0,
                    move_ordering: flags & 2 != 0,
                    transposition_table: flags & 4 != 0,
                    table_capacity: 65_536,
                };
                let result = search(&game, limits(depth), options).unwrap();
                assert_eq!(result.score, Some(expected.0), "{side:?} depth {depth}");
                assert!(expected.1.contains(&result.best_move.unwrap()));
                assert_eq!(result.completed_depth, depth);
                assert_eq!(result.stop_reason, StopReason::Depth);
                assert!(result.nodes >= 1);
            }
        }
    }
}

fn mating_position(attacker: Color, mated: bool) -> GameState {
    let sq = |x, y, z| {
        if attacker == Color::Black {
            Square::new(x, y, z)
        } else {
            Square::new(8 - x, 8 - y, 8 - z)
        }
    };
    let mut b = Board::empty();
    b.set(
        sq(0, 0, 0),
        Some(Piece::new(attacker.opponent(), PieceKind::King)),
    );
    b.set(sq(8, 8, 8), Some(Piece::new(attacker, PieceKind::King)));
    b.set(sq(2, 2, 2), Some(Piece::new(attacker, PieceKind::Gold)));
    b.set(
        if mated { sq(1, 1, 1) } else { sq(1, 2, 1) },
        Some(Piece::new(attacker, PieceKind::Dragon)),
    );
    GameState::from_parts(
        b,
        [[0; 7]; 2],
        if mated { attacker.opponent() } else { attacker },
    )
}

#[test]
fn finds_mate_in_one_for_both_sides_and_terminal_precedes_zero_depth_and_budgets() {
    assert_eq!(MATE_SCORE, 1_000_000);
    for side in Color::ALL {
        let game = mating_position(side, false);
        assert_eq!(game.result(), None);
        for options in [basic(), SearchOptions::default()] {
            let result = search(&game, limits(1), options).unwrap();
            assert_eq!(result.score, Some(1_000_000));
            let next = game.apply_move(&result.best_move.unwrap()).unwrap();
            assert_eq!(
                next.result(),
                Some(GameResult::Win {
                    winner: side,
                    reason: WinReason::Checkmate
                })
            );
        }
        let mated = mating_position(side, true);
        let mut zero = limits(0);
        zero.max_nodes = Some(0);
        zero.max_time = Some(Duration::ZERO);
        zero.max_game_ply = Some(0);
        let result = search(&mated, zero, SearchOptions::default()).unwrap();
        assert_eq!(result.best_move, None);
        assert_eq!(result.score, Some(-1_000_000));
        assert_eq!(result.stop_reason, StopReason::Terminal);
        assert_eq!(result.nodes, 0);
        let mut resigned = GameState::from_parts(kings(), [[0; 7]; 2], side);
        resigned.resign();
        assert_eq!(
            search(&resigned, limits(2), basic()).unwrap().score,
            Some(-1_000_000)
        );
    }
}

#[test]
fn depth_two_saves_a_threatened_promoted_rook() {
    let mut b = kings();
    let from = Square::new(4, 4, 4);
    b.set(from, Some(Piece::new(Color::Black, PieceKind::Dragon)));
    b.set(
        Square::new(3, 2, 3),
        Some(Piece::new(Color::White, PieceKind::Knight)),
    );
    let game = GameState::from_parts(b, [[0; 7]; 2], Color::Black);
    let expected = oracle(&game, 2, None);
    assert_eq!(expected.0, 980); // retains dragon (1300) against knight (320); neither can capture immediately
    let result = search(&game, limits(2), SearchOptions::default()).unwrap();
    assert_eq!(result.score, Some(980));
    assert!(matches!(result.best_move,Some(Move::Normal {from:f,..}) if f==from));
    assert!(expected.1.contains(&result.best_move.unwrap()));
}

#[test]
fn depth_node_and_time_limits_keep_only_a_completed_iteration() {
    let game = GameState::from_parts(kings(), [[0; 7]; 2], Color::Black);
    let opts = SearchOptions::default();
    let depth_one = search(&game, limits(1), opts).unwrap();
    let mut budget = limits(4);
    budget.max_nodes = Some(depth_one.nodes + 1);
    let stopped = search(&game, budget, opts).unwrap();
    assert_eq!(stopped.completed_depth, 1);
    assert_eq!(stopped.best_move, depth_one.best_move);
    assert_eq!(stopped.score, depth_one.score);
    assert_eq!(stopped.nodes, depth_one.nodes + 1);
    assert_eq!(stopped.last_iteration_nodes, depth_one.last_iteration_nodes);
    assert_eq!(stopped.stop_reason, StopReason::Nodes);
    assert_eq!(stopped, search(&game, budget, opts).unwrap());
    for nodes in [0, 1] {
        let mut zero = limits(4);
        zero.max_nodes = Some(nodes);
        let r = search(&game, zero, opts).unwrap();
        assert_eq!(r.completed_depth, 0);
        assert_eq!(r.score, None);
        assert_eq!(r.best_move, game.legal_moves().into_iter().min());
        assert_eq!(r.nodes, nodes);
        assert_eq!(r.stop_reason, StopReason::Nodes);
    }
    let mut zero = limits(0);
    let r = search(&game, zero, opts).unwrap();
    assert_eq!(r.score, Some(0));
    assert_eq!(r.completed_depth, 0);
    assert_eq!(r.nodes, 1);
    zero.max_time = Some(Duration::ZERO);
    assert_eq!(
        search(&game, zero, opts).unwrap().stop_reason,
        StopReason::Time
    );
    // Deterministic clock: allow exactly the visits of depth one, then expire.
    let mut calls = 0u64;
    let mut timed = limits(4);
    timed.max_time = Some(Duration::from_millis(1));
    let r = search_with_clock(&game, timed, opts, || {
        calls += 1;
        if calls <= depth_one.nodes {
            Duration::ZERO
        } else {
            Duration::from_millis(1)
        }
    })
    .unwrap();
    assert_eq!(r.completed_depth, 1);
    assert_eq!(r.best_move, depth_one.best_move);
    assert_eq!(r.score, depth_one.score);
    assert_eq!(r.stop_reason, StopReason::Time);
    let mut real = limits(64);
    real.max_time = Some(Duration::from_millis(3));
    let t = std::time::Instant::now();
    let r = search(&game, real, opts).unwrap();
    assert_eq!(r.stop_reason, StopReason::Time);
    assert!(game.is_legal(&r.best_move.unwrap()));
    assert!(t.elapsed() < Duration::from_secs(2)); // soft deadline: one atomic operation may finish
}

#[test]
fn game_move_limit_and_invalid_configurations_are_explicit() {
    let game = GameState::new().with_ply(100);
    let mut capped = limits(3);
    capped.max_game_ply = Some(100);
    let r = search(&game, capped, SearchOptions::default()).unwrap();
    assert_eq!(r.best_move, None);
    assert_eq!(r.score, Some(0));
    assert_eq!(r.stop_reason, StopReason::Terminal);
    let tiny = GameState::from_parts(kings(), [[0; 7]; 2], Color::Black).with_ply(99);
    capped.max_depth = 2;
    assert_eq!(
        search(&tiny, capped, SearchOptions::default())
            .unwrap()
            .score,
        Some(0)
    );
    assert!(search(&tiny, limits(65), SearchOptions::default()).is_err());
    let options = SearchOptions {
        table_capacity: 1_000_001,
        ..SearchOptions::default()
    };
    assert!(search(&tiny, limits(1), options).is_err());
    let r = search(&tiny, limits(1), basic()).unwrap();
    assert!(r.tt_hits == 0 && r.nodes > 1);
}

#[test]
fn optimizations_preserve_values_and_reduce_work_on_fixed_positions() {
    let game = GameState::from_parts(kings(), [[0; 7]; 2], Color::Black);
    let plain = search(&game, limits(4), basic()).unwrap();
    let mut tt = basic();
    tt.transposition_table = true;
    tt.table_capacity = 65_536;
    let cached = search(&game, limits(4), tt).unwrap();
    assert_eq!(cached.score, plain.score);
    assert!(cached.tt_hits > 0);
    assert!(cached.nodes < plain.nodes, "TT {cached:?}, plain {plain:?}");
    let mut iterative = tt;
    iterative.iterative_deepening = true;
    let deep = search(&game, limits(4), iterative).unwrap();
    assert_eq!(deep.score, plain.score);
    assert!(deep.nodes > deep.last_iteration_nodes);
    assert!(deep.last_iteration_nodes <= cached.nodes);
    let mut b = kings();
    b.set(
        Square::new(4, 3, 4),
        Some(Piece::new(Color::Black, PieceKind::Pawn)),
    );
    b.set(
        Square::new(4, 2, 4),
        Some(Piece::new(Color::White, PieceKind::Rook)),
    );
    let tactical = GameState::from_parts(b, [[0; 7]; 2], Color::Black);
    let plain = search(&tactical, limits(2), basic()).unwrap();
    let mut ordered = basic();
    ordered.move_ordering = true;
    let fast = search(&tactical, limits(2), ordered).unwrap();
    assert_eq!(fast.score, plain.score);
    assert!(
        fast.nodes < plain.nodes,
        "ordered {fast:?}, plain {plain:?}"
    );
    // A tiny/full table can affect hit rate, never the minimax result.
    for capacity in [0, 1, 4] {
        tt.table_capacity = capacity;
        assert_eq!(search(&game, limits(3), tt).unwrap().score, Some(0));
    }
}

#[test]
fn repetition_and_perpetual_check_are_respected_at_the_horizon_for_both_colors() {
    for checking in [false, true] {
        for checker in Color::ALL {
            let sq = |x, y, z| {
                if checker == Color::Black {
                    Square::new(x, y, z)
                } else {
                    Square::new(8 - x, 8 - y, 8 - z)
                }
            };
            let mut b = Board::empty();
            b.set(sq(8, 8, 0), Some(Piece::new(checker, PieceKind::King)));
            b.set(
                sq(0, 0, 0),
                Some(Piece::new(checker.opponent(), PieceKind::King)),
            );
            if checking {
                b.set(sq(0, 4, 8), Some(Piece::new(checker, PieceKind::Rook)));
            }
            let mut g = GameState::from_parts(b, [[0; 7]; 2], checker.opponent());
            let cycle = if checking {
                [
                    (sq(0, 0, 0), sq(1, 0, 0)),
                    (sq(0, 4, 8), sq(1, 4, 8)),
                    (sq(1, 0, 0), sq(0, 0, 0)),
                    (sq(1, 4, 8), sq(0, 4, 8)),
                ]
            } else {
                [
                    (sq(0, 0, 0), sq(1, 0, 0)),
                    (sq(8, 8, 0), sq(7, 8, 0)),
                    (sq(1, 0, 0), sq(0, 0, 0)),
                    (sq(7, 8, 0), sq(8, 8, 0)),
                ]
            };
            for i in 0..12 {
                if i == 11 {
                    let expected = oracle(&g, 1, None);
                    assert_eq!(
                        search(&g, limits(1), SearchOptions::default())
                            .unwrap()
                            .score,
                        Some(expected.0)
                    );
                }
                let (from, to) = cycle[i % 4];
                g = g
                    .apply_move(&Move::Normal {
                        from,
                        to,
                        promote: false,
                    })
                    .unwrap();
            }
            let r = search(&g, limits(0), SearchOptions::default()).unwrap();
            assert_eq!(r.score, Some(if checking { 1_000_000 } else { 0 }));
            assert_eq!(r.best_move, None);
            assert_eq!(r.stop_reason, StopReason::Terminal);
        }
    }
}

#[test]
fn exact_budget_boundaries_and_noniterative_abort_are_distinguished() {
    let game = GameState::from_parts(kings(), [[0; 7]; 2], Color::Black);
    let opts = SearchOptions::default();
    let one = search(&game, limits(1), opts).unwrap();
    let mut exact = limits(1);
    exact.max_nodes = Some(one.nodes);
    assert_eq!(
        search(&game, exact, opts).unwrap().stop_reason,
        StopReason::Depth
    );
    let mut partial = limits(4);
    partial.max_nodes = Some(2);
    let r = search(&game, partial, basic()).unwrap();
    assert_eq!(r.stop_reason, StopReason::Nodes);
    assert_eq!(r.completed_depth, 0);
    assert_eq!(r.last_iteration_nodes, 0);
    assert_eq!(r.score, None);
    assert_eq!(r.nodes, 2);
    assert!(game.is_legal(&r.best_move.unwrap()));
    let mut both = limits(64);
    both.max_nodes = Some(0);
    both.max_time = Some(Duration::ZERO);
    let largest = SearchOptions {
        table_capacity: 1_000_000,
        ..opts
    };
    assert_eq!(
        search(&game, both, largest).unwrap().stop_reason,
        StopReason::Time
    );
    let mut at_cap = limits(1);
    at_cap.max_game_ply = Some(1);
    let mate = mating_position(Color::Black, false);
    assert_eq!(search(&mate, at_cap, opts).unwrap().score, Some(1_000_000));
}

#[test]
fn full_width_oracle_includes_drops_and_promoted_material_for_both_sides() {
    for side in Color::ALL {
        let mut hands = [[0; 7]; 2];
        hands[side.index()][0] = 1;
        let game = GameState::from_parts(kings(), hands, side);
        assert!(
            game.legal_moves()
                .iter()
                .any(|m| matches!(m, Move::Drop { .. }))
        );
        let expected = oracle(&game, 2, None);
        assert_eq!(expected.0, 100); // pawn remains on board or in hand, never sacrificed
        let result = search(&game, limits(2), SearchOptions::default()).unwrap();
        assert_eq!(result.score, Some(100));
        assert!(expected.1.contains(&result.best_move.unwrap()));
    }
}

#[test]
fn alpha_beta_node_count_and_equal_score_tie_are_hand_counted() {
    let game = GameState::from_parts(kings(), [[0; 7]; 2], Color::Black);
    let moves = game.legal_moves();
    assert_eq!(moves.len(), 7);
    let one = search(&game, limits(1), basic()).unwrap();
    assert_eq!(one.nodes, 8); // root + seven king moves
    let two = search(&game, limits(2), basic()).unwrap();
    // First child reads all seven replies; the other six cut after their first reply.
    assert_eq!(two.nodes, 21); // 1 + 7 + 7 + 6, rather than exhaustive 1 + 7 + 49
    assert_eq!(two.best_move, moves.into_iter().min());
    assert_eq!(two.score, Some(0));
}
