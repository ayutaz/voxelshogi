import { expect, it } from 'vitest';
import { encodePosition, policyAction, selectPolicyMove } from '../src/inference/policy-contract';
import { POLICY_ELEMENTS } from '../src/inference/manifest';

function position() {
  const board = new Uint8Array(729);
  board[0] = 1; board[100] = 8; board[728] = 28;
  return { board, hands: new Uint8Array([81, 16, 12, 8, 4, 6, 6, 0, 0, 0, 0, 0, 0, 12]) };
}
it('encodes all cells and hand channels with independent sparse expectations for Black', () => {
  const { board, hands } = position(), result = encodePosition(board, hands, 'b');
  expect(result).toBeInstanceOf(Float32Array); expect(result.length).toBe(31347);
  for (let cell = 0; cell < 729; cell++) {
    const expected = new Array<number>(43).fill(0);
    expected[cell === 0 ? 1 : cell === 100 ? 8 : cell === 728 ? 28 : 0] = 1;
    expected.splice(29, 14, .5, .25, .25, .25, .25, .25, .25, 0, 0, 0, 0, 0, 0, .5);
    expect(Array.from(result.slice(cell * 43, cell * 43 + 43))).toEqual(expected);
  }
  expect(board[0]).toBe(1); expect(hands[0]).toBe(81);
});

it('reverses every axis and swaps ownership/hands for White without changing piece kinds', () => {
  const { board, hands } = position(), result = encodePosition(board, hands, 'w');
  for (let cell = 0; cell < 729; cell++) {
    const expected = new Array<number>(43).fill(0);
    // Original cell 728 White dragon -> own dragon 14 at 0;
    // original cell 100 Black king -> opposing king 22 at 628;
    // original cell 0 Black pawn -> opposing pawn 15 at 728.
    expected[cell === 0 ? 14 : cell === 628 ? 22 : cell === 728 ? 15 : 0] = 1;
    expected.splice(29, 14, 0, 0, 0, 0, 0, 0, .5, .5, .25, .25, .25, .25, .25, .25);
    expect(Array.from(result.slice(cell * 43, cell * 43 + 43))).toEqual(expected);
  }
});

it('uses each standard piece count as its own hand denominator', () => {
  const counts = [162, 64, 48, 32, 16, 24, 24];
  const result = encodePosition(new Uint8Array(729), Uint8Array.from([...counts, ...counts]), 'b');
  expect(Array.from(result.slice(29, 43))).toEqual(new Array(14).fill(1));
});

for (const [move, black, white] of [
  ['111211', 2, 1062878], ['211111+', 1459, 1061423], ['111999+', 1457, 1061425],
  ['999111', 1061424, 1456], ['P*111', 1062882, 1063610], ['R*999', 1067984, 1067256],
  ['L*111', 1063611, 1064339], ['N*111', 1064340, 1065068], ['S*111', 1065069, 1065797],
  ['G*111', 1065798, 1066526], ['B*111', 1066527, 1067255],
] as const) {
  it(`maps ${move} to the hand-calculated canonical action`, () => {
    expect(policyAction(move, 'b')).toBe(black); expect(policyAction(move, 'w')).toBe(white);
  });
}

it('selects only Rust-supplied legal moves and resolves tied policies by canonical ID', () => {
  const policy = new Float32Array(POLICY_ELEMENTS);
  policy[0] = 1000; // illegal global maximum
  expect(selectPolicyMove(policy, new Float32Array([-.5]), ['211111', '111211'], 'b'))
    .toEqual({ move: '111211', action: 2, value: -.5, rawAction: 0, rawLegal: false });
  expect(selectPolicyMove(policy, new Float32Array([-.5]), ['111211', '211111'], 'w'))
    .toEqual({ move: '211111', action: 1061422, value: -.5, rawAction: 0, rawLegal: false });
  policy[1458] = 2000;
  expect(selectPolicyMove(policy, new Float32Array([.25]), ['111211', '211111'], 'b'))
    .toEqual({ move: '211111', action: 1458, value: .25, rawAction: 1458, rawLegal: true });
});

it('rejects every nonfinite output, including illegal and last policy entries', () => {
  for (const bad of [NaN, Infinity, -Infinity]) {
    const policy = new Float32Array(POLICY_ELEMENTS); policy[POLICY_ELEMENTS - 1] = bad;
    expect(() => selectPolicyMove(policy, new Float32Array([0]), ['111211'], 'b')).toThrow(/finite/i);
  }
});

it('rejects malformed tensors, moves, empty/duplicate legal sets and invalid Value', () => {
  const policy = new Float32Array(POLICY_ELEMENTS);
  for (const value of [new Float32Array(), new Float32Array([NaN]), new Float32Array([1.1]), new Float32Array([0, 0])])
    expect(() => selectPolicyMove(policy, value, ['111211'], 'b')).toThrow();
  expect(() => selectPolicyMove(new Float32Array(3), new Float32Array([0]), ['111211'], 'b')).toThrow();
  for (const legal of [[], ['111211', '111211'], ['bad'], ['K*111'], ['000111']])
    expect(() => selectPolicyMove(policy, new Float32Array([0]), legal, 'b')).toThrow();
});

it('rejects invalid board/hands metadata before producing features', () => {
  const board = Array<number>(729).fill(0), hands = Array<number>(14).fill(0);
  for (const invalid of [board.slice(1), [...board.slice(1), 29], [...board.slice(1), -.5], [...board.slice(1), NaN]])
    expect(() => encodePosition(invalid, hands, 'b')).toThrow();
  for (const invalid of [hands.slice(1), [163, ...hands.slice(1)], [.5, ...hands.slice(1)], [NaN, ...hands.slice(1)]])
    expect(() => encodePosition(board, invalid, 'b')).toThrow();
  expect(() => policyAction('111211', 'x' as 'b')).toThrow();
  expect(() => policyAction(111211 as unknown as string, 'b')).toThrow();
});
