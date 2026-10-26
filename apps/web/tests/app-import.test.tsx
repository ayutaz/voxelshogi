// @vitest-environment jsdom
import { StrictMode } from 'react';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, expect, it } from 'vitest';
import { App } from '../src/App';
import { loadWasm } from './loadWasm';

beforeAll(loadWasm);
afterEach(cleanup);
const fixtures = JSON.parse(readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../../crates/voxelshogi-wasm/tests/fixtures/search.json'), 'utf8')) as { record: unknown }[];

it('ignores an obsolete file read but accepts a fresh import under StrictMode', async () => {
  const mounted = render(<StrictMode><App /></StrictMode>);
  const pawn = () => mounted.container.querySelector('.board2d [data-square="382"]')!.textContent;
  expect(pawn()).toBe('歩');
  let finish!: (text: string) => void;
  const lateFile = { size: 1000, text: () => new Promise<string>((resolve) => { finish = resolve; }) };
  fireEvent.change(screen.getByTestId('import'), { target: { files: [lateFile] } });
  fireEvent.click(screen.getByRole('button', { name: '新規対局', exact: true }));
  await act(async () => { finish(JSON.stringify(fixtures[0]!.record)); });
  expect(pawn()).toBe('歩');
  expect(screen.queryByRole('alert')).toBeNull();
  await act(async () => {
    fireEvent.change(screen.getByTestId('import'), { target: { files: [{ size: 1000, text: async () => JSON.stringify(fixtures[0]!.record) }] } });
  });
  expect(pawn()).toBe(''); // the valid two-king record has no pawn on layer V
  expect(screen.getByRole('alert').textContent).toBe('棋譜を読み込みました');
});
