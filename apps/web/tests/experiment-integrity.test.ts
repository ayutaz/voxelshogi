import { expect, it } from 'vitest';
import { verifyDigest } from '../src/experiment/integrity';

it('compares SHA-256 of exact UTF-8 bytes and rejects corrupt files', async () => {
  await expect(
    verifyDigest('abc', 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'),
  ).resolves.toBeUndefined();
  await expect(
    verifyDigest('abcd', 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'),
  ).rejects.toThrow('SHA-256');
  await expect(verifyDigest('abc', '')).rejects.toThrow('SHA-256');
});
