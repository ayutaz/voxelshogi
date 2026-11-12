# 2026-11-12：全ドキュメント点検記録

リポジトリのMarkdown全130件（本書・新規文書・運用skills・PRテンプレートを含む）を棚卸しした。
更新56件、現行と一致29件、固定した過去記録45件。
現在の区切り・数値・固定HF版は[停止時点の記録](RESEARCH_CHECKPOINT_20261112.md)を確認元とする。

## 更新内容と確認範囲

- README／CLAUDE／AGENTS／STATUS／ROADMAP／全体計画／仕様を、ユーザー指定の一時停止へそろえた。
- 公開S、未学習推論ラボ、少量Mを分け、Full／Geometry各1,024更新・48局・1,376 NN参照監査と、棋力改善未確認を反映した。
- 元の公開失敗と別のHF退避を分け、pipeline_complete=false・回収review・削除receipt欠落も残した。
- P6と継続用のP5手順に停止時点への入口を付けた。日時付きの旧実験・予算・失敗・hashは書き換えず、本文の旧「現在」「次」を履歴として読む範囲を明記した。
- BENCHMARKSとデモ／技術記事の案内を追加した。元の本比較12 run・最終72局・M配布3形式・表示2案・実端末各60分を未完了として保持する。
- 10:31 JSTの小さいJSON snapshotは内容をMarkdownのコードブロックへ保持し、今回のPR差分を文書パスだけにした。実験入力や実行設定は変更していない。
- 全Markdown本文を読み取り、相対リンク・見出しアンカー・JSONブロック・秘密情報パターンを検査する。主要数値は停止時点の実行記録・manifest・receipt・予算台帳・公開S catalogと照合する。
- 13:21 JSTのGitHub一括取得ではmain CI／SecurityとPR #174〜#176がキュー待ち。13:22 JSTの読取でVast所有実機0、CloudRiftの稼働・遷移対象所有実機0。全storage種別の新規列挙ではない。
- 過去の完了記録は削除せず、整理した旧STATUS等の全文もGit履歴に残る。HFの固定Card・配布物は変更しない。外部価格・ライブラリ情報の再調査、全コマンド／モデル／E2Eの再実行は行っていない。
- コード・ルール・モデル・依存・CI設定の変更はない。文書だけの更新にTDD用の製品変異や重いテストは追加しない。必須CI未完了でmergeしない。

今回の作業は研究再開・新規課金・HF送信・技術記事の外部投稿を含まない。研究の一時停止を維持する。

## 全Markdownの分類

| 文書 | 分類 | 点検・扱い |
|---|---|---|
| [.agents/skills/ci-checks/SKILL.md](../.agents/skills/ci-checks/SKILL.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [.agents/skills/hf-publication/SKILL.md](../.agents/skills/hf-publication/SKILL.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [.github/pull_request_template.md](../.github/pull_request_template.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [AGENTS.md](../AGENTS.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [CLAUDE.md](../CLAUDE.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [README.md](../README.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [SECURITY.md](../SECURITY.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/BENCHMARKS.md](BENCHMARKS.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/C0_VALIDATION.md](C0_VALIDATION.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/CI_CD_PLAN.md](CI_CD_PLAN.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/CI_PERFORMANCE.md](CI_PERFORMANCE.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/COST_ESTIMATE.md](COST_ESTIMATE.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/DEMO_AND_ARTICLE.md](DEMO_AND_ARTICLE.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/DEPLOYMENT.md](DEPLOYMENT.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/DOCUMENTATION_AUDIT_20261112.md](DOCUMENTATION_AUDIT_20261112.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/GAME_ENGINE.md](GAME_ENGINE.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/HF_PUBLICATION.md](HF_PUBLICATION.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/M0_VALIDATION.md](M0_VALIDATION.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M1_PLAN.md](M1_PLAN.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M1_VALIDATION.md](M1_VALIDATION.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M2_PLAN.md](M2_PLAN.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M2_VALIDATION.md](M2_VALIDATION.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M3_PLAN.md](M3_PLAN.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M3_VALIDATION.md](M3_VALIDATION.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M4_COMPLETION.md](M4_COMPLETION.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M4_DATASET_CARD_DRAFT.md](M4_DATASET_CARD_DRAFT.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M4_DATA_CONTRACT.md](M4_DATA_CONTRACT.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M4_HF_PILOT_RELEASE.md](M4_HF_PILOT_RELEASE.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M4_PLAN.md](M4_PLAN.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M4_PRODUCTION.md](M4_PRODUCTION.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M4_PRODUCTION_QUOTE.md](M4_PRODUCTION_QUOTE.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M4_PRODUCTION_RUN.md](M4_PRODUCTION_RUN.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M4_REMOTE_PLAN.md](M4_REMOTE_PLAN.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/M4_VALIDATION.md](M4_VALIDATION.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M5_PLAN.md](M5_PLAN.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M6_ARENA.md](M6_ARENA.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_BROWSER_EVIDENCE.md](M6_BROWSER_EVIDENCE.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_COMPLETION.md](M6_COMPLETION.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M6_CUDA.md](M6_CUDA.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_EVALUATION.md](M6_EVALUATION.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_EXPORT.md](M6_EXPORT.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_INFERENCE_RELEASE.md](M6_INFERENCE_RELEASE.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_LOCAL_MODEL.md](M6_LOCAL_MODEL.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_MAIN.md](M6_MAIN.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M6_MODELS.md](M6_MODELS.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M6_PLAN.md](M6_PLAN.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M6_POLICY.md](M6_POLICY.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_PORTABLE.md](M6_PORTABLE.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M6_RENTAL_CONTROL.md](M6_RENTAL_CONTROL.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_RESUME_ARCHIVE.md](M6_RESUME_ARCHIVE.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_RETRY.md](M6_RETRY.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M6_RUNTIME.md](M6_RUNTIME.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_RUN_PROPOSAL.md](M6_RUN_PROPOSAL.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M6_SESSION.md](M6_SESSION.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_STATE_RELEASE.md](M6_STATE_RELEASE.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_TRAINING_CONTRACT.md](M6_TRAINING_CONTRACT.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_TRIAL.md](M6_TRIAL.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/M6_VAST.md](M6_VAST.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/M6_WORKER.md](M6_WORKER.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/MODEL_CONTRACT.md](MODEL_CONTRACT.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/NINE_KINGS_EXPERIMENT.md](NINE_KINGS_EXPERIMENT.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/OVERALL_PLAN.md](OVERALL_PLAN.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_2_COMPLETION.md](P5_2_COMPLETION.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/P5_2_DOCUMENTATION_AUDIT.md](P5_2_DOCUMENTATION_AUDIT.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/P5_2_EXECUTION_PLAN.md](P5_2_EXECUTION_PLAN.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_3_COMPARISON.md](P5_3_COMPARISON.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/P5_3_DIAGNOSIS.md](P5_3_DIAGNOSIS.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/P5_3_EXECUTION_BUDGET.md](P5_3_EXECUTION_BUDGET.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_3_PLAN.md](P5_3_PLAN.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_3_POOL_ARCHIVE.md](P5_3_POOL_ARCHIVE.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/P5_3_STARTUP.md](P5_3_STARTUP.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/P5_3_TRIAL.md](P5_3_TRIAL.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/P5_4_PARITY_FAILURE.md](P5_4_PARITY_FAILURE.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/P5_4_PLAN.md](P5_4_PLAN.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_4_RESULTS.md](P5_4_RESULTS.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/P5_4_STARTUP.md](P5_4_STARTUP.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/P5_DATA_PLAN.md](P5_DATA_PLAN.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_DEADLINE_INCIDENT.md](P5_DEADLINE_INCIDENT.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/P5_EVALUATION.md](P5_EVALUATION.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_EXECUTION.md](P5_EXECUTION.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_GENERATIONS.md](P5_GENERATIONS.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_NEXT_EXECUTION.md](P5_NEXT_EXECUTION.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_PILOT.md](P5_PILOT.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/P5_PRIOR_NORMALIZATION.md](P5_PRIOR_NORMALIZATION.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/P5_PROTECTED_INPUTS.md](P5_PROTECTED_INPUTS.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_REPLAY.md](P5_REPLAY.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_SELFPLAY.md](P5_SELFPLAY.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_SELFPLAY_DATASET.md](P5_SELFPLAY_DATASET.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_SELFPLAY_MAIN.md](P5_SELFPLAY_MAIN.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_SELFPLAY_RELEASE.md](P5_SELFPLAY_RELEASE.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_SELFPLAY_STATE.md](P5_SELFPLAY_STATE.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P5_SELFPLAY_TRIAL.md](P5_SELFPLAY_TRIAL.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/P5_TARGETS.md](P5_TARGETS.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/P5_VAST_EXECUTION.md](P5_VAST_EXECUTION.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_ARCHITECTURES.md](P6_ARCHITECTURES.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_BROWSER_PROBE.md](P6_BROWSER_PROBE.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_BROWSER_RESULTS.md](P6_BROWSER_RESULTS.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_CORPUS_ADMISSION.md](P6_CORPUS_ADMISSION.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_EXECUTION_PLAN.md](P6_EXECUTION_PLAN.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_EXECUTION_RECOVERY.md](P6_EXECUTION_RECOVERY.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_MODEL_CONVERSION.md](P6_MODEL_CONVERSION.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_MODEL_DISTRIBUTION.md](P6_MODEL_DISTRIBUTION.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_MODEL_EVALUATION.md](P6_MODEL_EVALUATION.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_MODEL_PUBLICATION.md](P6_MODEL_PUBLICATION.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_NEXT_STEPS_20261112.md](P6_NEXT_STEPS_20261112.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_OPERATOR_RESULTS.md](P6_OPERATOR_RESULTS.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_PILOT_DRIVER.md](P6_PILOT_DRIVER.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_RESOURCE_BUDGET.md](P6_RESOURCE_BUDGET.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_RESUMPTION_PLAN.md](P6_RESUMPTION_PLAN.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_SCREEN_RESULTS.md](P6_SCREEN_RESULTS.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_STATE_CAPACITY.md](P6_STATE_CAPACITY.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_TRAINING_STATE.md](P6_TRAINING_STATE.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_VISIT_DATA.md](P6_VISIT_DATA.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/P6_VISIT_TRAINING.md](P6_VISIT_TRAINING.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/POST_M6_PLAN.md](POST_M6_PLAN.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/PROJECT_SPEC.md](PROJECT_SPEC.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/RELATED_WORK.md](RELATED_WORK.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/RESEARCH.md](RESEARCH.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/RESEARCH_CHECKPOINT_20261112.md](RESEARCH_CHECKPOINT_20261112.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/ROADMAP.md](ROADMAP.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/RULESET.md](RULESET.md) | 現行と一致 | 今回変わらないルール・境界・手順を維持。全コマンド再実行の意味ではない |
| [docs/RULE_VARIANTS_RESEARCH.md](RULE_VARIANTS_RESEARCH.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/STATUS.md](STATUS.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/TECH_STACK_RESEARCH.md](TECH_STACK_RESEARCH.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/experiments/p6-final-protocol-freeze.md](experiments/p6-final-protocol-freeze.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/experiments/p6-live-plan-2026-11-12.md](experiments/p6-live-plan-2026-11-12.md) | 更新 | 停止方針・現況・参照先を更新、または現在の引継ぎ資料を追加 |
| [docs/experiments/p6-plan-review-2026-11-12.md](experiments/p6-plan-review-2026-11-12.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
| [docs/experiments/p6-resumption-2026-11-12.md](experiments/p6-resumption-2026-11-12.md) | 固定した過去記録 | 対象日・source・実験条件の記録を保持。現在の進捗や価格へ読み替えない |
