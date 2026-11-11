# 実M少量学習の実行ドライバー

[再開計画](P6_RESUMPTION_PLAN.md)のA・Cに使う実行経路を
`infrastructure/research/pilot/`へ移し、一時ファイルだけに依存しないようにする。
本書は実行契約であり、実2 run・CUDA再開・HF公開の成功報告ではない。
GPUの起動・学習条件の採用・最終評価は、この変更では実行しない。

## 入力と実行環境

- `attempt.validate_inputs`はsource、採用前監査、全開発入力の保護、教師診断のhashと、
  その診断に基づく明示的な教師判断を要求する。少量試行だけを許可し、本比較への採用は許可しない。
- 固定した実M構造・CUDA・全更新数を使う。小さいCI用モデルやCPUへの置換を拒否する。
  Pythonは外部Linuxの固定したuv／CUDA lockに従う。
- `attempt.run`はcleanな実sourceを確認し、入力を再監査してtrain／val特徴量を作る。
  元の固定入力と開発保護・教師判断を、保存再開のbindingへ含める。
  test特徴量、最終holdout、対局評価はこのドライバーでは生成・実行しない。
- `child.run_attempt`は別process groupで実行し、認証情報を渡さない。
  固定deadlineと停止要求で所有processへTERM、20秒後に必要ならKILLを送る。
  既存の起動logを上書きして再起動せず、観測結果を照合する。

## 1試行と同一軌跡の再開検証

`cycle.run_cycle`へ凍結済みinputs、途中停止step、固定deadline、公開API、
固定revisionの取得port、累積state upload ledgerを渡す。順序は次のとおり。

1. 連続実行で全更新数を学習する。
2. 同じ条件を途中stepで止め、型付きJSONとsafetensorsのresearch archiveを作る。
3. 外部LinuxからHFへ公開し、固定版の全ファイルhashを照合して別directoryへ復元する。
4. 復元したmodel／optimizer／乱数／進捗から残りを学習する。
5. 連続・復元後のlatest／best両方と全train／val履歴を完全一致で照合する。
6. 連続実行の最終stateもHFへ退避し、全ファイル検証と復元を確認する。

これは**科学的な1 run＋同一軌跡の再実行**で、独立seedを2本得たことにはならない。
時間・更新数・費用の見積もりには両軌跡、特徴量準備、archive、転送・復元・終了を含める。
テンソルの値・型・shape、optimizer、Python／NumPy／Torch／CUDA RNG、進捗、bindingを比較する。
checkpointの直列化byteが同じことだけで数値一致を代用しない。

## HF保存と復旧

保存先は`voxelshogi/voxelshogi-research-training-state-v1`、roleは`research-training-state`。
[HF公開ハーネス](HF_PUBLICATION.md)を通し、public/manual・Community OFF・Apache-2.0・
State Card・全ファイルhashを要求する。これは推論用モデル配布先ではない。
実checkpointやデータをMacへ中継しない。

一度でも公開を試みたcontrol directoryは再使用しない。
uploadの応答不明を理由に盲目的に再送せず、publication-attempt・receipt・固定HF版を照合する。
更新されたupload ledgerと必要成果を回収する前に、学習ホストを終了しない。
このmodule群はレンタル、独立停止監視、失敗時の未完了state救出やhostの解放を行わない。
ブラウザoperator専用の自動解放を、未退避checkpointのある学習へ流用しない。

## 検証範囲と次の作業

手書きのfake tensor・SDK・process・archive portを使う軽量テストで、実行順序、
入力binding、全更新数と途中停止の区別、資格情報を含まないchild環境、
全履歴とlatest／bestの検証、公開未検証時の拒否、二重送信拒否を確認する。
意図的な21種類のバグを関連テストで検出し、既知変異カタログへ登録する。
Macで実Torch、GPU、コーパス生成、HF uploadは実行しない。
このfake検証は実CUDA再開の証拠ではなく、Linuxの関連CI成功も実2 runの成功とは扱わない。

実行前には、教師判断・2構造・更新数・batch・共通計算予算を固定し、
全工程見積もりと所有資源・独立期限、state救出・ledger回収を含む外部supervisorを接続する。
実行後の開発用対局と全NN参照監査・費用・HF結果退避も別に必要。
最終holdoutを調整に使わず、12 run本比較とWeb配布の完了条件を維持する。
