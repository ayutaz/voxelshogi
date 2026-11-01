# P5-2：自己対局学習の安全な保存・復旧

2026-10-31 UTC。[世代更新](P5_GENERATIONS.md)で使う学習状態を、外部LinuxからHFへ退避し、別実機で継続するためのarchive契約。コードの追加・fake Hubでの検証と、実際の公開・復旧成功を区別する。

## 目的とゴール

親モデル・世代・入力・訪問分布の学習条件を保持し、optimizerと乱数を含む途中状態から同じ更新を続ける。公開ファイルは型付きJSONとsafetensorsに限定し、実行可能なpickleや生ログを送らない。

この変更では自己対局用profileと専用公開経路を追加する。実データ・全世代のHF公開、Replay Bufferとの組み合わせ、別VMからの復旧は、この変更だけでは完了しない。

## 形式と検証

`training.resume_archive`のpack／restore／verifyに`profile="selfplay"`を明示する。既定の`m6`と`voxelshogi-resume-archive-v1`は、既存の教師あり学習用として維持する。

自己対局は`voxelshogi-selfplay-resume-archive-v1`を使い、次を検査する。

- 元のsource SHA、全特徴量を含む入力hash、親model SHA、0〜63の整数世代、構造名、TrainConfigと固定epochの選択契約。
- 学習のrun bindingと、ファイル全件の相対パス・bytes・SHA-256。symlink・外部パス・変更されたファイルを拒否する。
- 保存対象はlatestだけ。自己対局の契約にはholdoutによるbest選択がないため、best checkpointやbest_val_lossの混入を拒否する。
- モデル・optimizer・乱数・進捗は既存の型付きtree形式で保存する。復元時は外部から渡した期待bindingと全ファイルを照合し、run.jsonを最後に確定する。

```bash
# 外部Linux専用。制御側の課金停止監視とは別の操作。
uv run --project infrastructure/cuda --locked --no-sync python -m training.resume_archive \
  pack runs/p5/selfplay/output/generation-000/training runs/p5/state-000 \
  --profile selfplay
uv run --project infrastructure/cuda --locked --no-sync python -m training.resume_archive \
  restore runs/p5/state-000 runs/p5/restored-training \
  --profile selfplay --expected-run runs/p5/reviewed-training-run.json
```

## 公開の境界

自己対局の再開状態は`artifact_role="selfplay-training-state"`と、専用宛先`voxelshogi/voxelshogi-transformer-s-selfplay-training-state-v1`の組み合わせに限定する。旧M6のtraining-state repoや通常のモデルrepoへ混ぜない。公開planには対象のライセンス承認、再開状態の公開承認、sourceに結び付いたexpected_bindingが必要。形式の実装を公開承認として扱わない。

公開には[既存ハーネス](HF_PUBLICATION.md)を使い、次を維持する。

- public/manual・Community OFFと、Model CardのTraining and provenance／Resume contents／Verification／Access and licenseの各節。
- 既存の再開状態と共通の累積1 GiB upload ledgerを、API操作前に予約する。失敗しても予約を消さず、同じplanを無確認で再送しない。有料ストレージ追加を自動承認しない。
- Linux上で全ファイルを固定Hub revisionから取得して照合する。アップロード応答だけではverifiedにしない。
- Macでの実転送・tensor処理を拒否する。通常モデルprofileも、この新しいarchive schemaを検出して拒否する。

実運用では、このarchiveに加えて、入力データ・Replay Buffer・確定世代のmodelとlineageをそれぞれ検証して退避する。復旧先でそれらがそろい、同じprotocolと履歴へ結び付くことを確認してから世代更新を再開する。

## 検証

metadata4件は実装前の失敗を確認した。既存のM6 archive・公開・upload ledgerと合わせた軽量39テストが成功し、追加9種類のmetadata変異および更新した既存2種類の変異を検出した。自己対局の本物の小さい学習→JSON＋safetensors→元private checkpoint除去→復旧→model／optimizer一致の追加テストと、pack時のschema変異はLinux CIで実行する。skip・collection error・timeoutを成功に数えない。

この記録は、実HFへのアップロード・全hash照合・別実機復旧の証拠ではない。P5-2とPhase5の完了条件は[段階別計画](POST_M6_PLAN.md#phase5)のまま維持する。
