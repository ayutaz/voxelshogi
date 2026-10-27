# M3 段階別の検証

2026-10-27。**M3全体は未完了。** [計画・G1〜G6](M3_PLAN.md) の全項目、実機WebGPU、各変換版の数値比較・公開デモ・最終公開の検証が必要。各節は対象時点の固定記録とし、依存smoke testだけでモデル推論の完了にしない。

## M3-0：uv環境・入出力・比較契約

- Python3.14.9、uv0.11.23。`uv add` からtorch2.14.1、numpy2.5.4、onnx1.23.2、onnxruntime1.31.1、onnxscript0.7.2、onnxconverter-common1.16.0、開発用pytest9.1.1とruff0.17.3を追加。解決された全依存と配布物hashは `uv.lock` に保存した。
- Mac M1で `uv run --locked` 経由のimport・小演算・dynamoによるopset18 ONNX変換・checker・ORT CPU推論を確認。`x=[-2,0,3]` に対する `y=2*x+1` の手計算 `[-3,1,7]` と一致。3.13へのfallbackは不要。
- Linuxのtorchだけ公式CPU indexを使い、GPUなしCIへCUDA一式を導入しない。[uv公式のPyTorch構成](https://docs.astral.sh/uv/guides/integration/pytorch/) を参照し、OSごとの解決をlockへ固定した。
- [モデル契約](MODEL_CONTRACT.md)：729×43の手番側表現、成り・駒打ちを含む1,067,985指し手ラベル、Policy/Value、全出力のshape・有限性と事前の形式別誤差基準を定義。
- TDD：`export.contract` 未実装によるREDを確認後、手計算fixtureを満たす最小実装。27件が成功。空出力・ゼロ出力・NaN/Inf・形状違い・両手番・成駒・持ち駒・番号の境界を含む。
- 既知変異5件：後手の軸反転、持ち駒の所有交換、成りラベル、誤差超過の拒否、基準値の有限性。隔離コピーでpytestの実行済み失敗を確認し、コンパイル／収集エラーを検出扱いにしない。`uv run --locked python scripts/ci/mutation-python.py` で再実行できる。
- Pythonの失敗・skip・中断・欠落がGateを止めるテストを先にREDにし、必須 `CI Gate` へPython jobを追加してGREEN。CI制御Nodeは50件。Python jobはlock整合・lint・format・27テスト・既知変異を実行する。共通の依存監査にもuv auditを追加し、Python CodeQLを必須チェックへ追加する。既存のcoverage集計のPythonもuvから実行する。
- `uv audit --locked` は27依存に既知の脆弱性・adverse statusなし。監査時点の結果であり将来の安全性の保証ではない。

代表モデルの正確なパラメータ数、出力照合、FP16／量子化、Web Worker・WebGPU・配信方式はM3-1以降で実装・検証する。モデルのライセンスは公開前に確定する。現時点でモデルの公開・学習・有料GPU利用は行っていない。

PR #20の初回CIでは、uv0.11.23に埋め込まれたPython配布一覧が3.14.9を認識できず、Python・監査・coverage集計が開始前に失敗した。3.13へ下げず、`actions/setup-python` で `.python-version` の処理系を先に用意する。依存管理とすべてのPython処理は引き続きuv経由にする。ローカルでも管理済み3.14.9をuvから使用しており、ライブラリ未対応ではない。

## M3-1：代表モデルとFP32変換（ローカル検証）

- 729 token・幅256・6層・8 head・FFN1024、実数で **5,021,064パラメータ**。Policyはfrom/to内積の2組（成りなし／あり）と駒打ち7種、Valueは手番側のtanh出力。6層すべてが実行され、ONNXにも6個のSoftmaxがあることを検証する。未使用の重みだけで5Mへ水増ししない。
- 固定seed314159でcheckpointをsafetensorsへ保存する。ライブラリは `uv add safetensors` で追加。PyTorchモデル・FP32 ONNX・入力・全出力の基準値と、依存版・ソースSHA／dirty・ソースファイルhashをmanifestへ記録する。
- 標準初期局面、1手進行の後手、成駒を含む戦術局面、持ち駒ありの4入力。入力snapshotは既存Rust/WASMから作成し、`node scripts/model-fixtures.mjs --check` で棋譜から再照合する。特徴量の期待値は別の手計算テストで検証する。
- opset18・dynamo exporter・固定batch1、外部重みなし。初回開発測定のONNXは20,420,291 bytes、checkpointは20,092,056 bytes。固定batch1の配布なので、batch8のbrowser測定はこの版では対象外。学習用PyTorchのbatch設計とは区別する。
- 4入力×Policy 1,067,985要素＋Value 1要素を全件照合。初回開発測定のPolicy最大絶対誤差は約2.00e-6、Valueは約1.79e-7で、事前のFP32基準を全要素が満たした。開発中の `sourceDirty=true` の測定であり、最終配布ファイルの確認と混同しない。
- 同じ環境・条件で2回生成し、manifest・checkpoint・ONNX・全参照ファイルのhashが一致することをテスト。別seedの重み差・入力を変えた出力差も確認する。入力値をゼロにしただけの成功にはしない。
- 改ざんファイル、パスの逸脱、出力shape、入力dtype、重複fixture、空variantを拒否する。shape/dtype/重複の拒否は先に失敗を確認して実装した。
- Pythonは計37テスト。既知変異は10件へ追加（attentionのsoftmax軸、Policyの成り並び、seed無視、6層の素通り、ファイルhash照合の欠落）。隔離コピーで全件検出した。

再生成は `uv run --locked python -m export.generate runs/m3/fp32-local`。モデルはまだローカルのみ。ライセンス確定後に作る公開配布物と、各低精度版・browserの数値比較は後続段階で実施する。

## M3-2：専用Worker・検証付き配信（開発途中）

- ORT Web 1.31.1のWebGPU bundleと、それが実際に参照するAsyncify bootstrap／WASMを組み合わせる。JSEP版との混用は実機で初期化失敗になったため使用しない。WASMは28,747,738 bytesあり、16 MiB単位の分割を取得して各部分・再結合後のSHA-256を検証する。JSも検証したbytesから読み込み、照合後に別URLのJSを再取得しない。MITライセンスと同版の第三者ライセンス通知を配布物に含める。
- 公開用の準備処理は未承認ライセンスとdirtyなソースを拒否する。ローカル検証用の配布物は `publication=false` とし、ブラウザ側もlocalhost以外では拒否する。モデル自体はgitへ追加しない。
- 専用Worker、要求ID・revision・モデルmanifest hash・形式・入力・backendの応答照合、中断時の終了、古い応答の破棄を実装。各要求でsessionとtensorを解放し、runtimeは同じWorkerで再利用する。40回モードはwarm-up10回・測定30回とし、中央値・nearest-rank p95を計算する。全40回の全出力を照合し、最大誤差を保持する。
- Mac M1の実機Chromeから専用Workerを通し、4局面すべてでFP32のPolicy 1,067,985要素とValueを基準値へ照合した。Policy最大絶対誤差はWASMで約1.49e-6、WebGPUで約1.81e-6。native profilingでは各1推論につきWASMはCPU provider 256 node、WebGPUはGPU provider 276 nodeで、GPU側のCPU fallbackは無効にした。要求したbackend名だけをGPU実行の証拠にはしない。
- 開発用モデルはM3-1の `sourceDirty=true` の同じローカル配布物。最終固定SHA・公開配布物の計測には数えない。実機probeは `runs/m3/worker-probe.json`（git管理外）へ保存した。公開用の固定測定JSONはM3-4で作成する。
- 新規単体47件、配信Node6件、型チェック・lintが成功。Webの既知変異は29件から40件へ追加し、全40件を実行済みのassertion失敗として検出した。全出力末尾の照合、session／tensor解放、GPU配置証拠、warm-up、中央値、最悪誤差保持、revisionと古いcallback、Worker終了、hash省略を含む。

画面、低精度版、3D同時動作・反復切替の最終計測、公開モデル・公開E2Eは残っている。専用Workerの局所確認だけでM3-2〜5やM3全体を完了にしない。

### 選択画面の追加（開発途中）

`/?models=1` に未学習の表示、配布manifestに存在する全形式・backend・4局面の選択、1回実行とwarm-up10＋測定30回、中断・再試行、3Dと断面表示、全出力の数値比較とhashの表示を追加した。実機Chromeで画面からWASM／WebGPU推論を行い、GPUの反復推論中にもカメラ操作と中断が可能なことを確認した。production buildにも専用Workerを別ファイルとして出力する。

StrictModeの解放、要求変更後の遅延した結果・progressの破棄、manifest取得失敗後の再試行をUI単体3件で検証。UIの既知変異4件も追加し、Web全44件の検出を確認した。これは低精度版や最終公開E2Eの代替にはしない。

## M3-3：FP16・INT8変換（ローカル開発測定）

同じFP32モデルから [契約](MODEL_CONTRACT.md#m3-3で比較する変換方式) の設定でFP16とINT8（重み）を作成する。FP16は入出力float32・内部float16、INT8は31 tensor／5,000,000要素を圧縮してfloat32へ逆量子化する。INT8の演算自体はfloat32であり、計算のINT8高速化と呼ばない。各形式の同じONNXをnative ORT CPUで実行し、4局面の全出力を形式別の基準値として保存する。FP32との差も別項目に保存する。

| 形式 | 開発配布物bytes | SHA-256 | FP32からのPolicy最大絶対差（4局面最大） |
|---|---:|---|---:|
| FP32 | 20,420,291 | `fa9e9c0bdfb3865fdbc00f72c85b444d241894883011b29af82294bc7bf1314a` | 0 |
| FP16 | 10,391,274 | `93d67d0613041d8fe85c0ed99762b8852358f2dd71b9b397c51e60961fbe5bc5` | 約0.0014863 |
| INT8（重み） | 5,426,735 | `c885770f7550f9a7a93e4722c266271decfd1678f07eb3c9418cde8bbb273d17` | 約0.0112903 |

未学習なので数値変化を棋力の低下と解釈しない。開発中のdirtyソースからの測定であり、最終配布物の再生成と公開照合は別に行う。

Mac M1・実機Chromeの専用Workerで、WASMは3形式×4局面が全出力照合に成功した。Policy最大絶対誤差はFP32で約1.49e-6、FP16で0.0009765625、INT8で約1.08e-6。WebGPUはFP32・INT8が各4局面に成功し、各最大は約1.81e-6と1.79e-6、native profileは全nodeがGPU providerだった（FP32 276、INT8 308 node/推論）。

**FP16 × M1 WebGPUは数値基準未達**。同じFP16ファイルの初期局面で674,245／1,067,985 Policy要素が事前基準を超過し、最大絶対差0.021484375、RMSE約0.0051392だった。basicでも同程度で、最適化allだけの問題には限定できない。中間出力の比較では、最初の入力projectionは完全一致、QKV projectionで最大差約0.01465、Attention後で約0.03418と差が増えた。LayerNormalizationのみfloat32、動的MatMul＋Softmaxをfloat32に保つ診断用候補も基準に届かず、採用していない。これらは破棄した診断候補であり、公開版への無記録の差し替えには使わない。CPU基準の最適化・GPUの累積精度等が関係する可能性はあるが、vendor kernelの根因まで断定しない。

FP16は検証済みのWASMで実行できる。WebGPUで基準未達なら出力は採用せず、超過数・最大誤差・閾値をエラー表示する。FP32等への自動fallbackで成功にしない。形式ごとに検証を通るbackendと不合格・未測定を区別するというM3計画に従い、最終固定配布物でも同じ全比較を行う。

Pythonは48テストへ拡充し、INT8の手計算、符号・scale・ties-to-even、元グラフの保持、FP16の実際の型、全形式の再生成一致、欠けた／非有限の差分情報も検証する。既知Python変異は16件（丸め・scale・zero point・逆量子化・FP16 I/O・追加の量子化近似を含む）。ブラウザには形式別の最適化設定・差分の検証と表示・runtime再利用時の形式切替の回帰を追加し、既知Web変異47件を検出した。最終計測と公開モデルの配信はまだ完了していない。
