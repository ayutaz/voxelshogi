//! Full-width, deterministic standard-rules CPU search (M1).
use crate::{Color, GameState, PieceKind};

/// Fixed material values in pawn=100 units. Kings are represented by terminal results.
pub fn piece_value(kind: PieceKind) -> i32 {
    [
        100, 300, 320, 450, 550, 800, 1000, 0, 550, 550, 550, 550, 1100, 1300,
    ][kind.index()]
}

/// Static material, including unpromoted pieces in hand, from the side to move.
/// This is not a terminal score or a probability of winning.
pub fn evaluate(game: &GameState) -> i32 {
    let side = game.side_to_move();
    let mut value = 0;
    for (_, piece) in game.board().pieces() {
        value += if piece.color == side {
            piece_value(piece.kind)
        } else {
            -piece_value(piece.kind)
        };
    }
    for color in Color::ALL {
        for (index, kind) in PieceKind::HAND.into_iter().enumerate() {
            let material = i32::from(game.hands()[color.index()][index]) * piece_value(kind);
            value += if color == side { material } else { -material };
        }
    }
    value
}

use crate::{GameResult, Move};
use std::{
    collections::HashMap,
    time::{Duration, Instant},
};

pub const MATE_SCORE: i32 = 1_000_000;
const INFINITY: i32 = 2_000_000;

/// Search budgets. A node is one entered position, including roots, leaves and TT hits.
/// Time is a soft deadline checked before each node; one move generation may finish late.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SearchLimits {
    pub max_depth: u8,
    pub max_nodes: Option<u64>,
    pub max_time: Option<Duration>,
    /// Optional absolute game ply cap. Natural outcomes take precedence over this draw.
    pub max_game_ply: Option<u32>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SearchOptions {
    pub iterative_deepening: bool,
    pub move_ordering: bool,
    pub transposition_table: bool,
    /// Maximum entries, 0 disables storage, at most one million. No random eviction.
    pub table_capacity: usize,
}
impl Default for SearchOptions {
    fn default() -> Self {
        Self {
            iterative_deepening: true,
            move_ordering: true,
            transposition_table: true,
            table_capacity: 65_536,
        }
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StopReason {
    Depth,
    Nodes,
    Time,
    Terminal,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SearchResult {
    pub best_move: Option<Move>,
    /// None if no iteration completed; the fallback move is not claimed to be best.
    pub score: Option<i32>,
    pub completed_depth: u8,
    /// Total across completed and interrupted iterations.
    pub nodes: u64,
    pub last_iteration_nodes: u64,
    pub tt_hits: u64,
    pub stop_reason: StopReason,
}

/// Deterministic for fixed depth/node budgets, position+history and options.
/// Runtime-only limits can complete different depths under different machine loads.
/// Input positions must satisfy GameState's standard-rules contract.
pub fn search(
    game: &GameState,
    limits: SearchLimits,
    options: SearchOptions,
) -> Result<SearchResult, &'static str> {
    let start = limits.max_time.map(|_| Instant::now());
    search_with_clock(game, limits, options, || {
        start.as_ref().map_or(Duration::ZERO, Instant::elapsed)
    })
}

/// Clock-injected variant for WASM adapters and deterministic deadline tests.
/// `elapsed` must report monotonically increasing elapsed time since this call began.
pub fn search_with_clock(
    game: &GameState,
    limits: SearchLimits,
    options: SearchOptions,
    elapsed: impl FnMut() -> Duration,
) -> Result<SearchResult, &'static str> {
    if limits.max_depth > 64 {
        return Err("max_depth must be 0..=64");
    }
    if options.table_capacity > 1_000_000 {
        return Err("table_capacity must be <= 1000000");
    }
    let mut moves = game.legal_moves();
    moves.sort();
    let mut result = SearchResult {
        best_move: moves.first().copied(),
        score: None,
        completed_depth: 0,
        nodes: 0,
        last_iteration_nodes: 0,
        tt_hits: 0,
        stop_reason: StopReason::Depth,
    };
    if let Some(score) = terminal(game, moves.is_empty(), limits.max_game_ply) {
        result.best_move = None;
        result.score = Some(score);
        result.stop_reason = StopReason::Terminal;
        return Ok(result);
    }
    let mut engine = Engine {
        limits,
        options,
        elapsed,
        table: HashMap::new(),
        nodes: 0,
        hits: 0,
    };
    let first = if options.iterative_deepening && limits.max_depth > 0 {
        1
    } else {
        limits.max_depth
    };
    for depth in first..=limits.max_depth {
        let before = engine.nodes;
        match engine.negamax(
            game,
            depth,
            -INFINITY,
            INFINITY,
            Some(moves.clone()),
            result.score.and(result.best_move),
        ) {
            Ok((score, best)) => {
                result.score = Some(score);
                result.best_move = best.or(result.best_move);
                result.completed_depth = depth;
                result.last_iteration_nodes = engine.nodes - before;
            }
            Err(reason) => {
                result.stop_reason = reason;
                break;
            }
        }
    }
    result.nodes = engine.nodes;
    result.tt_hits = engine.hits;
    Ok(result)
}

fn outcome_score(result: GameResult, side: Color) -> i32 {
    match result {
        GameResult::Draw { .. } => 0,
        GameResult::Win { winner, .. } => {
            if winner == side {
                MATE_SCORE
            } else {
                -MATE_SCORE
            }
        }
    }
}
fn terminal(game: &GameState, no_moves: bool, limit: Option<u32>) -> Option<i32> {
    if let Some(result) = game.recorded_result() {
        return Some(outcome_score(result, game.side_to_move()));
    }
    if no_moves {
        return Some(-MATE_SCORE);
    }
    if limit.is_some_and(|ply| game.ply() >= ply) {
        return Some(0);
    }
    None
}

// Each call owns a fresh table for the standard rules and fixed evaluation. Depth
// must match exactly (a deeper horizon can change material minimax). Absolute game
// limits use remaining plies. History-sensitive nodes never reuse cached scores.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
struct Key {
    hash: u64,
    depth: u8,
    remaining: Option<u32>,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Bound {
    Exact,
    Lower,
    Upper,
}
#[derive(Clone, Copy, Debug)]
struct Entry {
    score: i32,
    best: Option<Move>,
    bound: Bound,
}
struct Engine<F> {
    limits: SearchLimits,
    options: SearchOptions,
    elapsed: F,
    table: HashMap<Key, Entry>,
    nodes: u64,
    hits: u64,
}
impl<F: FnMut() -> Duration> Engine<F> {
    fn visit(&mut self) -> Result<(), StopReason> {
        if self
            .limits
            .max_time
            .is_some_and(|time| (self.elapsed)() >= time)
        {
            return Err(StopReason::Time);
        }
        if self
            .limits
            .max_nodes
            .is_some_and(|nodes| self.nodes >= nodes)
        {
            return Err(StopReason::Nodes);
        }
        self.nodes += 1;
        Ok(())
    }
    fn key(&self, game: &GameState, depth: u8) -> Option<Key> {
        if !self.options.transposition_table || game.repetition_possible_within(depth) {
            return None;
        }
        Some(Key {
            hash: game.hash(),
            depth,
            remaining: self
                .limits
                .max_game_ply
                .map(|limit| limit.saturating_sub(game.ply())),
        })
    }
    fn store(&mut self, key: Option<Key>, entry: Entry) {
        if let Some(key) = key {
            if self.table.len() < self.options.table_capacity || self.table.contains_key(&key) {
                self.table.insert(key, entry);
            }
        }
    }
    fn negamax(
        &mut self,
        game: &GameState,
        depth: u8,
        mut alpha: i32,
        beta: i32,
        root_moves: Option<Vec<Move>>,
        preferred: Option<Move>,
    ) -> Result<(i32, Option<Move>), StopReason> {
        self.visit()?;
        if let Some(result) = game.recorded_result() {
            return Ok((outcome_score(result, game.side_to_move()), None));
        }
        let key = self.key(game, depth);
        let cached = key.and_then(|key| self.table.get(&key)).copied();
        if let Some(entry) = cached {
            if entry.bound == Bound::Exact
                || (entry.bound == Bound::Lower && entry.score >= beta)
                || (entry.bound == Bound::Upper && entry.score <= alpha)
            {
                self.hits += 1;
                return Ok((entry.score, entry.best));
            }
        }
        // At the horizon only existence is needed: stop after the first legal move.
        // Mate/repetition still take precedence over material and game-ply caps.
        if depth == 0 {
            let score = terminal(game, !game.has_legal_move(), self.limits.max_game_ply)
                .unwrap_or_else(|| evaluate(game));
            self.store(
                key,
                Entry {
                    score,
                    best: None,
                    bound: Bound::Exact,
                },
            );
            return Ok((score, None));
        }
        let mut moves = root_moves.unwrap_or_else(|| game.legal_moves());
        let leaf = terminal(game, moves.is_empty(), self.limits.max_game_ply);
        if let Some(score) = leaf {
            self.store(
                key,
                Entry {
                    score,
                    best: None,
                    bound: Bound::Exact,
                },
            );
            return Ok((score, None));
        }
        order_moves(
            game,
            &mut moves,
            self.options.move_ordering,
            preferred.or(cached.and_then(|e| e.best)),
        );
        let original_alpha = alpha;
        let mut best = -INFINITY;
        let mut best_move = None;
        for mv in moves {
            let child = game.after_generated(&mv);
            let score = -self
                .negamax(&child, depth - 1, -beta, -alpha, None, None)?
                .0;
            if score > best {
                best = score;
                best_move = Some(mv);
            }
            alpha = alpha.max(score);
            if alpha >= beta {
                break;
            }
        }
        let bound = if best <= original_alpha {
            Bound::Upper
        } else if best >= beta {
            Bound::Lower
        } else {
            Bound::Exact
        };
        self.store(
            key,
            Entry {
                score: best,
                best: best_move,
                bound,
            },
        );
        Ok((best, best_move))
    }
}
fn order_moves(game: &GameState, moves: &mut [Move], enabled: bool, preferred: Option<Move>) {
    // Explicit total order: Move's derived ordering, with captures/promotions first.
    // No move is dropped; heuristics change only the order.
    moves.sort_by_cached_key(|mv| {
        let priority = if enabled {
            let capture = game
                .board()
                .get(mv.to())
                .map_or(0, |p| piece_value(p.kind) + piece_value(p.kind.unpromote()));
            let promotion = match *mv {
                Move::Normal {
                    from,
                    promote: true,
                    ..
                } => {
                    let kind = game.board().get(from).expect("generated source").kind;
                    piece_value(kind.promote().expect("promotable")) - piece_value(kind)
                }
                _ => 0,
            };
            (Some(*mv) == preferred, capture + promotion)
        } else {
            (false, 0)
        };
        (std::cmp::Reverse(priority), *mv)
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Board, Piece, Square};
    fn position() -> GameState {
        let mut b = Board::empty();
        for (sq, color, kind) in [
            (Square::new(8, 8, 8), Color::Black, PieceKind::King),
            (Square::new(0, 0, 0), Color::White, PieceKind::King),
            (Square::new(4, 3, 4), Color::Black, PieceKind::Pawn),
            (Square::new(4, 2, 4), Color::White, PieceKind::Rook),
        ] {
            b.set(sq, Some(Piece::new(color, kind)));
        }
        GameState::from_parts(b, [[0; 7]; 2], Color::Black)
    }
    fn engine(nodes: Option<u64>, capacity: usize) -> Engine<impl FnMut() -> Duration> {
        Engine {
            limits: SearchLimits {
                max_depth: 4,
                max_nodes: nodes,
                max_time: None,
                max_game_ply: None,
            },
            options: SearchOptions {
                iterative_deepening: false,
                move_ordering: true,
                transposition_table: true,
                table_capacity: capacity,
            },
            elapsed: || Duration::ZERO,
            table: HashMap::new(),
            nodes: 0,
            hits: 0,
        }
    }
    #[test]
    fn cache_bounds_are_not_mistaken_for_exact_scores() {
        let game = position();
        for (bound, score) in [(Bound::Lower, 1000), (Bound::Upper, 2000)] {
            let mut e = engine(None, 10_000);
            let key = e.key(&game, 2).unwrap();
            e.table.insert(
                key,
                Entry {
                    score,
                    best: None,
                    bound,
                },
            );
            assert_eq!(
                e.negamax(&game, 2, -INFINITY, INFINITY, None, None)
                    .unwrap()
                    .0,
                1550
            );
            assert!(e.nodes > 1);
            assert_eq!(e.table[&key].bound, Bound::Exact);
        }
        for (bound, score, alpha, beta) in [
            (Bound::Lower, 1000, 0, 1000),
            (Bound::Upper, 2000, 2000, 3000),
            (Bound::Exact, 1550, -INFINITY, INFINITY),
        ] {
            let mut e = engine(None, 4);
            let key = e.key(&game, 2).unwrap();
            e.table.insert(
                key,
                Entry {
                    score,
                    best: None,
                    bound,
                },
            );
            assert_eq!(
                e.negamax(&game, 2, alpha, beta, None, None).unwrap().0,
                score
            );
            assert_eq!(e.nodes, 1);
            assert_eq!(e.hits, 1);
        }
        let mut e = engine(None, 10_000);
        let key = e.key(&game, 2).unwrap();
        let lower = e.negamax(&game, 2, 0, 1000, None, None).unwrap().0;
        assert!(lower >= 1000);
        assert_eq!(e.table[&key].bound, Bound::Lower);
        let mut e = engine(None, 10_000);
        let upper = e.negamax(&game, 2, 2000, 3000, None, None).unwrap().0;
        assert!(upper <= 2000);
        assert_eq!(e.table[&key].bound, Bound::Upper);
    }
    #[test]
    fn cache_depth_remaining_plies_capacity_and_interrupted_nodes_are_isolated() {
        let game = position();
        let mut e = engine(None, 1);
        let key = e.key(&game, 2).unwrap();
        assert_ne!(e.key(&game, 1), Some(key));
        e.limits.max_game_ply = Some(20);
        let limited = e.key(&game, 2).unwrap();
        assert_ne!(limited, key);
        assert_eq!(limited.remaining, Some(20));
        assert_eq!(
            e.key(&game.clone().with_ply(19), 2).unwrap().remaining,
            Some(1)
        );
        assert_eq!(
            e.key(&game.clone().with_ply(21), 2).unwrap().remaining,
            Some(0)
        );
        for key in [key, limited] {
            e.store(
                Some(key),
                Entry {
                    score: 0,
                    best: None,
                    bound: Bound::Exact,
                },
            );
        }
        assert_eq!(e.table.len(), 1);
        e.store(
            Some(key),
            Entry {
                score: 10,
                best: None,
                bound: Bound::Lower,
            },
        );
        assert_eq!(e.table[&key].score, 10);
        let mut e = engine(Some(1), 100);
        assert_eq!(
            e.negamax(&game, 2, -INFINITY, INFINITY, None, None),
            Err(StopReason::Nodes)
        );
        assert!(e.table.is_empty());
        let mut e = engine(None, 0);
        e.negamax(&game, 1, -INFINITY, INFINITY, None, None)
            .unwrap();
        assert!(e.table.is_empty());
    }
    #[test]
    fn history_sensitive_positions_never_probe_position_only_scores() {
        let mut board = Board::empty();
        board.set(
            Square::new(8, 8, 8),
            Some(Piece::new(Color::Black, PieceKind::King)),
        );
        board.set(
            Square::new(0, 0, 0),
            Some(Piece::new(Color::White, PieceKind::King)),
        );
        let mut game = GameState::from_parts(board, [[0; 7]; 2], Color::Black);
        let cycle = [
            (Square::new(8, 8, 8), Square::new(7, 8, 8)),
            (Square::new(0, 0, 0), Square::new(1, 0, 0)),
            (Square::new(7, 8, 8), Square::new(8, 8, 8)),
            (Square::new(1, 0, 0), Square::new(0, 0, 0)),
        ];
        for n in 0..8 {
            let (from, to) = cycle[n % 4];
            game = game
                .apply_move(&Move::Normal {
                    from,
                    to,
                    promote: false,
                })
                .unwrap();
        }
        let fresh = GameState::from_parts(game.board().clone(), *game.hands(), game.side_to_move())
            .with_ply(game.ply());
        assert_eq!(fresh.hash(), game.hash());
        assert!(!fresh.repetition_possible_within(2));
        assert!(fresh.repetition_possible_within(3));
        assert!(!game.repetition_possible_within(0));
        assert!(game.repetition_possible_within(1));
        let mut e = engine(None, 1000);
        let key = e.key(&fresh, 1).unwrap();
        assert_eq!(e.key(&game, 1), None);
        // A score from another history must not be accepted, even with the same board/ply.
        e.table.insert(
            key,
            Entry {
                score: 1230,
                best: None,
                bound: Bound::Exact,
            },
        );
        assert_eq!(
            e.negamax(&game, 1, -INFINITY, INFINITY, None, None)
                .unwrap()
                .0,
            0
        );
        e.options.transposition_table = false;
        assert_eq!(e.key(&fresh, 1), None);
    }

    #[test]
    fn move_ordering_prioritizes_capture_promotion_and_explicit_preference_without_dropping_moves()
    {
        let game = position();
        let capture = Move::Normal {
            from: Square::new(4, 3, 4),
            to: Square::new(4, 2, 4),
            promote: false,
        };
        let promote = Move::Normal {
            from: Square::new(4, 3, 4),
            to: Square::new(4, 2, 4),
            promote: true,
        };
        let quiet = Move::Normal {
            from: Square::new(8, 8, 8),
            to: Square::new(7, 8, 8),
            promote: false,
        };
        for mv in [capture, promote, quiet] {
            assert!(game.is_legal(&mv));
        }
        let mut moves = vec![quiet, capture, promote];
        order_moves(&game, &mut moves, true, None);
        assert_eq!(moves, [promote, capture, quiet]);
        order_moves(&game, &mut moves, true, Some(quiet));
        assert_eq!(moves, [quiet, promote, capture]);
        order_moves(&game, &mut moves, false, Some(quiet));
        assert_eq!(moves, [capture, promote, quiet]);
    }
}
