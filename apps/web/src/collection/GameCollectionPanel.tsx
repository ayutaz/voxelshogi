import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { SubmissionClient } from './client';
import { COLLECTION_CONSENT, isGameSubmission, type GameSubmission } from './contract';

interface Props {
  mode: GameSubmission['mode']; selectedAgents: GameSubmission['selectedAgents']; getRecord: () => string;
  finished: boolean; canAbort: boolean; imported: boolean; onAbort: () => void;
}
export function GameCollectionPanel({ mode, selectedAgents, getRecord, finished, canAbort, imported, onAbort }: Props) {
  const client = useMemo(() => new SubmissionClient(), []);
  const status = useSyncExternalStore(client.subscribe, client.snapshot);
  const [checked, setChecked] = useState(false);
  const [setup, setSetup] = useState<{ available: boolean; commit: string } | null>(null);
  const [error, setError] = useState(false);
  const [receipt, setReceipt] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const requestId = useRef(crypto.randomUUID());
  const terminalSeen = useRef(false);
  useEffect(() => {
    let active = true;
    const abort = new AbortController();
    const read = async (path: string): Promise<unknown> => {
      const response = await fetch(path, { signal: abort.signal, credentials: 'omit', cache: 'no-store', redirect: 'error' });
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('metadata unavailable');
      return response.json();
    };
    void Promise.all([read('/api/collection'), read('/build-info.json')]).then(([config, build]) => {
      if (!active) return;
      const c = config as { enabled?: unknown; consent?: unknown }, b = build as { commit?: unknown };
      if (!c || !b || typeof b.commit !== 'string' || !/^[0-9a-f]{40}$/.test(b.commit)) throw new Error('invalid metadata');
      setSetup({ available: c.enabled === true && c.consent === COLLECTION_CONSENT, commit: b.commit });
    }).catch(() => { if (active) setSetup({ available: false, commit: '' }); });
    return () => { active = false; abort.abort(); client.setConsent(false); };
  }, [client]);
  const capture = useCallback(async (ending: 'finished' | 'aborted') => {
    if (!checked || imported || !setup?.available) return;
    try {
      const record: unknown = JSON.parse(getRecord());
      if (ending === 'aborted' && record && typeof record === 'object') Object.assign(record, { result: null, termination: 'Abandoned' });
      const packet = { schema: 1, requestId: requestId.current, consent: COLLECTION_CONSENT, ending,
        applicationCommit: setup.commit, mode, conditionsScope: 'selected-at-submission', selectedAgents, record };
      if (!isGameSubmission(packet)) throw new Error('invalid submission');
      setSubmitted(true);
      const result = await client.send(packet);
      if (result.state === 'sent') setReceipt(packet.requestId);
    } catch { setError(true); }
  }, [checked, imported, setup, getRecord, mode, selectedAgents, client]);
  useEffect(() => {
    if (!finished || terminalSeen.current) return;
    terminalSeen.current = true;
    void capture('finished');
  }, [finished, capture]);
  const retry = async () => { const result = await client.retry(); if (result.state === 'sent') setReceipt(requestId.current); };
  return <section className="collection-panel" aria-label="対局データの送信">
    <h2>対局データの送信（任意）</h2>
    <label className="check"><input type="checkbox" data-testid="collection-consent" checked={checked}
      disabled={!setup?.available || imported || !!receipt || (!checked && (finished || submitted))} onChange={event => { const next = event.target.checked; setChecked(next); client.setConsent(next); setError(false); }} />
      この対局の棋譜とAI設定を、改善調査のため送信する</label>
    <p className="muted">既定はOFFです。拒否しても遊べます。ONにした対局の終局時、または下の中断操作時に1回送ります。保持は30日が目安。学習やHF公開へ自動利用しません。<a href="/privacy.html" target="_blank" rel="noreferrer">送信内容・保持・削除の案内</a></p>
    {receipt ? <p className="muted">この対局は送信済みです。別の棋譜は送信しません。</p> : !checked && finished ? <p className="muted">終局後に送信をONにはできません。次の対局で開始前に選んでください。</p> : submitted && !checked ? <p className="muted">送信を停止しました。再開する場合は新しい対局で同意してください。</p> : null}
    {imported ? <p className="muted">読み込んだ棋譜は送信しません。</p> : setup && !setup.available ? <p className="muted">サーバー送信は現在利用できません。棋譜は端末へ保存できます。</p> : null}
    <button type="button" data-testid="collection-abort" disabled={!checked || !canAbort || imported || status.state !== 'idle' || !setup?.available}
      onClick={() => { onAbort(); void capture('aborted'); }}>ここまでを中断棋譜として送信</button>
    <p className="muted">OFFにすると未送信分と再送待ちを破棄します。送信済みデータの削除は案内の窓口へご相談ください。</p>
    {status.state === 'sending' && <p role="status">棋譜を送信中… 対局はそのまま操作できます。</p>}
    {status.state === 'sent' && <p role="status">棋譜が保存されました（合法性は未検証）。</p>}
    {(status.state === 'failed' || error) && <div role="alert"><p>送信できませんでした。対局と端末への保存は続けられます。</p>
      {status.state === 'failed' && <button type="button" onClick={() => void retry()}>同じ棋譜を再送</button>}</div>}
    {receipt && <p className="muted model-source" data-testid="collection-receipt">送信ID：{receipt}</p>}
  </section>;
}
