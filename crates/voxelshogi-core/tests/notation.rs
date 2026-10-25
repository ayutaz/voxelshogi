//! Text notation (VSFEN positions, move strings) and game records.

mod common;

use common::*;
use voxelshogi_core::notation::{NotationError, from_vsfen, parse_move, to_vsfen};
use voxelshogi_core::record::{GameRecord, RULESET_ID, RecordError, Termination};
use voxelshogi_core::{Board, Color, GameResult, GameState, Move, PieceKind, Square, WinReason};

#[test]
fn import_error_text_retains_the_reason_and_offending_move() {
    assert_eq!(
        NotationError::Invalid("bad square".into()).to_string(),
        "invalid notation: bad square"
    );
    assert_eq!(
        RecordError::BadMoveString {
            index: 2,
            text: "bad".into(),
        }
        .to_string(),
        "BadMoveString { index: 2, text: \"bad\" }"
    );
    let mut session = voxelshogi_core::session::Session::new();
    assert_eq!(
        session.play("bad"),
        Err("invalid notation: bad move string \"bad\"".into())
    );
}
const EMPTY_LAYER: &str = "9/9/9/9/9/9/9/9/9";

fn kings_only_vsfen(side: char, hands: &str) -> String {
    let mid = "4k4/9/9/9/9/9/9/9/4K4";
    let layers: Vec<&str> = (0..9)
        .map(|z| if z == 4 { mid } else { EMPTY_LAYER })
        .collect();
    format!("{} {side} {hands} 1", layers.join("|"))
}

#[test]
fn vsfen_requires_single_nonzero_empty_counts_and_canonical_hand_counts() {
    let valid = kings_only_vsfen('b', "-");
    for rank in ["09", "45"] {
        assert!(from_vsfen(&valid.replacen('9', rank, 1)).is_err());
    }
    for hands in ["01P", "001P", "0162P"] {
        assert!(from_vsfen(&kings_only_vsfen('b', hands)).is_err());
    }
    // The set contains 162 pawns. All may be in hand in a partial position.
    let parsed = from_vsfen(&kings_only_vsfen('b', "162P")).unwrap();
    assert_eq!(
        parsed.hands()[0][PieceKind::Pawn.hand_index().unwrap()],
        162
    );
}

#[test]
fn vsfen_accepts_exact_size_and_move_number_limits_but_rejects_larger_inputs() {
    let valid = kings_only_vsfen('b', "-");
    for bytes in [4095, 4096, 4097, 4098] {
        let padded = format!("{valid}{}", " ".repeat(bytes - valid.len()));
        let result = from_vsfen(&padded);
        assert_eq!(result.is_ok(), bytes <= 4096, "{bytes} bytes");
        if bytes > 4096 {
            assert_eq!(
                result.unwrap_err().to_string(),
                format!("invalid notation: input too long ({bytes} bytes)")
            );
        }
    }
    for number in [999_999, 1_000_000, 1_000_001, 1_000_002] {
        let position = valid.strip_suffix('1').unwrap().to_owned() + &number.to_string();
        match from_vsfen(&position) {
            Ok(g) => {
                assert!(number <= 1_000_000);
                assert_eq!(g.ply(), number - 1);
            }
            Err(_) => assert!(number > 1_000_000),
        }
    }
}

#[test]
fn record_move_limits_apply_to_json_and_replay_before_processing_moves() {
    for count in [19_999, 20_000, 20_001, 20_002] {
        let record = GameRecord {
            ruleset_id: RULESET_ID.into(),
            initial: kings_only_vsfen('b', "-"),
            moves: vec!["bad".into(); count],
            result: None,
            termination: None,
        };
        let parsed = GameRecord::from_json(&record.to_json());
        if count <= 20_000 {
            assert_eq!(parsed.unwrap(), record);
            // Within the limit, replay must proceed to validating the first move.
            assert_eq!(
                record.replay().unwrap_err(),
                RecordError::BadMoveString {
                    index: 0,
                    text: "bad".into()
                }
            );
        } else {
            assert_eq!(parsed.unwrap_err(), RecordError::TooLong(count));
            assert_eq!(record.replay().unwrap_err(), RecordError::TooLong(count));
        }
    }
}

#[test]
fn record_json_accepts_exact_byte_limit_and_rejects_larger_valid_json() {
    let record = GameRecord {
        ruleset_id: RULESET_ID.into(),
        initial: kings_only_vsfen('b', "-"),
        moves: vec![],
        result: None,
        termination: None,
    };
    let json = record.to_json();
    for bytes in [4_194_303, 4_194_304, 4_194_305, 4_194_306] {
        let padded = format!("{json}{}", " ".repeat(bytes - json.len()));
        let parsed = GameRecord::from_json(&padded);
        if bytes <= 4_194_304 {
            assert_eq!(parsed.unwrap(), record);
        } else {
            assert_eq!(parsed.unwrap_err(), RecordError::TooLong(bytes));
        }
    }
}

// ------------------------------------------------------------------ moves

#[test]
fn move_strings_use_file_rank_layer_digits() {
    let m = Move::Normal {
        from: sq(4, 6, 6),
        to: sq(4, 5, 6),
        promote: false,
    };
    assert_eq!(m.to_string(), "577567");
    let m = Move::Normal {
        from: sq(4, 2, 2),
        to: sq(4, 1, 2),
        promote: true,
    };
    assert_eq!(m.to_string(), "533523+");
    let m = Move::Drop {
        kind: PieceKind::Pawn,
        to: sq(4, 5, 4),
    };
    assert_eq!(m.to_string(), "P*565");
    assert_eq!(
        Move::Drop {
            kind: PieceKind::Rook,
            to: sq(0, 0, 0)
        }
        .to_string(),
        "R*111"
    );
}

#[test]
fn move_strings_parse_and_reject_garbage() {
    assert_eq!(
        parse_move("577567"),
        Ok(Move::Normal {
            from: sq(4, 6, 6),
            to: sq(4, 5, 6),
            promote: false
        })
    );
    assert_eq!(
        parse_move("533523+"),
        Ok(Move::Normal {
            from: sq(4, 2, 2),
            to: sq(4, 1, 2),
            promote: true
        })
    );
    assert_eq!(
        parse_move("G*999"),
        Ok(Move::Drop {
            kind: PieceKind::Gold,
            to: sq(8, 8, 8)
        })
    );
    for bad in [
        "", "57756", "5775670", "077567", "577567++", "K*555", "+P*555", "p*555", "P*55", "P-555",
        "577577",
    ] {
        assert!(parse_move(bad).is_err(), "{bad:?} should be rejected");
    }
}

#[test]
fn every_legal_move_roundtrips_through_its_string() {
    let mut rng = Rng(7);
    let mut g = GameState::new();
    for _ in 0..40 {
        let moves = g.legal_moves();
        for m in &moves {
            assert_eq!(parse_move(&m.to_string()), Ok(*m));
        }
        g = g
            .apply_move(&moves[rng.below(moves.len() as u64) as usize])
            .unwrap();
    }
}

// ------------------------------------------------------------------ VSFEN

#[test]
fn vsfen_of_a_hand_written_position() {
    let board = board_with(&[
        (sq(4, 8, 4), Color::Black, PieceKind::King),
        (sq(4, 0, 4), Color::White, PieceKind::King),
    ]);
    let g = GameState::from_parts(board, [[0; 7]; 2], Color::Black);
    assert_eq!(to_vsfen(&g), kings_only_vsfen('b', "-"));
}

#[test]
fn vsfen_lists_files_from_nine_to_one_and_marks_promotion_and_colour() {
    // (x=8,y=0,z=0) is file 9 → first character of the first rank of layer I.
    let board = board_with(&[
        (sq(8, 0, 0), Color::White, PieceKind::Dragon),
        (sq(0, 0, 0), Color::Black, PieceKind::Tokin),
        (sq(4, 8, 4), Color::Black, PieceKind::King),
        (sq(4, 0, 4), Color::White, PieceKind::King),
    ]);
    let mut hands = [[0u8; 7]; 2];
    hands[0][PieceKind::Pawn.hand_index().unwrap()] = 12;
    hands[0][PieceKind::Rook.hand_index().unwrap()] = 1;
    hands[1][PieceKind::Gold.hand_index().unwrap()] = 2;
    let g = GameState::from_parts(board, hands, Color::White);
    let s = to_vsfen(&g);
    assert!(s.starts_with("+r7+P/9/"), "{s}");
    // hands: Black first then White, each in R B G S N L P order, count before letter if > 1
    assert!(s.ends_with(" w R12P2g 1"), "{s}");
}

#[test]
fn initial_position_vsfen_roundtrips_and_matches_new_game() {
    let g = GameState::new();
    let s = to_vsfen(&g);
    let parsed = from_vsfen(&s).unwrap();
    assert_eq!(parsed.board(), &Board::initial());
    assert_eq!(parsed.side_to_move(), Color::Black);
    assert_eq!(parsed.hash(), g.hash());
    assert_eq!(to_vsfen(&parsed), s);
    // layer I, rank 一 (White's back rank): every square is on ring 4 → lances.
    assert!(s.starts_with("lllllllll/"), "{s}");
}

#[test]
fn vsfen_roundtrips_random_reachable_positions() {
    let mut rng = Rng(99);
    let mut g = GameState::new();
    for ply in 0..80 {
        let s = to_vsfen(&g);
        let p = from_vsfen(&s).unwrap_or_else(|e| panic!("ply {ply}: {e:?}\n{s}"));
        assert_eq!(p.board(), g.board());
        assert_eq!(p.hands(), g.hands());
        assert_eq!(p.side_to_move(), g.side_to_move());
        assert_eq!(p.hash(), g.hash());
        let moves = g.legal_moves();
        let caps: Vec<&Move> = moves
            .iter()
            .filter(|m| !g.board().is_empty(m.to()))
            .collect();
        let mv = if !caps.is_empty() {
            *caps[rng.below(caps.len() as u64) as usize]
        } else {
            moves[rng.below(moves.len() as u64) as usize]
        };
        g = g.apply_move(&mv).unwrap();
    }
    assert!(
        g.hands().iter().flatten().any(|&n| n > 0),
        "the walk should have produced pieces in hand"
    );
}

#[test]
fn vsfen_rejects_malformed_and_impossible_positions() {
    let ok = kings_only_vsfen('b', "-");
    assert!(from_vsfen(&ok).is_ok());
    let cases: Vec<(String, &str)> = vec![
        (String::new(), "empty"),
        (ok.replace(" b ", " x "), "bad side"),
        (ok.replacen("9/9/9/9/9/9/9/9/9|", "", 1), "8 layers"),
        (format!("{EMPTY_LAYER}|{ok}"), "10 layers"),
        (
            ok.replacen("9/9/9/9/9/9/9/9/9", "9/9/9/9/9/9/9/9", 1),
            "8 ranks",
        ),
        (ok.replacen("4k4", "5k4", 1), "rank too long"),
        (ok.replacen("4k4", "3k4", 1), "rank too short"),
        (ok.replacen("4k4", "4x4", 1), "unknown piece"),
        (ok.replacen("4k4", "4+k4", 1), "promoted king"),
        (ok.replacen("4k4", "4+g4", 1), "promoted gold"),
        (ok.replacen("4k4", "9", 1), "missing white king"),
        (
            ok.replacen("9/9/9/9/9/9/9/9/9", "k8/9/9/9/9/9/9/9/9", 1),
            "two white kings",
        ),
        (kings_only_vsfen('b', "K"), "king in hand"),
        (kings_only_vsfen('b', "0P"), "zero count"),
        (kings_only_vsfen('b', "163P"), "too many pawns"),
        (kings_only_vsfen('b', "PP"), "duplicate hand entry"),
        (ok.replacen(" 1", " 0", 1), "move number 0"),
        (ok.replacen(" 1", "", 1), "missing move number"),
        // a Black pawn on rank 一 can never move
        (
            ok.replacen("9/9/9/9/9/9/9/9/9", "P8/9/9/9/9/9/9/9/9", 1),
            "dead pawn",
        ),
        // two Black pawns in one (file, layer) column
        (
            ok.replacen("9/9/9/9/9/9/9/9/9", "9/P8/P8/9/9/9/9/9/9", 1),
            "nifu on board",
        ),
        // White (not to move) is in check from a Black lance on the same file below it
        (
            ok.replacen("4k4/9/9/9/9/9/9/9/4K4", "4k4/4L4/9/9/9/9/9/9/4K4", 1),
            "side not to move in check",
        ),
    ];
    for (s, why) in cases {
        assert!(
            matches!(from_vsfen(&s), Err(NotationError::Invalid(_))),
            "{why}: {s:?} should be rejected"
        );
    }
    // a huge input is rejected without heavy work
    assert!(from_vsfen(&"9".repeat(1 << 20)).is_err());
}

#[test]
fn vsfen_piece_totals_cannot_exceed_the_set() {
    // 25 Black rooks on the board + hand is more than the 24 rooks in the set.
    let mut layers = vec![EMPTY_LAYER.to_string(); 9];
    layers[4] = "4k4/9/9/9/9/9/9/9/4K4".to_string();
    layers[0] = "RRRRRRRRR/RRRRRRRRR/9/9/9/9/9/9/9".to_string();
    // (White is in check from these rooks, so White must be the side to move.)
    let s = format!("{} w 7R 1", layers.join("|"));
    assert!(from_vsfen(&s).is_err());
    let s = format!("{} w 6R 1", layers.join("|"));
    assert!(from_vsfen(&s).is_ok());
}

// ------------------------------------------------------------------ game records

fn play_random(seed: u64, plies: usize) -> (GameState, Vec<Move>) {
    let mut rng = Rng(seed);
    let mut g = GameState::new();
    let mut moves = Vec::new();
    for _ in 0..plies {
        let legal = g.legal_moves();
        if legal.is_empty() {
            break;
        }
        let m = legal[rng.below(legal.len() as u64) as usize];
        g = g.apply_move(&m).unwrap();
        moves.push(m);
    }
    (g, moves)
}

#[test]
fn record_carries_ruleset_id_and_replays_to_the_same_state() {
    let (end, moves) = play_random(3, 30);
    let rec = GameRecord::from_moves(&GameState::new(), &moves);
    assert_eq!(rec.ruleset_id, RULESET_ID);
    assert_eq!(RULESET_ID, "voxelshogi-standard-v1");
    assert_eq!(rec.moves.len(), 30);
    let replayed = rec.replay().unwrap();
    assert_eq!(replayed.hash(), end.hash());
    assert_eq!(replayed.ply(), 30);
}

#[test]
fn record_json_roundtrip() {
    let (_, moves) = play_random(5, 20);
    let mut rec = GameRecord::from_moves(&GameState::new(), &moves);
    rec.termination = Some(Termination::MaxPlies);
    let json = rec.to_json();
    let back = GameRecord::from_json(&json).unwrap();
    assert_eq!(back, rec);
    assert!(json.contains("\"ruleset_id\":\"voxelshogi-standard-v1\""));
}

#[test]
fn tampered_records_are_rejected_with_the_offending_index() {
    let (_, moves) = play_random(11, 10);
    let mut rec = GameRecord::from_moves(&GameState::new(), &moves);
    rec.moves[6] = "555554".into(); // empty source square at that point
    match rec.replay() {
        Err(RecordError::IllegalMove { index, .. }) => assert_eq!(index, 6),
        other => panic!("expected IllegalMove, got {other:?}"),
    }
    let mut rec2 = GameRecord::from_moves(&GameState::new(), &moves);
    rec2.moves[2] = "nonsense".into();
    assert!(matches!(
        rec2.replay(),
        Err(RecordError::BadMoveString { index: 2, .. })
    ));
    let mut rec3 = GameRecord::from_moves(&GameState::new(), &moves);
    rec3.ruleset_id = "some-other-rules".into();
    assert!(matches!(
        rec3.replay(),
        Err(RecordError::UnsupportedRuleset(_))
    ));
    assert!(GameRecord::from_json("{not json").is_err());
    let huge = format!(
        "{{\"ruleset_id\":\"{RULESET_ID}\",\"initial\":\"x\",\"moves\":[{}]}}",
        vec!["\"577567\""; 20_001].join(",")
    );
    assert!(matches!(
        GameRecord::from_json(&huge),
        Err(RecordError::TooLong(_))
    ));
}

#[test]
fn record_result_is_recomputed_on_replay() {
    // A record claiming a result is checked against the replay.
    let board = board_with(&[
        (sq(0, 0, 0), Color::White, PieceKind::King),
        (sq(1, 2, 1), Color::Black, PieceKind::Dragon),
        (sq(2, 2, 2), Color::Black, PieceKind::Gold), // protects (1,1,1)
        (sq(8, 8, 8), Color::Black, PieceKind::King),
    ]);
    let start = GameState::from_parts(board, [[0; 7]; 2], Color::Black);
    let mate = Move::Normal {
        from: sq(1, 2, 1),
        to: sq(1, 1, 1),
        promote: false,
    };
    let after = start.apply_move(&mate).unwrap();
    assert_eq!(
        after.result(),
        Some(GameResult::Win {
            winner: Color::Black,
            reason: WinReason::Checkmate
        })
    );
    let rec = GameRecord::from_moves(&start, &[mate]);
    assert_eq!(rec.result, after.result());
    assert_eq!(rec.replay().unwrap().result(), rec.result);
    let mut lying = rec.clone();
    lying.result = Some(GameResult::Win {
        winner: Color::White,
        reason: WinReason::Checkmate,
    });
    assert!(matches!(
        lying.replay(),
        Err(RecordError::ResultMismatch { .. })
    ));
    let _ = Square::new(0, 0, 0);
}
