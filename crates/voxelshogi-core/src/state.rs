//! Game state, legal move generation, move application and termination
//! (docs/RULESET.md §4–§6).

use crate::board::Board;
use crate::coord::{SIZE, Square};
use crate::movegen::{attacks, push_targets};
use crate::moves::Move;
use crate::piece::{Color, NUM_HAND_KINDS, Piece, PieceKind};
use crate::zobrist::hash_position;

/// Pieces in hand: `hands[color][hand_index]`, see [`PieceKind::HAND`].
pub type Hands = [[u8; NUM_HAND_KINDS]; 2];

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum WinReason {
    /// The loser had no legal move (詰み).
    Checkmate,
    Resignation,
    /// The loser gave check with every move of a fourfold repetition (連続王手の千日手).
    PerpetualCheck,
}

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum DrawReason {
    /// The same position occurred four times (千日手).
    Repetition,
}

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum GameResult {
    Win { winner: Color, reason: WinReason },
    Draw { reason: DrawReason },
}

#[derive(Clone, PartialEq, Eq, Debug)]
pub enum MoveError {
    /// The move is not legal in this position; the message says why.
    Illegal(String),
    /// The game has already ended.
    GameOver,
}

impl std::fmt::Display for MoveError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            MoveError::Illegal(why) => write!(f, "illegal move: {why}"),
            MoveError::GameOver => f.write_str("the game is over"),
        }
    }
}

impl std::error::Error for MoveError {}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
struct HistoryEntry {
    hash: u64,
    side: Color,
    in_check: bool,
}

/// A complete game position plus the history needed for repetition detection.
#[derive(Clone, Debug)]
pub struct GameState {
    board: Board,
    hands: Hands,
    side: Color,
    ply: u32,
    /// One entry per position since `from_parts`, the last one being the current position.
    history: Vec<HistoryEntry>,
    terminal: Option<GameResult>,
}

#[inline]
fn in_zone(color: Color, y: u8) -> bool {
    color.relative_rank(y) < 3
}

/// 行き所のない駒: a piece of this kind on rank `y` would have no move at all.
#[inline]
fn dead_end(kind: PieceKind, color: Color, y: u8) -> bool {
    let rr = color.relative_rank(y);
    match kind {
        PieceKind::Pawn | PieceKind::Lance => rr == 0,
        PieceKind::Knight => rr <= 1,
        _ => false,
    }
}

/// Whether any piece of `by` attacks `target`.
fn is_attacked(board: &Board, target: Square, by: Color) -> bool {
    board
        .pieces()
        .any(|(s, p)| p.color == by && attacks(board, s, target))
}

impl GameState {
    /// The standard initial position, Black to move.
    pub fn new() -> GameState {
        GameState::from_parts(Board::initial(), [[0; NUM_HAND_KINDS]; 2], Color::Black)
    }

    /// An arbitrary position (history starts here).
    pub fn from_parts(board: Board, hands: Hands, side: Color) -> GameState {
        let hash = hash_position(&board, &hands, side);
        let mut s = GameState {
            board,
            hands,
            side,
            ply: 0,
            history: Vec::new(),
            terminal: None,
        };
        let in_check = s.is_in_check(side);
        s.history.push(HistoryEntry {
            hash,
            side,
            in_check,
        });
        s
    }

    pub fn board(&self) -> &Board {
        &self.board
    }

    pub fn hands(&self) -> &Hands {
        &self.hands
    }

    pub fn hand_count(&self, color: Color, kind: PieceKind) -> u8 {
        kind.hand_index()
            .map_or(0, |i| self.hands[color.index()][i])
    }

    pub fn side_to_move(&self) -> Color {
        self.side
    }

    /// Number of moves played since `from_parts` / `new`.
    pub fn ply(&self) -> u32 {
        self.ply
    }

    /// Zobrist hash of the current position (board, hands, side to move).
    pub fn hash(&self) -> u64 {
        self.history.last().map_or(0, |e| e.hash)
    }

    pub fn is_in_check(&self, color: Color) -> bool {
        self.board
            .find_king(color)
            .is_some_and(|k| is_attacked(&self.board, k, color.opponent()))
    }

    /// Whether `mv` would leave the mover's king safe (the only dynamic legality test
    /// besides 打ち歩詰め). Uses a scratch board.
    fn king_safe_after(&self, scratch: &mut Board, mv: &Move) -> bool {
        let side = self.side;
        let (to, placed, from_piece) = match *mv {
            Move::Normal { from, to, promote } => {
                let p = self.board.get(from).expect("from occupied");
                let kind = if promote {
                    p.kind.promote().expect("promotable")
                } else {
                    p.kind
                };
                scratch.set(from, None);
                (to, Piece::new(side, kind), Some((from, p)))
            }
            Move::Drop { kind, to } => (to, Piece::new(side, kind), None),
        };
        let captured = scratch.get(to);
        scratch.set(to, Some(placed));
        let king = if placed.kind == PieceKind::King {
            Some(to)
        } else {
            scratch.find_king(side)
        };
        let safe = king.is_none_or(|k| !is_attacked(scratch, k, side.opponent()));
        scratch.set(to, captured);
        if let Some((from, p)) = from_piece {
            scratch.set(from, Some(p));
        }
        safe
    }

    /// 打ち歩詰め: does this pawn drop checkmate the opponent?
    fn is_pawn_drop_mate(&self, to: Square) -> bool {
        let opp = self.side.opponent();
        let gives_check = self
            .board
            .find_king(opp)
            .is_some_and(|k| to.offset(0, self.side.forward(), 0) == Some(k));
        if !gives_check {
            return false;
        }
        let next = self.make_unchecked(&Move::Drop {
            kind: PieceKind::Pawn,
            to,
        });
        !next.has_legal_move()
    }

    /// Visits legal moves until `f` returns `false`. Returns `false` if stopped early.
    fn for_each_legal(&self, f: &mut dyn FnMut(Move) -> bool) -> bool {
        if self.terminal.is_some() {
            return true;
        }
        let side = self.side;
        let in_check = self.is_in_check(side);
        let mut scratch = self.board.clone();
        let mut targets = Vec::with_capacity(256);
        for (from, piece) in self.board.pieces() {
            if piece.color != side {
                continue;
            }
            targets.clear();
            push_targets(&self.board, from, piece, &mut targets);
            for &to in &targets {
                let can_promote =
                    piece.kind.can_promote() && (in_zone(side, from.y()) || in_zone(side, to.y()));
                let must_promote = dead_end(piece.kind, side, to.y());
                for promote in [false, true] {
                    if (promote && !can_promote) || (!promote && must_promote) {
                        continue;
                    }
                    let mv = Move::Normal { from, to, promote };
                    if self.king_safe_after(&mut scratch, &mv) && !f(mv) {
                        return false;
                    }
                }
            }
        }
        let hand = self.hands[side.index()];
        if hand.iter().all(|&n| n == 0) {
            return true;
        }
        // 二歩: columns (x, z) that already hold an own unpromoted pawn.
        let own_pawn = Piece::new(side, PieceKind::Pawn);
        let mut pawn_column = [false; SIZE * SIZE];
        for (s, p) in self.board.pieces() {
            if p == own_pawn {
                pawn_column[s.z() as usize * SIZE + s.x() as usize] = true;
            }
        }
        for to in Square::all() {
            if !self.board.is_empty(to) {
                continue;
            }
            for (i, kind) in PieceKind::HAND.into_iter().enumerate() {
                if hand[i] == 0 || dead_end(kind, side, to.y()) {
                    continue;
                }
                if kind == PieceKind::Pawn && pawn_column[to.z() as usize * SIZE + to.x() as usize]
                {
                    continue;
                }
                let mv = Move::Drop { kind, to };
                // A drop cannot expose the own king; it only matters when already in check.
                if in_check && !self.king_safe_after(&mut scratch, &mv) {
                    continue;
                }
                if kind == PieceKind::Pawn && self.is_pawn_drop_mate(to) {
                    continue;
                }
                if !f(mv) {
                    return false;
                }
            }
        }
        true
    }

    /// All legal moves of the side to move (empty once the game is over).
    pub fn legal_moves(&self) -> Vec<Move> {
        let mut v = Vec::new();
        self.for_each_legal(&mut |m| {
            v.push(m);
            true
        });
        v
    }

    pub fn has_legal_move(&self) -> bool {
        !self.for_each_legal(&mut |_| false)
    }

    /// Checks a single move without generating the whole move list.
    pub fn check_move(&self, mv: &Move) -> Result<(), MoveError> {
        if self.terminal.is_some() {
            return Err(MoveError::GameOver);
        }
        let side = self.side;
        let illegal = |why: &str| Err(MoveError::Illegal(why.to_string()));
        match *mv {
            Move::Normal { from, to, promote } => {
                let Some(piece) = self.board.get(from) else {
                    return illegal("no piece on the source square");
                };
                if piece.color != side {
                    return illegal("the piece belongs to the opponent");
                }
                let mut targets = Vec::new();
                push_targets(&self.board, from, piece, &mut targets);
                if !targets.contains(&to) {
                    return illegal("the piece cannot move there");
                }
                if promote
                    && !(piece.kind.can_promote()
                        && (in_zone(side, from.y()) || in_zone(side, to.y())))
                {
                    return illegal("promotion is not allowed for this move");
                }
                if !promote && dead_end(piece.kind, side, to.y()) {
                    return illegal("the piece must promote (no further moves)");
                }
            }
            Move::Drop { kind, to } => {
                let Some(i) = kind.hand_index() else {
                    return illegal("this kind cannot be dropped");
                };
                if self.hands[side.index()][i] == 0 {
                    return illegal("the piece is not in hand");
                }
                if !self.board.is_empty(to) {
                    return illegal("the target square is occupied");
                }
                if dead_end(kind, side, to.y()) {
                    return illegal("the dropped piece would have no moves");
                }
                if kind == PieceKind::Pawn
                    && (0..SIZE as u8).any(|y| {
                        self.board.get(Square::new(to.x(), y, to.z()))
                            == Some(Piece::new(side, PieceKind::Pawn))
                    })
                {
                    return illegal("二歩 (two pawns in the same layer and file)");
                }
            }
        }
        let mut scratch = self.board.clone();
        if !self.king_safe_after(&mut scratch, mv) {
            return illegal("the move leaves the own king in check");
        }
        if let Move::Drop {
            kind: PieceKind::Pawn,
            to,
        } = *mv
        {
            if self.is_pawn_drop_mate(to) {
                return illegal("打ち歩詰め (pawn-drop checkmate)");
            }
        }
        Ok(())
    }

    pub fn is_legal(&self, mv: &Move) -> bool {
        self.check_move(mv).is_ok()
    }

    /// Plays a move assumed to be legal and returns the next state.
    fn make_unchecked(&self, mv: &Move) -> GameState {
        let side = self.side;
        let mut next = self.clone();
        match *mv {
            Move::Normal { from, to, promote } => {
                let p = next.board.get(from).expect("from occupied");
                if let Some(captured) = next.board.get(to) {
                    let i = captured
                        .kind
                        .unpromote()
                        .hand_index()
                        .expect("kings are never captured");
                    next.hands[side.index()][i] += 1;
                }
                let kind = if promote {
                    p.kind.promote().expect("promotable")
                } else {
                    p.kind
                };
                next.board.set(from, None);
                next.board.set(to, Some(Piece::new(side, kind)));
            }
            Move::Drop { kind, to } => {
                next.hands[side.index()][kind.hand_index().expect("droppable")] -= 1;
                next.board.set(to, Some(Piece::new(side, kind)));
            }
        }
        next.side = side.opponent();
        next.ply += 1;
        let hash = hash_position(&next.board, &next.hands, next.side);
        let in_check = next.is_in_check(next.side);
        next.history.push(HistoryEntry {
            hash,
            side: next.side,
            in_check,
        });
        next.terminal = next.repetition_result();
        next
    }

    /// 千日手 / 連続王手の千日手 on the fourth occurrence of the current position.
    fn repetition_result(&self) -> Option<GameResult> {
        let cur = *self.history.last()?;
        let occurrences: Vec<usize> = self
            .history
            .iter()
            .enumerate()
            .filter(|(_, e)| e.hash == cur.hash)
            .map(|(i, _)| i)
            .collect();
        if occurrences.len() < 4 {
            return None;
        }
        // Within the repetition span (first occurrence, now], a side gave check with every
        // move iff every position with the *other* side to move was a check.
        let span = &self.history[occurrences[0] + 1..];
        let all_checks_by = |checker: Color| {
            span.iter()
                .filter(|e| e.side == checker.opponent())
                .all(|e| e.in_check)
                && span.iter().any(|e| e.side == checker.opponent())
        };
        match (all_checks_by(Color::Black), all_checks_by(Color::White)) {
            (true, false) => Some(GameResult::Win {
                winner: Color::White,
                reason: WinReason::PerpetualCheck,
            }),
            (false, true) => Some(GameResult::Win {
                winner: Color::Black,
                reason: WinReason::PerpetualCheck,
            }),
            _ => Some(GameResult::Draw {
                reason: DrawReason::Repetition,
            }),
        }
    }

    /// Returns the state after `mv`, or an error if it is illegal. `self` is unchanged.
    pub fn apply_move(&self, mv: &Move) -> Result<GameState, MoveError> {
        self.check_move(mv)?;
        Ok(self.make_unchecked(mv))
    }

    /// In-place variant of [`GameState::apply_move`].
    pub fn play(&mut self, mv: &Move) -> Result<(), MoveError> {
        *self = self.apply_move(mv)?;
        Ok(())
    }

    /// The side to move resigns.
    pub fn resign(&mut self) {
        if self.terminal.is_none() {
            self.terminal = Some(GameResult::Win {
                winner: self.side.opponent(),
                reason: WinReason::Resignation,
            });
        }
    }

    /// The game result, or `None` while the game continues.
    pub fn result(&self) -> Option<GameResult> {
        if let Some(r) = self.terminal {
            return Some(r);
        }
        if !self.has_legal_move() {
            return Some(GameResult::Win {
                winner: self.side.opponent(),
                reason: WinReason::Checkmate,
            });
        }
        None
    }
}

impl Default for GameState {
    fn default() -> Self {
        GameState::new()
    }
}
