# M6の固定評価ハーネス

M6-3〜4の評価コードを学習前に準備した。**実データでの学習・test評価・60局の対局はまだ実行していない。** 事前条件は[M6教師・評価契約](M6_TRAINING_CONTRACT.md)、全体の完了条件は[M6計画](M6_PLAN.md)を参照する。

## 評価する重みを固定する

`training.evaluate`は、未学習seed314159、val最良checkpoint、または実際の変換済みONNXを受け付ける。学習済み候補は完了epochのbest参照だけから読む。入力cacheのhash・教師契約・学習config・コードcommit・step／学習例数・val選択を照合し、途中epochやtestで選んだという設定を拒否する。optimizerを公開用の重みに含めず、選択したmodelのTensorだけをsafetensorsに固定する。

変換版は配布packageの全ファイルhashを検証し、指定したFP32・FP16・INT8ファイルを読む。学習済みpackageには選択元のbinding／receiptと、Torchで評価したsafetensorsのhashを要求する。この来歴の追加は後続の学習済みexport実装へ接続する。別形式への自動置換はしない。

```bash
# 外部Linuxのみ。CUDA環境・承認済みの実機で実行する形。まだ実行していない。
uv run --project infrastructure/cuda --locked python -m training.evaluate runs/m6/cache runs/m6/eval-initial --baseline --max-seconds 3600
uv run --project infrastructure/cuda --locked python -m training.evaluate runs/m6/cache runs/m6/eval-trained --training-run runs/m6/train --max-seconds 3600
uv run --project infrastructure/cuda --locked python -m training.evaluate runs/m6/cache runs/m6/eval-int8 --bundle runs/m6/export --precision int8 --device cpu --max-seconds 3600
```

ONNXの参照評価はORT CPU・batch1・1 threadで明示的に実行する。INT8重み版はM3と同じbasic最適化、他の2形式はall最適化を使う。これをCUDA／WebGPU実機の性能値と呼ばない。Torch側も実行backendと重みhashを出力し、すべて合法集合の最大logit、同点は最小canonical IDを使う。Valueはこの最初の対局policyには使わず、探索AIをニューラル探索に置き換えたとは扱わない。

## testと対局

固定testの有効教師を全件読み、Policy Top-1／Top-5・交差エントロピー、Value MSE／MAE、マスク前後の合法手率を記録する。監査済みtest件数と一致しなければ成功にしない。完了したtest結果は入力hashと自身のhashを照合して再利用する。途中停止は未完了として残し、testで学習やモデル選択はしない。

対局は固定seedの合法な序盤8手を一度作り、その同じ棋譜からモデルの先後を入れ替える。Randomはseed7000〜7019の40局、M1探索は8000〜8009の20局。Randomのseedは100000＋序盤seed、M1は深さ2／10,000ノード／TT4,096。手数上限は序盤を含む256手で、最終手の自然終局を先に判定する。

Rustの棋譜では上限終了が`Draw/MaxPlies`で表現されるが、評価では**cutoffに分類し、自然引分へ加算しない**。自然引分は千日手。勝敗は終局結果の勝者とモデルの担当色から判定し、最後に指した色で推測しない。一次指標は勝数／開始局数で、cutoffも分母に残す。

95%区間は、序盤seedごとの先後2局を一組としてbootstrapする。10,000回・seed314159、昇順の250番目と9,750番目を区間とする。少数の序盤による結果であり、0勝や同一の組平均から得た狭い区間を、棋力一般の確実性として解釈しない。勝・負・自然引分・cutoffの生カウントも表示する。

## 停止・再開と証拠

完了した対局を1局ずつatomicに保存する。`--resume`ではモデルhash・コード・評価条件を照合し、保存棋譜の全手・終局・序盤prefixをRustで再検証してから再利用する。モデルを切り替えた同じrunへの再開は拒否する。終了した2局が揃わない組は集計を完了扱いにしない。

SIGINT／SIGTERM・時間上限はtest batch間と対局の手と手の間で確認し、中断を勝ち負け・引分へ変換しない。違法なモデル出力・改変された結果等の失敗は記録して停止し、同じ失敗runの自動やり直しで隠さない。新しいrunで再検証する。最終reportにはモデルID・精度・backend・重み／入力hash、固定条件、test、cohort集計、全棋譜ファイルのhashを残す。

Linux CIでは小さい2王局面の4局、1手詰め、保存棋譜の再検証、中断、CPU tensorの違法最大logitと同点を使う。smoke用profileは別schemaで、正式60局の評価に数えない。Macで実行するのは手計算の生カウント・paired統計・選択metadataだけ。実対局・モデル計算・本評価はLinuxで行う。
