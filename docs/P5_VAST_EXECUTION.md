# Vast.aiでのPhase5／6研究ジョブ

研究用の用途・予算・絶対期限をVast.aiへ接続する。M6の完了済み承認を流用せず、`training.vast_research_control`を使う。実機試行は未実施。2026-11-02 11:13 UTCの再確認ではVast.ai残高0・所有実機0。保守的予約US$75／100、Phase5 US$14／20を維持する。

Planは`voxelshogi-vast-research-plan-v1`。共通のpurpose、source_commit、workload_sha256、maximum_seconds、maximum_hourly_usd、maximum_usd、estimated_secondsに、正の整数のoffer_idとdisk_gb=80を加える。最大30分〜4時間・US$1/時以下・単RTX5090・転送無料・verified・CUDA13対応・専用SSH鍵という既存見積もり条件を維持する。source・workload・planの改変、両サービスの所有競合、残高不足、重複予約を作成前に拒否する。

独立監視は手動main限定の`.github/workflows/vast-deadline.yml`とmain限定`gpu-control` environmentを使う。VAST_API_KEYは制御側だけに置き、GPUへ送らない。監視は正確なlabelの一覧・削除だけを扱い、作成APIを持たない。削除成功の応答と、完全にページ取得した一覧からの消滅を両方確認する。応答不明や観測済みIDの不明な消失を成功にしない。provider自身の強制リース期限ではない。

レンタル前に新しいlabel・30分〜4時間の絶対期限で監視を起動し、実run IDを`--guard-run`へ渡す。実際のVast workflow／job／Arm成功／監視stepをGitHub APIで確認する。CloudRiftのrunは代用できない。GitHub側は期限20分前、Macの予備停止はローカル期限15分前。ローカル絶対期限は独立監視より60秒以上早くし、provider確認後と作成API直前に残り時間を再検査する。

```bash
uv run --locked --no-sync python -m training.vast_research_control \
  runs/p5/REPLACE_WITH_NEW_CONTROL rent --phase phase5 \
  --plan runs/p5/plan.json --workload runs/p5/workload.json \
  --guard-run REPLACE_WITH_RUNNING_VAST_GUARD_RUN_ID
# 同じcontrolに対するstatus／attach-key／terminate。再作成ではない。
```

作成応答がタイムアウトしたら同じlabelを監査し、再作成しない。cleanupはplan／workloadがなくても、保存されたaccount ID・label／instance IDで続行する。HFの送信は別の公開ハーネスとSSH標準入力による一時資格情報を使い、Dataset／state／Model Cardと固定revision全hashを確認する。

19ケースの実装前失敗を確認後、既存M6・CloudRiftも含む軽量160テストとRuffが成功した。追加7変異を実行したassertion失敗で検出した。workflowの契約検査を隔離baselineでも実行できるよう`.github`をコピー対象に加えた。全回帰とactionlintはPR CIで検証する。これらはfake providerの検査であり、実レンタル・期限停止・HF復旧の達成証拠ではない。
