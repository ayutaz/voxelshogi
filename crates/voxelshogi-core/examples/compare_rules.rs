//! JSONL to stdout; timing/progress to stderr. No wall-clock cutoff changes the moves.
use std::{
    io::{self, Write},
    time::Instant,
};
use voxelshogi_core::{
    capture::CaptureRule,
    experiment::{ExperimentRecord, SearchConfig},
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<String> = std::env::args().collect();
    if a.len() != 7 && !(a.len() == 8 && a[7] == "baseline") {
        return Err(
            "usage: compare_rules PAIRS MAX_PLIES WIDTH DEPTH SEED_START ENGINE_COMMIT [baseline]"
                .into(),
        );
    }
    let pairs: u64 = a[1].parse()?;
    let max: u32 = a[2].parse()?;
    let search = SearchConfig {
        width: a[3].parse()?,
        depth: a[4].parse()?,
    };
    let start: u64 = a[5].parse()?;
    if pairs == 0 || pairs > 10000 || start.checked_add(pairs).is_none() {
        return Err("invalid seed range".into());
    }
    let mut out = io::BufWriter::new(io::stdout().lock());
    let all = Instant::now();
    if a.len() == 8 {
        for seed in start..start + pairs {
            for swapped in [false, true] {
                let r =
                    voxelshogi_core::experiment::play_baseline(max, seed, swapped, search, &a[6])?;
                serde_json::to_writer(&mut out, &r)?;
                writeln!(out)?;
                out.flush()?;
            }
        }
        eprintln!(
            "standard baseline: {} games, {:.3}s",
            pairs * 2,
            all.elapsed().as_secs_f64()
        );
        return Ok(());
    }

    for rule in [
        CaptureRule::FirstFive,
        CaptureRule::AllKings,
        CaptureRule::ScoreLimit,
    ] {
        let timer = Instant::now();
        let mut nodes = 0;
        let mut plies = 0;
        for seed in start..start + pairs {
            for swapped in [false, true] {
                let record = ExperimentRecord::play(rule, max, seed, swapped, search, &a[6])?;
                // Replaying every recorded move independently checks the fast search transitions.
                voxelshogi_core::experiment::Replay::from_json(&serde_json::to_string(&record)?)?;
                nodes += record.nodes;
                plies += record.moves.len();
                serde_json::to_writer(&mut out, &record)?;
                writeln!(out)?;
            }
        }
        out.flush()?;
        eprintln!(
            "{}: {} games, {} plies, {} nodes, {:.3}s",
            rule.id(),
            pairs * 2,
            plies,
            nodes,
            timer.elapsed().as_secs_f64()
        );
    }
    eprintln!("total {:.3}s", all.elapsed().as_secs_f64());
    Ok(())
}
