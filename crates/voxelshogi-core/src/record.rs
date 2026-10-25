//! Game records (棋譜) tagged with the ruleset they were played under.
//!
//! JSON shape: `{"ruleset_id", "initial" (VSFEN), "moves" ([move strings]),
//! "result", "termination"}`. Records are untrusted input: [`GameRecord::replay`]
//! re-validates every move and the claimed result.

use crate::moves::Move;
use crate::notation::{from_vsfen, parse_move, to_vsfen};
use crate::state::{DrawReason, GameResult, GameState};

pub const RULESET_ID: &str = "voxelshogi-standard-v1";
/// Records with more moves than this are rejected.
pub const MAX_RECORD_MOVES: usize = 20_000;
/// JSON inputs larger than this are rejected before parsing.
pub const MAX_RECORD_BYTES: usize = 4 << 20;

/// How a game ended when it was not by a rule outcome reached on the board.
#[derive(Clone, Copy, PartialEq, Eq, Debug, serde::Serialize, serde::Deserialize)]
pub enum Termination {
    /// The side to move after the last move resigned.
    Resignation,
    /// Adjudicated as a draw by a move limit (not a rule outcome).
    MaxPlies,
    /// Stopped without a result.
    Abandoned,
}

#[derive(Clone, PartialEq, Eq, Debug, serde::Serialize, serde::Deserialize)]
pub struct GameRecord {
    pub ruleset_id: String,
    pub initial: String,
    pub moves: Vec<String>,
    #[serde(default)]
    pub result: Option<GameResult>,
    #[serde(default)]
    pub termination: Option<Termination>,
}

#[derive(Clone, PartialEq, Eq, Debug)]
pub enum RecordError {
    UnsupportedRuleset(String),
    BadPosition(String),
    BadMoveString {
        index: usize,
        text: String,
    },
    IllegalMove {
        index: usize,
        reason: String,
    },
    ResultMismatch {
        recorded: Option<GameResult>,
        replayed: Option<GameResult>,
    },
    TooLong(usize),
    Json(String),
}

impl std::fmt::Display for RecordError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for RecordError {}

impl GameRecord {
    /// Builds a record from engine-generated moves. Panics if a move is illegal.
    pub fn from_moves(start: &GameState, moves: &[Move]) -> GameRecord {
        let mut g = start.clone();
        for m in moves {
            g = g
                .apply_move(m)
                .unwrap_or_else(|e| panic!("from_moves: {m}: {e}"));
        }
        GameRecord {
            ruleset_id: RULESET_ID.to_string(),
            initial: to_vsfen(start),
            moves: moves.iter().map(Move::to_string).collect(),
            result: g.result(),
            termination: None,
        }
    }

    /// Replays the record from scratch, validating every move and the claimed result.
    pub fn replay(&self) -> Result<GameState, RecordError> {
        if self.ruleset_id != RULESET_ID {
            return Err(RecordError::UnsupportedRuleset(self.ruleset_id.clone()));
        }
        if self.moves.len() > MAX_RECORD_MOVES {
            return Err(RecordError::TooLong(self.moves.len()));
        }
        let mut g =
            from_vsfen(&self.initial).map_err(|e| RecordError::BadPosition(e.to_string()))?;
        for (index, text) in self.moves.iter().enumerate() {
            let mv = parse_move(text).map_err(|_| RecordError::BadMoveString {
                index,
                text: text.clone(),
            })?;
            g = g.apply_move(&mv).map_err(|e| RecordError::IllegalMove {
                index,
                reason: e.to_string(),
            })?;
        }
        let replayed = match self.termination {
            Some(Termination::Resignation) => {
                g.resign();
                g.result()
            }
            Some(Termination::MaxPlies) => g.result().or(Some(GameResult::Draw {
                reason: DrawReason::MaxPlies,
            })),
            Some(Termination::Abandoned) | None => g.result(),
        };
        if replayed != self.result {
            return Err(RecordError::ResultMismatch {
                recorded: self.result,
                replayed,
            });
        }
        Ok(g)
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("records always serialize")
    }

    pub fn from_json(s: &str) -> Result<GameRecord, RecordError> {
        if s.len() > MAX_RECORD_BYTES {
            return Err(RecordError::TooLong(s.len()));
        }
        let rec: GameRecord =
            serde_json::from_str(s).map_err(|e| RecordError::Json(e.to_string()))?;
        if rec.moves.len() > MAX_RECORD_MOVES {
            return Err(RecordError::TooLong(rec.moves.len()));
        }
        Ok(rec)
    }
}
