//! VoxelShogi core rule engine: 9×9×9 three-dimensional shogi.
//!
//! The ruleset follows shogitter.com's 三次元将棋 (see `docs/RULESET.md`).
//! This crate has no dependency on browsers, Python or GPUs.

pub mod board;
pub mod coord;
pub mod movegen;
pub mod moves;
pub mod piece;
pub mod state;
pub mod zobrist;

pub use board::Board;
pub use coord::{NUM_SQUARES, SIZE, Square};
pub use moves::Move;
pub use piece::{Color, Piece, PieceKind, Player};
pub use state::{DrawReason, GameResult, GameState, Hands, MoveError, WinReason};
