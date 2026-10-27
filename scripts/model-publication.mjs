import assert from 'node:assert/strict';
import { appendFileSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export function publicationPolicy(data) {
  assert.ok(data && !Array.isArray(data) && data.schema === 1 && data.trained === false, 'unsupported M3 publication policy');
  assert.ok(typeof data.modelId === 'string' && /^[a-zA-Z0-9._-]{1,128}$/.test(data.modelId), 'invalid publication model ID');
  assert.equal(typeof data.approved, 'boolean', 'explicit approval state is required');
  if (data.approved) {
    assert.equal(data.license, 'Apache-2.0', 'unsupported approved model license');
    assert.ok(typeof data.approvedAt === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$/.test(data.approvedAt) && Number.isFinite(Date.parse(data.approvedAt)), 'valid approval date required');
  } else {
    assert.equal(data.license, null, 'pending approval must not assign a publication license');
    assert.equal(data.approvedAt, null, 'pending approval cannot have an approval date');
  }
  return { publication: data.approved, modelId: data.modelId, license: data.license, approvedAt: data.approvedAt };
}

export function verifyPublication(policy, manifest) {
  assert.equal(policy.publication, true, 'model publication approval is pending');
  assert.equal(manifest.id, policy.modelId, 'model ID differs from approved scope');
  assert.equal(manifest.license, policy.license, 'model license differs from approval');
  assert.equal(manifest.trained, false, 'M3 approval does not cover trained models');
  assert.equal(manifest.sourceDirty, false, 'publication requires clean source');
  assert.ok(typeof manifest.sourceCommit === 'string' && /^[0-9a-f]{40}$/.test(manifest.sourceCommit), 'source commit required');
  assert.deepEqual(manifest.variants.map(v => v.id), ['fp32', 'fp16', 'int8'], 'all approved variants must be present');
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [policyFile, modelDirectory] = process.argv.slice(2);
  assert.ok(policyFile, 'usage: node scripts/model-publication.mjs POLICY.json [MODEL_DIRECTORY]');
  const policy = publicationPolicy(JSON.parse(readFileSync(policyFile, 'utf8')));
  if (modelDirectory) verifyPublication(policy, JSON.parse(readFileSync(resolve(modelDirectory, 'manifest.json'), 'utf8')));
  if (process.env.GITHUB_OUTPUT) appendFileSync(process.env.GITHUB_OUTPUT, `publication=${policy.publication}\n`);
  console.log(JSON.stringify(policy));
}
