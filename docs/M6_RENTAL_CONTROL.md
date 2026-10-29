# M6のGPU起動・費用上限・終了制御

[M6の具体案](M6_RUN_PROPOSAL.md)に合わせ、既存の総額US$100とM6専用の提案枠US$24を同時に守る起動制御を準備する。**費用配分・学習成果物ライセンス・再開状態公開の判断はまだ確認待ち。M6の実レンタルは行っていない。** この実装やテスト用の承認fixtureを、ユーザーの承認として扱わない。

## 目的と上限

M4の小CPU構成には24時間のquoteがあるが、M6の初回試行は最大4時間／US$4。同じSKUでもM4の時間を流用しない。M4の既存quoteは保持し、M6だけ`M6Rental`の用途・phaseに従う。

| 対象 | 起動条件 |
|---|---|
| 初回試行 | `phase=trial`、最大14,400秒／US$4。4時間には環境構築・監査・cache・CUDA試行・退避と終了を含む |
| 実測後の作業 | `phase=main`、1回最大72,000秒／US$20。実CUDA試行のreport hashと、15分の終了余裕を含めて上限に収まる見積もりが必要 |
| M6の累積 | 全試行・再レンタルの予約を合計し、24時間／US$24以下 |
| プロジェクト全体 | M4の既存予約も含む同じledgerでUS$100以下。予約上限と実請求は分ける |

CloudRiftの既知のRTX5090 SKUだけを対象とし、実際の単価が100 cents/時以下・GPU1台・空きとpublic IPがあることをAPIで起動直前に確認する。GPU／CUDAの実対応は起動後の[preflight](M6_CUDA.md)でも確認する。24 GiB RAM構成を第一候補とし、同GPU・同単価の既知の48 GiB構成も選択できる。これらの実機が現在空いていることや、24時間でM6が完了することは保証しない。

## 用途の承認を混ぜない

M6の承認記録は以下のschemaを使う。**未確定の現在はこのfalse／nullの状態であり、実行できる承認ファイルを自動生成しない。** 3点が実際に確定した後、制御側のignored `runs/`へ小さい記録を用意し、hashを起動記録に残す。

```json
{
  "schema": "voxelshogi-m6-rental-approval-v1",
  "approved": false,
  "maximum_usd": 24,
  "maximum_seconds": 86400,
  "maximum_hourly_usd": 1,
  "license": null,
  "state_publication_approved": false
}
```

M6設定に`--purpose m6`がない場合は、資格情報を読む前に拒否する。用途の承認・試行の上限・main見積もりの不備は、読み取りAPIを呼ぶ前に拒否する。M6の予約は`m6-trial`／`m6-main`として全体ledgerに追加し、過去のM4予約を削除したり、未使用額を実請求の返金として扱ったりしない。同一tagは再予約しない。

## 停止処理を先に準備する

`rent-request.json`、期限、起動要求の識別を記録し、独立したguardianを**課金APIの前に**起動する。guardianは`python -m training.rental_control`をrepo rootから呼び、M6のpurpose・SKU・所有tagを引き継ぐ。PIDが存在するだけで成功とはせず、PID・tag・deadline hashが一致するready記録を10秒以内に確認する。起動に失敗した所有子プロセスは回収し、GPUを借りない。

ready待ちの0.1秒間隔はローカル子プロセスの起動確認だけで、CIやprovider APIのポーリングではない。通常のCI取得は10分以上の間隔を維持する。古いterminal・deadline・readyを持つ制御ディレクトリは新しいレンタルに使わず、既存実機の確認・終了を先に行う。

guardianは上限の15分前から終了を要求し、所有instanceだけの状態と`resources_released=true`を確認する。承認記録が取り除かれても、既存所有実機の終了は妨げない。provider応答が未確認なら、期限超過を記録して終了確認を継続する。終了要求の送信だけを課金停止の証拠にしない。制御側のプロセス・ネットワークが必ず動き続けるという保証ではなく、実行中は所有guardianを維持し、終了と資源解放を実際に確認する。

## 承認後の操作

実際に見積もりと承認記録がそろった後、制御側で専用SSH鍵と新しい制御ディレクトリを用意する。以下はAPI操作を伴うため、未承認の現在は実行しない。providerキーは制御側だけに置き、GPUへコピーしない。Macでは制御と小さい記録の回収だけを行い、モデル・データ・学習計算を中継しない。

```bash
uv run --locked python -m training.rental_control runs/m6/trial-control rent --purpose m6 --sku rtx59-3-24-750-xam.1 --phase trial --maximum-seconds 14400 --budget runs/m4/cost-budget.json --approval runs/m6/approval.json
uv run --locked python -m training.rental_control runs/m6/trial-control status --purpose m6
uv run --locked python -m training.rental_control runs/m6/trial-control terminate --purpose m6
```

mainの承認記録には`main_estimate`として`trial_sha256`・`estimated_seconds`・`maximum_seconds`を追加し、同じ場所の`trial.json`と照合する。実CUDA試行のverified・同じ入力順・test未使用・CUDA device・64 step以上・有限な速度・実GPU memory使用を検査する。見積もりの算出根拠、モデル／データ／コードの一致、監査・評価・ブラウザ・転送に必要な時間も別途レビューしてから固定する。JSONの形式検査だけで実学習や実機検証を完了としない。

## 検証

Macではproviderを使わない25の制御テストに加え、古い制御状態・用途の取り違えの拒否と、ネットワークを禁止した隔離checkoutでのguardian実プロセス起動を確認する。対象のM4／M6テストは合計30件。9変異を既知回帰へ追加し、全133 training変異と全回帰はLinux CIで確認する。承認の実記録作成、実起動・実測・終了の確認は未実施。
