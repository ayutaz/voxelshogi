# 実Mのブラウザ演算検証

再試行時のGit管理worker、HFの応答照合と早期解放は[復旧手順](P6_EXECUTION_RECOVERY.md)を使う。
通信失敗の旧0ケース記録を残し、復旧コードの検証を実ブラウザ測定の完了と混同しない。

Workerはruntime初期化、モデル取得、session作成、fixture読込、各warmup／測定、releaseの進行を送る。
controllerは進行ごとに結果JSONへ保存し、時間上限・Workerエラーでも最後の段階とfixture／stepを残す。
進行通知は完了として扱わず、1ケース180秒の固定期限を更新しない。
全8ケース・fixture 0／3・各8 warmup＋32測定・全出力数値基準は維持する。
この実装だけで旧timeoutの原因が判明した、または全構造／WebGPUが成功したとは扱わない。

Vast作成APIの`env`は[公式CLI](https://github.com/vast-ai/vast-cli/blob/master/vast.py)の
`parse_env`と同じJSON mapで`NVIDIA_DRIVER_CAPABILITIES=all`を指定する。
CLIの`-e ...`文字列をJSON値へそのまま送らない。
[NVIDIAの定義](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html)では、
未指定の既定はcompute／utilityで、Vulkanにはgraphicsが必要になる。
次の所有実機で環境変数・Vulkan device・実ブラウザのproviderを確認し、
このpayload修正だけを過去のWebGPU失敗原因の確定や推論成功と扱わない。

2026-11-05。[実行計画](P6_EXECUTION_PLAN.md)の2で使う計測手順。
実M・ONNXと単GPUの計測済みファイルを使い、ブラウザ対応は別に検証する。
この手順の追加は実ブラウザ測定の完了記録ではない。

## 目的と固定条件

Full／Axial／Geometry／3D-CNNの未学習seed66001、20〜35M規模の実ONNXを対象とする。
4構造×WASM／WebGPUの8組、各組で凍結fixture 0／3、各8 warmup＋32測定を行う。
全Policy 1,067,985要素とValue 1要素を、公開した同じCUDA FP32の参照値と比較する。
Policy atol／rtolは1e-4、Valueは両方1e-5。合法手内argmaxも一致を要求する。

研究用の512MiB以下のファイルを別契約で扱い、既存M3／M6の64MiB上限やモデルID・承認を緩めない。
通常のWeb配信には組み込まず、外部Linuxのloopbackに限定した一時HTTPサーバーを使う。
モデルと全参照、ORT runtimeの実bytesとSHA-256をブラウザでも確認する。
公開HFのmanual取得ゲートを別の公開配布で迂回しない。

## 外部Linuxでの手順

前提は、指定したHF固定revisionの全ファイルhash・public/manual・Community OFFの再確認、
関連CIを通ったclean source、固定Node／pnpmと依存lock、Playwrightブラウザの導入である。
データ・モデル・大きなstagingは外部Linuxに置き、Macへ中継しない。
`PUBLICATION`は検証済みのoperator公開folder、plan／receiptはその実公開のものを指定する。

```bash
uv run --project infrastructure/cuda --locked python -m training.research_browser_inputs \
  PUBLICATION FRESH_BROWSER_INPUTS --plan PUBLICATION_PLAN.json --receipt VERIFIED_RECEIPT.json
node scripts/research-browser-probe.mjs FRESH_BROWSER_INPUTS FRESH_RUN/result.json
```

準備処理は全公開ファイルを再hashし、receiptのrelease hash・固定revisionを照合する。
元ONNXをbyte一致でコピーし、safetensorsの全参照をlittle-endian float32へ抽出する。
参照入力は凍結したRust局面と一致を要求し、準備後にも元の全公開物を再hashする。

実行処理は既存Webの`openBackend`を使うWorkerだけを一時bundleする。
HTTPサーバーは127.0.0.1へbindし、列挙したpayload・runtime・Workerだけを返す。
1組ごとに新しいcontextとWorkerを作り、推論時間はCPUへの出力読戻し・GPU完了を含める。
operator profileで実際のproviderを確認し、WebGPUのCPU fallback・software adapterを成功にしない。
OS／driver cacheは制御していない。RSSは前後の観測値でありpeakとは表記しない。

## 判断と残る作業

`matrix_complete`は全8組の結果が得られたこと、`complete`は全8組成功を表す。
WASMで4構造すべて成功しない場合はコマンドを失敗にする。
WebGPUの失敗もメッセージ・段階・provider情報を残し、WASM成功へ混ぜない。
成功した構造とbackendの一覧を対応候補とし、失敗や未測定を対応済みと表記しない。
ネットワーク失敗を自動的に「演算未対応」と分類しない。

軽量テストは手計算の全要素誤差・既知のSHA-256・matrix・providerの不正を検出する。
Linuxのstagingテストは不透明なfake ONNXを使う入出力検証で、実M推論の証拠ではない。
実測結果の固定HF保存・資源解放、学習済みMの変換版、観戦表示・操作・実スマートフォン、
各対応端末60分と公開E2Eは別途実行して記録する。

## 取得先とWorkerの境界

初回PRのCodeQLで、message由来のURLを取得する経路（`js/client-side-request-forgery`）とorigin検証の欠落が指摘された。必須jobが成功していても、errorを含むため保護ルールが取り込みを拒否した。この結果を残し、再解析で修正を確認する。

研究payloadの取得APIはURLを受け取らず、同一originの`/payload/`とURL componentとしてエンコードしたファイル名だけを使う。Cookieを送らずredirectも拒否する。HTTP側も同じエンコード済み経路を登録する。ORT runtimeはWorker自身の127.0.0.1 origin、固定version・既知のファイル名へ限定し、messageに別originや別pathがある場合は拒否する。

WorkerはDedicatedWorkerGlobalScopeの所有者用implicit MessagePortだけを受理し、そのmessageの空origin・null sourceをpayloadの読み取り前に確認する。Window向けのcross-document messageとは区別する（[HTMLのWorker定義](https://html.spec.whatwg.org/multipage/workers.html#dom-dedicatedworkerglobalscope-postmessage)、[MessageEventの定義](https://html.spec.whatwg.org/multipage/comms.html#the-messageevent-interface)）。軽量VMテストで、異なるorigin・送信元・Window相当のscopeがモデル処理へ到達しないことを確認する。これは実ブラウザ測定の代わりではない。
