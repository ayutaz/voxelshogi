//! VoxelShogi core rule engine: 9×9×9 three-dimensional shogi.
//!
//! The ruleset follows shogitter.com's 三次元将棋 (see `docs/RULESET.md`).
//! This crate has no dependency on browsers, Python or GPUs.

pub mod board;
pub mod coord;
pub mod piece;

pub use board::Board;
pub use coord::{NUM_SQUARES, SIZE, Square};
pub use piece::{Color, Piece, PieceKind, Player};
