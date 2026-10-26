//! Native single-thread search measurements. Build before timing; never a CI speed gate.
use std::{
    process::Command,
    time::{Duration, Instant},
};
use voxelshogi_core::search::{SearchLimits, SearchOptions, search};
use voxelshogi_core::{Board, Color, GameState, Piece, PieceKind, Square};

fn measure(
    label: &str,
    game: &GameState,
    limits: SearchLimits,
    options: SearchOptions,
) -> serde_json::Value {
    let start = Instant::now();
    let result = search(game, limits, options).expect("valid benchmark limits");
    let seconds = start.elapsed().as_secs_f64();
    serde_json::json!({"position":label,"vsfen":voxelshogi_core::notation::to_vsfen(game),"history":"starts at this position","limits":{"depth":limits.max_depth,"nodes":limits.max_nodes,"timeMs":limits.max_time.map(|t|t.as_millis()),"maxGamePly":limits.max_game_ply},"options":{"iterativeDeepening":options.iterative_deepening,"moveOrdering":options.move_ordering,"transpositionTable":options.transposition_table,"tableCapacity":options.table_capacity},"result":{"bestMove":result.best_move.map(|m|m.to_string()),"score":result.score,"depth":result.completed_depth,"nodes":result.nodes,"lastIterationNodes":result.last_iteration_nodes,"ttHits":result.tt_hits,"stopReason":format!("{:?}",result.stop_reason)},"seconds":seconds,"nodesPerSecond":result.nodes as f64/seconds})
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let engine = std::env::args()
        .nth(1)
        .ok_or("usage: search_bench FULL_ENGINE_SHA")?;
    if engine.len() != 40 || !engine.bytes().all(|c| c.is_ascii_hexdigit()) {
        return Err("expected full commit SHA".into());
    }
    let status = Command::new("git")
        .args([
            "diff",
            "--exit-code",
            &engine,
            "--",
            "Cargo.toml",
            "Cargo.lock",
            "rust-toolchain.toml",
            "crates/voxelshogi-core/src",
            "crates/voxelshogi-core/examples/search_bench.rs",
        ])
        .status()?;
    if !status.success() {
        return Err("runtime source differs from the named engine commit".into());
    }
    let rust = Command::new("rustc").arg("--version").output()?;
    if !rust.status.success() {
        return Err("rustc version unavailable".into());
    }
    let initial = GameState::new();
    let mut b = Board::empty();
    b.set(
        Square::new(8, 8, 8),
        Some(Piece::new(Color::Black, PieceKind::King)),
    );
    b.set(
        Square::new(0, 0, 0),
        Some(Piece::new(Color::White, PieceKind::King)),
    );
    let sparse = GameState::from_parts(b, [[0; 7]; 2], Color::Black);
    let default = SearchOptions::default();
    let plain = SearchOptions {
        iterative_deepening: false,
        move_ordering: false,
        transposition_table: false,
        table_capacity: 0,
    };
    let limits = |depth| SearchLimits {
        max_depth: depth,
        max_nodes: None,
        max_time: None,
        max_game_ply: None,
    };
    // Warm-up outside measurements. Run this executable without other heavy local jobs.
    search(&sparse, limits(2), default)?;
    let mut measurements = Vec::new();
    for depth in [1, 2] {
        measurements.push(measure("initial", &initial, limits(depth), default));
    }
    for options in [
        plain,
        SearchOptions {
            transposition_table: true,
            table_capacity: 65_536,
            ..plain
        },
        SearchOptions {
            move_ordering: true,
            ..plain
        },
        default,
    ] {
        measurements.push(measure("two-kings", &sparse, limits(4), options));
    }
    for _ in 0..3 {
        let mut timed = limits(64);
        timed.max_time = Some(Duration::from_secs(1));
        measurements.push(measure("initial-one-second", &initial, timed, default));
    }
    let mut fixed = limits(64);
    fixed.max_nodes = Some(10_000);
    measurements.push(measure("initial-fixed-nodes", &initial, fixed, default));
    println!(
        "{}",
        serde_json::to_string_pretty(
            &serde_json::json!({"schema":"voxelshogi-search-benchmark-v1","engine":engine,"rulesetId":voxelshogi_core::record::RULESET_ID,"os":std::env::consts::OS,"arch":std::env::consts::ARCH,"rust":String::from_utf8(rust.stdout)?.trim(),"threads":1,"measurements":measurements})
        )?
    );
    Ok(())
}
