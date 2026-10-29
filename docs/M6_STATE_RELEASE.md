# 再開状態の公開profileとアップロード上限

[再開archive](M6_RESUME_ARCHIVE.md)専用の`artifact_role="training-state"`を準備する。**optimizer・乱数状態の公開方針と学習済み成果物のライセンスはまだ確認待ち。実repo作成・転送・GPU起動は行っていない。** [具体案](M6_RUN_PROPOSAL.md)が確定するまで、実際のplanで公開承認をtrueにしない。

## 目的と送信範囲

GPUを終了しても学習を再開できるよう、JSON＋safetensorsのlatest／必要なbestと構造化した履歴を外部に保持する。通常のモデルや推論パッケージの公開許可を、optimizer状態の公開へ拡大しない。

宛先は`voxelshogi/voxelshogi-transformer-s-training-state`だけ。モデルrepoと分け、public/manual・Community OFFで扱う。対象ライセンスの承認に加えて`state_publication_approved=True`と、退避前から保持した`expected_binding`をplanに固定する。source commit・cache・設定・環境がarchiveの自己申告と一致するだけでなく、外部の期待条件と一致することを検査する。

manifestが列挙したrootの`config.json`／`history.json`、各roleの`config.json`／`state.safetensors`と、manifest、Card／LICENSE／任意NOTICEだけを対象にする。余分なファイル、pickle／`.pt`、生ログ、symlink、hashの違い、未評価のbestを拒否する。Cardは`Training and provenance`、`Resume contents`、`Verification`、`Access and license`の4節を持ち、optimizerと乱数の公開範囲・復旧方法・実際の照合結果を明記する。

## 承認後のplan

以下は外部Linuxで、実際に公開方針とライセンスが確定した後に使う。`expected_binding`は元runの`run.json`から先に保持する。ダウンロードしたarchiveのbindingを期待値にして再開条件を合わせない。

```python
from training.hub_release import plan_release

plan = plan_release(
    archive_folder,
    repo_id="voxelshogi/voxelshogi-transformer-s-training-state",
    repo_type="model",
    artifact_role="training-state",
    state_publication_approved=True,
    expected_binding=expected_binding,
    license_id=approved_license,
    license_approved=True,
    source_commit=source_commit,
)
```

通常profileのplan形式は変更しない。推論用catalogへstate repoを登録する機能も付けない。公開設定の確認、親commit固定、固定Hub commitの全hash照合には既存のHFハーネスを使う。

## 保存上限の維持

再開状態の**新規アップロードの累積上限は1 GiB**。同じbytesの再送や過去commit分も差し引かず、各planの全ファイルbytesを保守的に予約する。単一archiveは既存のファイル／フォルダー上限にも従う。有料storageの追加・履歴書き換え・自動削除はしない。HF無料public storageはbest-effortで、容量保証とは扱わない。

上限が実際に承認された後だけ、制御側で小さいledgerを一度作る。既存のledgerを新しい空のledgerで上書きしない。全レンタルで同じ予約履歴を引き継ぎ、1つの所有制御プロセスが順に更新する。OSのfile lockは同じホストの並行更新を防ぐもので、複数ホストへ複製したledgerの同時更新には使わない。

```json
{"schema":"voxelshogi-state-upload-budget-v1","approved_maximum_new_bytes":1073741824,"reservations":[]}
```

plan全体のSHA-256と全bytesの予約を、API操作より前にfile lock・flush・fsyncで確定する。ledger欠落、上限未承認／超過、同一planの重複予約は転送前に止まる。Macでの実行もAPI・ledger変更前に止まる。dry-runはledgerを更新しない。

```bash
# 承認済み外部Linux上だけ。planとCard・全hashを先に確認する。
uv run --locked python -m training.hub_release runs/m6/archive runs/m6/state-plan.json --execute --upload-budget runs/m6/state-upload-budget.json --receipt runs/m6/state-receipt.json
```

転送失敗・応答喪失でも予約は残す。既存Hub commitとファイルの照合を先に行い、成功したか不明なアップロードを盲目的に繰り返さない。返ったreceiptと固定revisionの全照合を確認し、新しいLinux runへの再取得・復旧まで確かめる。GPU終了前に小さいledger／manifest／receiptを制御側へ回収し、次のレンタルで継承する。Macへarchiveやモデルを中継しない。

## 検証と残作業

opaque metadataを使う対象4ファイル52テストで、別の公開承認・宛先・期待binding、余分なファイル・hash・best・symlink・Card、送信前予約・重複・上限・Mac拒否、API失敗時の予約保持を検証する。追加5変異と全回帰はCIへ含める。モデルやTensorはMacで実行しない。

実データのCUDA試行、実際のarchiveの転送・固定revision照合と復旧、実レンタルの終了制御へのledger引継ぎは未実施。profileの単体テストだけで外部保存を完了と表示しない。
