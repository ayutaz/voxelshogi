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
        // Bound generation independently of the engine's ply/result counters.
        for _ in 0..max_plies {
            if g.outcome().is_some() {
                break;
            }
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
            outcome: g
                .outcome()
                .ok_or("move cap reached without a capture-game outcome")?,
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
        CaptureGame::from_parts(b, [[0; 7]; 2], Color::Black, rule, 2).unwrap()
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
        // Keep real-game fixtures finite even if a mutant stops decreasing depth.
        // The synthetic tree below separately checks nonzero horizons through depth 3.
        let g = CaptureGame::from_parts(
            g.board().clone(),
            *g.hands(),
            g.side(),
            CaptureRule::AllKings,
            4,
        )
        .unwrap();
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
    // Count actual generated moves as well as consulting the game outcome.
    for _ in 0..max_plies {
        if pos.terminal_score().is_some() {
            break;
        }
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

#[cfg(test)]
mod audit_contracts {
    use super::*;
    use crate::{Board, GameState, Hands, Piece, Square};
    const VALUES: [i32; 14] = [
        100, 300, 320, 450, 550, 800, 1000, 0, 550, 550, 550, 550, 1100, 1300,
    ];
    #[derive(Clone)]
    struct Data {
        board: Board,
        hands: Hands,
        side: Color,
    }
    impl Position for Data {
        fn board(&self) -> &Board {
            &self.board
        }
        fn hands(&self) -> &Hands {
            &self.hands
        }
        fn side(&self) -> Color {
            self.side
        }
        fn hash(&self) -> u64 {
            7
        }
        fn legal_moves(&self) -> Vec<Move> {
            panic!("data-only position")
        }
        fn after_generated(&self, _: &Move) -> Self {
            panic!("data-only position")
        }
        fn terminal_score(&self) -> Option<i32> {
            None
        }
        fn evaluate(&self) -> i32 {
            material(self)
        }
    }
    #[test]
    fn material_and_standard_evaluation_have_hand_counted_board_hand_and_advancement_terms() {
        for side in Color::ALL {
            let sign = if side == Color::Black { 1 } else { -1 };
            for kind in PieceKind::ALL {
                let mut board = Board::empty();
                board.set(Square::new(4, 4, 4), Some(Piece::new(side, kind)));
                let data = Data {
                    board: board.clone(),
                    hands: [[0; 7]; 2],
                    side,
                };
                assert_eq!(material(&data), sign * (VALUES[kind.index()] + 12));
                let standard = StandardPosition {
                    game: GameState::from_parts(board, [[0; 7]; 2], side),
                    limit: 400,
                };
                assert_eq!(standard.evaluate(), sign * (VALUES[kind.index()] + 12));
            }
            for (i, kind) in PieceKind::HAND.into_iter().enumerate() {
                let mut hands = [[0; 7]; 2];
                hands[side.index()][i] = 2;
                assert_eq!(
                    material(&Data {
                        board: Board::empty(),
                        hands,
                        side
                    }),
                    sign * 2 * VALUES[kind.index()]
                );
            }
        }
    }
    #[test]
    fn splitmix_and_move_ranking_follow_fixed_numeric_contracts() {
        // Evaluated with arbitrary-precision arithmetic, reductions modulo 2^64,
        // and integer division by 2^30/2^27/2^31, independently of native wrapping.
        for (input, expected) in [
            (0, 0xe220a8397b1dcdaf),
            (1, 0x910a2dec89025cc1),
            (u64::MAX, 0xe4d971771b652c20),
        ] {
            assert_eq!(mix(input), expected);
        }
        let from = Square::new(4, 3, 4);
        let to = Square::new(4, 2, 4);
        assert_eq!(from.index(), 355);
        assert_eq!(to.index(), 346);
        // Normal key = (355*729+346)*2 = 518282, plus one for promotion.
        for kind in PieceKind::ALL {
            let mut board = Board::empty();
            board.set(from, Some(Piece::new(Color::Black, PieceKind::Pawn)));
            board.set(to, Some(Piece::new(Color::White, kind)));
            let data = Data {
                board,
                hands: [[0; 7]; 2],
                side: Color::Black,
            };
            let captured = if kind == PieceKind::King {
                100_000
            } else {
                VALUES[kind.index()] * 10
            };
            assert_eq!(
                order(
                    &data,
                    Move::Normal {
                        from,
                        to,
                        promote: false
                    },
                    42
                ),
                (captured + 3, 0x452b823b157f3cdb)
            );
            assert_eq!(
                order(
                    &data,
                    Move::Normal {
                        from,
                        to,
                        promote: true
                    },
                    42
                ),
                (captured + 503, 0xa9e85a5fb76686de)
            );
        }
        let data = Data {
            board: Board::empty(),
            hands: [[0; 7]; 2],
            side: Color::White,
        };
        assert_eq!(
            order(
                &data,
                Move::Normal {
                    from,
                    to,
                    promote: false
                },
                42
            ),
            (-3, 0x452b823b157f3cdb)
        );
        let random = [
            0x59463314cb2150bf,
            0xeb21428386756844,
            0x04cc518e5ccbb7a5,
            0xcef60e44048b254b,
            0x202c37c0248c4938,
            0x92bb8628c97e22f1,
            0x081ed5bf3bb77de1,
        ];
        for (i, kind) in PieceKind::HAND.into_iter().enumerate() {
            assert_eq!(
                order(
                    &data,
                    Move::Drop {
                        kind,
                        to: Square::new(4, 4, 4)
                    },
                    42
                ),
                (0, random[i])
            );
        }
    }
    #[derive(Clone)]
    struct Tree {
        board: Board,
        hands: Hands,
        side: Color,
        ply: u8,
        path: usize,
        equal: bool,
    }
    impl Position for Tree {
        fn board(&self) -> &Board {
            &self.board
        }
        fn hands(&self) -> &Hands {
            &self.hands
        }
        fn side(&self) -> Color {
            self.side
        }
        fn hash(&self) -> u64 {
            7
        }
        fn terminal_score(&self) -> Option<i32> {
            None
        }
        fn evaluate(&self) -> i32 {
            if self.equal {
                return 0;
            }
            match self.ply {
                0 => 17,
                1 => [100, -300][self.path],
                2 => [-50, 500, -200, -1000][self.path],
                3 => [91, -37, 23, -83, -43, 79, 13, 61][self.path],
                _ => panic!("tree depth"),
            }
        }
        fn legal_moves(&self) -> Vec<Move> {
            // Invalid depth recursion must fail a test, rather than run to timeout.
            assert!(self.ply < 3, "search did not decrease its depth");
            [5, 6]
                .map(|x| Move::Normal {
                    from: Square::new(4, 4, 4),
                    to: Square::new(x, 4, 4),
                    promote: false,
                })
                .to_vec()
        }
        fn after_generated(&self, m: &Move) -> Self {
            let mut next = self.clone();
            next.path = 2 * self.path + usize::from(m.to().x() == 6);
            next.ply += 1;
            next.side = self.side.opponent();
            next
        }
    }
    fn reference(g: &impl Position, c: SearchConfig, depth: u8, seed: u64) -> (i32, Vec<Move>) {
        if let Some(score) = g.terminal_score() {
            return (score, vec![]);
        }
        if depth == 0 {
            return (
                (if g.side() == Color::Black { 1 } else { -1 }) * g.evaluate(),
                vec![],
            );
        }
        let mut best = i32::MIN;
        let mut moves = vec![];
        for mv in candidates(g, c, seed) {
            let score = -reference(&g.after_generated(&mv), c, depth - 1, seed).0;
            if score > best {
                best = score;
                moves.clear();
            }
            if score == best {
                moves.push(mv);
            }
        }
        (best, moves)
    }
    #[test]
    fn retained_tree_search_and_choose_match_unpruned_reference_on_nonzero_payoffs() {
        let config = |depth| SearchConfig { depth, width: 2 };
        for side in Color::ALL {
            let tree = Tree {
                board: Board::empty(),
                hands: [[0; 7]; 2],
                side,
                ply: 0,
                path: 0,
                equal: false,
            };
            for depth in 0..=3 {
                for seed in 0..8 {
                    let expected = reference(&tree, config(depth), depth, seed);
                    let mut nodes = 0;
                    assert_eq!(
                        search(
                            &tree,
                            config(depth),
                            depth,
                            -2_000_000,
                            2_000_000,
                            seed,
                            &mut nodes
                        ),
                        expected.0
                    );
                    assert!(nodes > 0);
                    if depth > 0 {
                        let (mv, nodes) = choose(&tree, config(depth), seed).unwrap();
                        assert!(expected.1.contains(&mv));
                        assert!(nodes > 0);
                    }
                    if depth == 0 {
                        assert_eq!(nodes, 1);
                    }
                }
            }
        }
        let equal = Tree {
            board: Board::empty(),
            hands: [[0; 7]; 2],
            side: Color::Black,
            ply: 0,
            path: 0,
            equal: true,
        };
        for seed in 0..8 {
            let (mv, nodes) = choose(&equal, config(1), seed).unwrap();
            assert_eq!(mv, candidates(&equal, config(1), seed)[0]);
            assert_eq!(nodes, 2);
        }
    }
    #[test]
    fn record_generation_assigns_seed_streams_and_counts_nodes_for_each_side() {
        let config = SearchConfig { depth: 1, width: 4 };
        for seed in [17, 42, 913] {
            let base = mix(seed);
            for swapped in [false, true] {
                let streams = if swapped {
                    [base ^ 0xd1b54a32d192ed03, base]
                } else {
                    [base, base ^ 0xd1b54a32d192ed03]
                };
                let mut capture = CaptureGame::new(CaptureRule::ScoreLimit, 2).unwrap();
                let mut standard = StandardPosition {
                    game: GameState::new(),
                    limit: 2,
                };
                let mut capture_moves = vec![];
                let mut standard_moves = vec![];
                for stream in streams {
                    let (mv, n) = choose_move(&capture, config, stream).unwrap();
                    assert_eq!(n, 4);
                    capture_moves.push(mv.to_string());
                    capture = capture.after_move(&mv).unwrap();
                    let (mv, n) = choose(&standard, config, stream).unwrap();
                    assert_eq!(n, 4);
                    standard_moves.push(mv.to_string());
                    standard = standard.after_generated(&mv);
                }
                let capture = ExperimentRecord::play(
                    CaptureRule::ScoreLimit,
                    2,
                    seed,
                    swapped,
                    config,
                    "fixture",
                )
                .unwrap();
                let standard = play_baseline(2, seed, swapped, config, "fixture").unwrap();
                assert_eq!(capture.moves, capture_moves);
                assert_eq!(capture.nodes, 8);
                assert_eq!(standard.record.moves, standard_moves);
                assert_eq!(standard.nodes, 8);
            }
        }
    }
    #[test]
    fn position_adapters_preserve_hands_hash_and_asymmetric_king_scores() {
        for (black, white, expected) in [(8, 7, 24_200), (7, 8, -25_800)] {
            let mut b = Board::empty();
            for x in 0..black {
                b.set(
                    Square::new(x, 8, 0),
                    Some(Piece::new(Color::Black, PieceKind::King)),
                );
            }
            for x in 0..white {
                b.set(
                    Square::new(x, 0, 0),
                    Some(Piece::new(Color::White, PieceKind::King)),
                );
            }
            let mut hands = [[0; 7]; 2];
            hands[0][0] = 2;
            hands[1][6] = 1;
            let g = CaptureGame::from_parts(b, hands, Color::Black, CaptureRule::ScoreLimit, 2)
                .unwrap();
            assert_eq!(evaluation(&g), expected);
            assert_eq!(Position::hands(&g), &hands);
            assert!(g.hash() > 1);
            assert_eq!(Position::hash(&g), g.hash());
        }
        for side in Color::ALL {
            let mut hands = [[0; 7]; 2];
            hands[side.index()][6] = 2;
            let p = StandardPosition {
                game: GameState::from_parts(Board::empty(), hands, side),
                limit: 2,
            };
            assert_eq!(
                p.evaluate(),
                if side == Color::Black { 2000 } else { -2000 }
            );
            assert_eq!(p.hands(), &hands);
        }
        for (black, white, score) in [(9, 5, 1_000_000), (5, 9, -1_000_000)] {
            let mut b = Board::empty();
            for x in 0..black {
                b.set(
                    Square::new(x, 8, 0),
                    Some(Piece::new(Color::Black, PieceKind::King)),
                );
            }
            for x in 0..white {
                b.set(
                    Square::new(x, 0, 0),
                    Some(Piece::new(Color::White, PieceKind::King)),
                );
            }
            let mut g =
                CaptureGame::from_parts(b, [[0; 7]; 2], Color::Black, CaptureRule::ScoreLimit, 2)
                    .unwrap();
            for (from, to) in [
                (Square::new(4, 8, 0), Square::new(4, 7, 0)),
                (Square::new(0, 0, 0), Square::new(0, 1, 0)),
            ] {
                g = g
                    .after_move(&Move::Normal {
                        from,
                        to,
                        promote: false,
                    })
                    .unwrap();
            }
            assert_eq!(Position::terminal_score(&g), Some(score));
        }
    }
    #[test]
    fn standard_control_terminal_score_honors_material_perspective_and_game_limit() {
        let mut game = GameState::new();
        game.resign();
        let mut p = StandardPosition { game, limit: 0 };
        assert_eq!(p.terminal_score(), Some(-1_000_000));
        p.game = GameState::new();
        assert_eq!(p.terminal_score(), Some(0));
        p.limit = 1;
        assert_eq!(p.terminal_score(), None);
    }
}
