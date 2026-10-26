//! Experimental nine-king capture rules. Standard shogi remains in `state`.
use crate::{Board, Color, Hands, Move, Piece, PieceKind, Square, movegen, zobrist};

#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CaptureRule {
    FirstFive,
    AllKings,
    ScoreLimit,
}
impl CaptureRule {
    pub fn id(self) -> &'static str {
        match self {
            Self::FirstFive => "voxelshogi-nine-kings-first5-v0",
            Self::AllKings => "voxelshogi-nine-kings-all-v0",
            Self::ScoreLimit => "voxelshogi-nine-kings-score-v0",
        }
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Reason {
    Target,
    ScoreLimit,
    MoveLimit,
    Repetition,
    NoMoves,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Outcome {
    pub winner: Option<Color>,
    pub reason: Reason,
}
#[derive(Clone, Debug)]
pub struct CaptureGame {
    board: Board,
    hands: Hands,
    side: Color,
    rule: CaptureRule,
    ply: u32,
    limit: u32,
    captured: [u8; 2],
    history: Vec<u64>,
}
fn dead(kind: PieceKind, side: Color, y: u8) -> bool {
    match kind {
        PieceKind::Pawn | PieceKind::Lance => side.relative_rank(y) == 0,
        PieceKind::Knight => side.relative_rank(y) <= 1,
        _ => false,
    }
}
impl CaptureGame {
    pub fn new(rule: CaptureRule, limit: u32) -> Result<Self, String> {
        let standard = Board::initial();
        let mut board = Board::empty();
        for (s, p) in standard.pieces().filter(|(s, _)| s.z() == 4) {
            for z in 0..9 {
                board.set(Square::new(s.x(), s.y(), z), Some(p));
            }
        }
        Self::from_parts(board, [[0; 7]; 2], Color::Black, rule, limit)
    }
    /// Fixture constructor; histories always start at ply zero. Missing kings count as captured.
    pub fn from_parts(
        board: Board,
        hands: Hands,
        side: Color,
        rule: CaptureRule,
        limit: u32,
    ) -> Result<Self, String> {
        if limit == 0 || limit % 2 != 0 || limit > 2000 {
            return Err("limit must be even and in 2..=2000".into());
        }
        let mut kings = [0u16; 2];
        let mut total = [0u32; 7];
        let mut columns = std::collections::HashSet::new();
        for (s, p) in board.pieces() {
            if p.kind == PieceKind::King {
                kings[p.color.index()] += 1;
            } else {
                total[p.kind.unpromote().hand_index().unwrap()] += 1;
            }
            if dead(p.kind, p.color, s.y()) {
                return Err("immobile piece".into());
            }
            if p.kind == PieceKind::Pawn && !columns.insert((p.color, s.x(), s.z())) {
                return Err("two pawns in a column".into());
            }
        }
        for h in hands {
            for (i, n) in h.into_iter().enumerate() {
                total[i] += u32::from(n);
            }
        }
        if kings.iter().any(|&n| n > 9)
            || total
                .iter()
                .zip([162, 36, 36, 36, 36, 18, 18])
                .any(|(&n, max)| n > max)
        {
            return Err("piece inventory exceeds the nine-layer set".into());
        }
        let hash = zobrist::hash_position(&board, &hands, side);
        Ok(Self {
            board,
            hands,
            side,
            rule,
            ply: 0,
            limit,
            captured: [(9 - kings[1]) as u8, (9 - kings[0]) as u8],
            history: vec![hash],
        })
    }
    pub fn board(&self) -> &Board {
        &self.board
    }
    pub fn hands(&self) -> &Hands {
        &self.hands
    }
    pub fn side(&self) -> Color {
        self.side
    }
    pub fn ply(&self) -> u32 {
        self.ply
    }
    pub fn hash(&self) -> u64 {
        *self.history.last().unwrap()
    }
    pub fn captured(&self) -> [u8; 2] {
        self.captured
    }
    pub fn rule(&self) -> CaptureRule {
        self.rule
    }
    fn terminal(&self) -> Option<Outcome> {
        let target = match self.rule {
            CaptureRule::FirstFive => 5,
            CaptureRule::AllKings => 9,
            CaptureRule::ScoreLimit => 10,
        };
        for color in Color::ALL {
            if self.captured[color.index()] >= target {
                return Some(Outcome {
                    winner: Some(color),
                    reason: Reason::Target,
                });
            }
        }
        if self.history.iter().filter(|&&h| h == self.hash()).count() >= 4 {
            return Some(Outcome {
                winner: None,
                reason: Reason::Repetition,
            });
        }
        if self.ply >= self.limit {
            return Some(if self.rule == CaptureRule::ScoreLimit {
                Outcome {
                    winner: match self.captured[0].cmp(&self.captured[1]) {
                        std::cmp::Ordering::Greater => Some(Color::Black),
                        std::cmp::Ordering::Less => Some(Color::White),
                        _ => None,
                    },
                    reason: Reason::ScoreLimit,
                }
            } else {
                Outcome {
                    winner: None,
                    reason: Reason::MoveLimit,
                }
            });
        }
        None
    }
    fn visit(&self, f: &mut dyn FnMut(Move) -> bool) -> bool {
        if self.terminal().is_some() {
            return true;
        }
        let side = self.side;
        for (from, p) in self.board.pieces().filter(|(_, p)| p.color == side) {
            for to in movegen::targets(&self.board, from) {
                let can = p.kind.can_promote()
                    && (side.relative_rank(from.y()) < 3 || side.relative_rank(to.y()) < 3);
                for promote in [false, true] {
                    if (promote && !can) || (!promote && dead(p.kind, side, to.y())) {
                        continue;
                    }
                    if !f(Move::Normal { from, to, promote }) {
                        return false;
                    }
                }
            }
        }
        let hand = self.hands[side.index()];
        if hand == [0; 7] {
            return true;
        }
        let mut columns = [false; 81];
        for (s, p) in self.board.pieces() {
            if p == Piece::new(side, PieceKind::Pawn) {
                columns[s.z() as usize * 9 + s.x() as usize] = true;
            }
        }
        for to in Square::all().filter(|&s| self.board.is_empty(s)) {
            for (i, kind) in PieceKind::HAND.into_iter().enumerate() {
                if hand[i] == 0
                    || dead(kind, side, to.y())
                    || (kind == PieceKind::Pawn && columns[to.z() as usize * 9 + to.x() as usize])
                {
                    continue;
                }
                if !f(Move::Drop { kind, to }) {
                    return false;
                }
            }
        }
        true
    }
    pub fn legal_moves(&self) -> Vec<Move> {
        let mut v = Vec::new();
        self.visit(&mut |m| {
            v.push(m);
            true
        });
        v
    }
    pub fn outcome(&self) -> Option<Outcome> {
        self.terminal().or_else(|| {
            if self.visit(&mut |_| false) {
                Some(Outcome {
                    winner: None,
                    reason: Reason::NoMoves,
                })
            } else {
                None
            }
        })
    }
    pub fn after_move(&self, mv: &Move) -> Result<Self, String> {
        let mut found = false;
        self.visit(&mut |m| {
            if m == *mv {
                found = true;
                false
            } else {
                true
            }
        });
        if !found {
            return Err("illegal move or finished game".into());
        }
        Ok(self.after_generated(mv))
    }
    /// Only called with a move generated for this exact state inside the experiment search.
    pub(crate) fn after_generated(&self, mv: &Move) -> Self {
        let mut next = self.clone();
        match *mv {
            Move::Normal { from, to, promote } => {
                let p = self.board.get(from).unwrap();
                if let Some(c) = self.board.get(to) {
                    if c.kind == PieceKind::King {
                        next.captured[self.side.index()] += 1;
                    } else {
                        next.hands[self.side.index()][c.kind.unpromote().hand_index().unwrap()] +=
                            1;
                    }
                }
                next.board.set(from, None);
                next.board.set(
                    to,
                    Some(Piece::new(
                        self.side,
                        if promote {
                            p.kind.promote().unwrap()
                        } else {
                            p.kind
                        },
                    )),
                );
            }
            Move::Drop { kind, to } => {
                next.hands[self.side.index()][kind.hand_index().unwrap()] -= 1;
                next.board.set(to, Some(Piece::new(self.side, kind)));
            }
        }
        next.side = self.side.opponent();
        next.ply += 1;
        next.history
            .push(zobrist::hash_position(&next.board, &next.hands, next.side));
        next
    }
}
