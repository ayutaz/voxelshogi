// @vitest-environment jsdom
import {cleanup,render,screen} from '@testing-library/react';
import {afterEach,expect,it} from 'vitest';
import {MoveList} from '../src/components/Panels';
import type {Snapshot} from '../src/game/store';
afterEach(cleanup);
it('labels a White-first imported record consistently at the start and after its first move',()=>{
  const snap={side:'w',ply:0,moves:['111222','999888']} as Snapshot;
  const {rerender}=render(<MoveList snap={snap} onGoto={()=>{}}/>);
  expect(screen.getByRole('button',{name:/^1\./}).textContent).toContain('☖');
  expect(screen.getByRole('button',{name:/^2\./}).textContent).toContain('☗');
  rerender(<MoveList snap={{...snap,side:'b',ply:1}} onGoto={()=>{}}/>);
  expect(screen.getByRole('button',{name:/^1\./}).textContent).toContain('☖');
});
