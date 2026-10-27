import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';

export function residentSets(text, processInfo) {
  const expected = new Map(processInfo.map(p => [Number(p.id), p.type])), found = new Set(), processes = [];
  for (const row of text.trim().split('\n').filter(Boolean)) {
    assert.match(row.trim(), /^\d+\s+\d+$/, 'invalid ps measurement');
    const [pid, kib] = row.trim().split(/\s+/).map(Number);
    assert.ok(expected.has(pid), 'unexpected process outside dedicated browser');
    assert.ok(!found.has(pid), 'duplicate process measurement');
    assert.ok(Number.isSafeInteger(kib * 1024), 'invalid resident set size');
    found.add(pid); processes.push({ pid, type: expected.get(pid), rssBytes: kib * 1024 });
  }
  return { scope: 'sum of dedicated Chrome process RSS; shared pages may be counted more than once', processes,
    totalRssBytes: processes.reduce((sum, p) => sum + p.rssBytes, 0), missingProcessIds: [...expected.keys()].filter(id => !found.has(id)) };
}

export async function browserMemory(browserCdp, page) {
  const { processInfo } = await browserCdp.send('SystemInfo.getProcessInfo');
  const ids = processInfo.map(p => Number(p.id));
  assert.ok(ids.length > 0 && ids.every(id => Number.isSafeInteger(id) && id > 0), 'invalid dedicated browser process IDs');
  const raw = execFileSync('ps', ['-o', 'pid=,rss=', '-p', ids.join(',')], { encoding: 'utf8' });
  const mainHeap = page && !page.isClosed() ? await page.evaluate(() => {
    const memory = performance.memory;
    return memory ? { scope: 'main page JS heap only; excludes Worker WASM and GPU memory', usedBytes: memory.usedJSHeapSize, allocatedBytes: memory.totalJSHeapSize } : null;
  }) : null;
  return { at: new Date().toISOString(), mainHeap, residentSet: residentSets(raw, processInfo), gpuTotal: null, gpuTotalReason: 'native ORT WebGPU allocation totals are not exposed by this browser API' };
}
