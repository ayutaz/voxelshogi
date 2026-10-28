# M4の外部本生成・検証・再生成

実装契約: 2026-10-28。本生成は[2026-10-29 JSTに完了](M4_COMPLETION.md)。以下は段階4で固定した実行契約。目標は、標準1王の**重複を除いた約10万局面**を生成し、全件の履歴・合法性・教師を検証し、固定環境で全再生成したファイルのバイト一致を確認すること。実機の少量計測と試料のHF公開は成功。[本規模データの全検証・全再生成・公開・資源終了は完了](M4_COMPLETION.md)。下記は実装と検証手順。[次の起動前準備・本生成・公開の順序](M4_PLAN.md#次に実行する単位)。

## 小規模生成から追加するもの

- `GenerationConfig.search_opening_plies`で、探索対局の序盤だけ固定seedの合法手を選ぶ。全非終端行に同じ固定条件の探索教師を記録し、序盤の実際の着手と探索推奨手を区別する。既定0は従来の探索対局を維持する。同一初期局面から同じ探索軌跡を繰り返して件数を水増ししない。
- 1〜4プロセスで対局を生成し、対局ID順で重複除外・Parquet・manifestを確定する。投入済み未回収の対局数をワーカー数までに抑え、生成完了順で分割や重複の代表を変えない。再開時も既存の全件検証を先に行う。
- 全件検証器は生成器の着手選択helperを使わず、seed・対局ID・手数から序盤着手を再計算する。教師の固定条件再探索、全履歴、自然終局、対局単位のsplit、全体での重複を確認する。
- 総行数、重複除外後の有効局面、生成元別の有効件数、全有効教師、重複を除いた有効教師を分けて記録する。探索教師を持たないrandom/rules行を最善手教師へ数えない。

行schemaは`voxelshogi-dataset-v1`のまま、生成方策の設定と来歴をmanifestに追加する。過去のデータは記録済みのソースコミットで検証する。新しいコードで過去のmanifestを暗黙に読み替えたり、異なる設定を同じ生成物として扱ったりしない。

## 実行の契約

`training.production`は外部Linux専用。通常の小規模CLIの5分／セッション10分上限は変更せず、別の承認済み実行枠を使う。ジョブには次を固定する。

| 項目 | 条件 |
|---|---|
| 来歴 | cleanな40桁のソースコミット、uv.lockのhash、Python、OS、GPU・ドライバ、論理CPU、ジョブhash |
| 生成条件 | seed、対局数・最大手数、生成元、序盤分岐手数、教師の固定深さ／ノード、1〜4ワーカー |
| 費用枠 | provider、具体的な利用承認、最大実行秒数・単価・消費上限。実行時間×単価が承認枠を超えるジョブを拒否 |
| 資源監視 | 所有プロセス群RSS合計1 GiB、pressure／swap、時間、所有子孫の終了。別名ledgerで同じ作業の上限を繰り返しリセットしない |
| 完了判定 | productionの最低有効件数は100,000。教師が1件もないもの、総行数だけが10万のもの、未完了や再生成不一致を成功にしない |
| CI | purpose=`ci-smoke`、provider=`ci`、30秒以内・小さいfixtureのみ。実機速度や本生成の証拠へ流用しない |

具体的なジョブは初回と代表試行の計測後に作り、時間・金額・生成条件を提示して承認を得る。ジョブ内の`approved=true`は承認の記録であり、エージェントが承認を作り出す機能ではない。初回起動は一度、自動承認レビューが具体的な課金承認不足として拒否した。その後2026-10-28に、ユーザーが米国RTX 5090×1・最大60分・消費上限US$2を明示承認し、06:30 UTCに同じ単価$1/時の構成を起動した。初回実機は終了・資源解放済み。その後ユーザーが費用合計US$100とM4合成データv1のCC-BY-4.0を承認した。現在は初回・試料公開・本生成を同じ総枠内で管理し、実測見積もり・ジョブ上限・残額を記録する。M6学習は今回の実行対象外。

```bash
# 承認済みのVast.ai／CloudRiftのLinuxでだけ実行する
uv run --locked python -m training.production runs/m4/approved-job.json runs/m4/production
```

1回のジョブで生成→全件検証→全再生成→全ファイルhash比較を行い、`report.json`にcomplete、各工程の時間、件数、サイズ、manifestと各ファイルのhashを残す。途中停止はcomplete=falseとし、同じ設定・ledgerで再開する。ジョブの停止はインスタンス課金の停止ではないため、外側の終了経路を維持する。

[本生成の具体的な見積もり案](M4_PRODUCTION_QUOTE.md)に生成条件・実測・承認範囲を記録する。本生成見積もりは、代表試行の生成・検証・再生成時間を合計し、重複除外後の有効率で必要行数を補正する。起動・準備・転送・照合・終了と余裕を加え、実構成の総単価で計算する。CPU数倍の線形高速化は仮定しない。短い初回試行からの外挿を確定見積もりとして出さず、長い対局と並列の代表試行を通す。

## 保存と公開

生成と再生成の双方を外部ホストに置く。Macへ回収するのは小さい集計・manifest・hash・receiptだけ。公開用stagingには検証済みParquet、manifest、検証記録、Dataset Cardと確定済みLICENSEだけを用意し、[HF公開スキルとハーネス](HF_PUBLICATION.md)で`voxelshogi/`配下へ直接送る。固定Hub revisionの全ファイルを外部Linuxでダウンロード・照合し、完了receiptを確認してから資源を終了する。ライセンスやゲートの確認待ちがある場合は、生成前に保持方法・費用も決める。

## 本生成の起動・公開ハーネス

`training.rental_control`は制御側だけで使う。既存の承認済み累積予算ledgerをロックして旧SKUはUS$12、[CPU少なめの代替SKU](M4_PRODUCTION_QUOTE.md#空き状況に応じた代替構成)はUS$24を予約し、選択SKU・地域の単価US$1/時以下・GPU1枚・空き・公開IPと、別のVoxelShogi実機が稼働していないことを起動前に確認する。専用SSH公開鍵を使い、providerキーは制御側の`.env`からだけ読む。新規入金・自動チャージ・追加volumeを行わない。

起動要求と不変の期限を保存し、独立した終了guardianを先に起動してから1台だけ要求する。同じ状態ディレクトリで要求を再発行しない。旧SKUは11時間45分、代替SKUは23時間45分で終了要求を開始し、各12／24時間まで15分の余裕を置く。応答断でIDが不明な場合も所有tagから回収して終了し、空の一覧を資源解放の証拠にしない。終了後はID指定の`Inactive`・`resources_released=true`と永続volumeを確認する。終了APIが確認できない場合は、その事実を記録して同じ資源のcleanupを続ける。

```bash
# 制御側。承認済みledgerと専用SSH鍵を準備し、PR必須CI・通常merge後だけ実行する。
uv run --locked --no-sync python -m training.rental_control runs/m4/production-control rent
uv run --locked --no-sync python -m training.rental_control runs/m4/production-control status
# 実行・公開・照合後、または停止時。対象はこの状態ディレクトリの所有実機だけ。
uv run --locked --no-sync python -m training.rental_control runs/m4/production-control terminate
```

`training.production_release`はジョブ作成と、既存試料を保持した本生成の公開を担当する。実行するcleanな40桁SHAをジョブへ固定する。認証はHF CLI等の承認済み資格情報を一時的な環境／メモリで渡し、値を引数・ログへ書かない。

```bash
# 外部Linux。checkoutした統合済みの40桁SHAを使う。
uv run --locked python -m training.production_release preflight runs/m4/production
uv run --locked python -m training.production_release job runs/m4/approved-job.json --source "$(git rev-parse HEAD)"
uv run --locked python -m training.production runs/m4/approved-job.json runs/m4/production
uv run --locked python -m training.production_release publish runs/m4/production
```

`preflight`は生成前に認証アカウント・HF親commit・public/manual・Community OFFを確認する。`publish`は、生成・検証・全再生成の完了、10万有効件数、件数内訳、manifest・実ファイルhashを確認する。試料2 configは固定した既存Hub commitから取得して全hashを確認し、`production-64`を追加する。Dataset Cardは実際の件数・生成元・教師・split・使い方・制約・ライセンスから作成する。

上記コマンドは旧SKUの12時間枠。代替SKUを選ぶ場合は`rent`と`job`の両コマンドへ`--sku rtx59-3-24-750-xam.1`を追加し、24時間枠とする。`status`・`terminate`・guardianは保存済み所有ID・期限を使う。

送信時の親commitを固定し、別の変更を上書きしない。返されたHub commitへ固定した全ファイルを外部Linuxへ並列取得し、各ファイルのbytes・SHA-256を全件照合してから`publication/complete.json`を確定する。検証用cacheを公開stagingへ混ぜない。アップロード後のreceiptは先に保存し、再開時は同じcommitの検証を続けて二重アップロードを避ける。認証・通信が失敗しても本生成を最初から再実行せず、同じプロセス・report・receiptを調べる。

この起動前準備だけでは本生成完了ではない。[M4計画](M4_PLAN.md)の全件生成・検証・再生成・公開・資源終了まで実行し、結果と費用を固定記録へ残す。

## 検証

Macでは固定seedの手選択、対局順の重複処理、全工程を含む費用計算、未承認・予算超過・10万未満・Mac実行の拒否だけを純粋／軽量テストで確認する。実Rust・Parquetの1/2/4ワーカー一致、ワーカー数変更を含む停止再開、再hash後の序盤着手改ざん検出、CLIの子プロセス監視と全再生成、小規模データを本生成完了としないことはLinux CIで確認する。

変異テストの基準実行にもCLIの来歴条件を適用するため、隔離コピーへ専用の`mutation-baseline`ブランチと初期commitを作る。コピーした.gitignoreとJUnit出力の除外を使い、実行結果だけではdirtyにならず、ソース変異はdirtyとして検出する。元リポジトリのGit履歴やremoteをコピーせず、外部へpushしない。通常のLinux CIでCLIを含む全基準テストを実行する。
