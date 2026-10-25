//! WebAssembly bindings: a thin wrapper around [`voxelshogi_core::session::Session`].
//! All rules live in `voxelshogi-core`; nothing here re-implements them.

use voxelshogi_core::record::RULESET_ID;
use voxelshogi_core::session::Session;
use voxelshogi_core::{Color, NUM_SQUARES, Square, notation};
use wasm_bindgen::prelude::*;

#[wasm_bindgen(js_name = rulesetId)]
pub fn ruleset_id() -> String {
    RULESET_ID.to_string()
}

/// A game session (position at a cursor in a move list).
#[wasm_bindgen]
pub struct Game {
    session: Session,
}

#[wasm_bindgen]
impl Game {
    #[wasm_bindgen(constructor)]
    #[allow(clippy::new_without_default)]
    pub fn new() -> Game {
        Game {
            session: Session::new(),
        }
    }

    #[wasm_bindgen(js_name = fromVsfen)]
    pub fn from_vsfen(vsfen: &str) -> Result<Game, JsError> {
        Session::from_vsfen(vsfen)
            .map(|session| Game { session })
            .map_err(|e| JsError::new(&e))
    }

    /// Imports an untrusted record (every move is re-validated).
    #[wasm_bindgen(js_name = fromRecordJson)]
    pub fn from_record_json(json: &str) -> Result<Game, JsError> {
        Session::from_record_json(json)
            .map(|session| Game { session })
            .map_err(|e| JsError::new(&e))
    }

    pub fn vsfen(&self) -> String {
        notation::to_vsfen(self.session.state())
    }

    /// `"b"` or `"w"`.
    #[wasm_bindgen(js_name = sideToMove)]
    pub fn side_to_move(&self) -> String {
        match self.session.state().side_to_move() {
            Color::Black => "b".into(),
            Color::White => "w".into(),
        }
    }

    /// Current cursor position (number of moves played to reach the shown position).
    pub fn ply(&self) -> u32 {
        self.session.cursor() as u32
    }

    /// Total number of moves in the move list (may exceed `ply()` after undo).
    #[wasm_bindgen(js_name = moveCount)]
    pub fn move_count(&self) -> u32 {
        self.session.len() as u32
    }

    /// Zobrist hash as 16 hex digits.
    pub fn hash(&self) -> String {
        format!("{:016x}", self.session.state().hash())
    }

    /// 729 piece codes (`0` empty, `1 + kind + 14 * color`), index `z*81 + y*9 + x`.
    pub fn board(&self) -> Vec<u8> {
        let b = self.session.state().board();
        (0..NUM_SQUARES)
            .map(|i| {
                b.get(Square::from_index(i).expect("in range"))
                    .map_or(0, |p| p.code())
            })
            .collect()
    }

    /// 14 counts: Black's then White's hand in `P L N S G B R` order.
    pub fn hands(&self) -> Vec<u8> {
        self.session
            .state()
            .hands()
            .iter()
            .flatten()
            .copied()
            .collect()
    }

    #[wasm_bindgen(js_name = legalMoves)]
    pub fn legal_moves(&self) -> Vec<String> {
        self.session
            .state()
            .legal_moves()
            .iter()
            .map(ToString::to_string)
            .collect()
    }

    pub fn play(&mut self, mv: &str) -> Result<(), JsError> {
        self.session.play(mv).map_err(|e| JsError::new(&e))
    }

    pub fn undo(&mut self) -> bool {
        self.session.undo()
    }

    pub fn redo(&mut self) -> bool {
        self.session.redo()
    }

    pub fn goto(&mut self, ply: u32) -> Result<(), JsError> {
        self.session
            .goto(ply as usize)
            .map_err(|e| JsError::new(&e))
    }

    #[wasm_bindgen(js_name = moveList)]
    pub fn move_list(&self) -> Vec<String> {
        self.session.moves().to_vec()
    }

    /// The move that led to the current position, if any.
    #[wasm_bindgen(js_name = lastMove)]
    pub fn last_move(&self) -> Option<String> {
        let c = self.session.cursor();
        (c > 0).then(|| self.session.moves()[c - 1].clone())
    }

    #[wasm_bindgen(js_name = isInCheck)]
    pub fn is_in_check(&self, black: bool) -> bool {
        self.session
            .state()
            .is_in_check(if black { Color::Black } else { Color::White })
    }

    /// The result as JSON (e.g. `{"Win":{"winner":"White","reason":"Resignation"}}`), or undefined.
    pub fn result(&self) -> Option<String> {
        self.session
            .state()
            .result()
            .map(|r| serde_json::to_string(&r).expect("serializable"))
    }

    pub fn resign(&mut self) {
        self.session.resign();
    }

    #[wasm_bindgen(js_name = recordJson)]
    pub fn record_json(&self) -> String {
        self.session.to_record_json()
    }
}
