import assert from 'node:assert/strict';
import test from 'node:test';
import { publicationPolicy, verifyPublication } from '../model-publication.mjs';

const pending = () => ({ schema: 1, modelId: 'voxelshogi-transformer-s-untrained-314159-v1', trained: false, approved: false, license: null, approvedAt: null });
const approved = () => ({ ...pending(), approved: true, license: 'Apache-2.0', approvedAt: '2026-10-27T00:00:00Z' });
const model = () => ({ id: pending().modelId, trained: false, license: 'Apache-2.0', sourceCommit: 'a'.repeat(40), sourceDirty: false, variants: ['fp32', 'fp16', 'int8'].map(id => ({ id })) });

test('pending approval cannot publish, and approval is scoped to an untrained model', () => {
  assert.equal(publicationPolicy(pending()).publication, false);
  assert.throws(() => verifyPublication(publicationPolicy(pending()), model()), /approval/);
  assert.throws(() => verifyPublication(publicationPolicy(pending()), { ...model(), license: null }), /approval/);
  const policy = publicationPolicy(approved());
  assert.equal(policy.publication, true); assert.equal(policy.license, 'Apache-2.0');
  assert.doesNotThrow(() => verifyPublication(policy, model()));
  for (const change of [{ id: 'other' }, { trained: true }, { license: null }, { sourceDirty: true }, { sourceCommit: null }, { variants: [] }]) {
    assert.throws(() => verifyPublication(policy, { ...model(), ...change }));
  }
});

test('inconsistent approval, unknown schemas, licenses and dates are rejected', () => {
  for (const change of [{ approved: true }, { license: 'Apache-2.0' }, { trained: true }, { schema: 2 }, { modelId: '../other' }, { approvedAt: 'today' }]) {
    assert.throws(() => publicationPolicy({ ...pending(), ...change }));
  }
  assert.throws(() => publicationPolicy({ ...approved(), approvedAt: 'not-a-date' }));
  assert.throws(() => publicationPolicy({ ...approved(), license: 'unknown' }));
});
