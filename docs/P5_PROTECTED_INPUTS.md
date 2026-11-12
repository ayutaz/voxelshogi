# P5-2：自己対局へ入れない入力の固定

**2026-11-12・一時停止**：既存Sの公開デモと、Mの少量2 run・48局評価を現段階の成果とする。
本比較12 run・MのWeb配布・観戦表示2案／実端末各60分は未完了のまま停止する。
追加GPU・生成・学習を自動再開しない。[停止時点の結果と固定HF版](RESEARCH_CHECKPOINT_20261112.md)を現在の確認元とし、
以下の旧「現在」「次」「予算」は対象時点の記録、実行コマンドは再開後の手順として読む。

**2026-11-03 16:56:12 UTC・P5-2の終了と停止**：[本条件3世代48対局・HF保存・別VM後続世代](P5_2_COMPLETION.md)の結果を記録した。使用した所有課金資源は0。棋力改善・P5-3・DDP・Phase6は未完了であり、結果共有後に停止する。

2026-11-03 UTC。`training/selfplay_protection.py`は、検証済みの既存コーパス・開発評価・P5-1のholdoutから、自己対局学習の除外集合を作る。探索・教師の再計算・学習は行わない。Rust再生や大きいコーパスの読み取りを伴うため、実データでの作成は外部Linuxに限定する。

## 保護する対象

| 対象 | 検査と範囲 |
|---|---|
| M4／M6 | 固定`production-64` revisionの全splitを既存auditで照合し、全行の入力IDを保護する |
| P5-0 | 固定した実験proofのrun・ファイルhash・全手再生を照合し、採点開始から終端までの全入力を保護する |
| P5-1 | HF `voxelshogi/voxelshogi-search-v1`の固定revision `1b86f7e83b70a69cdfa3cc0bd4e9b0886623c472`から取得・全hash照合したplan／receiptを要求する。val／test familyはsample行だけに限らず、初期・途中・終端の全履歴をRustで再生して保護する |

P5-1の教師JSON・探索値・採用条件はこの処理の入力に使わない。教師の検証が未完了の候補も、そのholdout入力を後続学習から除外するためにのみ利用する。既存の学習不採用判断を変更しない。棋譜の合法性・終局／cutoff・元の固定protocolは検査する。

入力IDは手番正規化後の盤・持ち駒・ruleset・特徴量契約を含み、plyを除く。各入力元が空の場合や、出所・IDが不正な場合は作成を拒否する。出力は一意IDを昇順に並べた`protected.json`と、入力元別件数・合併後件数・出所hash・HF receiptを記した`audit.json`。教師の採用数は0である。

## 外部Linuxでの作成

先に既存公開ハーネスで入力を固定HF revisionから取得し、全ファイルを照合する。P5-1の`verified=false`の退避receiptをそのまま使わず、実ダウンロード照合とCommunity OFFの確認を完了させる。P5-0の小さい実行記録は、固定proofと一致する制御側の退避記録を渡す。データやcheckpointをMac経由で取得し直さない。

```bash
uv run --project infrastructure/cuda --locked --no-sync python -m training.selfplay_protection \
  runs/p5/inputs/production-64 \
  runs/p5/inputs/control-matches runs/p5/inputs/m6-matches \
  runs/p5/inputs/p51 runs/p5/inputs/p51-plan.json runs/p5/inputs/p51-verified.json \
  runs/p5/protection
```

自己対局protocolには`protected.json`全体のSHA-256・ID数・出所を固定する。生成前に`audit.json`の実件数と入力元を確認し、その後に探索・手数・学習条件を凍結する。空の仮集合を使って実験を開始しない。

## 確認範囲

メタデータ4テストでは、sampleされない途中局面と終端の保護、違法な履歴／初期盤／結果の拒否、入力元別件数と一意な合併、空入力・不正ID・違うrevision・未照合HF receiptの拒否を確認した。Linux CIには実Rust・Parquetで、教師JSONを学習不能な内容へ変更してもholdout履歴の保護だけは行う試験を置く。各prefixを独立に復元した参照集合と比較する。これらは実固定コーパスでの保護集合作成や、実GPUでの漏洩監査完了を意味しない。

## 照合済み集合を別VMで使う

[固定HF index](https://huggingface.co/datasets/voxelshogi/voxelshogi-protected-inputs-v1/tree/ec3bfa0acfa6c5c9f59f98bf1750a3143c0007d8)は、上記の全固定入力から作成した116,008件を保存する。`protected.parquet`のexclusions splitは`input_id: string`の一列で、整列済みの一意IDを保持する。`config.json`は元の`protected.json`の全bytesで、SHA-256は`364ee551512b1c98871308aafc939059f4a26743340b2aa904555c92d4a39944`。`manifest.json`には元revision・全件の入力監査・転送receiptを保持し、`validation.json`はParquet全IDの往復一致を記録する。

外部Linuxで固定revisionの全6ファイルを既存公開ハーネスで照合し、config.jsonのbytesをそのままprotocolの保護入力へ渡す。JSONを再整形せず、protocolのhash・件数・出所を照合する。全コーパスの再取得を省くための固定indexで、除外範囲を減らす方法ではない。教師の採用数は0。CC-BY-4.0、public/manual・Community OFF、4節のDataset Cardを維持する。
