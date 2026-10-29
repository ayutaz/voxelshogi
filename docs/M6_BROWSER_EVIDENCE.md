# M6の実機ブラウザ計測の記録検査

目的は、学習済み3形式を対象実機で比較した記録について、未完了の測定を完了扱いにしないこと。[検査コード](../scripts/trained-browser-evidence.mjs)はmetadataだけを検査し、GPUやモデルを実行しない。実モデルの読み込み・推論・実機操作の証拠は別に採取する。

## 完了として受理する記録

- Linux実機、固定したアプリcommit、学習済みモデルのsource／Hub revision／manifestと全3ONNXのhashを記録する。
- FP32／FP16／INT8重み版×WASM／WebGPU×固定4局面×3Dあり／なしの48条件を列挙し、欠落・重複を拒否する。初回、準備10回、測定30回を区別する。
- 成功した条件には、Rustの合法な手とaction、全4入力・Policy全1,067,985要素とValueの同形式参照照合、実行providerとoperatorの記録を要求する。[学習済み数値契約](M6_MAIN.md#fp32変換の失敗と次の基準)のmarkerと出力別atol／rtolを照合し、広い上限や非有限な差を拒否する。
- WebGPUはNVIDIAのadapter、3DはNVIDIAのrendererを確認する。実際に準備・推論したbackendと選択条件を照合する。
- 3Dありでは、反復推論中の実描画・trusted camera入力を記録する。描画と資源観測の5秒超の空白、資源サンプル不足を完了へ含めない。RSSは共有ページを重複計上し得る観測値、main JS heapはWorker／GPUを含まない値として扱う。
- WASMの全3形式を測定する。GPUの未対応・数値基準未達は実際の初期化エラーとして残し、404や一般的な実行失敗を未対応へ分類しない。GPUモデルの成功条件も必要。
- WASMとWebGPUで各20回、直前と異なる実行可能版へ切り替え、各回の同形式照合と資源観測を記録する。初回ロードは回数へ含めない。未対応形式を成功した切替として数えない。

`candidate=true`の記録は候補パッケージの私的な事前検証としてだけ受理し、最終の公開証拠とは区別する。smokeや未完了の行を全量の結果へ昇格させない。HFのmanual gateは維持し、モデルをCloudflareへ複製しない。

## ローカルとCI

手書きのopaque metadataによる7テストをREDから実装した。欠落・重複、CPU代替、数値照合不一致、別モデル混入、初回を含む切替、未対応の誤分類、描画／資源観測不足、候補・smoke・Macの混同を拒否する。Macではこの小さいmetadataテストだけを実行し、モデル・GPU・ブラウザ計測を行わない。

追加14件の既知変異は`mutation-controls.mjs`に含め、CI制御の合計33変異を実行する。通常の`node --test scripts/ci/*.test.mjs`と必須CIへ自動で含まれる。これらのテスト成功自体は実モデルの実機検証ではない。

## 実際の計測スクリプト

外部Linuxで、[実行スクリプト](../scripts/measure-trained-models.mjs)に、HFハーネスで全件照合したフォルダーと固定revisionのcatalogを渡す。

```bash
# Linuxのみ。対象sourceで pnpm --dir apps/web wasm を済ませる。
node scripts/measure-trained-models.mjs runs/m6/verified-model runs/m6/catalog.json runs/m6/browser-full.json https://voxelshogi.yousan-apps.workers.dev
# 公開catalogへの登録前は --candidate を付ける。候補のmetadataだけを私的に差し替え、最終公開証拠とは扱わない。
```

公開アプリのinference-buildから実Workerのpath・bytes・hashを照合し、実ファイルをFileとして専用Workerへ渡す。Rustで固定棋譜を再生してrootと合法手を作り、表示にも同じ棋譜を読み込む。初回は新context／Worker、反復は同じ検証済みsessionを使う。準備10回を除いた30回で、実応答を遅延させず、CPU出力readbackを含むinferenceMsと往復時間を別々に残す。描画・trusted inputは測定区間で実リクエストがpendingのときだけ数える。

NVIDIAの実機ブラウザを起動し、SystemInfoでGPUサービスの初期化を待つ。48条件と各backendで20実切替、Worker終了、RSS・main heap・取得不能なGPU総量の理由を記録する。新しいcontextをcoldと呼ぶが、OS／driver cacheの初期化までは保証しない。初期化時のGPU未対応は理由を保持し、実行失敗・404と区別する。

`--smoke --candidate`はWASM FP32の1条件・準備10回＋測定1回・2切替だけの動作確認。Linux CIの実ONNXによる[スモークE2E](../apps/web/arena-model-e2e/benchmark.spec.mjs)へ含め、学習済みモデル／物理GPU／全量計測の完了には数えない。Macでは実行しない。

Arenaの操作は既存の[モデルE2E](../apps/web/arena-model-e2e/arena.spec.ts)で、各形式の合法手・棋譜条件・再開／停止・速度・中断・人間対AIを確認する。外部Linuxの `M6_MODEL_FIXTURE` は、検証した実モデルのmodel/とcatalog.json、破損拒否検証専用のcorrupted/を置いた私的フォルダーを指定できる。CIの初期値は従来の合成metadata＋未学習重みであり、学習結果へ読み替えない。

ドライバーの8つの純粋テストは、履歴・手番・解放、初回を除く20切替、ファイルの初回送信、応答ID／progress、Worker交換、中断、エラーstage、準備と測定の分離、手計算した行動IDを検証する。追加10変異を含めCI制御の合計43変異で検出確認する。

FP16重み版はmanifestの`fp16-weight-only`に対応する`model.variants[].fp16WeightOnly`と、Worker検証の同フラグ／`computePrecision=float32`を照合する。混合FP16は従来どおり`shader-f16`を要求する。重み版をnative FP16演算と呼ばず、同じ数値基準と48条件・各20切替を維持する。

2026-10-29の学習済み候補計測では、48条件の数値照合と40実切替が通った後、WASMの3D条件でtrusted camera入力が0のため全量検査が失敗した。準備10回が終わる前に20回の操作を使い切っていた。操作開始は実際の測定リクエストがpendingになった後へ移し、失敗・完了した要求は操作開始を待ち続けない。独立したイベント順の軽量テスト2件と、待機を除去する変異で検出する。数値・描画・操作の検査条件を緩めず、失敗記録を保持して再計測する。CI制御の既知変異は45件。
