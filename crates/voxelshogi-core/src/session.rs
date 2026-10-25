//! Interactive game session: a move list with a cursor (undo/redo/goto) and
//! record import/export. Used by the WASM bindings; contains no browser code.

use crate::notation::{from_vsfen, parse_move, to_vsfen};
use crate::record::{GameRecord, Termination};
use crate::state::{GameResult, GameState, WinReason};

#[derive(Clone, Debug)]
pub struct Session {
    /// `states[i]` is the position after `i` moves; `states[0]` is the start.
    states: Vec<GameState>,
    moves: Vec<String>,
    cursor: usize,
}

impl Session {
    pub fn new() -> Session {
        Session::from_state(GameState::new())
    }

    fn from_state(start: GameState) -> Session {
        Session {
            states: vec![start],
            moves: Vec::new(),
            cursor: 0,
        }
    }

    pub fn from_vsfen(s: &str) -> Result<Session, String> {
        from_vsfen(s)
            .map(Session::from_state)
            .map_err(|e| e.to_string())
    }

    /// Imports an untrusted record: every move and the claimed result are re-validated.
    pub fn from_record_json(s: &str) -> Result<Session, String> {
        let rec = GameRecord::from_json(s).map_err(|e| e.to_string())?;
        rec.replay().map_err(|e| e.to_string())?;
        let mut session = Session::from_vsfen(&rec.initial)?;
        for m in &rec.moves {
            session.play(m)?;
        }
        if rec.termination == Some(Termination::Resignation) {
            session.resign();
        }
        Ok(session)
    }

    pub fn state(&self) -> &GameState {
        &self.states[self.cursor]
    }

    pub fn moves(&self) -> &[String] {
        &self.moves
    }

    pub fn len(&self) -> usize {
        self.moves.len()
    }

    pub fn is_empty(&self) -> bool {
        self.moves.is_empty()
    }

    pub fn cursor(&self) -> usize {
        self.cursor
    }

    pub fn can_undo(&self) -> bool {
        self.cursor > 0
    }

    pub fn can_redo(&self) -> bool {
        self.cursor < self.moves.len()
    }

    /// Plays a move at the cursor. Moves after the cursor are discarded.
    pub fn play(&mut self, mv: &str) -> Result<(), String> {
        let m = parse_move(mv).map_err(|e| e.to_string())?;
        let next = self.state().apply_move(&m).map_err(|e| e.to_string())?;
        self.states.truncate(self.cursor + 1);
        self.moves.truncate(self.cursor);
        self.states.push(next);
        self.moves.push(m.to_string());
        self.cursor += 1;
        Ok(())
    }

    pub fn undo(&mut self) -> bool {
        self.can_undo() && {
            self.cursor -= 1;
            true
        }
    }

    pub fn redo(&mut self) -> bool {
        self.can_redo() && {
            self.cursor += 1;
            true
        }
    }

    pub fn goto(&mut self, ply: usize) -> Result<(), String> {
        if ply > self.moves.len() {
            return Err(format!(
                "ply {ply} is beyond the {} recorded moves",
                self.moves.len()
            ));
        }
        self.cursor = ply;
        Ok(())
    }

    /// The side to move at the cursor resigns; later moves are discarded.
    pub fn resign(&mut self) {
        self.states.truncate(self.cursor + 1);
        self.moves.truncate(self.cursor);
        self.states[self.cursor].resign();
    }

    pub fn to_record_json(&self) -> String {
        let last = self.states.last().expect("at least the start state");
        let result = last.result();
        let termination = match result {
            Some(GameResult::Win {
                reason: WinReason::Resignation,
                ..
            }) => Some(Termination::Resignation),
            _ => None,
        };
        GameRecord {
            ruleset_id: crate::record::RULESET_ID.to_string(),
            initial: to_vsfen(&self.states[0]),
            moves: self.moves.clone(),
            result,
            termination,
        }
        .to_json()
    }
}

impl Default for Session {
    fn default() -> Self {
        Session::new()
    }
}
