import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export function testOutcome(result) {
  const output = result.stdout ?? '';
  if (result.error || result.signal || !/running [1-9]\d* tests?/.test(output)) return 'error';
  if (result.status === 0 && /test result: ok\. [1-9]\d* passed;/.test(output)) return 'passed';
  if (result.status === 101 && /test result: FAILED\. \d+ passed; [1-9]\d* failed;/.test(output)) return 'caught';
  return 'error';
}

const mutations = [
  { name: 'forward-direction', file: 'piece.rs', before: 'Color::Black => -1,', after: 'Color::Black => 1,', args: ['--lib', 'piece::tests::color_directions'] },
  { name: 'checkmate-winner', file: 'state.rs', before: 'winner: self.side.opponent(),\n                reason: WinReason::Checkmate,', after: 'winner: self.side,\n                reason: WinReason::Checkmate,', args: ['--test', 'rules', 'protected_dragon_next_to_cornered_king_is_checkmate'] },
  { name: 'hash-seed', file: 'zobrist.rs', before: '0x766F_7865_6C73_6867', after: '0x766F_7865_6C73_6868', args: ['--lib', 'zobrist::tests::initial_position_hash_is_pinned'] },
  { name: 'kind-index', file: 'piece.rs', before: 'pub const fn index(self) -> usize {\n        self as usize\n    }\n\n    #[inline]\n    pub fn from_index', after: 'pub const fn index(self) -> usize {\n        0\n    }\n\n    #[inline]\n    pub fn from_index', args: ['--test', 'piece_contracts', 'kind_indices_match_the_public_encoding'] },
  { name: 'promotion-status', file: 'piece.rs', before: '(self as usize) >= 8', after: 'true', args: ['--test', 'piece_contracts', 'promotion_status_distinguishes_base_and_promoted_kinds'] },
  { name: 'japanese-label', file: 'piece.rs', before: "pub const fn japanese(self) -> &'static str {\n        match self {", after: "pub const fn japanese(self) -> &'static str {\n        return \"\";\n        match self {", args: ['--test', 'piece_contracts', 'japanese_labels_match_the_public_piece_names'] },
  { name: 'error-message', file: 'state.rs', before: 'match self {\n            MoveError::Illegal(why)', after: 'return Ok(());\n        match self {\n            MoveError::Illegal(why)', args: ['--test', 'rules', 'move_errors_display_the_reason_for_users'] },
  { name: 'hand-count', file: 'state.rs', before: 'kind.hand_index()\n            .map_or(0, |i| self.hands[color.index()][i])', after: '0', args: ['--test', 'rules', 'hand_count_returns_each_sides_count_and_zero_for_undroppable_kinds'] },
  { name: 'all-hand-kinds', file: 'state.rs', before: 'hand.iter().all(|&n| n == 0)', after: 'hand.iter().all(|&n| n != 0)', args: ['--test', 'rules', 'every_hand_kind_can_be_dropped_when_all_seven_are_held'] },
];

function main() {
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const output = resolve(root, 'coverage/mutations');
  mkdirSync(output, { recursive: true });
  const work = mkdtempSync(join(tmpdir(), 'voxelshogi-mutations-'));
  const results = [];
  const run = (name, args) => {
    const result = spawnSync('cargo', ['test', '--locked', '-p', 'voxelshogi-core', ...args], {
      cwd: work,
      env: { ...process.env, CARGO_TERM_COLOR: 'never', CARGO_TARGET_DIR: join(root, 'target/mutation-smoke') },
      encoding: 'utf8', timeout: 120_000, maxBuffer: 8 * 1024 * 1024,
    });
    writeFileSync(join(output, `${name}.log`), `${result.stdout ?? ''}\n${result.stderr ?? ''}`);
    return testOutcome(result);
  };
  try {
    for (const file of ['Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml']) cpSync(join(root, file), join(work, file));
    cpSync(join(root, 'crates'), join(work, 'crates'), { recursive: true, filter: (source) => !['target', 'pkg'].includes(basename(source)) });
    assert.equal(run('baseline', []), 'passed', 'Original tests must pass before injecting mutations');
    for (const mutation of mutations) {
      const path = join(work, 'crates/voxelshogi-core/src', mutation.file);
      const original = readFileSync(path, 'utf8');
      assert.equal(original.split(mutation.before).length - 1, 1, `Stale mutation anchor: ${mutation.name}`);
      try {
        writeFileSync(path, original.replace(mutation.before, mutation.after));
        const outcome = run(mutation.name, mutation.args);
        results.push({ name: mutation.name, outcome });
        console.log(`${mutation.name}: ${outcome}`);
        assert.equal(outcome, 'caught', `Mutation was not caught by a failing test: ${mutation.name}`);
      } finally {
        writeFileSync(path, original);
      }
    }
    assert.equal(results.length, 9);
  } finally {
    writeFileSync(join(output, 'results.json'), JSON.stringify({ results }, null, 2) + '\n');
    rmSync(work, { recursive: true, force: true });
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) main();
