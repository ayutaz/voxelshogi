# Phase5 評価v2：契約と実行の段階

2026-10-30。Phase5〜6実行の指示に基づき、[P5-0](POST_M6_PLAN.md#phase5)から進める。M6の評価v1・固定test・公開revisionは変更しない。

## 目的と完了条件

M6で教師模倣精度が上がっても対局の改善が確認できなかった原因を、評価の打切り、局面の分布、教師、探索方式に分けて調べる。P5-0の完了には、次のすべてが必要。

1. 対局前に評価条件と参加モデルを固定する契約・独立テスト。
2. Rustによる全手再生と、train／開発用評価／最終holdoutの全局面についての漏洩照合。
3. 戦術・中終盤・標準序盤の固定した開発用少量試行。終局率・対局長・先後差・時間を測定し、本比較へ進む条件を決める。

**1の契約・集計境界は[PR #77](https://github.com/ayutaz/voxelshogi/pull/77)で必須8チェックと関連CI成功後に取り込み済み**。Linux用runnerとRust全手再生は[PR #78](https://github.com/ayutaz/voxelshogi/pull/78)で必須・関連CI成功後に取り込み済み。2の全件漏洩監査は後続。metadataテストを実対局・独立したルール検証・外部GPU試行の代わりにしない。実局面集合・全件漏洩監査・外部試行は未完了。

## 固定する契約

実装は[training/evaluation_v2.py](../training/evaluation_v2.py)。`validate_protocol`は条件のSHA-256を返す。schemaは`voxelshogi-evaluation-v2`。余分なfield・未知の方式・不正な型・重複case／同一openingを拒否する。

| 項目 | 意味 |
|---|---|
| `source_commit` | 評価実行コードの固定commit。実行時にclean sourceとの一致を別途確認する |
| `purpose` | 開発用`development`または最終`holdout`。開発用の結果を最終評価へ付け替えない |
| `participants` | 比較する両者のartifact hash・backend・着手方式を事前固定する |
| `search_limits` | 深さ・ノード数・`table_capacity`。時間上限で着手を選ばず、外側のジョブ監督で費用と停止を制御する |
| `cases` | 名前、層別区分、seed、履歴付きopening、開始局面からの追加手数上限。各caseで同じopeningの先後2局をそろえる |
| `bootstrap` | 先後2局を1単位とする10,000回のresampling。seedも事前固定する |
| `sensitivity` | 必要なpair数と終局率の最低値。通過しても棋力改善・区間精度の証明にはしない |

実際の対局数・seed・上限・局面・感度の採否値は、外部試行の前に実行用protocolへ固定する。テスト中のopaqueな盤面文字列や少数のcaseはmetadataの手計算fixtureであり、合法局面・本評価集合ではない。

## 集計と検証の境界

`summarize_matches`は開始時の条件hash、参加者hash、case／seed／先後の完全性、openingの初期盤面と履歴prefix、追加手数、宣言結果・終了理由を検査する。空集合・欠落・重複・途中結果を成功としない。合法性・千日手・王手等のルール判断はRust再生に任せる。

- 勝ち・負け・自然引分・打切りを別々に報告し、先後別・局面の層別にも集計する。
- 勝率の分母は開始局数。終局した対局に限る勝点率は、その条件付き指標と明示する。
- 打切りの最終勝点は未知とし、各打切りを0〜1点とした全局の勝点範囲を報告する。全打切りなら範囲は`[0,1]`、自然引分は0件となる。
- paired bootstrapは観測したopeningの再標本化である。0勝の`[0,0]`を母集団の勝率保証にせず、類似局面の相関・少数標本の限界を残す。
- `check_disjoint_positions`へ渡すIDは、全対象局面の盤・持ち駒・手番をRust snapshotから正規化したSHA-256。手数は除き、rulesetを含める。履歴hashやroot局面だけの照合を全件漏洩監査とは呼ばない。

## 検証と次の実装

Macでは小さいmetadataだけで10テストを先に実行してREDを確認後、GREENを確認。勝敗・引分・打切りの手計算、先後pairの区間、条件改変、履歴・上限・結果の改変、漏洩と感度判定を検証した。新規9変異も実行済みassertionで検出し、[継続ハーネス](../scripts/ci/mutation-training.py)へ追加した。ルール・探索・モデルはMacで実行しない。既存v1を含む全回帰はLinux CIで確認する。

Linux専用runnerと全手再生の接続はPR #78で取り込み済み（次節）。続いて実局面集合・全件漏洩監査・少量試行を進める。外部試行は[Phase5の用途別制御](P5_EXECUTION.md)・見積もり・停止／資源解放をそろえてから開始する。Phase5〜6は依頼済みの範囲として進め、実測で予算不足が見込まれるときは既存の条件付き追加枠と照合する。


## Linux用runner

[training/evaluation_v2_runner.py](../training/evaluation_v2_runner.py)は、clean sourceのcommitとprotocolを照合してから実行する。対象は、固定したRust探索／Python RNGによる合法手乱択と、hash照合済みM6-SのFP32 safetensorsを使うTorch CPU／CUDA。ONNXや別構造を実行済みとはしない。Randomのbackendは`python-rng`、探索は`rust`と区別する。

```bash
# 外部Linux。事前に固定したprotocolと対応する重みを指定する。
uv run --project infrastructure/cuda --locked python -m training.evaluation_v2_runner \
  runs/p5/protocol.json runs/p5/evaluation --model /mnt/selected.safetensors
```

各caseの履歴をRustで復元し、同じ開始局面で先後を交換する。手数上限はopeningの履歴長を除いた追加手数。最後の許容手での自然終局は打切りより優先する。中断・非合法手・未終局の合法手欠落は完了結果にしない。

各対局は保存前にRustで全手・宣言結果を再生する。出力はprotocol、各棋譜、集計、実行環境・全棋譜のbytes／hashと集計hashを結ぶrun receipt。既存の出力先は上書きせず、中断・失敗時は`complete=false`を残す。`verify_run`は保存後にファイルのhash、全棋譜のRust再生、全件再集計をやり直す。これだけで入力コーパス全件の漏洩検査が済んだとはしない。

Macではfake portsの操作・局面IDに関する7テストと、新規7変異の検出を確認。既存v1・v2を含む軽量集計は計22テストが成功した。実Rustの詰み／打切り・決定的な棋譜・中断・改変拒否・全receiptの統合テスト4件を含む全回帰はPR #78のLinux CIで成功した。Macでエンジン・探索・実モデルを実行しない。
