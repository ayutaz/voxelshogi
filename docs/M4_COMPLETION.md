# M4完了：本生成・全件検証・HF公開

2026-10-29 JST。1,800局の生成・全件検証・同一環境での全再生成を完了し、重複除外後113,321局面をHFへ公開した。公開対象全1,831ファイルのbytes・SHA-256が固定Hub commitで一致し、実機の終了・資源解放・残存volume 0件を確認した。[固定したjob・report・全hash一覧・receipt・終了記録](experiments/m4-production-release-2026-10-29.json)。

## 公開物とDataset Card

- リポジトリ: [voxelshogi/voxelshogi-synthetic-v1](https://huggingface.co/datasets/voxelshogi/voxelshogi-synthetic-v1)
- 固定Hub revision: `6e7fb29d2469b56a895042fbb089d86e7b4d074f`、本生成config: `production-64`
- [公開したDataset Card](https://huggingface.co/datasets/voxelshogi/voxelshogi-synthetic-v1/blob/6e7fb29d2469b56a895042fbb089d86e7b4d074f/README.md): 81,623 bytes、SHA-256 `0858826c604a4af6256d848b173479cda27c11ce3454fde54b01c9be4c6f4cb2`
- public/manual・Community OFF、データのライセンスはCC-BY-4.0。既存の`pilot-16`と`representative-64`を保持した。コードのApache-2.0と学習済みモデルのライセンスは別。

Cardにはconfig別の件数・重複・教師・生成元・split、ソース・seed・探索条件、列と取得方法、再生成・検証、制約・取得申請・帰属を記載した。Card自体のhashも公開receiptと一致した。取得申請の承認後、外部Linuxで上記revisionとconfigを固定して取得する。config間の重複を独立サンプルとして合算しない。

## 本生成の結果

| 項目 | 実測 |
|---|---:|
| 対局数 | 1,800 |
| 総行数 | 116,921 |
| 除外した重複 | 3,600 |
| 有効局面 | 113,321 |
| 有効探索教師 | 36,894（重複除外前38,321） |
| 有効生成元 | random 37,941／rules 37,935／search 37,445 |
| 有効split | train 90,642／val 11,381／test 11,298 |
| 本生成Parquet | 1,800ファイル・38,552,239 bytes |
| 生成 | 4,255.160秒 |
| 全件検証 | 8,069.726秒 |
| 全再生成 | 4,222.838秒 |
| 全3工程 | 16,547.724秒、約4時間36分 |
| 観測最大RSS | 618,491,904 bytes、約589.84 MiB |

全履歴の再生、盤・持ち駒・合法手・着手・終局・静的評価・固定条件で再探索した教師、対局単位split、対局をまたぐ重複を全件検証した。生成器の着手選択helperを検証器の正解として使わない。全再生成では、全Parquet・manifestと空の所有マーカーがバイト一致した。manifestのSHA-256は`555af2d9c2c9fdfc2bc01611ccaaac39aab203202acfc2611f473ee5618df591`。

## 環境・速度・費用

ソースは[PR #43](https://github.com/ayutaz/voxelshogi/pull/43)の統合済み`ae37ea25a7280774837e9aaac8f35d11decb2c32`、lockは`7a01ef9cba3655bd3702c92b5f45307c400432c77578c0e32ed4f70dc2ae088b`。CloudRift米国RTX 5090×1、Dedicated・ゲスト7論理CPU、RAM48 GiB、Python3.14.9、driver580.159.03。GPUを学習に使った実績ではなく、GPUサービスのCPUで生成した。

seed17、各生成元600局、最大64手、深さ2／10,000ノード、TT4,096、探索序盤16手の固定seed分岐、4ワーカーを固定した。ジョブは10時間45分・所有プロセス群RSS1 GiB、実機全体は12時間／US$12を上限として実行した。Macにはデータ本体を置かず、小さいJSON・hash・Cardだけを回収した。

生成全体の経過時間当たり27.48行/秒、有効局面26.63/秒、有効探索教師8.67/秒（重複除外前の教師9.01/秒）。1対局当たりの償却経過時間は生成2.364秒・検証4.483秒・再生成2.346秒。混合3生成元・4ワーカーの通算値であり、単独探索の応答時間やprocess CPU秒、CUDA学習速度とは区別する。[費用見積もりへの反映](COST_ESTIMATE.md#m4本生成の実績2026-10-29-jst)。

18:20 UTCごろに終了を要求し、`Inactive`・`resources_released=true`、稼働中VoxelShogi実機0・永続volume 0を確認した。準備から資源解放確認まで約5.04時間、単価US$1/時との積は参考約US$5.04で、実請求は未回収。生成しなかった先行準備実機の上限US$24も保守的に残し、過去US$5と今回上限US$12を合わせた予約上限はUS$41・未予約額US$59。実請求額・サービス残高とは区別する。

## ゴールの照合と制約

| M4のゴール | 確認元 |
|---|---|
| Python境界・環境とCI | [実装・独立期待値・変異・停止再開の記録](M4_VALIDATION.md)、PR #43の必須CI、同じ実機の境界11テスト |
| 有効10万局面と全件検証 | 上記113,321局面とreport。教師付き36,894局面を別記 |
| 固定条件での全再生成一致 | reportの`regenerated_bytes_match=true`、全ファイルhashとmanifest |
| split・重複・漏洩対策 | 対局単位splitと全体の重複除外を全件検証。非nullの`duplicate_of`は学習・評価から除外 |
| 性能・費用・資源制限 | 実測4時間36分、速度・費用更新、RSS上限内、実機終了・資源解放 |
| Card付き実公開 | 固定Hub commit、public/manual・Community OFF、公開対象1,831ファイルの全hash一致 |

最大64手で打ち切る集合で、自然勝敗ラベルや強い棋力を保証しない。random/rules行を最善手教師へ数えず、`teacher_valid=true`かつ`duplicate_of=null`だけを探索教師に使う。探索評価を勝率とみなさない。同一固定環境でのバイト再現を確認したもので、異なるOS・CPUのバイト一致は未検証。M6の学習・棋力評価は未実行。

M5も[固定3局145手の全件一致](M5_PLAN.md)まで完了した。これは全棋譜・全終局条件の完全互換ではなく、第三者棋譜を今回のデータに含めていない。次は[M6-0〜1の教師・評価条件と学習／再開の実装](M6_PLAN.md)。GPU学習の費用・モデルライセンスは別途決める。
