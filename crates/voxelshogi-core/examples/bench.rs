//! Rough throughput measurement: `cargo run --release -p voxelshogi-core --example bench`.
use std::time::Instant;
use voxelshogi_core::GameState;

fn main() {
    let mut seed = 1u64;
    let mut rand = |n: usize| {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        (seed % n as u64) as usize
    };
    let g = GameState::new();
    let t = Instant::now();
    let n = 50;
    let mut total = 0;
    for _ in 0..n {
        total += g.legal_moves().len();
    }
    let dt = t.elapsed().as_secs_f64() / n as f64;
    println!(
        "initial: {} legal moves, {:.2} ms per legal_moves()",
        total / n,
        dt * 1e3
    );

    let t = Instant::now();
    let mut plies = 0;
    let mut gens = 0usize;
    let mut moves_sum = 0usize;
    for _game in 0..3 {
        let mut g = GameState::new();
        for _ in 0..150 {
            let moves = g.legal_moves();
            gens += 1;
            moves_sum += moves.len();
            if moves.is_empty() {
                break;
            }
            g = g.apply_move(&moves[rand(moves.len())]).unwrap();
            plies += 1;
        }
    }
    let dt = t.elapsed().as_secs_f64();
    println!(
        "random self-play: {plies} plies in {dt:.2}s → {:.1} plies/s, avg {} legal moves, {:.2} ms per (generate+apply)",
        plies as f64 / dt,
        moves_sum / gens,
        dt * 1e3 / plies as f64
    );
}
