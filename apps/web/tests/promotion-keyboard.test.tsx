// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { PromotionDialog } from '../src/components/Panels';

afterEach(cleanup);
it('moves focus into promotion choices, traps Tab in both directions and restores the board trigger', () => {
  render(<button type="button">盤の移動先</button>);
  const trigger = screen.getByRole('button', { name: '盤の移動先' }); trigger.focus();
  const dialog = render(<PromotionDialog onChoose={vi.fn()} onCancel={vi.fn()} />);
  const promote = screen.getByRole('button', { name: '成る' });
  const plain = screen.getByRole('button', { name: '成らない' });
  const cancel = screen.getByRole('button', { name: 'キャンセル' });
  expect(document.activeElement).toBe(promote);
  fireEvent.keyDown(promote, { key: 'Tab', shiftKey: true }); expect(document.activeElement).toBe(cancel);
  fireEvent.keyDown(cancel, { key: 'Tab' }); expect(document.activeElement).toBe(promote);
  fireEvent.keyDown(promote, { key: 'Tab' }); expect(document.activeElement).toBe(plain);
  dialog.unmount(); expect(document.activeElement).toBe(trigger);
});
it('cancels with Escape without choosing a move or hijacking browser Tab shortcuts', () => {
  const choose = vi.fn(), cancel = vi.fn();
  render(<PromotionDialog onChoose={choose} onCancel={cancel} />);
  const promote = screen.getByRole('button', { name: '成る' }); promote.focus();
  const tab = new KeyboardEvent('keydown', { key: 'Tab', ctrlKey: true, bubbles: true, cancelable: true });
  promote.dispatchEvent(tab); expect(tab.defaultPrevented).toBe(false);
  fireEvent.keyDown(promote, { key: 'Escape' });
  expect(cancel).toHaveBeenCalledTimes(1); expect(choose).not.toHaveBeenCalled();
});
