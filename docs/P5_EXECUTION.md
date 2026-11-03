# Phase5〜6の外部実行と初期費用制御

**2026-11-03 UTC更新**：[Vast研究用制御](P5_VAST_EXECUTION.md)と[初回実機試行](P5_SELFPLAY_TRIAL.md)を参照。実CUDA・固定入力取得／保護集合・有料実機の独立期限停止と解放を確認した。次の小規模試行は最大2時間／予約US$2、全体予約US$78／100、Phase5 US$17／20。利用クレジットの確認項目は`credit`で、追加入金は不要と訂正済み。追加US$100は未適用。以下は初期配分・過去試行の記録で、実学習・HF往復・本条件・別VM復旧の完了を示さない。

**2026-11-02 UTC更新**：main限定の`gpu-control` environmentとCloudRift Secretはユーザー承認後に設定済み。無料の独立監視は接続・正常終了を確認した。有料試行はRTX5090の在庫検査で作成前に拒否され、追加予約なし。単GPUの代替として台湾RTX4090を制御へ追加する。取得時の構成は[固定記録](experiments/p5-alternative-gpu-2026-11-02.json)、実期限停止・P5-1復旧・自己対局の本実行は引き続き未完了。

**終了遅延後の更新**：[インシデントと独立監視](P5_DEADLINE_INCIDENT.md)。実機は資源解放済み。全体予約US$73／100、Phase5 US$12／20に修正。以下の過去試行の上限は達成証拠ではない。新しい有料実行は独立監視の検証後に行う。

2026-10-30。Phase6まで進める指示と既存のプロジェクト費用枠に基づく。[段階別計画](POST_M6_PLAN.md)に従い、[P5-0の外部32局試行と資源解放](P5_PILOT.md)まで完了した。追加生成・自己対局学習は未実施。制御の実装は[training/research_rental_control.py](../training/research_rental_control.py)で、単体テストと実機の実行証拠を区別する。

## 目的と完了条件

M6専用制御の承認・用途を使い回さず、Phase5の評価／生成／自己対局とPhase6の演算／学習／公開作業を、同じ累積ledgerで制御する。外部試行の開始には次をすべて満たす。

- コードと入力workloadを固定し、用途・構成・見積もり・上限のあるplanと照合する。
- 既存の予約を残して、プロジェクト総枠と当該Phaseの上限に入る。
- 公式APIで単価・在庫・IP方式を再確認し、両GPUサービスの所有実機との競合がない。
- 課金開始前に独立した終了監視プロセスが起動し、所有tag・期限hash・PIDが一致する。
- 成果物の退避・hash照合後に実機を終了し、所有実機の`resources_released=true`まで確認する。

## 初期上限

| 対象 | 上限と扱い |
|---|---|
| プロジェクト基本枠 | 既存US$100。M6完了時の予約上限US$61をそのまま保持し、未予約分US$39の内側で進める |
| Phase5 | 初期の累積予約上限US$20。評価・データ・自己対局等の用途を分けて記録する |
| Phase6 | 初期の累積予約上限US$19。Phase5の余りを自動で加算しない |
| 1ジョブ | 最長4時間、単GPU・一時ディスク込みUS$1/時以下。最大US$4を保守的に予約する |
| 条件付き追加US$100 | 未使用。実測見積もりで不足を記録し、既存承認に沿ってledger・制御を更新してから有効化する。現行の初期制御は総枠100のまま |

これは新しい資金・実支出・サービス残高ではなく、既存総枠と実行指示に基づく初期配分。M6枠の残りUS$4や過去の予約をPhase5へ読み替えない。請求額が未回収の予約は、短時間で終了しても上限のまま控除する。有料保存の追加は含まない。

P5-0のUS$4に加え、[P5-1のデータ試行](experiments/p5-data-launch-2026-10-30.json)へUS$4を予約した。現在の保守的予約上限は全体US$69／100、Phase5 US$8／20。未予約分は全体US$31、Phase5 US$12、Phase6の初期枠はUS$19のまま。P5-0実機は資源解放済み。P5-1は06:02 UTC時点で稼働中で、結果と資源終了の確認は後続。実請求は未回収、条件付き追加US$100はまだ有効化していない。

単GPUの初期候補はM6で利用したRTX5090構成。2026-10-30の読み取りではCloudRiftに単GPUと2GPUの空き候補があったが、これは予約ではなく起動時に再取得する。初期制御は1GPUのみで、2／4GPUの価格や速度を確認済みとはしない。4GPUの検証条件・費用制御はP5-4で実測見積もりに基づいて追加する。

最初の評価試行は、セットアップ・固定データ／重みの取得・漏洩照合・少量対局・退避／照合・終了を含め最大4時間／US$4の枠内で完了した。次も入力とコードが固定される前にレンタルしない。稼働中に実装や承認を待たせず、時間不足なら未完了の証拠を退避して終了する。

## Planとworkload

2026-11-02 UTCの公式VMカタログでは、米国の対応済みRTX5090候補2件は在庫0。一方、台湾`ap-east-tw-kn-2`の`rtx49-18-80-450-kn-packed.1`（RTX4090×1、18 CPU／80 GiB RAM／24 GiB VRAM、一時disk約420 GiB）は在庫2・US$0.39/時だった。専用public IPはなく、SSHはproviderのhost addressとport mappingを使う。このSKU・地域・共有IPの組み合わせだけを研究用制御へ追加し、旧M4／M6の構成を広げない。2GPU版・未知の地域・public IPへの変更は拒否する。在庫は起動時に再確認する。

最初は従来どおり最大1時間／保守的予約US$1の独立停止＋HF固定revision取得試行を行う。時給が低くても予約額を減らさず、GitHub側の期限20分前停止・Mac側の予備停止・両サービスの所有照合・既存ledger上限・clean sourceとworkload hashの検査を保つ。4090の学習速度、CUDA起動、共有SSH接続は未実測であり、5090の測定値を流用しない。V100の空きも観測したが、CUDA13の学習環境へそのまま切り替える対象にはしない。

追加テスト5ケースのうち正常構成・独立監視欠落の2ケースが実装前に失敗した。関連する軽量87テスト、Ruff、追加3変異（候補削除・構成拘束の除去・地域の誤配送）はローカルで成功／検出を確認した。探索・tensor処理・学習はMacで実行していない。全回帰と必須8チェックの結果を確認してから通常mergeし、その後に有料試行を行う。

Planは`voxelshogi-research-rental-plan-v1`。purpose、実行元commit、workloadファイルのSHA-256、SKU／datacenter／public-IP方式、最大秒数・最大時給・最大額・想定秒数を持つ。最大時間は30分〜4時間で、想定時間と別に終了確認用の15分を残す。未知の用途・不一致の構成・途中で変わったplanを拒否する。

Workloadは`source_commit`を持つJSONで、評価の場合は評価protocolそのものを指定できる。planのhashはファイルの実bytes、評価v2内のprotocol hashはcanonical JSONのhashであり、両者を混同しない。Macの制御コードも同じclean commitで実行する。重い処理はそのcommitを取得した外部Linuxへ置く。

```bash
# 検証済みplan・workload・専用の公開SSH鍵を用意し、CI成功後に制御側で実行する形。
# 独立監視のmain workflowを起動し、Arm成功と監視step実行中を確認したrun ID。
# 過去試行のtagは再使用しない。新しいcontrol directory・plan・workloadを用意する。
guard_run_id='REPLACE_WITH_RUNNING_GUARD_RUN_ID'
uv run --locked python -m training.research_rental_control runs/p5/evaluation-control rent \
  --phase phase5 --plan runs/p5/evaluation-plan.json --workload runs/p5/protocol.json \
  --guard-run "$guard_run_id"
uv run --locked python -m training.research_rental_control runs/p5/evaluation-control status --phase phase5
uv run --locked python -m training.research_rental_control runs/p5/evaluation-control terminate --phase phase5
```

provider APIキーはMacの制御側だけで使い、外部GPUへ渡さない。CloudRiftの認証は公式APIのheader、Vast.aiは所有実機の読み取り確認だけに使う。両方ともredirect・エラー本文の出力を拒否する。plan・workload・APIキーはGitへ入れず、専用の`runs/`以下へ置く。終了監視はplan／workloadが失われても所有tagと期限記録でcleanupを継続できる。

## 検証と未実施の範囲

Macでは小さいprovider／ledger fixtureでRED→GREEN、予算・用途・時間・改変・稼働競合・終了監視とcleanupを検証する。新規10変異はすべて実行済みassertionで検出し、通常CIへ追加した。[PR #80](https://github.com/ayutaz/voxelshogi/pull/80)は必須8チェックと関連CI成功後に取り込み済み。実APIの読み取りと、モックによるrent／terminateは別の証拠として扱う。

P5-0では起動前の独立guard照合、実機起動・固定workloadの完走、証拠退避、終了要求と`Inactive`・`resources_released=true`まで確認した。期限前に終了したため、実期限到達による停止と複数GPUは未実測。次のworkload・コード・入力と必須CIをそろえてから新しい実機を借りる。成果物の公開は[HF公開ハーネス](HF_PUBLICATION.md)を使い、public/manual・Community OFF・Card・licenseの承認対象・固定revision全hash照合を守る。公開許可を新しい未確定のlicenseへ自動拡大しない。
