import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const REPO = 'voxelshogi/voxelshogi-transformer-s';
const REVISION = '6ab524574d36536348dbe323a2b779b9cebe37ed';
const FIXTURES = ['initial-b', 'after-one-w', 'mate-in-one-b', 'material-b'];
const PRECISIONS = ['fp32', 'fp16', 'int8'];
const paths = ['LICENSE', 'README.md', 'manifest.json', 'model.safetensors', 'evaluation.json', 'test.json',
  ...PRECISIONS.map(p => `${p}.onnx`), ...FIXTURES.map(f => `inputs/${f}.f32`),
  ...PRECISIONS.flatMap(p => FIXTURES.flatMap(f => ['policy', 'value'].map(output => `reference/${p}/${f}-${output}.f32`)))].sort();

assert.equal(process.platform, 'linux', 'Full model downloads/verification belong on Linux');
const release = JSON.parse(readFileSync(new URL('../export/public-s-release.json', import.meta.url)));
const { plan, receipt } = release;
assert.equal(plan.repo_id, REPO);
assert.equal(plan.access_profile, 'public-s-inference-v1');
assert.equal(plan.gated, false);
assert.equal(receipt.hub_commit, REVISION);
assert.deepEqual(plan.files.map(file => file.path).sort(), paths);
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const previous = JSON.parse(readFileSync(new URL('../docs/experiments/m6-portable-release.json', import.meta.url))).publication.plan;
assert.equal(plan.source_commit, previous.source_commit);
assert.deepEqual(plan.files.filter(file => file.path !== 'README.md'), previous.files.filter(file => file.path !== 'README.md'));
const card = readFileSync(new URL('../export/public-s-model-card.md', import.meta.url));
assert.deepEqual(plan.files.find(file => file.path === 'README.md'), {path:'README.md',bytes:card.length,sha256:digest(card)});
const catalog = JSON.parse(readFileSync(new URL('../apps/web/public/models/m6/catalog.json', import.meta.url))).releases.find(item=>item.publicDownload===true);
assert.ok(catalog); assert.equal(catalog.revision,receipt.hub_commit);
assert.deepEqual(catalog.manifest, plan.files.find(file=>file.path==='manifest.json'));
assert.deepEqual(catalog.notices, ['README.md','LICENSE','NOTICE'].flatMap(name=>plan.files.filter(file=>file.path===name)));
const base = 'https://huggingface.co/voxelshogi/voxelshogi-transformer-s';
const metadata = await fetch(`https://huggingface.co/api/models/voxelshogi/voxelshogi-transformer-s/revision/${REVISION}`).then(response => { assert.equal(response.status, 200); return response.json(); });
assert.equal(metadata.private, false); assert.equal(metadata.gated, false); assert.equal(metadata.sha, receipt.hub_commit);
assert.deepEqual(metadata.siblings.map(file => file.rfilename).filter(path => path !== '.gitattributes').sort(), plan.files.map(file => file.path).sort());
const discussions = await fetch('https://huggingface.co/api/models/voxelshogi/voxelshogi-transformer-s/discussions');
assert.equal(discussions.status, 403); assert.equal((await discussions.json()).error, 'Discussions are disabled for this repo');
const verified = [];
for (let start = 0; start < paths.length; start += 4) {
  const batch = await Promise.all(paths.slice(start, start + 4).map(async path => {
    const file = plan.files.find(file => file.path === path);
    const response = await fetch(`${base}/resolve/${REVISION}/${path}`, { credentials: 'omit' });
    assert.equal(response.status, 200, file.path);
    const bytes = Buffer.from(await response.arrayBuffer());
    assert.equal(bytes.length, file.bytes, file.path); assert.equal(digest(bytes), file.sha256, file.path);
    return file;
  }));
  verified.push(...batch);
}
const proof = { schema: 1, repo: plan.repo_id, revision: receipt.hub_commit, anonymous: true, gated: false, communityDisabled: true, files: verified, verified: true };
const output = process.argv[2] ?? join(mkdtempSync(join(tmpdir(), 'voxelshogi-public-s-')), 'verification.json');
writeFileSync(output, JSON.stringify(proof, null, 2) + '\n', {flag:'wx',mode:0o600});
console.log(JSON.stringify({ verified: true, anonymous: true, files: verified.length, revision: receipt.hub_commit }));
