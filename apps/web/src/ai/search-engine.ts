import { Game } from '../wasm/pkg/voxelshogi_wasm.js';
import { createRng, pickRandomMove } from './random';
import { identity, parseAiResult, parseRequest, type AiResult, type SearchFailure, type SearchReply } from './search-protocol';

/** One dedicated worker owns this engine, its WASM initialization and each Game. */
export class SearchEngine {
  private ready: Promise<void> | null = null;
  private busy = false;
  constructor(private readonly initialize: () => Promise<void>, private readonly now = () => performance.now()) {}

  async run(data: unknown): Promise<SearchReply> {
    const root = identity(data);
    const failure = (code: SearchFailure['code'], error: unknown): SearchFailure =>
      ({ ...root, kind: 'error', code, message: error instanceof Error ? error.message : String(error) });
    if (this.busy) return failure('busy', 'Worker already has an active search');
    let request;
    try { request = parseRequest(data); } catch (error) { return failure('input', error); }
    this.busy = true;
    const start = this.now();
    let stage: SearchFailure['code'] = 'initialization';
    let game: Game | undefined;
    try {
      this.ready ??= this.initialize();
      await this.ready;
      const initialized = this.now();
      stage = 'input';
      game = Game.fromRecordJson(request.recordJson);
      game.goto(request.cursor);
      if (game.hash() !== request.hash || game.sideToMove() !== request.side) throw new Error('record/cursor does not match requested root');
      const replayed = this.now();
      stage = 'execution';
      let result: AiResult;
      if (request.difficulty === 'easy') {
        result = parseAiResult(JSON.parse(game.bestMove(JSON.stringify({ maxDepth: 0, maxNodes: 0, maxGamePly: request.limits.maxGamePly }))), request);
        if (result.stopReason !== 'terminal') result = { schema: 1, bestMove: pickRandomMove(game.legalMoves(), createRng(request.seed)), score: null,
          completedDepth: 0, nodes: '0', lastIterationNodes: '0', ttHits: '0', stopReason: 'random' };
      } else {
        result = parseAiResult(JSON.parse(game.bestMove(JSON.stringify(request.limits))), request);
      }
      const searched = this.now();
      return { ...root, kind: 'result', result, metrics: { initMs: initialized - start,
        replayMs: replayed - initialized, searchMs: searched - replayed, totalMs: searched - start } };
    } catch (error) { return failure(stage, error); }
    finally { game?.free(); this.busy = false; }
  }
}
