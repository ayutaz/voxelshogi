# 訪問分布を使うM構造の固定更新数学習

2026-11-05。[実行計画](P6_EXECUTION_PLAN.md)の少量学習・構造比較に使う学習側の契約。
実MのGPU学習結果や12 runの完了記録ではない。

## 目的と範囲

既存の`research_fit`はM4の単一正解手を使う教師あり学習である。
`research_visit_fit.fit_visits`は検証済み自己対局の合法手への訪問分布を保ち、
Full／Axial／Geometry／3D-CNNの明示した構造・seedを初期化する。
既存M6モデル・教師・resume bindingは変更しない。

総学習量は`total_updates`で固定する。`max_new_steps`は一度の実行の上限であり、
到達時は`max_new_steps`を返す。総更新数未達を完了とは扱わない。
epoch／batch位置は値の出所別の固定seed samplerから計算し、端数batchを含めて
更新数と実例数の対応を再開時に検証する。同じ更新数だけで同じFLOPsとは主張しない。
本比較の計算量・更新数・費用は実M計測後に別途固定する。

## データと損失

入力は[コーパス採用前監査](P6_CORPUS_ADMISSION.md)を通したtrain／valと監査hashである。
固定HF版の全hash、Rust全履歴、保護入力除外、選択IDとfamily分割、教師品質の確認は
実行driverの前提条件であり、任意のhash文字列を渡すだけで検証済みとは扱わない。
学習側もtrain／valのcanonical input・familyの非重複と全特徴量byte・教師・由来をbindingへ含める。
testや最終評価のデータは学習APIへ渡さない。

Policyは合法手全体を正規化した訪問分布の交差エントロピー、ValueはMSEで、和を最適化する。
AdamWはFP32、foreach／fused無効、勾配norm上限1、TF32無効、決定的演算を使う。
terminal／bootstrapの出所別にbatchを分け、bootstrap値や手数打切りを確定した勝敗・引分へ読み替えない。

固定val全件を`validate_every`更新ごとと最終更新時に評価し、損失最小のstateを保存する。
指標はPolicy CE・Value MSE・総損失・件数・Valueの出所別件数である。
val損失低下は棋力向上の証拠にはしない。

## 保存再開と検証

`research`形式の安全なstate archiveへ、構造・総更新数・val間隔・データ／監査hash・source・
環境・optimizer・RNG・batch位置を保存する。学習履歴は許可した指標とIDだけを受け入れ、
更新番号の連続性と予定したval実行を照合する。従来のM4教師あり形式と区別する。

軽量テストは手書きの7更新・3更新ごとのval・混在出所のbatch位置と不正bindingを確認する。
Linuxの数値結合テストでは全4構造について、7更新の連続実行と4更新→archive復旧→3更新の
model／optimizer／RNG／進捗の完全一致を確認する。最大手が同じで分布の異なる教師から
異なる重みになることも確認し、argmaxへの誤変換を検出する。
ゼロlogit／ゼロValueの検証期待値はPolicy CE=`ln(2)`、Value MSE=`0.04`の手計算を使う。
変異は総更新数・optimizer更新・分割・監査binding・val履歴を対象とする。

[監査済みvisitの特徴量への接続](P6_VISIT_DATA.md)を用意した。実データの採用、外部GPUの2 run試行、FLOPs算定、HFへの実state公開、
実際の棋力比較は後続の実行項目であり、この学習コードの追加で完了とはしない。
