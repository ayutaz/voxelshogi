import type { PolicySource } from '../inference/policy-client';
import type { PolicyPosition, PolicyRoot, PolicySelection, PolicyValidation } from '../inference/policy-session';

export interface ModelSeat extends PolicySource { sourceId: string; repo: string; revision: string; sourceCommit: string; license: string }
export interface ModelConditions { sourceId: string; repo: string; revision: string; sourceCommit: string; license: string; selection: PolicySelection }
export interface ModelDecision { root: PolicyPosition; model: ModelSeat }
export interface ModelCompleted extends PolicyRoot {
  kind: 'model-result'; requestId: number; model: ModelConditions; validation: PolicyValidation;
  result: { bestMove: string | null; value: number | null; rawAction: number | null; rawLegal: boolean | null };
  inferenceMs: number; roundTripMs: number;
}
export function modelSeatKey(seat: Pick<ModelSeat, 'sourceId' | 'selection'>): string {
  if (typeof seat.sourceId !== 'string' || !/^[A-Za-z0-9-]{1,64}$/.test(seat.sourceId)) throw new Error('invalid local model source identity');
  const selection = seat.selection;
  return JSON.stringify([seat.sourceId, selection.modelId, selection.packageHash, selection.precision, selection.backend]);
}
