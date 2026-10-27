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
