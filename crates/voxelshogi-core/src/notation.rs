//! Text notation: move strings and VSFEN positions (docs/GAME_ENGINE.md).
//!
//! VSFEN (VoxelShogi FEN) is `<board> <side> <hands> <move number>`:
//! * board: 9 layers `z = 0..8` joined by `|`; each layer is 9 ranks `y = 0..8`
//!   joined by `/`; each rank lists files from 9 to 1 (`x = 8..0`) like SFEN.
//!   Pieces use `P L N S G B R K` (Black uppercase, White lowercase), `+` marks a
//!   promoted piece, and a digit 1..9 counts consecutive empty squares.
//! * side: `b` or `w`.
//! * hands: `-`, or Black's then White's pieces in `R B G S N L P` order, each
//!   optionally preceded by its count (e.g. `R12P2g`).
//! * move number: 1 for the first move (ply + 1).

use crate::board::Board;
use crate::coord::{SIZE, Square};
use crate::moves::Move;
use crate::piece::{Color, NUM_HAND_KINDS, Piece, PieceKind};
use crate::state::{GameState, Hands};

/// Inputs longer than this are rejected before parsing.
pub const MAX_VSFEN_LEN: usize = 4096;
/// Order in which hand pieces are written (hand indices of R B G S N L P).
const HAND_ORDER: [usize; NUM_HAND_KINDS] = [6, 5, 4, 3, 2, 1, 0];

#[derive(Clone, PartialEq, Eq, Debug)]
pub enum NotationError {
    Invalid(String),
}

impl std::fmt::Display for NotationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let NotationError::Invalid(s) = self;
        write!(f, "invalid notation: {s}")
    }
}

impl std::error::Error for NotationError {}

fn invalid<T>(msg: impl Into<String>) -> Result<T, NotationError> {
    Err(NotationError::Invalid(msg.into()))
}

/// Parses `577567`, `533523+` or `P*565`.
pub fn parse_move(s: &str) -> Result<Move, NotationError> {
    let b = s.as_bytes();
    if b.len() == 5 && b[1] == b'*' {
        let kind = match b[0] {
            c @ (b'P' | b'L' | b'N' | b'S' | b'G' | b'B' | b'R') => {
                PieceKind::from_letter(c as char).unwrap()
            }
            _ => return invalid(format!("bad drop piece in {s:?}")),
        };
        let to = Square::parse_ascii(&s[2..])
            .ok_or_else(|| NotationError::Invalid(format!("bad square in {s:?}")))?;
        return Ok(Move::Drop { kind, to });
    }
    let promote = match b.len() {
        6 => false,
        7 if b[6] == b'+' => true,
        _ => return invalid(format!("bad move string {s:?}")),
    };
    let sq = |r: std::ops::Range<usize>| {
        s.get(r)
            .and_then(Square::parse_ascii)
            .ok_or_else(|| NotationError::Invalid(format!("bad square in {s:?}")))
    };
    let (from, to) = (sq(0..3)?, sq(3..6)?);
    if from == to {
        return invalid(format!("null move {s:?}"));
    }
    Ok(Move::Normal { from, to, promote })
}

fn piece_str(p: Piece) -> String {
    p.to_string()
}

pub fn to_vsfen(g: &GameState) -> String {
    let board = g.board();
    let mut layers = Vec::with_capacity(SIZE);
    for z in 0..SIZE as u8 {
        let mut ranks = Vec::with_capacity(SIZE);
        for y in 0..SIZE as u8 {
            let mut rank = String::new();
            let mut empty = 0;
            for x in (0..SIZE as u8).rev() {
                match board.get(Square::new(x, y, z)) {
                    None => empty += 1,
                    Some(p) => {
                        if empty > 0 {
                            rank.push_str(&empty.to_string());
                            empty = 0;
                        }
                        rank.push_str(&piece_str(p));
                    }
                }
            }
            if empty > 0 {
                rank.push_str(&empty.to_string());
            }
            ranks.push(rank);
        }
        layers.push(ranks.join("/"));
    }
    let side = match g.side_to_move() {
        Color::Black => "b",
        Color::White => "w",
    };
    let mut hands = String::new();
    for color in Color::ALL {
        for i in HAND_ORDER {
            let n = g.hands()[color.index()][i];
            if n == 0 {
                continue;
            }
            if n > 1 {
                hands.push_str(&n.to_string());
            }
            hands.push_str(&piece_str(Piece::new(color, PieceKind::HAND[i])));
        }
    }
    if hands.is_empty() {
        hands.push('-');
    }
    format!("{} {side} {hands} {}", layers.join("|"), g.ply() + 1)
}

fn parse_rank(s: &str, y: u8, z: u8, board: &mut Board) -> Result<(), NotationError> {
    let mut x: i32 = SIZE as i32 - 1;
    let mut chars = s.chars().peekable();
    let mut prev_digit = false;
    while let Some(c) = chars.next() {
        if let Some(d) = c.to_digit(10) {
            if d == 0 || prev_digit {
                return invalid(format!("bad empty count in rank {s:?}"));
            }
            x -= d as i32;
            prev_digit = true;
            if x < -1 {
                return invalid(format!("rank {s:?} is longer than 9 squares"));
            }
            continue;
        }
        prev_digit = false;
        let promoted = c == '+';
        let letter = if promoted {
            chars
                .next()
                .ok_or_else(|| NotationError::Invalid(format!("dangling '+' in {s:?}")))?
        } else {
            c
        };
        let base = PieceKind::from_letter(letter)
            .ok_or_else(|| NotationError::Invalid(format!("unknown piece {letter:?}")))?;
        let kind = if promoted {
            base.promote()
                .ok_or_else(|| NotationError::Invalid(format!("{base:?} cannot be promoted")))?
        } else {
            base
        };
        let color = if letter.is_ascii_uppercase() {
            Color::Black
        } else {
            Color::White
        };
        if x < 0 {
            return invalid(format!("rank {s:?} is longer than 9 squares"));
        }
        board.set(Square::new(x as u8, y, z), Some(Piece::new(color, kind)));
        x -= 1;
    }
    if x != -1 {
        return invalid(format!("rank {s:?} does not have 9 squares"));
    }
    Ok(())
}

fn parse_hands(s: &str) -> Result<Hands, NotationError> {
    let mut hands: Hands = [[0; NUM_HAND_KINDS]; 2];
    if s == "-" {
        return Ok(hands);
    }
    let mut seen = [[false; NUM_HAND_KINDS]; 2];
    let mut count = String::new();
    for c in s.chars() {
        if c.is_ascii_digit() {
            count.push(c);
            if count.len() > 3 {
                return invalid("hand count too long");
            }
            continue;
        }
        let kind = PieceKind::from_letter(c)
            .ok_or_else(|| NotationError::Invalid(format!("bad hand piece {c:?}")))?;
        let i = kind
            .hand_index()
            .ok_or_else(|| NotationError::Invalid("a king cannot be in hand".into()))?;
        let color = if c.is_ascii_uppercase() {
            Color::Black
        } else {
            Color::White
        };
        let n: u32 = if count.is_empty() {
            1
        } else {
            count
                .parse()
                .map_err(|_| NotationError::Invalid("bad count".into()))?
        };
        if n == 0 || count.starts_with('0') || n > 162 {
            return invalid(format!("bad hand count {count:?}"));
        }
        if std::mem::replace(&mut seen[color.index()][i], true) {
            return invalid(format!("duplicate hand entry {c:?}"));
        }
        hands[color.index()][i] = n as u8;
        count.clear();
    }
    if !count.is_empty() {
        return invalid("hand count without a piece");
    }
    Ok(hands)
}

/// Parses and validates a VSFEN string (see [`GameState::validate`]).
pub fn from_vsfen(s: &str) -> Result<GameState, NotationError> {
    if s.len() > MAX_VSFEN_LEN {
        return invalid(format!("input too long ({} bytes)", s.len()));
    }
    let fields: Vec<&str> = s.split_ascii_whitespace().collect();
    let [board_s, side_s, hands_s, num_s] = fields[..] else {
        return invalid("expected 4 space-separated fields");
    };
    let layers: Vec<&str> = board_s.split('|').collect();
    if layers.len() != SIZE {
        return invalid(format!("expected 9 layers, got {}", layers.len()));
    }
    let mut board = Board::empty();
    for (z, layer) in layers.iter().enumerate() {
        let ranks: Vec<&str> = layer.split('/').collect();
        if ranks.len() != SIZE {
            return invalid(format!("layer {} has {} ranks", z + 1, ranks.len()));
        }
        for (y, rank) in ranks.iter().enumerate() {
            parse_rank(rank, y as u8, z as u8, &mut board)?;
        }
    }
    let side = match side_s {
        "b" => Color::Black,
        "w" => Color::White,
        _ => return invalid(format!("bad side {side_s:?}")),
    };
    let hands = parse_hands(hands_s)?;
    let number: u32 = num_s
        .parse()
        .map_err(|_| NotationError::Invalid(format!("bad move number {num_s:?}")))?;
    if number == 0 || number > 1_000_000 {
        return invalid(format!("bad move number {number}"));
    }
    let g = GameState::from_parts(board, hands, side).with_ply(number - 1);
    g.validate().map_err(NotationError::Invalid)?;
    Ok(g)
}
