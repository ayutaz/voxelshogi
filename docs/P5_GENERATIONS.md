# P5-2：自己対局の学習と世代更新

2026-10-30 UTC。探索・Actor・検証付きPolicy/Value・Replay Bufferに、FP32学習と世代更新を接続する実装。Phase5全体の目的と完了条件は[段階別計画](POST_M6_PLAN.md#phase5)を維持する。

## 目的と完了条件

完成episodeの訪問分布とValueの出所を保ったまま学習し、親モデルから子モデルへ更新する。protocol・source・入力集合・model hashを固定し、停止後も同じ学習を継続できることを確かめる。

このPRの対象は学習器・世代更新・公開再試行の接続。P5-2の実験完了には、本条件の複数世代、HFデータ／再開状態の公開・全hash照合、別実機からの復旧が必要で、現時点では未達。CLI単独実行はHFへ自動公開しない。実運用の公開・復旧ハーネスが完成するまで、これだけで有料自己対局を開始しない。

## 学習と再開

`training/selfplay_training.py`は以下を固定する。

- Replay Bufferで全手検証済みのepisodeだけを使う。正規化入力IDが保護集合に含まれる局面を除外し、train内の反復は保持して件数を報告する。
- terminal-v1とbootstrap-v1を混ぜたバッチを作らない。各epochで全対象局面を1回ずつ使い、seedとepochに基づく順番・バッチ位置で再開する。
- Policyは探索訪問回数の分布を使い、合法手全体で正規化する。best moveだけへの変換は行わない。Valueは明示した尺度でMSEを計算する。
- FP32・AdamW、勾配の有限性確認とnorm上限1。既定は1epoch・batch4・learning rate 0.0001。epoch数は事前固定し、holdoutをモデル選択へ使わない。
- 入力行・全特徴量byte・source・親model・世代・config・環境をcheckpointへ結び付ける。変更された入力へのresumeを拒否する。
- ローカルの所有checkpointは既存の安全な読み込み契約を使う。公開時にはJSON＋safetensorsの再開archiveへ変換し、実行可能なpickleを送らない。既存M6専用archiveの契約を自己対局へ黙って流用しない。

## 世代更新

`training/selfplay_generations.py`のprotocolは、既定案を3世代×16episode、Replay容量32episodeとする。1世代の手順はActor→完成episodeの検証と保存→保護入力除外→学習→FP32子モデル保存→lineage確定である。モデル出力のbindingと実推論回数も照合する。

開始局面のfamilyは生成前にtrain専用として固定する。同じfamilyの開始局面は世代間で共有し、探索seedは世代ごとに区別する。標準初期局面からのseed付き序盤と、履歴付きの到達可能局面を宣言できる。実試行ではP5-1を踏まえた中終盤のtrain局面を含め、打切りばかりの条件にしない。評価・holdout局面をfamilyへ混ぜない。

保護入力ファイルは全M6固定コーパス、P5-0開発評価の採点対象入力、P5-1のholdoutを外部Linuxで照合して作る。ファイル全体のhash・ID数・整列済み一意ID・固定revision等の出所をprotocolへ結び付ける。任意の空集合で監査済みとは扱わない。

公開callbackは、世代確定後に呼び出す。datasetとstateの2つの照合済みreceiptがそろったときだけ公開cursorを進める。途中失敗後の再開では、未公開の確定世代を先に再送確認し、同じ対局や学習を再生成しない。run.jsonのcompleteはローカルの予定世代完了、externally_persistedは確定世代すべての公開receiptがあることを示し、別実機復旧の成功とは区別する。テスト用receiptは実際のHF公開証拠に数えない。

## 実行境界

実モデル・特徴量生成・学習はLinux専用。Macはmetadataの小さい単体確認だけを行う。実行時はclean sourceを照合する。

```bash
# 外部Linux上で、事前固定protocolと照合済み入力を使う。
uv run --project infrastructure/cuda --locked --no-sync python -m training.selfplay_generations \
  runs/p5/selfplay/protocol.json runs/p5/inputs/base.safetensors \
  runs/p5/inputs/protected.json runs/p5/selfplay/output \
  --max-new-generations 1 --max-seconds 900
```

このCLIの秒数上限はジョブの保存停止であり、GPU課金の停止ではない。所有資源の独立終了監視・台帳・HF退避・資源解放の確認を別途行う。現行実装はTransformer-Sだけを対象にし、Phase6のMモデル・別構造の比較へ同じ速度を外挿しない。

## 検証の範囲

外部CloudRiftの別checkoutで、CUDAを隠したCPU計算として次を確認した。既存のデータ生成と同じ実機を共有したため、性能評価には使わない。

- [学習器5件のRED→GREEN](experiments/p5-selfplay-training-functional-2026-10-30.json)：`log(2)`＋Value MSE 1の手計算、疎な0.75／0.25分布の勾配−0.25／＋0.25・非合法手0、更新、全特徴量byte変更時の拒否、checkpoint再開一致。
- [実Sモデル・Rustの2世代動作確認](experiments/p5-selfplay-generations-functional-2026-10-30.json)：各2episode、各1手・探索1回の小さい条件で、通し実行と別ディレクトリへコピーした再開の全model hash・Replay一致。約15.65秒。別VMやHF復旧の確認ではない。

取得記録のsource／overlay hashを保持する。公開cursorを追加した現在版と、公開失敗→再試行・親lineage／重み改変の追加検査は通常Linux CIで検証する。Macのmetadata9件と8種類のmetadata変異は成功。新しい数値・世代変異はLinux CIで実行し、skipやtimeoutを検出成功として数えない。全テストbaselineの上限だけ180秒へ延ばし、個々の変異は既存の60秒を維持する。

世代結合テストではsource SHA自体を実checkoutのHEADと照合するが、意図的な変異をlineage検査まで届けるため、clean判定だけをfixtureで分離する。本番コードのclean guardは変更せず、その比較・dirty拒否は既存のresearch rentalテストで検証する。dirty検出だけによる変異の検出成功を数えない。
