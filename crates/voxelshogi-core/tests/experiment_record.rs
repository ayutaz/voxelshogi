use voxelshogi_core::capture::CaptureGame;
use voxelshogi_core::capture::CaptureRule;
use voxelshogi_core::experiment::{ExperimentRecord, Replay, SearchConfig, choose_move};

#[test]
fn complete_record_replays_and_rejects_forgery() {
    let config = SearchConfig { depth: 2, width: 4 };
    let record =
        ExperimentRecord::play(CaptureRule::ScoreLimit, 2, 17, false, config, "fixture").unwrap();
    assert_eq!(record.moves.len(), 2);
    let text = serde_json::to_string(&record).unwrap();
    let replay = Replay::from_json(&text).unwrap();
    assert_eq!(replay.len(), 2);
    assert_eq!(
        format!("{:016x}", replay.state(2).unwrap().hash()),
        record.final_hash
    );
    assert_eq!(replay.state(2).unwrap().outcome(), Some(record.outcome));
    assert!(replay.state(3).is_err());
    for key in ["final_hash", "ruleset_id"] {
        let mut v: serde_json::Value = serde_json::from_str(&text).unwrap();
        v[key] = "forged".into();
        assert!(Replay::from_json(&v.to_string()).is_err());
    }
    let mut v: serde_json::Value = serde_json::from_str(&text).unwrap();
    v["moves"][0] = "111111".into();
    assert!(Replay::from_json(&v.to_string()).is_err());
    let mut v: serde_json::Value = serde_json::from_str(&text).unwrap();
    v["outcome"]["winner"] = "Black".into();
    assert!(Replay::from_json(&v.to_string()).is_err());
    let mut v: serde_json::Value = serde_json::from_str(&text).unwrap();
    v["max_plies"] = 3.into();
    assert!(Replay::from_json(&v.to_string()).is_err());
    assert!(voxelshogi_core::record::GameRecord::from_json(&text).is_err());
    assert!(Replay::from_json(&" ".repeat(4 * 1024 * 1024 + 1)).is_err());
}
#[test]
fn bounded_search_is_reproducible_and_returns_legal_moves() {
    let g = CaptureGame::new(CaptureRule::AllKings, 400).unwrap();
    let c = SearchConfig { depth: 2, width: 8 };
    let a = choose_move(&g, c, 42).unwrap();
    let b = choose_move(&g, c, 42).unwrap();
    assert_eq!(a, b);
    assert!(g.legal_moves().contains(&a.0));
    assert!(a.1 > 8);
    assert!(choose_move(&g, SearchConfig { depth: 0, width: 8 }, 0).is_err());
}

#[test]
fn standard_baseline_uses_existing_rules_and_verified_record() {
    let r = voxelshogi_core::experiment::play_baseline(
        2,
        17,
        false,
        SearchConfig { depth: 2, width: 4 },
        "fixture",
    )
    .unwrap();
    assert_eq!(r.record.moves.len(), 2);
    let g = r.record.replay().unwrap();
    assert_eq!(format!("{:016x}", g.hash()), r.final_hash);
    assert_eq!(r.record.ruleset_id, "voxelshogi-standard-v1");
    assert_eq!(
        r,
        voxelshogi_core::experiment::play_baseline(
            2,
            17,
            false,
            SearchConfig { depth: 2, width: 4 },
            "fixture"
        )
        .unwrap()
    );
}
