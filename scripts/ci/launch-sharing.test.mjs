import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('sharing points to a real readable 1200 by 630 PNG on the public arena', () => {
  const html = readFileSync(new URL('../../apps/web/index.html', import.meta.url), 'utf8');
  const tags = [...html.matchAll(/<meta\b[^>]*>/g)].map(([tag]) => tag);
  const content = key => tags.find(tag => tag.includes(`="${key}"`))?.match(/content="([^"]*)"/)?.[1];
  const origin = 'https://voxelshogi.yousan-apps.workers.dev';
  assert.equal(content('og:type'), 'website');
  assert.equal(content('og:url'), origin + '/');
  assert.equal(content('og:title'), '将棋、9層にした。｜VoxelShogi Arena');
  assert.equal(content('og:description'), content('description'));
  assert.equal(content('twitter:card'), 'summary_large_image');
  assert.equal(content('og:image'), origin + '/social/voxelshogi.png');
  assert.equal(content('twitter:image'), content('og:image'));
  assert.ok(content('og:image:alt')?.includes('9層'));
  const png = readFileSync(new URL('../../apps/web/public/social/voxelshogi.png', import.meta.url));
  assert.equal(png.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  assert.equal(png.readUInt32BE(16), 1200); assert.equal(png.readUInt32BE(20), 630);
  assert.ok(png.length > 10000 && png.length < 1000000);
});
