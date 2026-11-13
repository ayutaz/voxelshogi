export type SubmissionState = { state: 'off' | 'idle' | 'sending' | 'sent' | 'failed' };

/** One game, one frozen payload. No background retries or unload transmission. */
export class SubmissionClient {
  private consent = false;
  private generation = 0;
  private body: string | null = null;
  private requestId = '';
  private active: AbortController | null = null;
  private state: SubmissionState = { state: 'off' };
  private listeners = new Set<() => void>();
  constructor(private fetcher: typeof fetch = fetch) {}
  snapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private publish(state: SubmissionState['state']) { this.state = { state }; for (const listener of this.listeners) listener(); return this.state; }
  setConsent(enabled: boolean) {
    if (enabled === this.consent) return;
    this.consent = enabled;
    this.newGame();
  }
  newGame() {
    this.generation++; this.active?.abort(); this.active = null; this.body = null; this.requestId = '';
    return this.publish(this.consent ? 'idle' : 'off');
  }
  async send(value: unknown): Promise<SubmissionState> {
    if (!this.consent) return this.state;
    if (this.state.state !== 'idle') return this.state;
    try {
      if (!value || typeof value !== 'object' || !('requestId' in value) || typeof value.requestId !== 'string') throw new Error('invalid submission');
      this.body = JSON.stringify(value); this.requestId = value.requestId;
    } catch { return this.publish('failed'); }
    return this.transmit();
  }
  async retry(): Promise<SubmissionState> {
    if (!this.consent || this.state.state !== 'failed' || !this.body) return this.state;
    return this.transmit();
  }
  private async transmit(): Promise<SubmissionState> {
    const generation = this.generation, abort = new AbortController(); this.active = abort;
    const timeout = setTimeout(() => abort.abort(), 10000);
    this.publish('sending');
    try {
      const response = await this.fetcher('/api/games', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: this.body, signal: abort.signal, credentials: 'omit', cache: 'no-store', redirect: 'error' });
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('not acknowledged');
      const ack: unknown = await response.json();
      if (!ack || typeof ack !== 'object' || !('requestId' in ack) || ack.requestId !== this.requestId || !('status' in ack) || !['received_unverified', 'verified', 'rejected'].includes(String(ack.status))) throw new Error('invalid acknowledgement');
      if (generation !== this.generation) return this.state;
      return this.publish('sent');
    } catch {
      return generation === this.generation ? this.publish('failed') : this.state;
    } finally { clearTimeout(timeout); if (this.active === abort) this.active = null; }
  }
}
