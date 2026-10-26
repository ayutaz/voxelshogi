use serde_json::{Value, json};
use std::time::Duration;
use voxelshogi_core::search::{SearchLimits, SearchOptions, search};
use voxelshogi_core::session::Session;
use voxelshogi_core::{Board, Color, GameState, Piece, PieceKind, Square, notation};
use voxelshogi_wasm::search_api::best_move_with_clock;

fn kings(side: Color, ply: u32) -> Session {
    let mut b = Board::empty();
    b.set(
        Square::new(8, 8, 8),
        Some(Piece::new(Color::Black, PieceKind::King)),
    );
    b.set(
        Square::new(0, 0, 0),
        Some(Piece::new(Color::White, PieceKind::King)),
    );
    Session::from_vsfen(&notation::to_vsfen(
        &GameState::from_parts(b, [[0; 7]; 2], side).with_ply(ply),
    ))
    .unwrap()
}
fn run(s: &Session, config: Value) -> Value {
    serde_json::from_str(&best_move_with_clock(s, &config.to_string(), || Duration::ZERO).unwrap())
        .unwrap()
}

#[test]
fn adapter_matches_native_and_hand_counted_corner_king_tree_without_changing_cursor() {
    for side in Color::ALL {
        let mut s = kings(side, 41);
        let before = s.to_record_json();
        for (depth, expected_nodes) in [(0, 1), (1, 8), (2, 29)] {
            let r = run(&s, json!({"maxDepth":depth}));
            // Each corner king has seven moves. Depth 2: 1+7+7+6=21,
            // plus the completed eight-node depth-1 iteration.
            assert_eq!(r["score"], 0);
            assert_eq!(r["nodes"], expected_nodes.to_string());
            assert_eq!(r["completedDepth"], depth);
            assert_eq!(r["stopReason"], "depth");
            let native = search(
                s.state(),
                SearchLimits {
                    max_depth: depth as u8,
                    max_nodes: None,
                    max_time: None,
                    max_game_ply: None,
                },
                SearchOptions::default(),
            )
            .unwrap();
            assert_eq!(r["bestMove"], native.best_move.unwrap().to_string());
            assert_eq!(
                r["lastIterationNodes"],
                native.last_iteration_nodes.to_string()
            );
            assert_eq!(r["ttHits"], native.tt_hits.to_string());
        }
        assert_eq!(s.to_record_json(), before);
        assert_eq!(s.cursor(), 0);
        assert_eq!(s.state().ply(), 41);
        assert_eq!(
            run(&s, json!({"maxDepth":2,"maxGamePly":41}))["stopReason"],
            "terminal"
        );
        assert_ne!(
            run(&s, json!({"maxDepth":0,"maxGamePly":42}))["bestMove"],
            Value::Null
        );
        let mv = run(&s, json!({"maxDepth":1}))["bestMove"]
            .as_str()
            .unwrap()
            .to_owned();
        s.play(&mv).unwrap();
        s.undo();
        let with_future = s.to_record_json();
        run(&s, json!({"maxDepth":1}));
        assert_eq!(s.cursor(), 0);
        assert_eq!(s.len(), 1);
        assert_eq!(s.to_record_json(), with_future);
    }
}

#[test]
fn incomplete_iterations_have_null_scores_and_clock_is_injected() {
    let s = kings(Color::Black, 0);
    for nodes in [0, 1, 9] {
        let r = run(&s, json!({"maxDepth":4,"maxNodes":nodes}));
        assert_eq!(r["nodes"], nodes.to_string());
        assert_eq!(r["stopReason"], "nodes");
        assert_eq!(r["score"], if nodes == 9 { json!(0) } else { Value::Null });
        assert_eq!(r["completedDepth"], if nodes == 9 { 1 } else { 0 });
        assert!(
            s.state()
                .is_legal(&notation::parse_move(r["bestMove"].as_str().unwrap()).unwrap())
        );
    }
    let r: Value = serde_json::from_str(
        &best_move_with_clock(&s, r#"{"maxDepth":4,"maxTimeMs":0.5}"#, || {
            Duration::from_micros(500)
        })
        .unwrap(),
    )
    .unwrap();
    assert_eq!(r["stopReason"], "time");
    assert_eq!(r["nodes"], "0");
    assert_eq!(r["score"], Value::Null);
    let r = run(
        &s,
        json!({"maxDepth":2,"options":{"iterativeDeepening":false,"moveOrdering":false,"transpositionTable":false,"tableCapacity":0}}),
    );
    assert_eq!(r["nodes"], "21");
    assert_eq!(r["score"], 0);
}

#[test]
fn terminal_records_do_not_produce_fallback_moves() {
    let mut s = kings(Color::White, 0);
    s.resign();
    let r = run(&s, json!({"maxDepth":0,"maxNodes":0,"maxTimeMs":0}));
    assert_eq!(r["bestMove"], Value::Null);
    assert_eq!(r["score"], -1_000_000);
    assert_eq!(r["stopReason"], "terminal");
    for (termination, result, score) in [
        ("MaxPlies", json!({"Draw":{"reason":"MaxPlies"}}), json!(0)),
        ("Abandoned", Value::Null, Value::Null),
    ] {
        let mut record: Value =
            serde_json::from_str(&kings(Color::Black, 0).to_record_json()).unwrap();
        record["termination"] = json!(termination);
        record["result"] = result;
        let s = Session::from_record_json(&record.to_string()).unwrap();
        let r = run(&s, json!({"maxDepth":1}));
        assert_eq!(r["bestMove"], Value::Null);
        assert_eq!(r["score"], score);
        assert_eq!(r["stopReason"], "terminal");
        assert_eq!(r["nodes"], "0");
    }
}

#[test]
fn rejects_unsafe_numbers_unknown_fields_and_invalid_options_even_at_terminal() {
    let mut s = kings(Color::Black, 0);
    s.resign();
    for bad in [
        "{}",
        "null",
        r#"{"maxDepth":65}"#,
        r#"{"maxDepth":-1}"#,
        r#"{"maxDepth":1.5}"#,
        r#"{"maxDepth":1,"maxNodes":9007199254740992}"#,
        r#"{"maxDepth":1,"maxNodes":-1}"#,
        r#"{"maxDepth":1,"maxNodes":1.5}"#,
        r#"{"maxDepth":1,"maxTimeMs":-0.1}"#,
        r#"{"maxDepth":1,"maxTimeMs":1e999}"#,
        r#"{"maxDepth":1,"maxTimeMs":9007199254740992}"#,
        r#"{"maxDepth":1,"maxGamePly":4294967296}"#,
        r#"{"maxDepth":1,"options":{"tableCapacity":1000001}}"#,
        r#"{"maxDepth":1,"options":{"tableCapacity":-1}}"#,
        r#"{"maxDepth":1,"maxNode":5}"#,
        r#"{"maxDepth":1,"options":{"moveOrder":false}}"#,
        r#"{"maxDepth":1,"options":{"moveOrdering":1}}"#,
    ] {
        assert!(
            best_move_with_clock(&s, bad, || Duration::ZERO).is_err(),
            "accepted {bad}"
        );
    }
    assert!(best_move_with_clock(&s, &" ".repeat(4097), || Duration::ZERO).is_err());
    assert!(best_move_with_clock(&s, r#"{"maxDepth":64,"maxNodes":9007199254740991,"maxTimeMs":0,"maxGamePly":4294967295,"options":{"tableCapacity":1000000}}"#, || Duration::ZERO).is_ok());
}

#[test]
fn native_executes_shared_hand_counted_wasm_fixtures() {
    let fixtures: Vec<Value> = serde_json::from_str(include_str!("fixtures/search.json")).unwrap();
    assert_eq!(fixtures.len(), 12);
    for f in fixtures {
        let s = Session::from_record_json(&f["record"].to_string()).unwrap();
        let r = run(&s, f["config"].clone());
        for (key, expected) in f["expected"].as_object().unwrap() {
            assert_eq!(&r[key], expected, "{}: {key}", f["name"]);
        }
        if let Some(winner) = f.get("mateWinner") {
            let mut next = s.clone();
            next.play(r["bestMove"].as_str().unwrap()).unwrap();
            assert_eq!(
                serde_json::to_value(next.result()).unwrap(),
                json!({"Win":{"winner":winner,"reason":"Checkmate"}})
            );
        }
    }
}
