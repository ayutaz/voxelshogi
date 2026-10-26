//! Emit complete native results for the real-WASM CI parity check.
use std::time::Duration;
use voxelshogi_core::session::Session;
use voxelshogi_wasm::search_api::best_move_with_clock;

fn main() {
    let fixtures: Vec<serde_json::Value> =
        serde_json::from_str(include_str!("../tests/fixtures/search.json")).unwrap();
    let results: Vec<serde_json::Value> = fixtures
        .iter()
        .map(|f| {
            let s = Session::from_record_json(&f["record"].to_string()).unwrap();
            serde_json::from_str(
                &best_move_with_clock(&s, &f["config"].to_string(), || Duration::ZERO).unwrap(),
            )
            .unwrap()
        })
        .collect();
    println!("{}", serde_json::to_string(&results).unwrap());
}
