# P5-2：自己対局へ入れない入力の固定

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
