import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { appendFileSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { setTimeout } from 'node:timers/promises';
import { pathToFileURL } from 'node:url';

function validateCommit(commit) {
  assert.match(commit ?? '', /^[0-9a-f]{40}$/, 'A complete commit SHA is required');
}

export function productionConfig(env) {
  const missing = ['CLOUDFLARE_API_TOKEN', 'CLOUDFLARE_ACCOUNT_ID', 'WORKERS_SUBDOMAIN'].filter((name) => !env[name]?.trim());
  assert.equal(missing.length, 0, `Missing production configuration: ${missing.join(', ')}`);
  assert.match(env.WORKERS_SUBDOMAIN, /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/, 'Invalid Workers subdomain');
  return `https://voxelshogi.${env.WORKERS_SUBDOMAIN}.workers.dev`;
}

export function isCurrentCommit(candidate, current) {
  validateCommit(candidate);
  validateCommit(current);
  return candidate === current;
}

export function stampBuild(dir, commit) {
  validateCommit(commit);
  writeFileSync(join(dir, 'build-info.json'), JSON.stringify({ commit }) + '\n');
}

export function parseDeploymentVersion(log) {
  const matches = [...log.matchAll(/^Current Version ID:\s*([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\s*$/gm)];
  assert.equal(matches.length, 1, 'Expected exactly one Cloudflare version ID');
  return matches[0][1];
}

export async function waitForDeployment(baseURL, commit, options = {}) {
  validateCommit(commit);
  const { attempts = 30, delay = 2_000, fetch = globalThis.fetch, sleep = setTimeout } = options;
  assert.ok(Number.isInteger(attempts) && attempts > 0 && attempts <= 60, 'Invalid publication attempt limit');
  const url = new URL('/build-info.json', baseURL);
  assert.ok(['https:', 'http:'].includes(url.protocol), 'Invalid deployment URL');
  url.searchParams.set('commit', commit);
  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      const response = await fetch(url, { cache: 'no-store', signal: AbortSignal.timeout(5_000) });
      if (response.ok && response.headers.get('content-type')?.includes('application/json')) {
        const info = await response.json();
        if (info.commit === commit) return;
      }
    } catch {
      // Retry transient network errors and invalid responses within a fixed budget.
    }
    if (attempt + 1 < attempts) await sleep(delay);
  }
  throw new Error(`Commit ${commit} not published after ${attempts} checks`);
}

async function main() {
  const action = process.argv[2];
  const commit = process.env.GITHUB_SHA ?? execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  if (action === 'stamp') {
    stampBuild(process.argv[3] ?? 'dist', commit);
  } else if (action === 'config') {
    const url = productionConfig(process.env);
    appendFileSync(process.env.GITHUB_ENV, `E2E_BASE_URL=${url}\n`);
  } else if (action === 'candidate') {
    const current = execFileSync('git', ['ls-remote', 'origin', 'refs/heads/main'], { encoding: 'utf8' }).split(/\s/)[0];
    const deploy = isCurrentCommit(commit, current);
    appendFileSync(process.env.GITHUB_OUTPUT, `current=${deploy}\n`);
    if (!deploy) console.log(`Skipping stale candidate ${commit}; main is ${current}`);
  } else if (action === 'verify') {
    await waitForDeployment(process.env.E2E_BASE_URL, commit);
    console.log(`Published commit verified: ${commit}`);
  } else if (action === 'record-version') {
    validateCommit(commit);
    const version = parseDeploymentVersion(readFileSync(process.argv[3], 'utf8'));
    writeFileSync('deployment-info.json', JSON.stringify({ commit, version, run: process.env.GITHUB_RUN_ID }) + '\n');
    console.log(`Cloudflare version: ${version}`);
  } else {
    throw new Error('Use deployment.mjs stamp|config|candidate|verify|record-version');
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) await main();
