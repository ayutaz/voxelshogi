import { beforeAll, expect, it } from 'vitest';
import { loadWasm } from './loadWasm';
import { ExperimentReplay } from '../src/wasm/pkg/voxelshogi_wasm.js';
import { readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';

beforeAll(() => loadWasm());
it.each(['', 'long/'])('validates every shipped experiment and seeks without changing the record: %s', (prefix) => {
  const dir = new URL(`../public/experiments/${prefix}`, import.meta.url);
  const manifest = JSON.parse(readFileSync(new URL('manifest.json', dir), 'utf8'));
  const files = readdirSync(dir).filter((n) => n.endsWith('.record.json'));
  expect(files.length).toBe(3);
  for (const file of files) {
    const text = readFileSync(new URL(file, dir), 'utf8');
    const record = JSON.parse(text);
    const entry = manifest.entries.find((e: { file: string }) => e.file === file);
    expect(createHash('sha256').update(text).digest('hex')).toBe(entry.sha256);
    expect(record.engine).toBe(manifest.engine);
    expect(record.search).toEqual(manifest.search);
    expect(record.ruleset_id).toBe(entry.id);
    const replay = new ExperimentReplay(text);
    const zero = JSON.parse(replay.snapshot(0));
    expect(zero.captured).toEqual([0, 0]);
    expect(zero.board.filter((p: number) => p !== 0).length).toBe(360);
    const end = JSON.parse(replay.snapshot(record.moves.length));
    expect(end.hash).toBe(record.final_hash);
    expect(end.outcome).toEqual(record.outcome);
    expect(JSON.parse(replay.snapshot(0))).toEqual(zero);
    expect(() => replay.snapshot(record.moves.length + 1)).toThrow();
    const events: number[] = [];
    for (let ply = 1; ply <= record.moves.length; ply++) {
      if (JSON.parse(replay.snapshot(ply)).kingCapture) events.push(ply);
    }
    expect(events).toEqual(entry.sample.kingCapturePlies);
    expect(events.length).toBeGreaterThan(0);
    replay.free();
  }
});
