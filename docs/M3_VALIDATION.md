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
