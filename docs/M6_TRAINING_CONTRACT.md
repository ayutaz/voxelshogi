# M6 教師・損失・評価契約 v1

2026-10-29。`voxelshogi-supervision-v1`を最初の学習前に固定する。実装は[training/supervision.py](../training/supervision.py)、入出力と座標は[既存契約](MODEL_CONTRACT.md)。ルール・合法性はRustのM4再生検証に従い、この層で将棋のルールを再実装しない。

## 入力と監査

HF `voxelshogi/voxelshogi-synthetic-v1`のrevision `6e7fb29d2469b56a895042fbb089d86e7b4d074f`、config `production-64`だけを使う。既存試料は追加しない。[M4公開receipt](experiments/m4-production-release-2026-10-29.json)のplan hash・宛先・固定revisionと、対象全ファイルのbytes／SHA-256を照合してからParquetを読む。manifest・shard一覧・設定・schema・行数も照合する。

監査は1対局のParquetずつ読む。履歴長・手番・合法手文字列とcanonical IDの対応、教師flagと深さ／score、終端・split、重複の最初の出現参照を検査する。`legal_moves`と`legal_actions`は別々にソートされているため、同じ順序と仮定してzipしない。盤・持ち駒・手番が同じ局面を手数にかかわらず検出し、誤った重複flagやsplit漏洩を拒否する。

M4の全件Rust再探索・再生成の証拠は固定ファイルhashで引き継ぐ。この監査がルールの独立再実装や全再探索を行ったとは主張しない。実データのsplit別教師件数・完了深さ別件数はまだ未集計。学習前に外部Linuxで全件集計し、M4の総行数116,921・重複3,600・有効113,321・有効教師36,894等と照合する。全splitに有効教師がなければ停止する。

```bash
# 固定revisionを取得・照合する外部Linuxでのみ。Macでは実行しない。
uv run --locked python -m training.supervision runs/m6/input/production-64 runs/m6/input-audit.json
```

出力は教師契約、実件数・split別教師・完了深さ・除外理由、検証済みファイル一覧とhash。空集合、未完了、件数不一致、未検証ファイルの読み込みを成功としない。法的な取得条件・public/manual・Community OFFは[HF公開手順](HF_PUBLICATION.md)を維持する。

## 教師と損失

| 対象 | 固定する解釈 |
|---|---|
| 採用行 | search行、`teacher_valid=true`、完了深さ1〜2、整数score、`duplicate_of=null`、非終端。深さ0・scoreなしの代替手を採用しない |
| Policy | `teacher.best_move`をcanonicalな行動IDに変換する。序盤分岐の`played_move`へ置き換えない。合法集合に含まれることを確認 |
| Value | `tanh(teacher.score / 1000)`。scoreは既に手番側の視点なので、後手で再度符号を反転しない。静的`evaluation`・実勝敗を混ぜない |
| 終局尺度 | coreの±1,000,000は±1へ飽和する。最終行自体は教師なしとして除外し、64手打ち切りを引分・0の教師に変換しない |
| Policy損失 | Rust由来の合法集合に対する交差エントロピーのbatch平均。同一logitの合法2手ならlog(2) |
| Value損失 | Value教師との二乗誤差のbatch平均。合計はPolicy損失＋1×Value損失 |
| 初期化・選択 | seed314159、M3と同じ5,021,064パラメータ。valの合計損失が小さいcheckpointを選び、同点は早いstep。testで選択しない |

Valueは探索の尺度を圧縮した蒸留値で、勝率ではない。最初の尺度を1000に固定し、異なる尺度や採用条件を試す場合は新しいprofileと設定hashで比較する。全件の密な特徴量・行動マスクをRAMへ積まない。キャッシュを作る場合も外部Linuxの分割ファイルとし、入力revision・契約・source hashに結び付ける。

## 評価を先に固定する

- 教師精度は固定testの有効教師でPolicy Top-1／Top-5・交差エントロピー、Value MSE／MAEを測る。マスク前の合法手率と、合法集合から選んだ後の合法手率を区別する。
- 対局は標準初期局面から固定seedで8手の合法な序盤を作り、同じ序盤でモデルの先後を交換する。Randomはseed7000〜7019の20組40局、M1探索は8000〜8009の10組20局。未学習基準と学習済み基準・全変換版に同じ集合を使う。
- M1は深さ2／10,000ノード／TT4,096。NNは合法logit最大、同点は小さい行動ID。Randomの乱数seedは100000＋序盤seed。履歴を保持し、自然終局を優先して序盤込み256手で打ち切る。
- 一次指標は勝数／開始局数。勝ち・負け・自然引分・打ち切りを別々に記録し、打ち切りを引分に変えない。実行失敗や未完了の対局集合を評価完了としない。
- 95%区間は先後2局を1単位とした序盤seedのpaired bootstrap、10,000回・seed314159とする。少数の序盤であることを明示し、狭い結果や0勝を棋力一般の証明にしない。対局の生カウント・条件も残す。
- 変換・校正・選択はtrain/valで行い、選択済みcheckpointと事前に指定したFP32／FP16／INT8重み版のtest比較を行う。変換後の棋力・数値・速度・サイズを同じ条件で報告する。

## 配布と実装の境界

M6モデルはHFのpublic/manual・Community OFFで公開し、承認済み利用者が取得した実ONNXをWebのファイル選択で読み込む方式を採る。公開catalogのmodel ID・形式・hashに照合してWorkerへ渡す。重みを別の公開URLへ複製して取得ゲートを迂回しない。既存M3の承認済み配布は維持する。

現時点で実装したのは教師抽出とデータ監査。学習・損失、保存再開、対局評価、変換後の測定、Webの読込・観戦は[M6計画](M6_PLAN.md)の後続作業である。Macで確認するのは小さい手書きmetadata fixtureの純粋テストだけで、Rust／Parquetの接続と全回帰はLinux CI、実データ監査と学習は外部Linuxで行う。
