import type { ArenaOptions } from '../ai/arena-controller';
import type { CollectionAgent } from './contract';

/** Normalizes settings; the automatic collector freezes these at the first real move. */
export function collectionAgents(options: ArenaOptions): { b: CollectionAgent; w: CollectionAgent } {
  const agent = (side: 'b' | 'w'): CollectionAgent => {
    if ((side === 'b' && options.mode === 'h-r') || (side === 'w' && options.mode === 'r-h')) return { kind: 'human' };
    const difficulty = side === 'b' ? options.bDifficulty : options.wDifficulty;
    if (difficulty === 'easy') return { kind: 'easy', seed: options.seed };
    if (difficulty === 'normal') return { kind: 'normal', seed: options.seed, maxDepth: options.limits.maxDepth ?? 6,
      maxNodes: options.limits.maxNodes ?? 50000, maxTimeMs: options.limits.maxTimeMs ?? 1000 };
    const model = side === 'b' ? options.bModel : options.wModel;
    if (!model) throw new Error('selected model is missing');
    return { kind: 'model', modelId: model.selection.modelId, repo: model.repo, revision: model.revision,
      sourceCommit: model.sourceCommit, license: model.license, precision: model.selection.precision,
      backend: model.selection.backend, packageHash: model.selection.packageHash };
  };
  return { b: agent('b'), w: agent('w') };
}
