# Vast.aiでのPhase5／6研究ジョブ

**2026-11-12・一時停止**：既存Sの公開デモと、Mの少量2 run・48局評価を現段階の成果とする。
本比較12 run・MのWeb配布・観戦表示2案／実端末各60分は未完了のまま停止する。
追加GPU・生成・学習を自動再開しない。[停止時点の結果と固定HF版](RESEARCH_CHECKPOINT_20261112.md)を現在の確認元とし、
以下の旧「現在」「次」「予算」は対象時点の記録、実行コマンドは再開後の手順として読む。

**2026-11-05 00:13 UTC・現在の確認元**：[P5-4の実測・各HF再開と資源解放](P5_4_RESULTS.md)まで完了。4GPU専用controllerは単価上限US$3.50/時・転送予約US$1を扱い、最終試行は3時間・予約US$11.50。単GPUの条件と区別する。 現在の予算・保存容量は[STATUS](STATUS.md)、以下は対象時点の手順・試行履歴として読む。

**2026-11-03 16:56:12 UTC・P5-2の終了と停止**：[本条件3世代48対局・HF保存・別VM後続世代](P5_2_COMPLETION.md)の結果を記録した。使用した所有課金資源は0。棋力改善・P5-3・DDP・Phase6は未完了であり、結果共有後に停止する。

研究用の用途・予算・絶対期限には`training.vast_research_control`を使う。実CUDA・学習・HF保存／復旧・資源解放は[P5-2完了記録](P5_2_COMPLETION.md)、実機での独立期限削除は[初回試行](P5_SELFPLAY_TRIAL.md)を確認する。通常の早期解放と期限停止を混同しない。

利用可能な前払い額は`credit`を確認し、`balance=0`をクレジット不足と扱わない。個人の残高・メール・資格情報を公開記録へ保存しない。全体US$85／基本枠100、Phase5 US$24／配分24。Phase6配分15、条件付き追加US$100は未適用。保守的予約とサービス残高・確定請求は別である。

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
