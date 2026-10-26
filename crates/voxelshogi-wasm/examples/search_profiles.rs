//! Native timings for the exact record/cursor/config sent to a browser Worker.
use std::io::{self, Read};
use std::time::Instant;
use voxelshogi_core::session::Session;
use voxelshogi_wasm::search_api::best_move_with_clock;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let requests: Vec<serde_json::Value> = serde_json::from_str(&input)?;
    let results: Vec<_> = requests.iter().map(|r| {
        let start = Instant::now();
        let mut s = Session::from_record_json(r["recordJson"].as_str().unwrap()).unwrap();
        s.goto(r["cursor"].as_u64().unwrap() as usize).unwrap();
        let replay_ms = start.elapsed().as_secs_f64() * 1000.0;
        let search_start = Instant::now();
        let result: serde_json::Value = serde_json::from_str(&best_move_with_clock(&s, &r["limits"].to_string(), || search_start.elapsed()).unwrap()).unwrap();
        let search_ms = search_start.elapsed().as_secs_f64() * 1000.0;
        serde_json::json!({"name":r["name"], "result":result, "replayMs":replay_ms,"searchMs":search_ms,"totalMs":start.elapsed().as_secs_f64()*1000.0})
    }).collect();
    println!("{}", serde_json::to_string(&results)?);
    Ok(())
}
