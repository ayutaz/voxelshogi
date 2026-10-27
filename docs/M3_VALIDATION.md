# M3 段階別の検証

2026-10-27。**M3全体は未完了。** ローカルの固定ファイルで3形式の数値比較・実機WebGPU・3D同時動作・全48組の計測と20回の実切替を確認した。ライセンス確定、CIで作る実公開ファイルの照合・公開デモ・公開後の実機計測が残る。最新の固定結果は末尾の「ローカル固定配布物の実機計測」、各節は対象時点の記録として読む。[計画・G1〜G6](M3_PLAN.md) の全項目を満たすまで完了にしない。

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

## ブラウザ実モデルCIと計測コード

- `model-playwright.config.ts` の6 E2Eを追加。3形式それぞれの4局面・全Policy/Value照合、実Workerの推論中のtrustedなカメラ操作と実draw・中断・再試行、改ざんしたONNXのhash拒否、Worker内GPU機能を無効化した負例を検証する。GPU機能の負例はGPU実行の証拠として扱わない。実機Chromeで6件が成功（45.6秒、再試行なし）。共通化した観測helperで既存21件も28.0秒で全成功し、C0の追加3回も42.3秒・再試行なしで成功した。
- CIの専用 `models` jobはuvと固定Pythonから3形式を生成し、ローカル専用配布物をproduction buildへ含めて6件を実行する。通常PRにも適用し、失敗・skip・中断・欠落はCI Gateを止める。未承認モデルとそのtraceはartifactへ含めない。モデルE2Eの設定・テストもTypeScriptの検証対象とする。
- Node制御は58テスト。Gateの実モデルCI依存、RSS単位、公開ライセンス、clean source、配布hashの既知5変異も別プロセスの実行済みassertion失敗として検出し、通常CIへ追加する。
- `scripts/measure-browser-models.mjs` は全48組の初回／warm-up10＋測定30回、3Dの実入力／描画、main JS heapと専用Chrome process RSS、モデル20回切替とWorkerのcloseを記録する。RSS合計は共有ページの重複を含みうる観測値であり、実メモリの厳密なpeakとは呼ばない。native ORTのGPU総使用量はこのAPIから取得できないためN/Aと理由を保存する。
- 短い `--smoke` で実GPUの40推論、3Dの実操作・描画とメモリ取得、Workerの終了を確認した。`smoke=true, complete=false` を出力し、この値は正式な性能記録には採用しない。最終固定SHAによる全計測と公開後照合を別途実施する。

### 転送量と休止を含む計測の補強

WorkerのResource Timingから、取得URL・時間・HTTPヘッダーを含むtransferSize・圧縮されたbodyのencodedBodySize・展開後のdecodedBodySizeを区別して結果へ保存する。キャッシュ時の転送0とファイルサイズ0を混同しない。実モデルE2Eは各形式の実ONNX転送も確認し、休止を抑止した実行で6件が42.3秒・再試行なしで成功した。Webは169単体・既知48変異が成功している。

最初の全48組＋20回切替では、39組が合格、FP16×WebGPUの8組が事前基準に届かず拒否、FP16×WASMのmaterial-b・3Dなしの反復がタイムアウトした。`pmset -g log` で2026-10-27 05:34:42 UTCのIdle Sleepと05:43:02 UTCのWake、500秒の休止を確認。メモリ観測も05:34:44.337から05:43:03.866まで途切れており、この試行を正式な性能結果に採用しない。失敗ログと未完了扱いのJSONを保持する。20回のWorkerは全てcloseし、残存は0だった。

Macでの計測プロセスに限り `caffeinate -i -w <自プロセスPID>` を起動し、終了時に解除する。画面や恒久設定は変更しない。1秒ごとのメモリ観測が5秒を超えて途切れた場合も、計測中断として合格にしない。休止をまたいだ実モデルE2E・変異検証のタイムアウトも成功へ数えず、休止抑止下での成功を別に保存した。正式な全組計測は固定ビルドで再実行する。

## ローカル固定配布物の実機計測

2026-10-27 06:45:30〜06:55:32 UTC、Apple M1・8 GiB・macOS Darwin27.0.0・実機Chrome156.0.8078.48。計測／Webは `c19fb598e1c5ceb09e6b586131dd36583d55fcbd`、モデル生成は `d44f5aaaf8388933fce391741beca4976cdfa9f0`、双方clean。モデルmanifest SHAは `f28b1192f5654acbcf2f1084c26b85859fdba32ad0ecf56e6f783ee880ed3f32`。各ONNXのbytesとhashはM3-3の表と一致するが、ここではcleanな固定ソースから生成したものを測定した。モデルのlicenseはnull、publication=falseのlocalhost配布であり、公開済みとは扱わない。

- [全48組の生JSON](experiments/m3-browser-local.json)：3Dの有無×WASM／WebGPU×3形式×4局面。40組が全出力照合に成功、FP16×WebGPUの8組は事前基準未達として拒否。予期しない失敗0、観測間隔最大1,256ms。各成功組は初回1回とwarm-up10＋測定30回、全40回の全出力を照合した。GPUはCPU fallback無効・native providerの配置証拠を含み、CPUへのreadback完了を待って計時した。
- [休止した初回試行の記録](experiments/m3-browser-interrupted.json)：39成功・8数値拒否・1中断。元JSONのSHAと中断時刻を保存し、成功試行へ上書きしない。
- 全組計測の旧切替ループは初回FP32ロードを含む20回だったため、実際の変更は19回。この点を修正し、`b5a01bd1f238a11c68217fd8897438ba99d1f7a0` のcleanなコード／buildで[追加の20回実切替](experiments/m3-browser-switches-local.json)を実施した。初回を除く全20回が直前と異なる形式で、21 Worker作成／21終了・残存0。`switchesComplete=true`、`complete=false`とし、この追加試行だけで全組の性能測定成功とはしない。

以下は4局面それぞれの中央値の最小〜最大（ms）。p95は各局面でnearest-rankを求めたうちの最大値で、全局面を混ぜた百分位ではない。

| backend・形式 | 3Dなし median | 3Dあり median | 3Dあり p95最大 |
|---|---:|---:|---:|
| WASM FP32 | 304.80〜307.10 | 320.25〜334.40 | 387.30 |
| WASM FP16 | 393.80〜397.30 | 392.40〜395.70 | 401.20 |
| WASM INT8重み | 315.55〜322.70 | 318.40〜322.25 | 377.50 |
| WebGPU FP32 | 51.95〜53.95 | 53.00〜54.00 | 58.70 |
| WebGPU INT8重み | 53.15〜54.50 | 53.75〜55.05 | 60.80 |
| WebGPU FP16 | 数値基準未達 | 数値基準未達 | 採用しない |

この端末ではINT8重みの圧縮による推論高速化は確認できず、FP16のWASMもFP32より遅い。圧縮の利点は主に配布サイズで、棋力は未評価。3Dありの初回load段階（manifest・runtimeの準備とモデル／入力／参照値の取得・照合）はFP32 577.3〜767.4ms、FP16 348.3〜436.7ms、INT8重み221.5〜269.8ms。session初期化・初回推論・Worker往復・形式別転送量は生JSONに分けて保存した。localhostの値なのでインターネット越しのロード時間には換算しない。新contextでもOS／driver cacheは未制御であり、完全なcold bootではない。

成功した3Dあり20組すべてで実推論中のtrustedなカメラ入力と実drawを確認。推論中rAF間隔は全組のp95が16.7〜16.8ms、観測最大も約16.8ms。ただし入力から描画までの遅延や全負荷でのFPSを保証する値ではない。main pageのJS heap観測最大14,682,418 bytes、Chrome所有process RSS合計の観測最大1,545,256,960 bytes（約1.44 GiB）。RSSは共有ページの重複を含みうる。GPU総使用量とORT内部一時bufferはこのAPIから取得不可でN/A、既知の入出力tensorは4,397,332 bytes。Worker終了は確認したが、driverが保持する全メモリの即時返却までは証明しない。

## 公開準備と残る完了条件

PR #22〜#26は必須8チェック成功後に通常取り込み済み。PR #26のhead `c19fb59` は [CI](https://github.com/ayutaz/voxelshogi/actions/runs/40462994498)・[CodeQL](https://github.com/ayutaz/voxelshogi/actions/runs/40462994451)・[品質](https://github.com/ayutaz/voxelshogi/actions/runs/40462994406) が成功し、mainは `2cfac44`。PR #25統合後の [main CI](https://github.com/ayutaz/voxelshogi/actions/runs/40462552399) も公開確認まで成功した。これはモデル本体公開の証拠ではない。

[PR #27](https://github.com/ayutaz/voxelshogi/pull/27)では公開設定を `export/publication.json` に固定し、未承認のfalse/nullを維持する。承認後の経路用に、ライセンス・Model Card、アプリWorkerを含むbuild manifest、実配信全ファイルのhash／bytes／MIME／cacheの監査と公開6 E2Eを用意した。ローカルではWeb172単体・既知50変異、Node66単体・制御13変異、型・lint・build・actionlint、実機モデル6 E2Eが47.9秒・再試行なしで成功した。公開条件分岐は未実行で、成功扱いにしない。

| ゴール | 現在の根拠・残り |
|---|---|
| G1・G2 | 固定モデル・全3変換・同形式の基準比較をローカルで確認。M1 WebGPUのFP16は非対応として記録 |
| G3 | 実機WebGPU配置・3D入力／描画・中断／再試行・20回実切替を確認 |
| G4 | ローカルの固定SHAは一致。CIが作成する実公開ファイルの全配信照合は残る |
| G5 | ライセンス回答待ち。未学習モデルの全実行可能版を公開して各版を実ロードする検証は残る |
| G6 | [ADR-019](ARCHITECTURE_DECISIONS.md#adr-019-m3の精度形式backend配信方式2026-10-27)と[費用](COST_ESTIMATE.md)へローカルの判断を記録。公開バイト列の実機再計測と最終CI／公開確認は残る |

配信監査は公開サイトのmanifestだけで自己照合せず、ダウンロードした検証済みCI artifactのbuild／アプリ／モデルmanifestと一致させる。同じcommit名を保ったまま実Workerとmanifestを差し替える負例を先に失敗させ、検証を追加した。Worker照合・モデル照合を消す変異も検出。既存の探索観戦等の全21 E2Eも実機Chromeで23.7秒・再試行なしで成功した。

LinuxのCIで生成するONNXや参照値は、producer metadata等によりMacで生成したファイルとhashが異なる可能性がある。公開後は実配信された同じbytesでWebGPUを再測定し、このローカル結果を最終公開結果へ読み替えない。有料GPU・R2は利用していない。
