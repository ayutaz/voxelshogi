//! Session: the interactive game model used by the web UI (move list with a cursor,
//! undo/redo, record import/export).

mod common;

use voxelshogi_core::notation::to_vsfen;
use voxelshogi_core::record::{GameRecord, Termination};
use voxelshogi_core::session::Session;
use voxelshogi_core::{Color, GameResult, GameState, WinReason};

fn first_moves(n: usize) -> Vec<String> {
    let mut g = GameState::new();
    let mut out = Vec::new();
    for _ in 0..n {
        let m = g.legal_moves()[0];
        out.push(m.to_string());
        g = g.apply_move(&m).unwrap();
    }
    out
}

#[test]
fn new_session_starts_at_initial_position() {
    let s = Session::new();
    assert_eq!(s.cursor(), 0);
    assert_eq!(s.len(), 0);
    assert_eq!(s.state().hash(), GameState::new().hash());
    assert!(!s.can_undo() && !s.can_redo());
}

#[test]
fn emptiness_tracks_the_record_and_goto_accepts_both_endpoints() {
    let mut session = Session::new();
    assert!(session.is_empty());
    session.goto(0).unwrap();
    session.play("577567").unwrap();
    assert!(!session.is_empty());
    let after = session.state().hash();
    session.goto(1).unwrap();
    assert_eq!(session.state().hash(), after);
    session.goto(0).unwrap();
    assert!(!session.is_empty(), "undo retains the move in the record");
    session.goto(1).unwrap();
    assert_eq!(session.state().hash(), after);
    assert!(session.goto(2).is_err());
    assert_eq!(session.cursor(), 1);
}

#[test]
fn play_advances_and_rejects_illegal_moves_without_changing_state() {
    let mut s = Session::new();
    let before = s.state().hash();
    assert!(s.play("555554").is_err());
    assert!(s.play("garbage").is_err());
    assert_eq!(s.state().hash(), before);
    assert_eq!(s.len(), 0);
    s.play("577567").unwrap();
    assert_eq!(s.cursor(), 1);
    assert_eq!(s.state().side_to_move(), Color::White);
    assert_eq!(s.moves(), &["577567".to_string()]);
}

#[test]
fn undo_redo_and_goto_move_the_cursor_and_restore_exact_states() {
    let mut s = Session::new();
    let mv = first_moves(6);
    let mut hashes = vec![s.state().hash()];
    for m in &mv {
        s.play(m).unwrap();
        hashes.push(s.state().hash());
    }
    assert!(s.undo());
    assert_eq!(s.cursor(), 5);
    assert_eq!(s.state().hash(), hashes[5]);
    assert!(s.redo());
    assert_eq!(s.state().hash(), hashes[6]);
    assert!(!s.redo());
    s.goto(2).unwrap();
    assert_eq!(s.state().hash(), hashes[2]);
    assert_eq!(s.len(), 6, "goto does not discard the future");
    assert!(s.goto(7).is_err());
    s.goto(0).unwrap();
    assert!(!s.undo());
    assert_eq!(s.state().hash(), hashes[0]);
}

#[test]
fn playing_after_undo_truncates_the_future() {
    let mut s = Session::new();
    for m in first_moves(4) {
        s.play(&m).unwrap();
    }
    s.goto(2).unwrap();
    let alt = s.state().legal_moves()[1].to_string();
    s.play(&alt).unwrap();
    assert_eq!(s.len(), 3);
    assert_eq!(s.cursor(), 3);
    assert!(!s.can_redo());
    assert_eq!(s.moves()[2], alt);
}

#[test]
fn record_export_import_roundtrip_including_resignation() {
    let mut s = Session::new();
    for m in first_moves(5) {
        s.play(&m).unwrap();
    }
    s.resign();
    assert_eq!(
        s.state().result(),
        Some(GameResult::Win {
            winner: Color::Black,
            reason: WinReason::Resignation
        })
    );
    assert!(
        s.play(
            &s.state()
                .legal_moves()
                .first()
                .map(|m| m.to_string())
                .unwrap_or_default()
        )
        .is_err()
    );
    let json = s.to_record_json();
    let rec = GameRecord::from_json(&json).unwrap();
    assert_eq!(rec.termination, Some(Termination::Resignation));
    assert_eq!(rec.initial, to_vsfen(&GameState::new()));
    let t = Session::from_record_json(&json).unwrap();
    assert_eq!(t.len(), 5);
    assert_eq!(t.cursor(), 5);
    assert_eq!(t.state().result(), s.state().result());
    // stepping back from a resigned game re-opens play
    let mut t = t;
    t.goto(4).unwrap();
    assert_eq!(t.state().result(), None);
}

#[test]
fn import_rejects_invalid_records() {
    assert!(Session::from_record_json("{}").is_err());
    let mut s = Session::new();
    for m in first_moves(3) {
        s.play(&m).unwrap();
    }
    let json = s.to_record_json().replace(&s.moves()[1], "111112");
    assert!(Session::from_record_json(&json).is_err());
}

#[test]
fn session_from_vsfen_uses_that_start_position() {
    let g = GameState::new()
        .apply_move(&GameState::new().legal_moves()[0])
        .unwrap();
    let v = to_vsfen(&g);
    let s = Session::from_vsfen(&v).unwrap();
    assert_eq!(s.state().hash(), g.hash());
    assert_eq!(s.state().side_to_move(), Color::White);
    assert!(Session::from_vsfen("bad").is_err());
    let rec = GameRecord::from_json(&s.to_record_json()).unwrap();
    assert_eq!(rec.initial, v);
}

#[test]
fn external_termination_survives_export_and_only_applies_at_record_end() {
    use voxelshogi_core::DrawReason;
    for termination in [Termination::MaxPlies, Termination::Abandoned] {
        let expected = (termination == Termination::MaxPlies).then_some(GameResult::Draw {
            reason: DrawReason::MaxPlies,
        });
        let record = GameRecord {
            ruleset_id: voxelshogi_core::record::RULESET_ID.into(),
            initial: to_vsfen(&GameState::new()),
            moves: vec!["577567".into(), "533543".into()],
            result: expected,
            termination: Some(termination),
        };
        let mut s = Session::from_record_json(&record.to_json()).unwrap();
        assert_eq!(s.result(), expected);
        assert_eq!(s.termination(), Some(termination));
        assert!(s.is_finished());
        let before = s.to_record_json();
        assert!(
            s.play("567557").is_err(),
            "externally stopped games cannot advance"
        );
        s.resign();
        assert_eq!(
            s.to_record_json(),
            before,
            "a finished result cannot be replaced"
        );
        assert_eq!(GameRecord::from_json(&before).unwrap(), record);
        assert!(s.undo());
        assert_eq!(s.result(), None);
        assert_eq!(s.termination(), None);
        assert!(!s.is_finished());
        assert_eq!(
            s.to_record_json(),
            before,
            "export includes the redo future"
        );
        assert!(s.redo());
        assert!(s.is_finished());
        s.goto(0).unwrap();
        assert!(s.play("577567").is_ok());
        assert!(!s.is_finished());
        let branched = GameRecord::from_json(&s.to_record_json()).unwrap();
        assert_eq!(branched.moves, ["577567"]);
        assert_eq!(branched.termination, None);
        assert_eq!(branched.result, None);
        branched.replay().unwrap();
    }
}

#[test]
fn resignation_at_an_earlier_cursor_replaces_future_external_termination() {
    let record = GameRecord {
        ruleset_id: voxelshogi_core::record::RULESET_ID.into(),
        initial: to_vsfen(&GameState::new()),
        moves: vec!["577567".into()],
        result: None,
        termination: Some(Termination::Abandoned),
    };
    let mut s = Session::from_record_json(&record.to_json()).unwrap();
    s.goto(0).unwrap();
    s.resign();
    assert_eq!(
        s.result(),
        Some(GameResult::Win {
            winner: Color::White,
            reason: WinReason::Resignation,
        })
    );
    assert_eq!(s.termination(), Some(Termination::Resignation));
    let saved = GameRecord::from_json(&s.to_record_json()).unwrap();
    assert!(saved.moves.is_empty());
    assert_eq!(saved.termination, Some(Termination::Resignation));
    saved.replay().unwrap();
}

#[test]
fn imported_resignation_retains_the_exact_validated_replay_result() {
    use voxelshogi_core::{Board, Piece, PieceKind, Square};
    for winner in Color::ALL {
        let sq = |x, y, z| {
            if winner == Color::Black {
                Square::new(x, y, z)
            } else {
                Square::new(8 - x, 8 - y, 8 - z)
            }
        };
        let mut board = Board::empty();
        for (at, color, kind) in [
            (sq(0, 0, 0), winner.opponent(), PieceKind::King),
            (sq(8, 8, 8), winner, PieceKind::King),
            (sq(2, 2, 2), winner, PieceKind::Gold),
            (sq(1, 1, 1), winner, PieceKind::Dragon),
        ] {
            board.set(at, Some(Piece::new(color, kind)));
        }
        let game = GameState::from_parts(board, [[0; 7]; 2], winner.opponent());
        assert_eq!(
            game.result(),
            Some(GameResult::Win {
                winner,
                reason: WinReason::Checkmate
            })
        );
        // Existing record validation accepts a recorded resignation at this
        // position. Import/export must retain that validated result exactly.
        let expected = Some(GameResult::Win {
            winner,
            reason: WinReason::Resignation,
        });
        let record = GameRecord {
            ruleset_id: voxelshogi_core::record::RULESET_ID.into(),
            initial: to_vsfen(&game),
            moves: vec![],
            result: expected,
            termination: Some(Termination::Resignation),
        };
        assert_eq!(record.replay().unwrap().result(), expected);
        let imported = Session::from_record_json(&record.to_json()).unwrap();
        assert_eq!(imported.result(), expected);
        assert_eq!(
            GameRecord::from_json(&imported.to_record_json()).unwrap(),
            record
        );
        // An interactive resignation still cannot overwrite an already finished game.
        let mut interactive = Session::from_vsfen(&record.initial).unwrap();
        interactive.resign();
        assert_eq!(
            interactive.result(),
            Some(GameResult::Win {
                winner,
                reason: WinReason::Checkmate
            })
        );
    }
}
