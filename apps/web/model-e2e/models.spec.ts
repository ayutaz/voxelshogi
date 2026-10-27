import { test, expect } from '@playwright/test';
import { installInteractionProbe, readInteractionProbe } from '../e2e/interaction-probe';
import type { ClientResult } from '../src/inference/client';

const fixtures = ['initial-b', 'after-one-w', 'mate-in-one-b', 'material-b'];
for (const variant of ['fp32', 'fp16', 'int8']) {
  test(`real WASM executes ${variant} and compares every output for all four positions`, async ({ page }) => {
    await page.goto('/?models=1');
    await page.getByLabel('3D表示').uncheck();
    await page.getByLabel('精度形式').selectOption(variant);
    for (const fixture of fixtures) {
      await page.getByLabel('検証局面').selectOption(fixture);
      await page.getByRole('button', { name: '推論を実行', exact: true }).click();
      await expect(page.getByTestId('inference-result')).toBeVisible({ timeout: 60_000 });
      const result = JSON.parse((await page.getByTestId('inference-json').textContent())!) as ClientResult;
      expect(result.request).toMatchObject({ variant, fixture, backend: 'wasm', packageHash: await page.getByTestId('model-hash').textContent() });
      expect(result.comparison.policy.elements).toBe(1_067_985);
      expect(result.comparison.value.elements).toBe(1);
      expect(result.comparison.policy.exceeded + result.comparison.value.exceeded).toBe(0);
      expect(result.metrics.samples).toHaveLength(1);
      expect(result.profile.providers.CPUExecutionProvider).toBeGreaterThan(0);
      expect(Object.keys(result.profile.providers)).toEqual(['CPUExecutionProvider']);
      expect(Number.isFinite(result.value)).toBe(true);
    }
  });
}

test('real inference leaves 3D camera responsive and cancellation prevents a late result', async ({ page }, testInfo) => {
  await installInteractionProbe(page, { phaseTestId: 'inference-phase', cancelTestId: 'cancel-inference', runningText: 'running' });
  await page.goto('/?models=1');
  await expect(page.getByTestId('board3d')).toHaveAttribute('data-ready', 'true');
  await expect(page.getByRole('button', { name: '中断', exact: true })).toHaveAttribute('data-testid', 'cancel-inference');
  await page.getByRole('button', { name: '推論を実行', exact: true }).click();
  await expect(page.getByTestId('inference-result')).toBeVisible({ timeout: 60_000 });
  await page.getByRole('button', { name: '30回を計測', exact: true }).click();
  await expect(page.getByTestId('inference-phase')).toHaveAttribute('data-phase', 'running', { timeout: 60_000 });
  await page.evaluate(() => window.interactionProbe.armCamera());
  const box = (await page.getByTestId('board3d').boundingBox())!;
  await page.mouse.move(box.x + box.width * .4, box.y + box.height * .4);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * .6, box.y + box.height * .6, { steps: 6 });
  await page.mouse.up();
  await expect(page.getByTestId('inference-phase')).toHaveAttribute('data-phase', 'cancelled');
  const timeline = await readInteractionProbe(page), camera = timeline.camera!;
  expect(camera).toMatchObject({ pending: true, trusted: true, phase: 'running' });
  const down = timeline.events.filter(e => e.kind === 'pointerdown' && e.at <= camera.at).at(-1)!;
  expect(down.pending).toBe(true);
  expect(timeline.events.some(e => e.kind === 'draw' && e.pending && e.at > down.at && e.at <= camera.at)).toBe(true);
  expect(timeline.events.some(e => e.kind === 'terminate' && e.at >= camera.at)).toBe(true);
  await expect(page.getByTestId('inference-result')).toHaveCount(0);
  await testInfo.attach('real-model-interaction.json', { body: JSON.stringify(timeline), contentType: 'application/json' });
  await page.getByLabel('3D表示').uncheck();
  await page.getByRole('button', { name: '推論を実行', exact: true }).click();
  await expect(page.getByTestId('inference-result')).toBeVisible({ timeout: 60_000 });
});

test('corrupted model bytes are rejected by hash and a new Worker can retry', async ({ page, context }) => {
  const pattern = '**/models/m3/models/**/fp32.onnx';
  await context.route(pattern, async route => {
    const response = await route.fetch(), bytes = Buffer.from(await response.body());
    bytes[0] = bytes[0]! ^ 1;
    await route.fulfill({ status: 200, contentType: 'application/octet-stream', body: bytes });
  });
  await page.goto('/?models=1'); await page.getByLabel('3D表示').uncheck();
  await page.getByRole('button', { name: '推論を実行', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText(/hash/i, { timeout: 60_000 });
  await expect(page.getByTestId('inference-result')).toHaveCount(0);
  await context.unroute(pattern);
  await page.getByRole('button', { name: '推論を実行', exact: true }).click();
  await expect(page.getByTestId('inference-result')).toBeVisible({ timeout: 60_000 });
});

test('an unavailable GPU is reported by the real Worker without CPU substitution', async ({ page, context }) => {
  // A negative capability test, never evidence of GPU execution.
  await context.route('**/assets/inference.worker-*.js', async route => {
    const response = await route.fetch();
    await route.fulfill({ status: 200, contentType: 'text/javascript', body: 'Object.defineProperty(navigator,"gpu",{value:undefined});\n' + await response.text() });
  });
  await page.goto('/?models=1'); await page.getByLabel('3D表示').uncheck();
  await page.getByLabel('実行先').selectOption('webgpu');
  await page.getByRole('button', { name: '推論を実行', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('WebGPU is not available', { timeout: 60_000 });
  await expect(page.getByTestId('inference-result')).toHaveCount(0);
});
