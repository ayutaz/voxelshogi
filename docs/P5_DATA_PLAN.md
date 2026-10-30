# P5-1：教師と長期対局分布の比較

2026-10-30。[開発用評価32局](P5_PILOT.md)を受けた次の実行単位。
新しい生成・学習はまだ行っていない。既存M4／M6のrevision・分割・結果を保持する。

## 目的とゴール

浅い教師の限界と、64手以降の局面不足を切り分ける。
同じ履歴付き局面へ2種類の探索を適用し、初期寄り／長期戦の分布を比較する。
教師の完了深さ・有効件数・重複・生成／検証／再生成時間を測り、
valと開発用評価を使って次の本規模条件を決める。
最終testで教師・epoch・採用条件を調整しない。

完了には、独立した期待値と変異、全手再生、全件検証と再生成照合、
Dataset Card・実件数・license・HF public/manual・Community OFF・固定revisionの
全hash照合が必要。少量試料を新しい本規模データと呼ばない。

## 切り分け方

| 軸 | 対照 | 比較候補 |
|---|---|---|
| 教師 | 深さ2／10,000ノード | 深さ3／100,000ノード。最低完了深さ3に達しない教師は除外・件数報告 |
| 分布 | 既存と同じ64手以内 | 96手以降の継続局面を含む、最大512手の対局 |

軌跡を作るpolicyと教師の探索を分ける。
まずM1の固定探索とseed付き序盤から履歴を作り、その**同じ局面**を両教師で読む。
深い教師へ変えた結果、軌跡まで変わる比較を教師だけの改善とは扱わない。
同じ早期・後期位置に対して教師をpairedにし、全2×2条件の実件数を報告する。
終局で後期の位置が得られない場合も、その不足を記録する。

最初の少量試行は次節の条件を実行前のJSONへ固定する。P5-0の時間は同条件の参考値で、
100,000ノードの教師時間へ比例外挿しない。既存runnerの64手／10,000ノード上限と
M6固定教師契約を緩めず、研究用の契約と実行経路を別に作る。

## 最初の少量試行の固定条件

[契約と生成](../training/research_data.py)の`pilot_protocol(source_commit)`を使う。
実行元は必須・関連CIに成功したclean commitとし、実行用JSONのbytes／hashも
レンタルplanへ固定する。下記は事前条件で、生成済み件数ではない。

| 項目 | 固定条件 |
|---|---|
| 対局とsplit | 8局。seed9300〜9304をtrain、9305〜9306をval、9307を最終testへ固定 |
| 軌跡 | 標準初期局面から16手をseed付き合法乱択。その後M1の深さ3／20,000ノード／TT4,096 |
| 終了 | 自然終局または合計512手。自然終局を優先し、打切りを自然引分としない |
| 採取 | ply16・48（early）、96・160・256・384・480（late）。未終局局面だけ、最大56局面に両教師を付ける |
| 教師 | shallow：深さ2／10,000ノード・最低完了深さ1。deep：深さ3／100,000ノード・最低完了深さ3。いずれもTT4,096 |
| ラベル | best-move-v1の合法手IDと、search-score-v1の`tanh(score/1000)`。PUCT訪問分布や実勝率とは区別する |
| 次の比較へ進むcoverage条件 | 除外後のtrain・valでearly／late×両教師の各cellに2件以上。train＋valのdeep有効率がearly／lateそれぞれ80%以上 |

coverage条件は、小さいval学習比較へ進める分布が得られたかのscreenであり、
深い教師の棋力・学習改善や本規模採用を証明しない。未達なら件数と原因を報告し、
この試料を完成した本規模データと扱わず、次の条件を別の実行単位として事前固定する。
testの教師結果をcoverageの採否に使わない。生成後に閾値を下げない。

[Linux専用runner](../training/research_data_runner.py)は完成した対局ごとにParquetを
atomic保存し、manifestをcommit点にする。中断した対局は登録せず、同じseedから
やり直す。再開時は既存の全手・教師・軌跡を再検証し、異なる条件では再開しない。
Parquetの各行は採取局面で、履歴・手番・物理局面ID・正規化入力ID・合法手と、
両教師の探索結果／有効targetを保持する。全軌跡と終局はmanifestに保持する。

```bash
# 外部Linux。生成元commitがcleanで、費用・終了guardが用意済みの場合。
uv run --locked python -m training.research_data_runner preset runs/p5/data-protocol.json
uv run --locked python -m training.research_data_runner generate runs/p5/data-protocol.json runs/p5/data-pilot
uv run --locked python -m training.research_data_runner verify runs/p5/data-protocol.json runs/p5/data-pilot
uv run --locked python -m training.research_data_runner audit runs/p5/data-protocol.json runs/p5/data-pilot \
  --corpus /mnt/dataset/production-64 --control-run /mnt/p5-control --model-run /mnt/p5-m6
```

`audit`は凍結M6コーパス全splitと、P5-0の保存済み全32局の開始後・終端局面を
正規化入力IDでも照合する。既存データ／開発用評価と同じ入力は全て除外し、
新split間の衝突も片側だけを残さず全て除外する。同一split内の重複は最初だけ残す。
全件再生成は別の空ディレクトリで同じprotocolを実行し、全Parquetとmanifestの
bytes／hashを照合する。公開stagingはmanifestに列挙したデータと検証結果・Card・
licenseだけで構成し、所有markerや稼働ログを含めない。

## データの検証

- 新しいsplitは対局単位で生成前に固定し、同じ開始履歴の系統やseedを世代間で別splitへ移さない。
- 既存のM6 val／testと新しい最終holdoutをtrainへ入れない。
  物理局面のほか、手番正規化したモデル入力の同値性も確認する。
  履歴によるルール結果の違いと、入力が同じことは別に記録する。
- 最終holdoutは開発用の8局面と分離する。合成少数駒を教材へ足す場合は
  実対局由来と区別し、露出済みの診断結果だけで採用を決めない。
- 自然終局・探索スコア・打切りbootstrapのValueを区別し、未完了探索を0点教師にしない。
- 原本・設定・ruleset・履歴・teacher条件・完了深さ・source／model hashを追跡する。

## 実行・公開

Macは仕様・小さいmetadataテストだけを扱う。生成、Parquet、探索、実モデル、
全件再生、再生成、HF staging／転送／取得照合は外部Linuxで行う。
単価・在庫と全工程を再確認し、[用途別費用制御](P5_EXECUTION.md)の
Phase5残枠内でplan・workload・独立guardを固定してから借りる。
入力取得に時間を要した今回の実測を、次の取得・照合の見積もりへ含める。
成果物はHFの`voxelshogi/`配下へCard付きで送り、取得gateと全hashを照合して資源を解放する。
