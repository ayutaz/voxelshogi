// Replays local JSONL with real WASM, derives metrics, and ships three representative records.
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const digest = (text) => createHash('sha256').update(text).digest('hex');
function distribution(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const q = (p) => sorted[Math.max(0, Math.ceil(p * sorted.length) - 1)];
  return { median: q(0.5), p90: q(0.9), min: sorted[0], max: sorted.at(-1) };
}
// Cluster bootstrap: keep both colour assignments of a seed together (2,000 draws).
export function pairInterval(games, value) {
  const pairs = new Map();
  for (const g of games) {
    const pair = pairs.get(g.record.seed) ?? [];
    pair.push(g);
    pairs.set(g.record.seed, pair);
  }
  const values = [...pairs.values()].map((p) => {
    if (p.length !== 2 || p[0].record.swapped === p[1].record.swapped) throw Error('incomplete seed pair');
    return (value(p[0]) + value(p[1])) / 2;
  });
  if (!values.length) throw Error('empty pairs');
  let state = 0x74529a31;
  const random = () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return state >>> 0;
  };
  const means = [];
  for (let n = 0; n < 2000; n++) {
    let sum = 0;
    for (let i = 0; i < values.length; i++) sum += values[random() % values.length];
    means.push(sum / values.length);
  }
  means.sort((a, b) => a - b);
  return [means[49], means[1949]];
}
export function summarize(games) {
  if (!games.length) throw Error('empty experiment');
  const reasons = {},
    wins = { Black: 0, White: 0, draw: 0 };
  let plies = 0,
    cross = 0,
    kings = 0,
    nodes = 0;
  const drought = [],
    first = [];
  for (const g of games) {
    const r = g.record;
    reasons[r.outcome.reason] = (reasons[r.outcome.reason] ?? 0) + 1;
    wins[r.outcome.winner ?? 'draw']++;
    plies += r.moves.length;
    cross += g.cross;
    kings += g.captured[0] + g.captured[1];
    nodes += r.nodes;
    if (g.events.length) first.push(g.events[0]);
    let last = 0,
      quiet = 0;
    for (const p of g.events) {
      quiet = Math.max(quiet, p - last - 1);
      last = p;
    }
    drought.push(Math.max(quiet, r.moves.length - last));
  }
  return {
    games: games.length,
    wins,
    reasons,
    plies: distribution(games.map((g) => g.record.moves.length)),
    meanCapturedKings: kings / games.length,
    firstKingCapture: distribution(first),
    gamesWithoutKingCapture: games.length - first.length,
    decisiveRate95: pairInterval(games, (g) => Number(g.record.outcome.winner !== null)),
    targetRate95: pairInterval(games, (g) => Number(g.record.outcome.reason === 'target')),
    longestKingDrought: distribution(drought),
    crossLayerRate: plies ? cross / plies : 0,
    nodes,
  };
}
export function representative(games) {
  if (!games.length) throw Error('empty experiment');
  const median = distribution(games.map((g) => g.record.moves.length)).median;
  return [...games].sort(
    (a, b) =>
      Math.abs(a.record.moves.length - median) - Math.abs(b.record.moves.length - median) ||
      a.record.seed - b.record.seed ||
      Number(a.record.swapped) - Number(b.record.swapped),
  )[0];
}
async function main(input, output, report, baselineInput) {
  if (!input || !output || !report)
    throw Error('usage: node scripts/experiment-pack.mjs INPUT.jsonl PUBLIC_DIRECTORY REPORT.json');
  const { initSync, ExperimentReplay, Game } = await import('../apps/web/src/wasm/pkg/voxelshogi_wasm.js');
  initSync({ module: readFileSync(new URL('../apps/web/src/wasm/pkg/voxelshogi_wasm_bg.wasm', import.meta.url)) });
  const source = readFileSync(input, 'utf8');
  const groups = new Map();
  const identities = new Set();
  let settings;
  for (const text of source.trim().split('\n')) {
    const record = JSON.parse(text);
    if (!Number.isSafeInteger(record.seed)) throw Error('seed must be safe in JavaScript');
    const config = JSON.stringify([record.engine, record.search, record.max_plies]);
    if (settings && settings !== config) throw Error('mixed engine/search/limits');
    settings = config;
    const identity = JSON.stringify([record.ruleset_id, record.seed, record.swapped]);
    if (identities.has(identity)) throw Error('duplicate game');
    identities.add(identity);
    const replay = new ExperimentReplay(text);
    const events = [];
    let cross = 0;
    for (let ply = 1; ply <= record.moves.length; ply++) {
      if (JSON.parse(replay.snapshot(ply)).kingCapture) events.push(ply);
      const m = record.moves[ply - 1];
      if (!m.includes('*') && m[2] !== m[5]) cross++;
    }
    const captured = JSON.parse(replay.snapshot(record.moves.length)).captured;
    replay.free();
    const group = groups.get(record.ruleset_id) ?? [];
    group.push({ record, captured, events, cross });
    groups.set(record.ruleset_id, group);
  }
  if (groups.size !== 3) throw Error('three rules required');
  const populations = [...groups.values()].map((gs) => gs.map((g) => `${g.record.seed}:${g.record.swapped}`).sort());
  if (populations.some((p) => JSON.stringify(p) !== JSON.stringify(populations[0])))
    throw Error('unmatched rule populations');
  const pairSeeds = [...new Set([...groups.values()][0].map((g) => g.record.seed))].sort((a, b) => a - b);
  if (populations[0].length !== pairSeeds.length * 2) throw Error('both colours required for each seed');
  mkdirSync(output, { recursive: true });
  const entries = [];
  for (const [id, games] of groups) {
    const chosen = representative(games);
    const text = JSON.stringify(chosen.record, null, 2) + '\n';
    const filename = id + '.record.json';
    writeFileSync(`${output}/${filename}`, text);
    entries.push({
      id,
      file: filename,
      sha256: digest(text),
      sample: {
        seed: chosen.record.seed,
        swapped: chosen.record.swapped,
        plies: chosen.record.moves.length,
        kingCapturePlies: chosen.events,
      },
      summary: summarize(games),
    });
  }
  let baseline;
  if (baselineInput) {
    const source = readFileSync(baselineInput, 'utf8');
    const games = [];
    const seen = new Set();
    for (const line of source.trim().split('\n')) {
      const r = JSON.parse(line);
      const identity = `${r.seed}:${r.swapped}`;
      if (seen.has(identity) || JSON.stringify([r.engine, r.search, r.max_plies]) !== settings)
        throw Error('baseline settings/identity mismatch');
      seen.add(identity);
      const game = Game.fromRecordJson(JSON.stringify(r.record));
      if (game.hash() !== r.final_hash) throw Error('baseline final hash mismatch');
      game.free();
      const end = r.record.result;
      const winner = end.Win?.winner ?? null;
      const reason = end.Win?.reason ?? end.Draw?.reason;
      const names = {
        Checkmate: 'checkmate',
        PerpetualCheck: 'perpetual_check',
        Repetition: 'repetition',
        MaxPlies: 'move_limit',
      };
      if (!names[reason]) throw Error('unknown baseline outcome');
      const moves = r.record.moves;
      games.push({
        record: { ...r, moves, outcome: { winner, reason: names[reason] } },
        captured: [0, 0],
        events: [],
        cross: moves.filter((m) => !m.includes('*') && m[2] !== m[5]).length,
      });
    }
    if (JSON.stringify([...seen].sort()) !== JSON.stringify(populations[0])) throw Error('unmatched baseline seeds');
    baseline = { rulesetId: 'voxelshogi-standard-v1', sourceSha256: digest(source), summary: summarize(games) };
  }
  const manifest = {
    schema: 'voxelshogi-experiment-manifest-v1',
    sourceSha256: digest(source),
    baseline,
    uncertainty: 'seed-pair cluster bootstrap, 2000 resamples, percentile 95%; fixed heuristic only',
    engine: JSON.parse(settings)[0],
    search: JSON.parse(settings)[1],
    maxPlies: JSON.parse(settings)[2],
    pairSeeds,
    selection: 'nearest median game length, including cutoffs; ties: seed ascending, unswapped first',
    entries,
  };
  writeFileSync(`${output}/manifest.json`, JSON.stringify(manifest, null, 2) + '\n');
  writeFileSync(report, JSON.stringify(manifest, null, 2) + '\n');
  console.log(
    JSON.stringify(
      entries.map((e) => ({ id: e.id, ...e.summary })),
      null,
      2,
    ),
  );
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main(...process.argv.slice(2));
