import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { LoadedModel } from '../ai/model-library';
import { loadLocalModel, parseTrainedCatalog, readTrainedCatalog, type TrainedRelease } from './local-model';
import { localFile, packModelFiles } from './policy-protocol';

type Packet = Omit<LoadedModel, 'sourceId'>;
function guidance(error: string): string {
  if (/hash mismatch|size mismatch/.test(error)) return 'ファイルの内容が配布情報と一致しません。配布先からフォルダーを取得し直してください。';
  if (/missing local model file/.test(error)) return '必要なファイルが足りません。取得したモデルのフォルダー全体を選んでください。';
  if (/folder|file count/.test(error)) return 'モデルのフォルダーを1つ選んでください。分割したフォルダーや、上位フォルダーは選ばないでください。';
  if (/size|oversized/.test(error)) return '読み込み可能な容量を超えています。公開Sモデルのフォルダーを確認してください。';
  if (/catalog|download/.test(error)) return '配布情報を取得できません。通信を確認して、モデル読み込みを開き直してください。';
  return 'モデルを読み込めませんでした。配布元・フォルダー内のファイル・対応する精度形式を確認してください。';
}
export default function ModelLibraryPanel({ onLoaded }: { onLoaded: (packet: Packet) => void }) {
  const [releases, setReleases] = useState<TrainedRelease[] | null>(null);
  const [selected, setSelected] = useState('');
  const [message, setMessage] = useState('配布情報を読み込み中…');
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0), read = useRef<AbortController | null>(null);
  const loaded = useRef(onLoaded);
  useLayoutEffect(() => { loaded.current = onLoaded; }, [onLoaded]);
  useEffect(() => {
    let active = true;
    const abort = new AbortController();
    void readTrainedCatalog('/models/m6/catalog.json', fetch, abort.signal).then(parseTrainedCatalog).then(items => {
      if (!active) return;
      setReleases(items); setSelected(items[0]?.id ?? ''); setMessage('');
    }).catch(reason => { if (active) setError(String(reason)); });
    return () => { active = false; abort.abort(); generation.current += 1; read.current?.abort(); };
  }, []);
  const release = releases?.find(item => item.id === selected);
  const cancel = () => { generation.current++; read.current?.abort(); };
  const load = async (files: File[]) => {
    cancel();
    if (!release) return;
    const current = generation.current, abort = new AbortController(); read.current = abort;
    setError(null); setMessage('フォルダーの配布情報を確認中…');
    try {
      const packed = packModelFiles(files);
      const source = await loadLocalModel(packed.map(localFile), release, abort.signal);
      if (current !== generation.current) return;
      loaded.current({ release: source.release, model: source.model, files: packed });
      setMessage('フォルダーを追加しました。AI開始時にモデルと同形式の参照値をWorkerで検査します。');
    } catch (reason) {
      if (current === generation.current) { setError(String(reason)); setMessage(''); }
    }
  };
  return <div className="model-library" data-testid="model-library">
    <p className="muted">公開Sは「AIと対戦」または先手・後手のAI設定で選ぶと自動で読み込めます。申請・ログインは不要です。</p>
    <p className="muted">以下は、手元に保存したモデルを使う場合の追加操作です。</p>
    <ol className="muted"><li>HFの配布ファイル一式を同じフォルダーへダウンロードする。</li><li>そのフォルダーを選択し、先手・後手のAIでモデルと精度形式を選ぶ。</li></ol>
    <p className="muted">公開Sは1ファイル最大64MiB、フォルダー合計512MiBまで。推論は端末のCPU／GPUを使います。フォルダー選択に対応するPCブラウザをおすすめします。</p>
    {releases?.length === 0 && <p>公開済みの学習モデルはまだありません。</p>}
    {!!releases?.length && <>
      <label>配布モデル<select value={selected} data-testid="model-release" onChange={event => { cancel(); setSelected(event.target.value); setError(null); setMessage(''); }}>
        {releases.map(item => <option key={item.id} value={item.id}>{item.id}</option>)}
      </select></label>
      {release && <p><a href={`https://huggingface.co/${release.repo}/tree/${release.revision}`} target="_blank" rel="noreferrer">Hugging Faceで取得</a>（{release.license}）</p>}
      <label>取得したモデルのフォルダー<input type="file" multiple {...{ webkitdirectory: '' }} data-testid="model-folder" onChange={event => {
        const files = Array.from(event.target.files ?? []); event.target.value = ''; if (files.length) void load(files);
      }} /></label>
    </>}
    {message && <p role="status">{message}</p>}
    {error && <div role="alert"><p>{guidance(error)}</p><details><summary>技術情報</summary><p>{error}</p></details></div>}
  </div>;
}
