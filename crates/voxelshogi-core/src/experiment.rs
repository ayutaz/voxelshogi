//! Deterministic, width-limited research agent and verified experiment records.
//! This is deliberately separate from the forthcoming full M1 search engine.
use crate::{
    Color, Move, PieceKind,
    capture::{CaptureGame, CaptureRule, Outcome},
    notation::parse_move,
};

#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SearchConfig {
    pub depth: u8,
    pub width: usize,
}
impl SearchConfig {
    pub fn validate(self) -> Result<(), String> {
        if !(1..=3).contains(&self.depth) || !(1..=64).contains(&self.width) {
            return Err("search requires depth 1..=3 and width 1..=64".into());
        }
        Ok(())
    }
}
fn mix(mut x: u64) -> u64 {
    x = x.wrapping_add(0x9e3779b97f4a7c15);
    x = (x ^ (x >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
    x = (x ^ (x >> 27)).wrapping_mul(0x94d049bb133111eb);
    x ^ (x >> 31)
}
fn value(k: PieceKind) -> i32 {
    [
        100, 300, 320, 450, 550, 800, 1000, 0, 550, 550, 550, 550, 1100, 1300,
    ][k.index()]
}
/// Black's perspective. King capture dominates material; advancement breaks quiet plateaus.
pub fn evaluation(g: &CaptureGame) -> i32 {
    let mut score = 25_000 * (i32::from(g.captured()[0]) - i32::from(g.captured()[1]));
    score += material(g);
    score
}
trait Position: Clone {
    fn board(&self) -> &crate::Board;
    fn hands(&self) -> &crate::Hands;
    fn side(&self) -> Color;
    fn hash(&self) -> u64;
    fn legal_moves(&self) -> Vec<Move>;
    fn after_generated(&self, m: &Move) -> Self;
    fn terminal_score(&self) -> Option<i32>;
    fn evaluate(&self) -> i32;
}
impl Position for CaptureGame {
    fn board(&self) -> &crate::Board {
        self.board()
    }
    fn hands(&self) -> &crate::Hands {
        self.hands()
    }
    fn side(&self) -> Color {
        self.side()
    }
    fn hash(&self) -> u64 {
        self.hash()
    }
    fn legal_moves(&self) -> Vec<Move> {
        self.legal_moves()
    }
    fn after_generated(&self, m: &Move) -> Self {
        self.after_generated(m)
    }
    fn terminal_score(&self) -> Option<i32> {
        self.outcome().map(|o| {
            o.winner.map_or(0, |w| {
                if w == self.side() {
                    1_000_000
                } else {
                    -1_000_000
                }
            })
        })
    }
    fn evaluate(&self) -> i32 {
        evaluation(self)
    }
}
#[derive(Clone)]
struct StandardPosition {
    game: crate::GameState,
    limit: u32,
}
impl Position for StandardPosition {
    fn board(&self) -> &crate::Board {
        self.game.board()
    }
    fn hands(&self) -> &crate::Hands {
        self.game.hands()
    }
    fn side(&self) -> Color {
        self.game.side_to_move()
    }
    fn hash(&self) -> u64 {
        self.game.hash()
    }
    fn legal_moves(&self) -> Vec<Move> {
        self.game.legal_moves()
    }
    fn after_generated(&self, m: &Move) -> Self {
        Self {
            game: self.game.apply_move(m).expect("generated legal move"),
            limit: self.limit,
        }
    }
    fn terminal_score(&self) -> Option<i32> {
        match self.game.result() {
            Some(crate::GameResult::Win { winner, .. }) => Some(if winner == self.side() {
                1_000_000
            } else {
                -1_000_000
            }),
            Some(crate::GameResult::Draw { .. }) => Some(0),
            None if self.game.ply() >= self.limit => Some(0),
            None => None,
        }
    }
    fn evaluate(&self) -> i32 {
        material(self)
    }
}
fn material(g: &impl Position) -> i32 {
    let mut score = 0;
    for (s, p) in g.board().pieces() {
        score += (if p.color == Color::Black { 1 } else { -1 })
            * (value(p.kind) + i32::from(8 - p.color.relative_rank(s.y())) * 3);
    }
    for c in Color::ALL {
        for (i, n) in g.hands()[c.index()].iter().enumerate() {
            score += (if c == Color::Black { 1 } else { -1 })
                * i32::from(*n)
                * value(PieceKind::HAND[i]);
        }
    }
    score
}
fn order(g: &impl Position, m: Move, seed: u64) -> (i32, u64) {
    let (rank, key) = match m {
        Move::Normal { from, to, promote } => {
            let capture = g.board().get(to).map_or(0, |p| {
                if p.kind == PieceKind::King {
                    100_000
                } else {
                    value(p.kind) * 10
                }
            });
            let gain = if promote { 500 } else { 0 };
            let forward = i32::from(g.side().relative_rank(from.y()))
                - i32::from(g.side().relative_rank(to.y()));
            (
                capture + gain + forward * 3,
                (from.index() * 729 + to.index()) as u64 * 2 + u64::from(promote),
            )
        }
        Move::Drop { kind, to } => (0, 1_100_000 + kind.index() as u64 * 729 + to.index() as u64),
    };
    (rank, mix(seed ^ g.hash() ^ key))
}
fn candidates(g: &impl Position, c: SearchConfig, seed: u64) -> Vec<Move> {
    let mut moves = g.legal_moves();
    moves.sort_by_cached_key(|&m| std::cmp::Reverse(order(g, m, seed)));
    moves.truncate(c.width);
    moves
}
fn search(
    g: &impl Position,
    c: SearchConfig,
    depth: u8,
    mut alpha: i32,
    beta: i32,
    seed: u64,
    nodes: &mut u64,
) -> i32 {
    *nodes += 1;
    let sign = if g.side() == Color::Black { 1 } else { -1 };
    if let Some(score) = g.terminal_score() {
        return score;
    }
    if depth == 0 {
        return sign * g.evaluate();
    }
    let mut best = -2_000_000;
    for m in candidates(g, c, seed) {
        let score = -search(
            &g.after_generated(&m),
            c,
            depth - 1,
            -beta,
            -alpha,
            seed,
            nodes,
        );
        best = best.max(score);
        alpha = alpha.max(score);
        if alpha >= beta {
            break;
        }
    }
    best
}
pub fn choose_move(g: &CaptureGame, c: SearchConfig, seed: u64) -> Result<(Move, u64), String> {
    choose(g, c, seed)
}
fn choose(g: &impl Position, c: SearchConfig, seed: u64) -> Result<(Move, u64), String> {
    c.validate()?;
    if g.terminal_score().is_some() {
        return Err("game over".into());
    }
    let mut best = None;
    let mut alpha = -2_000_000;
    let mut nodes = 0;
    for m in candidates(g, c, seed) {
        let score = -search(
            &g.after_generated(&m),
            c,
            c.depth - 1,
            -2_000_000,
            -alpha,
            seed,
            &mut nodes,
        );
        if best.is_none() || score > alpha {
            alpha = score;
            best = Some(m);
        }
    }
    best.map(|m| (m, nodes))
        .ok_or_else(|| "no legal move".into())
}

#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExperimentRecord {
    pub schema: String,
    pub ruleset_id: String,
    pub max_plies: u32,
    pub seed: u64,
    pub swapped: bool,
    pub search: SearchConfig,
    pub engine: String,
    pub moves: Vec<String>,
    pub outcome: Outcome,
    pub final_hash: String,
    pub nodes: u64,
}
fn rule(id: &str) -> Result<CaptureRule, String> {
    [
        CaptureRule::FirstFive,
        CaptureRule::AllKings,
        CaptureRule::ScoreLimit,
    ]
    .into_iter()
    .find(|r| r.id() == id)
    .ok_or_else(|| "unknown experimental ruleset".into())
}
impl ExperimentRecord {
    pub fn play(
        rule: CaptureRule,
        max_plies: u32,
        seed: u64,
        swapped: bool,
        search: SearchConfig,
        engine: &str,
    ) -> Result<Self, String> {
        search.validate()?;
        let mut g = CaptureGame::new(rule, max_plies)?;
        let mut moves = Vec::new();
        let mut nodes = 0;
        while g.outcome().is_none() {
            let stream = (g.side() == Color::White) ^ swapped;
            let (mv, n) = choose_move(
                &g,
                search,
                mix(seed) ^ if stream { 0xd1b54a32d192ed03 } else { 0 },
            )?;
            nodes += n;
            g = g.after_move(&mv)?;
            moves.push(mv.to_string());
        }
        Ok(Self {
            schema: "voxelshogi-capture-experiment-v1".into(),
            ruleset_id: rule.id().into(),
            max_plies,
            seed,
            swapped,
            search,
            engine: engine.into(),
            moves,
            outcome: g.outcome().unwrap(),
            final_hash: format!("{:016x}", g.hash()),
            nodes,
        })
    }
}
pub struct Replay {
    pub record: ExperimentRecord,
    states: Vec<CaptureGame>,
}
impl Replay {
    pub fn from_json(json: &str) -> Result<Self, String> {
        if json.len() > 4 * 1024 * 1024 {
            return Err("record exceeds 4 MiB".into());
        }
        let r: ExperimentRecord = serde_json::from_str(json).map_err(|e| e.to_string())?;
        if r.schema != "voxelshogi-capture-experiment-v1"
            || r.moves.len() > r.max_plies as usize
            || r.engine.is_empty()
            || r.engine.len() > 128
        {
            return Err("invalid record metadata".into());
        }
        r.search.validate()?;
        let mut g = CaptureGame::new(rule(&r.ruleset_id)?, r.max_plies)?;
        let mut states = vec![g.clone()];
        for text in &r.moves {
            let m = parse_move(text).map_err(|e| e.to_string())?;
            g = g.after_move(&m)?;
            states.push(g.clone());
        }
        if g.outcome() != Some(r.outcome) || format!("{:016x}", g.hash()) != r.final_hash {
            return Err("record outcome or final hash mismatch".into());
        }
        Ok(Self { record: r, states })
    }
    pub fn len(&self) -> usize {
        self.record.moves.len()
    }
    pub fn is_empty(&self) -> bool {
        self.record.moves.is_empty()
    }
    pub fn state(&self, ply: usize) -> Result<&CaptureGame, String> {
        self.states
            .get(ply)
            .ok_or_else(|| "ply out of range".into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Board, Piece, Square};
    fn fixture(rule: CaptureRule) -> CaptureGame {
        let mut b = Board::empty();
        for x in 0..9 {
            b.set(
                Square::new(x, 8, 0),
                Some(Piece::new(Color::Black, PieceKind::King)),
            );
        }
        for x in 0..5 {
            b.set(
                Square::new(x, 0, 0),
                Some(Piece::new(Color::White, PieceKind::King)),
            );
        }
        b.set(
            Square::new(4, 1, 0),
            Some(Piece::new(Color::Black, PieceKind::Rook)),
        );
        CaptureGame::from_parts(b, [[0; 7]; 2], Color::Black, rule, 400).unwrap()
    }
    #[test]
    fn finds_immediate_target_and_evaluation_has_hand_calculated_sign() {
        let g = fixture(CaptureRule::FirstFive);
        // Four captured kings, a rook, +7 ranks of rook advancement. Kings: 0 advancement.
        assert_eq!(evaluation(&g), 101021);
        let (m, _) = choose_move(
            &g,
            SearchConfig {
                depth: 2,
                width: 64,
            },
            7,
        )
        .unwrap();
        assert!(
            matches!(m, Move::Normal {from,to,..} if from==Square::new(4,1,0) && to==Square::new(4,0,0))
        );
        assert_eq!(
            g.after_move(&m).unwrap().outcome().unwrap().winner,
            Some(Color::Black)
        );
    }
    // Plain exhaustive minimax over the SAME retained candidate tree, without alpha-beta.
    // Width truncation is intentionally not claimed to preserve the full minimax value.
    fn plain(g: &CaptureGame, c: SearchConfig, d: u8, seed: u64) -> i32 {
        if let Some(o) = g.outcome() {
            return o
                .winner
                .map_or(0, |w| if w == g.side() { 1_000_000 } else { -1_000_000 });
        }
        if d == 0 {
            return (if g.side() == Color::Black { 1 } else { -1 }) * evaluation(g);
        }
        candidates(g, c, seed)
            .iter()
            .map(|m| -plain(&g.after_move(m).unwrap(), c, d - 1, seed))
            .max()
            .unwrap()
    }
    #[test]
    fn alpha_beta_matches_plain_tree_and_fast_transitions_match_checked() {
        let mut g = CaptureGame::new(CaptureRule::AllKings, 400).unwrap();
        for ply in 0..32 {
            let moves = g.legal_moves();
            assert!(!moves.is_empty());
            for m in &moves {
                let a = g.after_generated(m);
                let b = g.after_move(m).unwrap();
                assert_eq!(a.board(), b.board());
                assert_eq!(a.hands(), b.hands());
                assert_eq!(a.captured(), b.captured());
                assert_eq!(a.hash(), b.hash());
                assert_eq!(a.ply(), b.ply());
                assert_eq!(a.side(), b.side());
                assert_eq!(a.outcome(), b.outcome());
            }
            g = g.after_generated(&moves[mix(ply) as usize % moves.len()]);
        }
        for depth in 1..=3 {
            let c = SearchConfig { depth, width: 4 };
            let mut nodes = 0;
            assert_eq!(
                search(&g, c, depth, -2_000_000, 2_000_000, 9, &mut nodes),
                plain(&g, c, depth, 9)
            );
            assert!(nodes > 0);
        }
    }
}

/// Standard one-king control. Its setup and king-safety differ, so it is not a victory-condition-only comparison.
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct BaselineRecord {
    pub record: crate::record::GameRecord,
    pub max_plies: u32,
    pub seed: u64,
    pub swapped: bool,
    pub search: SearchConfig,
    pub engine: String,
    pub final_hash: String,
    pub nodes: u64,
}
pub fn play_baseline(
    max_plies: u32,
    seed: u64,
    swapped: bool,
    search: SearchConfig,
    engine: &str,
) -> Result<BaselineRecord, String> {
    search.validate()?;
    CaptureGame::new(CaptureRule::AllKings, max_plies)?; // shared limit bounds
    let mut pos = StandardPosition {
        game: crate::GameState::new(),
        limit: max_plies,
    };
    let initial = crate::notation::to_vsfen(&pos.game);
    let mut moves = Vec::new();
    let mut nodes = 0;
    while pos.terminal_score().is_none() {
        let stream = (pos.side() == Color::White) ^ swapped;
        let (m, n) = choose(
            &pos,
            search,
            mix(seed) ^ if stream { 0xd1b54a32d192ed03 } else { 0 },
        )?;
        nodes += n;
        pos = pos.after_generated(&m);
        moves.push(m.to_string());
    }
    let natural = pos.game.result();
    let record = crate::record::GameRecord {
        ruleset_id: crate::record::RULESET_ID.into(),
        initial,
        moves,
        result: natural.or(Some(crate::GameResult::Draw {
            reason: crate::DrawReason::MaxPlies,
        })),
        termination: if natural.is_none() {
            Some(crate::record::Termination::MaxPlies)
        } else {
            None
        },
    };
    let replay = record.replay().map_err(|e| e.to_string())?;
    if replay.hash() != pos.hash() {
        return Err("baseline replay mismatch".into());
    }
    Ok(BaselineRecord {
        record,
        max_plies,
        seed,
        swapped,
        search,
        engine: engine.into(),
        final_hash: format!("{:016x}", pos.hash()),
        nodes,
    })
}
