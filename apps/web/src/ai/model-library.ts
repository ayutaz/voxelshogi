import type { Color } from '../game/model';
import type { TrainedRelease } from '../inference/local-model';
import type { ModelManifest, Precision } from '../inference/manifest';
import { fp16WeightOnly } from '../inference/manifest';
import type { ModelFile } from '../inference/policy-protocol';
import type { PolicySelection } from '../inference/policy-session';
import { modelSeatKey, type ModelSeat } from './arena-model';

export interface LoadedModel { sourceId: string; release: TrainedRelease; model: ModelManifest; files: ModelFile[] }
export interface ModelChoice { sourceId: string; precision: Precision; backend: PolicySelection['backend'] }
export interface ModelLibrary { entries: LoadedModel[]; choices: Partial<Record<Color, ModelChoice>> }

export function addModel(state: ModelLibrary, entry: LoadedModel): ModelLibrary {
  if (state.entries.some(item => item.sourceId === entry.sourceId)) throw new Error('model source must be fresh');
  const previous = state.entries.find(item => item.release.id === entry.release.id);
  const entries = state.entries.filter(item => item !== previous).concat(entry);
  if (entries.length > 4) throw new Error('読み込めるモデルは4個までです');
  const choices = { ...state.choices };
  for (const side of ['b', 'w'] as const) {
    const choice = choices[side];
    if (previous && choice?.sourceId === previous.sourceId) choices[side] = { ...choice, sourceId: entry.sourceId };
  }
  return { entries, choices };
}
export function removeModel(state: ModelLibrary, sourceId: string): ModelLibrary {
  return { entries: state.entries.filter(entry => entry.sourceId !== sourceId),
    choices: Object.fromEntries(Object.entries(state.choices).filter(([, choice]) => choice.sourceId !== sourceId)) };
}
export function chooseModel(state: ModelLibrary, side: Color, choice: ModelChoice): ModelLibrary {
  const entry = state.entries.find(item => item.sourceId === choice.sourceId);
  if (!entry) throw new Error('model is not loaded');
  if (!entry.model.variants.some(variant => variant.precision === choice.precision)) throw new Error('precision is not available');
  if (!['wasm', 'webgpu'].includes(choice.backend)) throw new Error('invalid backend');
  return { ...state, choices: { ...state.choices, [side]: { ...choice } } };
}
export function modelSeat(state: ModelLibrary, side: Color): ModelSeat | undefined {
  const choice = state.choices[side], entry = state.entries.find(item => item.sourceId === choice?.sourceId);
  if (!choice || !entry) return undefined;
  const { repo, revision, sourceCommit, license } = entry.release;
  const seat: ModelSeat = { sourceId: entry.sourceId, repo, revision, sourceCommit, license, files: entry.files,
    selection: { modelId: entry.release.id, packageHash: entry.release.manifest.sha256, precision: choice.precision, backend: choice.backend },
    fixtures: entry.model.fixtures.map(fixture => fixture.name), ...(fp16WeightOnly(entry.model.variants.find(v => v.precision === choice.precision)!) ? { fp16WeightOnly: true } : {}) };
  modelSeatKey(seat);
  return seat;
}
