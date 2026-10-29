// Pure runtime port; no real ORT, model, GPU or Rust execution.
import { afterEach, expect, it, vi } from 'vitest';
import { openBackend } from '../src/inference/backend';
import type { RuntimeIndex } from '../src/inference/runtime';
const fake = vi.hoisted(() => ({ load: vi.fn(), end: vi.fn(), release: vi.fn(), dispose: vi.fn() }));
vi.mock('../src/inference/runtime', () => ({ loadRuntime: fake.load }));
afterEach(() => vi.clearAllMocks());
it('flushes native placement events without releasing the reusable session', async () => {
  const original = console.log;
  fake.end.mockImplementation(() => console.log('{"cat":"Node","args":{"provider":"CPUExecutionProvider","op_name":"MatMul"}}'));
  fake.load.mockResolvedValue({ runtimeBytes: 10, dispose: fake.dispose, ort: {
    env: { wasm: {} }, InferenceSession: { create: async () => ({ endProfiling: fake.end, release: fake.release }) },
  } });
  const port = await openBackend({ assetBase: 'https://fixture.invalid/', index: { runtime: {} } } as RuntimeIndex, 'wasm', 'fp32');
  try {
    const session = await port.createSession(new Uint8Array(3), 'fp32');
    expect(port.profile()).toEqual({ providers: {}, operators: {} });
    await session.finishProfiling?.();
    expect(fake.end).toHaveBeenCalledTimes(1);
    expect(port.profile()).toEqual({ providers: { CPUExecutionProvider: 1 }, operators: { MatMul: 1 } });
    expect(fake.release).not.toHaveBeenCalled();
    await session.release(); expect(fake.release).toHaveBeenCalledTimes(1);
  } finally { await port.dispose(); }
  expect(console.log).toBe(original); expect(fake.dispose).toHaveBeenCalledTimes(1);
});
