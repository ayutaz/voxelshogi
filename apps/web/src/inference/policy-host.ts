import { parsePolicyRequest, policyRoot, samePolicySelection, type ModelFile, type PolicyFailure, type PolicyPhase, type PolicyProgress, type PolicyRequest, type PolicyResponse } from './policy-protocol';
import { parsePolicyPosition, parsePolicySelection, type PolicySelection, type PolicySession, type PolicyValidation } from './policy-session';

export interface PolicyRuntime { session: Pick<PolicySession, 'bestMove' | 'dispose'>; validation: PolicyValidation }
export type CreatePolicyRuntime = (files: ModelFile[], selection: PolicySelection, phase: (value: PolicyPhase) => void) => Promise<PolicyRuntime>;

function failure(value: unknown, code: PolicyFailure['code'], error: unknown): PolicyFailure {
  const object = value && typeof value === 'object' ? value as Record<string, unknown> : {};
  const requestId = typeof object.requestId === 'number' && Number.isSafeInteger(object.requestId) && object.requestId > 0 ? object.requestId : 0;
  let selection: PolicyFailure['selection'] = null, root: PolicyFailure['root'] = null;
  try { selection = parsePolicySelection(object.selection); root = policyRoot(parsePolicyPosition(object.root)); } catch { /* Invalid requests cannot supply a trusted root. */ }
  const message = error instanceof Error && error.message ? error.message.slice(0, 500) : 'policy Worker failed';
  return { schema: 1, kind: 'error', requestId, selection, root, code, message };
}

/** Serial dedicated-Worker host. A fatal error requires a fresh Worker. */
export class PolicyWorkerHost {
  private active: PolicyRuntime | null = null;
  private selection: PolicySelection | null = null;
  private busy = false;
  private closed = false;
  constructor(private readonly create: CreatePolicyRuntime, private readonly progress: (value: PolicyProgress) => void = () => {}) {}

  async run(value: unknown): Promise<PolicyResponse> {
    let request: PolicyRequest;
    try { request = parsePolicyRequest(value); } catch (error) { return failure(value, 'input', error); }
    if (this.closed) return failure(request, 'input', new Error('policy Worker is closed; create a new Worker'));
    if (this.busy) return failure(request, 'busy', new Error('policy Worker is busy'));
    if ((this.selection && !samePolicySelection(this.selection, request.selection)) || (this.active && request.files)) return failure(request, 'input', new Error('model/source changes require a new Worker'));
    if (!this.active && !request.files) return failure(request, 'input', new Error('first policy request requires model files'));
    this.busy = true;
    let stage: PolicyFailure['code'] = 'initialization';
    const phase = (phase: PolicyPhase) => {
      if (!this.closed) this.progress({ schema: 1, kind: 'progress', requestId: request.requestId, selection: { ...request.selection }, root: policyRoot(request.root), phase });
    };
    try {
      if (!this.active) {
        phase('loading');
        const prepared = await this.create(request.files!, request.selection, phase);
        if (this.closed) { await prepared.session.dispose(); throw new DOMException('policy initialization cancelled', 'AbortError'); }
        this.active = prepared; this.selection = { ...request.selection };
      }
      stage = 'inference'; phase('running');
      const result = await this.active.session.bestMove(request.root);
      if (this.closed) throw new DOMException('policy move cancelled', 'AbortError');
      return { schema: 1, kind: 'result', requestId: request.requestId, result, validation: this.active.validation };
    } catch (error) {
      let cleanupFailed = false;
      try { await this.dispose(); } catch { cleanupFailed = true; }
      const reply = failure(request, stage, error);
      if (cleanupFailed) reply.message = reply.message.slice(0, 470) + '; resource cleanup failed';
      return reply;
    } finally { this.busy = false; }
  }
  async dispose(): Promise<void> {
    this.closed = true;
    const active = this.active; this.active = null; this.selection = null;
    await active?.session.dispose();
  }
}
