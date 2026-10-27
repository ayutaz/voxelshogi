import { describe, expect, it } from 'vitest';
import { assetUrl, fetchVerified, joinVerifiedParts } from '../src/inference/assets';

const sha256 = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'; // SHA-256("abc")
const file = { path: 'weights.bin', bytes: 3, sha256 };

describe('verified inference distribution', () => {
  it('checks the actual body and uses only a safe relative asset path', async () => {
    expect(assetUrl('https://example.test/models/hash/', file.path)).toBe('https://example.test/models/hash/weights.bin');
    const data = await fetchVerified('https://example.test/models/hash/weights.bin', file, undefined,
      async () => new Response('abc'));
    expect(new TextDecoder().decode(data)).toBe('abc');
  });
  for (const path of ['../secret', '/other.bin', 'https://elsewhere.test/file', 'file?x=1', 'a/../b', 'a\\b', '']) {
    it(`rejects invalid asset path ${path}`, () => expect(() => assetUrl('https://example.test/models/hash/', path)).toThrow());
  }
  for (const body of ['abd', 'abcd', 'ab', '']) {
    it(`rejects changed or incorrectly sized body ${body}`, async () => {
      await expect(fetchVerified('https://example.test/file', file, undefined, async () => new Response(body))).rejects.toThrow();
    });
  }
  it('rejects HTTP failure, unsafe sizes and a failed/cancelled download', async () => {
    await expect(fetchVerified('https://example.test/file', file, undefined, async () => new Response('', { status: 404 }))).rejects.toThrow();
    await expect(fetchVerified('https://example.test/file', { ...file, bytes: 100_000_000 })).rejects.toThrow();
    await expect(fetchVerified('https://example.test/file', file, undefined, async () => { throw new DOMException('cancelled', 'AbortError'); })).rejects.toThrow();
  });
  it('compares decoded bytes even when HTTP Content-Length describes a compressed transfer', async () => {
    const bytes = await fetchVerified('https://example.test/file', file, undefined,
      async () => new Response('abc', { headers: { 'content-length': '2', 'content-encoding': 'br' } }));
    expect(new TextDecoder().decode(bytes)).toBe('abc');
  });
  it('reassembles the original bytes and verifies the whole-file hash too', async () => {
    const a = new TextEncoder().encode('a'), bc = new TextEncoder().encode('bc');
    expect(new TextDecoder().decode(await joinVerifiedParts([a, bc], file))).toBe('abc');
    await expect(joinVerifiedParts([bc, a], file)).rejects.toThrow();
    await expect(joinVerifiedParts([a], file)).rejects.toThrow();
  });
});
