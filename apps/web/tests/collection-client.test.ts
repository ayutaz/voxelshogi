import { expect, it, vi } from 'vitest';
import { SubmissionClient } from '../src/collection/client';

function frozen() { return { schema: 1, requestId: '00000000-0000-4000-8000-000000000001', consent: 'game-research-v1' }; }
it('makes zero requests without consent, including an ended game', async () => {
  const fetcher = vi.fn(); const client = new SubmissionClient(fetcher);
  expect(await client.send(frozen())).toEqual({ state: 'off' }); expect(fetcher).not.toHaveBeenCalled();
  client.setConsent(true); client.setConsent(false);
  expect(await client.send(frozen())).toEqual({ state: 'off' }); expect(fetcher).not.toHaveBeenCalled();
});
it('sends once when consented and retries the exact frozen body after a network failure', async () => {
  const fetcher = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(Response.json({ requestId: frozen().requestId, status: 'received_unverified' }, { status: 201 }));
  const client = new SubmissionClient(fetcher); client.setConsent(true);
  const value = frozen(); expect((await client.send(value)).state).toBe('failed');
  value.schema = 2;
  expect((await client.retry()).state).toBe('sent');
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(fetcher.mock.calls[0]![1].body).toBe(fetcher.mock.calls[1]![1].body);
  expect(JSON.parse(fetcher.mock.calls[0]![1].body)).toMatchObject({ schema: 1 });
  expect((await client.send(frozen())).state).toBe('sent'); expect(fetcher).toHaveBeenCalledTimes(2);
});
it('turning consent OFF cancels the request and deletes its retry payload', async () => {
  let finish!: (value: Response) => void;
  const fetcher = vi.fn(() => new Promise<Response>(resolve => { finish = resolve; }));
  const client = new SubmissionClient(fetcher); client.setConsent(true);
  const pending = client.send(frozen());
  const signal = (fetcher.mock.calls[0] as unknown as [string, RequestInit])[1].signal!;
  client.setConsent(false); expect(signal.aborted).toBe(true);
  finish(Response.json({ requestId: frozen().requestId, status: 'received_unverified' }, { status: 201 }));
  expect(await pending).toEqual({ state: 'off' });
  client.setConsent(true); expect((await client.retry()).state).toBe('idle'); expect(fetcher).toHaveBeenCalledTimes(1);
});
it('does not accept HTML, mismatched acknowledgements, or server errors as saved', async () => {
  for (const response of [new Response('<html/>'), Response.json({ requestId: 'other', status: 'received_unverified' }), Response.json({ error: 'collection_limit' }, { status: 429 })]) {
    const client = new SubmissionClient(vi.fn().mockResolvedValue(response)); client.setConsent(true);
    expect((await client.send(frozen())).state).toBe('failed');
  }
});
it('suppresses duplicate effect sends while pending and resets state for the next game', async () => {
  let finish!: (value: Response) => void;
  const fetcher = vi.fn(() => new Promise<Response>(resolve => { finish = resolve; }));
  const client = new SubmissionClient(fetcher); client.setConsent(true);
  const pending = client.send(frozen());
  expect((await client.send(frozen())).state).toBe('sending'); expect(fetcher).toHaveBeenCalledTimes(1);
  client.newGame(); finish(Response.json({ requestId: frozen().requestId, status: 'received_unverified' }));
  expect((await pending).state).toBe('idle');
});

it('calls the native browser fetch with its required global receiver', async () => {
  const nativeLike = vi.fn(function (this: unknown) {
    if (this !== globalThis) throw new TypeError('Illegal invocation');
    return Promise.resolve(Response.json({ requestId: frozen().requestId, status: 'received_unverified' }));
  });
  vi.stubGlobal('fetch', nativeLike);
  try {
    const client = new SubmissionClient(); client.setConsent(true);
    expect((await client.send(frozen())).state).toBe('sent');
    expect(nativeLike).toHaveBeenCalledTimes(1);
  } finally { vi.unstubAllGlobals(); }
});
