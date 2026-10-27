import { expect, it } from 'vitest';
import { resourceTimings } from '../src/inference/resources';

it('records actual decoded/encoded transfer sizes separately and excludes old or unrelated requests', () => {
  const entry = { entryType: 'resource', name: 'https://example.test/models/m3/runtime/hash/part.bin', startTime: 15, duration: 8,
    transferSize: 650, encodedBodySize: 300, decodedBodySize: 1000, nextHopProtocol: 'h2', deliveryType: '' };
  const entries = [entry, { ...entry, startTime: 2 }, { ...entry, name: 'https://other.test/models/m3/runtime/hash/part.bin' }, { ...entry, name: 'https://example.test/assets/main.js' }];
  expect(resourceTimings(entries, 'https://example.test', 10)).toEqual([{ url: entry.name, startMs: 15, durationMs: 8,
    transferBytes: 650, encodedBytes: 300, decodedBytes: 1000, protocol: 'h2', delivery: '' }]);
  expect(resourceTimings([{ ...entry, transferSize: 0 }], 'https://example.test', 10)[0]!.transferBytes).toBe(0); // cache, not zero file size
});
