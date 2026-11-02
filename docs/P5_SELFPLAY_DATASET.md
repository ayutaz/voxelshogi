# P5-2：自己対局データの退避と世代境界からの復旧

2026-11-02 UTC。目的は、元の実行フォルダやpickle形式のcheckpointへ依存せず、確定世代までのReplayと親子モデルの系譜を別の外部Linuxへ移すこと。実装は`training/selfplay_dataset.py`。実際のHF公開・別VMでの学習再開は後続で、Linux CIでの復旧とは区別する。

## 含める内容と復旧地点

`episodes.parquet`は`slot: int32`と`episode_json: string`。各行に1対局の全履歴、合法手、疎な訪問分布、Valueの出所、実行source／model／seedを保存する。学習に使う直近のReplay windowだけでなく、確定世代までの全対局を保持する。未確定世代や途中の対局を混ぜない。

`manifest.json`は凍結protocol・run ID・全世代の親子hash・学習進捗／入力監査・公開済みreceipt・Replay index・Parquetのbytes／SHA-256を保持する。確定世代数×事前固定対局数とReplay件数が一致する地点だけを受理する。未知の学習記録フィールド、途中epoch、親モデル／入力protocolの差を拒否する。`validation.json`にはRust再生で検証した実件数を残す。

復旧は確定世代の末尾から行う。既存の世代更新は世代ごとに新しいoptimizerを作るため、次の世代へ進む際に前世代のpickleは必要ない。途中のoptimizer stepからの再開は[JSON＋safetensorsの専用state archive](P5_SELFPLAY_STATE.md)が担当する。Datasetへ重みやoptimizerを混ぜず、モデル／stateは別のApache-2.0成果物として公開する。

## 外部Linuxでの使用

`run_generations(..., max_new_generations=1)`が戻り、run lockを解放してからstageする。`on_generation` callbackの内側では同じlockを取得しない。

```python
from training.selfplay_dataset import pack_dataset, restore_dataset

manifest = pack_dataset(run_dir, dataset_staging, expected_protocol=protocol)
# stagingへ承認済みCC-BY-4.0のLICENSEを置く。READMEは実件数から自動生成済み。
# 既存hub_releaseでdatasetをpublic/manual・Community OFFへ公開し、固定revisionの全hashを照合する。

restore_dataset(
    verified_dataset_download,
    new_run_dir,
    expected_protocol=protocol,
    models={0: verified_generation_000_model},  # 全確定世代のモデルが必要
)
# 同じbase model、protected-inputs、protocolを使ってrun_generationsを続ける。
```

`models`は各確定世代の番号から、別途取得・検証済みのsafetensorsへの対応。全モデルのSHA-256を照合し、不足・差異は復旧先の作成前に拒否する。全episodeをRustで再生し、凍結した世代別Actor設定とseed、合法手、ラベル計算、訪問数・呼び出し数を再検査する。PUCTのニューラル推論そのものを再実行したとはしない。

復旧先は新規ディレクトリに限定する。モデルのコピー後にもhashを検査し、Replayと全モデルがそろってから`run.json`をcommit pointとして書く。base modelとprotected-inputsはprotocolが固定する別入力として取得する。世代のDatasetとstateを固定revisionで照合し、両receiptを公開cursorへ反映する運用ハーネスは引き続き必要。

## 公開

既存の`hub_release.plan_release(..., repo_type="dataset", license_id="cc-by-4.0", ...)`を使う。公開候補は`voxelshogi/voxelshogi-selfplay-v1`。public/manualの取得ゲート、Community OFF、承認済みLICENSE、全hashの検証済みreceiptを要求する。Parquet、manifest、validation、README、LICENSEの5ファイルで構成し、元のrunフォルダ全体を送らない。

Dataset Cardは来歴・実件数・全seed／探索条件の所在、schemaと読み方、検証内容、アクセス・ライセンスの4節を自動生成する。自然終局とcutoffを数え、bootstrapを実勝敗や自然引分と呼ばない。重複を除いた学習入力件数とraw対局／sample件数を混同しない。stageができたことだけでHF公開・別実機復旧・棋力向上とは報告しない。

## 検証

メタデータ3テストと追加した未知フィールド拒否について実装前の失敗を確認した。関連する軽量34テスト、Ruffと3種類のメタデータ変異検出はMacで確認した。Linux CIには実Sモデル2世代の比較を置き、capacity=1に対して全2対局を退避し、元のrunを削除してからParquetと別モデルだけで復旧する。続きの世代のmodel hashと全Replayが中断なし実行と一致することを検査する。破損Parquet・不足／誤ったモデルの拒否、既存HF公開planへの接続と追加2変異もLinux CIの対象。
