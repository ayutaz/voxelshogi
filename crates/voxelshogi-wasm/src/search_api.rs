//! JSON boundary shared by native contract tests and the browser binding.
//! Search and rule decisions remain in voxelshogi-core.
use serde::Deserialize;
use std::time::Duration;
use voxelshogi_core::record::Termination;
use voxelshogi_core::search::{SearchLimits, SearchOptions, StopReason, search_with_clock};
use voxelshogi_core::session::Session;

const JS_MAX_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Config {
    max_depth: u8,
    max_nodes: Option<u64>,
    max_time_ms: Option<f64>,
    max_game_ply: Option<u32>,
    #[serde(default)]
    options: Options,
}

#[derive(Deserialize)]
#[serde(default, rename_all = "camelCase", deny_unknown_fields)]
struct Options {
    iterative_deepening: bool,
    move_ordering: bool,
    transposition_table: bool,
    table_capacity: usize,
}
impl Default for Options {
    fn default() -> Self {
        let o = SearchOptions::default();
        Self {
            iterative_deepening: o.iterative_deepening,
            move_ordering: o.move_ordering,
            transposition_table: o.transposition_table,
            table_capacity: o.table_capacity,
        }
    }
}

/// `elapsed` reports monotonic time since the call began (browser performance.now).
/// Counts are decimal strings so u64 values never silently round in JavaScript.
pub fn best_move_with_clock(
    session: &Session,
    config: &str,
    elapsed: impl FnMut() -> Duration,
) -> Result<String, String> {
    if config.len() > 4096 {
        return Err("search config exceeds 4096 bytes".into());
    }
    let c: Config = serde_json::from_str(config).map_err(|e| e.to_string())?;
    if c.max_depth > 64 || c.options.table_capacity > 1_000_000 {
        return Err("depth must be 0..64; tableCapacity must be 0..1000000".into());
    }
    if c.max_nodes.is_some_and(|n| n > JS_MAX_SAFE_INTEGER) {
        return Err("maxNodes must be a nonnegative safe integer".into());
    }
    if c.max_time_ms
        .is_some_and(|ms| !ms.is_finite() || ms < 0.0 || ms > JS_MAX_SAFE_INTEGER as f64)
    {
        return Err("maxTimeMs must be finite, nonnegative and <= Number.MAX_SAFE_INTEGER".into());
    }
    // These terminations exist at the session/record level, not on GameState.
    // A natural rule outcome still takes precedence over an external annotation.
    if session.state().result().is_none() && session.termination().is_some() {
        let score = (session.termination() == Some(Termination::MaxPlies)).then_some(0);
        return Ok(serde_json::json!({"schema":1,"bestMove":null,"score":score,
            "completedDepth":0,"nodes":"0","lastIterationNodes":"0","ttHits":"0","stopReason":"terminal"}).to_string());
    }
    let r = search_with_clock(
        session.state(),
        SearchLimits {
            max_depth: c.max_depth,
            max_nodes: c.max_nodes,
            max_time: c.max_time_ms.map(|ms| Duration::from_secs_f64(ms / 1000.0)),
            max_game_ply: c.max_game_ply,
        },
        SearchOptions {
            iterative_deepening: c.options.iterative_deepening,
            move_ordering: c.options.move_ordering,
            transposition_table: c.options.transposition_table,
            table_capacity: c.options.table_capacity,
        },
        elapsed,
    )
    .map_err(str::to_owned)?;
    let reason = match r.stop_reason {
        StopReason::Depth => "depth",
        StopReason::Nodes => "nodes",
        StopReason::Time => "time",
        StopReason::Terminal => "terminal",
    };
    Ok(
        serde_json::json!({"schema":1,"bestMove":r.best_move.map(|m|m.to_string()),
        "score":r.score,"completedDepth":r.completed_depth,"nodes":r.nodes.to_string(),
        "lastIterationNodes":r.last_iteration_nodes.to_string(),"ttHits":r.tt_hits.to_string(),
        "stopReason":reason})
        .to_string(),
    )
}
