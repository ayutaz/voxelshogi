// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { BoardFrame } from '../src/components/BoardFrame';
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it('keeps the 2D escape available after a 3D renderer failure', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  const fallback = vi.fn();
  function Broken(): never { throw new Error('WebGL unavailable'); }
  render(<BoardFrame on2D={fallback}><Broken /></BoardFrame>);
  expect(screen.getByRole('alert').textContent).toContain('立体盤を読み込めませんでした');
  fireEvent.click(screen.getByRole('button', { name: '2Dで続ける' }));
  expect(fallback).toHaveBeenCalledTimes(1);
});
