import { HAND_KINDS, parseMove, type Color } from '../game/model';
import { POLICY_ELEMENTS } from './manifest';

const SQUARES = 729, CHANNELS = 43, NORMAL_ACTIONS = 1062882;
const HAND_TOTALS = [162, 64, 48, 32, 16, 24, 24] as const;
function checkSide(side: Color) {
  if (side !== 'b' && side !== 'w') throw new Error('invalid side to move');
}

/** Encoding only. Rust validates positions and supplies legal moves. */
export function encodePosition(board: ArrayLike<number>, hands: ArrayLike<number>, side: Color): Float32Array {
  checkSide(side);
  if (board.length !== SQUARES || hands.length !== 14) throw new Error('invalid board/hands dimensions');
  for (let i = 0; i < SQUARES; i++) {
    if (!Number.isInteger(board[i]) || board[i]! < 0 || board[i]! > 28) throw new Error('invalid piece code');
  }
  for (let i = 0; i < 14; i++) {
    if (!Number.isInteger(hands[i]) || hands[i]! < 0 || hands[i]! > HAND_TOTALS[i % 7]!) throw new Error('invalid hand count');
  }
  const handFeatures = new Float32Array(14);
  for (let i = 0; i < 14; i++) handFeatures[i] = hands[side === 'b' ? i : (i + 7) % 14]! / HAND_TOTALS[i % 7]!;
  const features = new Float32Array(SQUARES * CHANNELS);
  for (let cell = 0; cell < SQUARES; cell++) {
    const piece = board[side === 'b' ? cell : 728 - cell]!;
    const channel = side === 'b' || piece === 0 ? piece : (piece - 1 + 14) % 28 + 1;
    features[cell * CHANNELS + channel] = 1;
    features.set(handFeatures, cell * CHANNELS + 29);
  }
  return features;
}

export function policyAction(text: string, side: Color): number {
  checkSide(side);
  if (typeof text !== 'string') throw new Error('move notation must be a string');
  const move = parseMove(text), to = side === 'b' ? move.to : 728 - move.to;
  if (move.from === null) return NORMAL_ACTIONS + HAND_KINDS.indexOf(move.drop!) * SQUARES + to;
  const from = side === 'b' ? move.from : 728 - move.from;
  return 2 * (from * SQUARES + to) + Number(move.promote);
}

export interface PolicyChoice { move: string; action: number; value: number; rawAction: number; rawLegal: boolean }
export function selectPolicyMove(policy: Float32Array, value: Float32Array, legal: readonly string[], side: Color): PolicyChoice {
  checkSide(side);
  if (!(policy instanceof Float32Array) || policy.length !== POLICY_ELEMENTS || !(value instanceof Float32Array) || value.length !== 1 || !Number.isFinite(value[0]) || Math.abs(value[0]!) > 1) throw new Error('invalid policy/Value output dimensions or values');
  if (legal.length === 0 || legal.length > POLICY_ELEMENTS) throw new Error('no legal moves supplied by the engine');
  let rawAction = 0, rawScore = -Infinity;
  for (let action = 0; action < POLICY_ELEMENTS; action++) {
    const score = policy[action]!;
    if (!Number.isFinite(score)) throw new Error('nonfinite policy output');
    if (score > rawScore) { rawAction = action; rawScore = score; }
  }
  const choices = legal.map(move => ({ move, action: policyAction(move, side) })).sort((a, b) => a.action - b.action);
  const ids = new Set(choices.map(choice => choice.action));
  if (ids.size !== choices.length) throw new Error('duplicate engine legal actions');
  let best = choices[0]!;
  for (const choice of choices) if (policy[choice.action]! > policy[best.action]!) best = choice;
  return { ...best, value: value[0]!, rawAction, rawLegal: ids.has(rawAction) };
}
