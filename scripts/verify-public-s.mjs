import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';

assert.equal(process.platform, 'linux', 'Full model downloads/verification belong on Linux');
const release = JSON.parse(readFileSync(new URL('../export/public-s-release.json', import.meta.url)));
const { plan, receipt } = release;
assert.equal(plan.repo_id, 'voxelshogi/voxelshogi-transformer-s');
assert.equal(plan.access_profile, 'public-s-inference-v1');
assert.equal(plan.gated, false);
assert.match(receipt.hub_commit, /^[0-9a-f]{40}$/);
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
const base = `https://huggingface.co/${plan.repo_id}`;
const metadata = await fetch(`https://huggingface.co/api/models/${plan.repo_id}/revision/${receipt.hub_commit}`).then(response => { assert.equal(response.status, 200); return response.json(); });
assert.equal(metadata.private, false); assert.equal(metadata.gated, false); assert.equal(metadata.sha, receipt.hub_commit);
assert.deepEqual(metadata.siblings.map(file => file.rfilename).filter(path => path !== '.gitattributes').sort(), plan.files.map(file => file.path).sort());
const discussions = await fetch(`https://huggingface.co/api/models/${plan.repo_id}/discussions`);
assert.equal(discussions.status, 403); assert.equal((await discussions.json()).error, 'Discussions are disabled for this repo');
const verified = [];
for (let start = 0; start < plan.files.length; start += 4) {
  const batch = await Promise.all(plan.files.slice(start, start + 4).map(async file => {
    const response = await fetch(`${base}/resolve/${receipt.hub_commit}/${file.path}`, { credentials: 'omit' });
    assert.equal(response.status, 200, file.path);
    const bytes = Buffer.from(await response.arrayBuffer());
    assert.equal(bytes.length, file.bytes, file.path); assert.equal(digest(bytes), file.sha256, file.path);
    return file;
  }));
  verified.push(...batch);
}
const proof = { schema: 1, repo: plan.repo_id, revision: receipt.hub_commit, anonymous: true, gated: false, communityDisabled: true, files: verified, verified: true };
writeFileSync(process.argv[2] ?? '/tmp/public-s-verification.json', JSON.stringify(proof, null, 2) + '\n');
console.log(JSON.stringify({ verified: true, anonymous: true, files: verified.length, revision: receipt.hub_commit }));
