# P5-2：ドキュメント点検記録

確認：2026-11-03 16:58 UTC。対象は追跡対象Markdown全91件、今回のHF公開先4 repoの固定revisionにあるCard計11件、運用skills 2件。実験の条件・実数・各HF revision・使用VMと限界は[P5-2完了記録](P5_2_COMPLETION.md)を参照。

## 点検方法と範囲

- 更新31件：P5-2の本条件48件・学習・各世代のHF保存・別VM後続世代・全入力hash監査・資源解放を反映した。小規模2件と修正前の部分成果16件を合算せず、費用の予約・参考額・未回収請求を分けた。
- 現行と一致29件：ルール・特徴量・M6のモデル入出力とブラウザ／保存契約、CI・公開・秘密管理の境界を照合した。変更は合法手の正規化精度と研究予算配分であり、NN・学習・出力logitsはFP32を維持する。
- 固定した過去記録31件：対象commit・日付・計測・失敗・承認の範囲と現在地への参照を点検し、元のbytesを保持した。過去の外部価格・文献を再調査したり、全ベンチマークを再実行した記録ではない。固定実験JSON・元hashも上書きしない。
- 全ローカルリンク・Markdownアンカーの存在を検査し、欠落0を確認する。HFは全3世代のDataset／state、保護index、両VMのcursor／reportを固定revisionで読み、Cardの実数・source・schema・license・限界を照合した。public/manual・Community OFFも確認した。
- 最終HF reportのmanifestは、全48対局監査・全HF復旧・別VM・確定run・protocol・累積upload ledgerの回収記録と一致した。データ・重みはMacに置かず、小さいCard・manifest・hash・集計だけを保存した。
- [ci-checks](../.agents/skills/ci-checks/SKILL.md)と[hf-publication](../.agents/skills/hf-publication/SKILL.md)は現行と一致。承認済みの送信を再承認待ちにせず、取得申請のmanual gate・Community OFF・外部Linux転送・10分以上のCI取得間隔を維持した。

この文書更新の必須CIと通常取り込みは対応するPR／Actionsで確認する。P5-2のパイプライン完了を棋力改善・Phase5全体・正式公開の完了に広げず、P5-3・DDP・Phase6の自動実行を止める。

## 全Markdownの分類

| 分類 | 文書 |
|---|---|
| 現行と一致 | [.agents/skills/ci-checks/SKILL.md](../.agents/skills/ci-checks/SKILL.md) |
| 現行と一致 | [.agents/skills/hf-publication/SKILL.md](../.agents/skills/hf-publication/SKILL.md) |
| 現行と一致 | [.github/pull_request_template.md](../.github/pull_request_template.md) |
| 現行と一致 | [AGENTS.md](../AGENTS.md) |
| 更新 | [CLAUDE.md](../CLAUDE.md) |
| 現行と一致 | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| 更新 | [README.md](../README.md) |
| 現行と一致 | [SECURITY.md](../SECURITY.md) |
| 現行と一致 | [docs/ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md) |
| 固定した過去記録 | [docs/C0_VALIDATION.md](C0_VALIDATION.md) |
| 固定した過去記録 | [docs/CI_CD_PLAN.md](CI_CD_PLAN.md) |
| 現行と一致 | [docs/CI_PERFORMANCE.md](CI_PERFORMANCE.md) |
| 更新 | [docs/COST_ESTIMATE.md](COST_ESTIMATE.md) |
| 現行と一致 | [docs/DEPLOYMENT.md](DEPLOYMENT.md) |
| 更新 | [docs/GAME_ENGINE.md](GAME_ENGINE.md) |
| 更新 | [docs/HF_PUBLICATION.md](HF_PUBLICATION.md) |
| 固定した過去記録 | [docs/M0_VALIDATION.md](M0_VALIDATION.md) |
| 固定した過去記録 | [docs/M1_PLAN.md](M1_PLAN.md) |
| 固定した過去記録 | [docs/M1_VALIDATION.md](M1_VALIDATION.md) |
| 固定した過去記録 | [docs/M2_PLAN.md](M2_PLAN.md) |
| 固定した過去記録 | [docs/M2_VALIDATION.md](M2_VALIDATION.md) |
| 固定した過去記録 | [docs/M3_PLAN.md](M3_PLAN.md) |
| 固定した過去記録 | [docs/M3_VALIDATION.md](M3_VALIDATION.md) |
| 固定した過去記録 | [docs/M4_COMPLETION.md](M4_COMPLETION.md) |
| 固定した過去記録 | [docs/M4_DATASET_CARD_DRAFT.md](M4_DATASET_CARD_DRAFT.md) |
| 現行と一致 | [docs/M4_DATA_CONTRACT.md](M4_DATA_CONTRACT.md) |
| 固定した過去記録 | [docs/M4_HF_PILOT_RELEASE.md](M4_HF_PILOT_RELEASE.md) |
| 固定した過去記録 | [docs/M4_PLAN.md](M4_PLAN.md) |
| 固定した過去記録 | [docs/M4_PRODUCTION.md](M4_PRODUCTION.md) |
| 固定した過去記録 | [docs/M4_PRODUCTION_QUOTE.md](M4_PRODUCTION_QUOTE.md) |
| 固定した過去記録 | [docs/M4_PRODUCTION_RUN.md](M4_PRODUCTION_RUN.md) |
| 固定した過去記録 | [docs/M4_REMOTE_PLAN.md](M4_REMOTE_PLAN.md) |
| 固定した過去記録 | [docs/M4_VALIDATION.md](M4_VALIDATION.md) |
| 固定した過去記録 | [docs/M5_PLAN.md](M5_PLAN.md) |
| 現行と一致 | [docs/M6_ARENA.md](M6_ARENA.md) |
| 現行と一致 | [docs/M6_BROWSER_EVIDENCE.md](M6_BROWSER_EVIDENCE.md) |
| 固定した過去記録 | [docs/M6_COMPLETION.md](M6_COMPLETION.md) |
| 現行と一致 | [docs/M6_CUDA.md](M6_CUDA.md) |
| 現行と一致 | [docs/M6_EVALUATION.md](M6_EVALUATION.md) |
| 現行と一致 | [docs/M6_EXPORT.md](M6_EXPORT.md) |
| 現行と一致 | [docs/M6_INFERENCE_RELEASE.md](M6_INFERENCE_RELEASE.md) |
| 現行と一致 | [docs/M6_LOCAL_MODEL.md](M6_LOCAL_MODEL.md) |
| 固定した過去記録 | [docs/M6_MAIN.md](M6_MAIN.md) |
| 固定した過去記録 | [docs/M6_MODELS.md](M6_MODELS.md) |
| 固定した過去記録 | [docs/M6_PLAN.md](M6_PLAN.md) |
| 現行と一致 | [docs/M6_POLICY.md](M6_POLICY.md) |
| 固定した過去記録 | [docs/M6_PORTABLE.md](M6_PORTABLE.md) |
| 現行と一致 | [docs/M6_RENTAL_CONTROL.md](M6_RENTAL_CONTROL.md) |
| 現行と一致 | [docs/M6_RESUME_ARCHIVE.md](M6_RESUME_ARCHIVE.md) |
| 固定した過去記録 | [docs/M6_RETRY.md](M6_RETRY.md) |
| 現行と一致 | [docs/M6_RUNTIME.md](M6_RUNTIME.md) |
| 固定した過去記録 | [docs/M6_RUN_PROPOSAL.md](M6_RUN_PROPOSAL.md) |
| 現行と一致 | [docs/M6_SESSION.md](M6_SESSION.md) |
| 現行と一致 | [docs/M6_STATE_RELEASE.md](M6_STATE_RELEASE.md) |
| 現行と一致 | [docs/M6_TRAINING_CONTRACT.md](M6_TRAINING_CONTRACT.md) |
| 固定した過去記録 | [docs/M6_TRIAL.md](M6_TRIAL.md) |
| 現行と一致 | [docs/M6_VAST.md](M6_VAST.md) |
| 現行と一致 | [docs/M6_WORKER.md](M6_WORKER.md) |
| 現行と一致 | [docs/MODEL_CONTRACT.md](MODEL_CONTRACT.md) |
| 固定した過去記録 | [docs/NINE_KINGS_EXPERIMENT.md](NINE_KINGS_EXPERIMENT.md) |
| 更新 | [docs/OVERALL_PLAN.md](OVERALL_PLAN.md) |
| 更新 | [docs/P5_2_COMPLETION.md](P5_2_COMPLETION.md) |
| 更新 | [docs/P5_2_DOCUMENTATION_AUDIT.md](P5_2_DOCUMENTATION_AUDIT.md) |
| 更新 | [docs/P5_2_EXECUTION_PLAN.md](P5_2_EXECUTION_PLAN.md) |
| 更新 | [docs/P5_DATA_PLAN.md](P5_DATA_PLAN.md) |
| 更新 | [docs/P5_DEADLINE_INCIDENT.md](P5_DEADLINE_INCIDENT.md) |
| 更新 | [docs/P5_EVALUATION.md](P5_EVALUATION.md) |
| 更新 | [docs/P5_EXECUTION.md](P5_EXECUTION.md) |
| 更新 | [docs/P5_GENERATIONS.md](P5_GENERATIONS.md) |
| 更新 | [docs/P5_NEXT_EXECUTION.md](P5_NEXT_EXECUTION.md) |
| 固定した過去記録 | [docs/P5_PILOT.md](P5_PILOT.md) |
| 更新 | [docs/P5_PRIOR_NORMALIZATION.md](P5_PRIOR_NORMALIZATION.md) |
| 更新 | [docs/P5_PROTECTED_INPUTS.md](P5_PROTECTED_INPUTS.md) |
| 更新 | [docs/P5_REPLAY.md](P5_REPLAY.md) |
| 更新 | [docs/P5_SELFPLAY.md](P5_SELFPLAY.md) |
| 更新 | [docs/P5_SELFPLAY_DATASET.md](P5_SELFPLAY_DATASET.md) |
| 更新 | [docs/P5_SELFPLAY_MAIN.md](P5_SELFPLAY_MAIN.md) |
| 更新 | [docs/P5_SELFPLAY_RELEASE.md](P5_SELFPLAY_RELEASE.md) |
| 更新 | [docs/P5_SELFPLAY_STATE.md](P5_SELFPLAY_STATE.md) |
| 更新 | [docs/P5_SELFPLAY_TRIAL.md](P5_SELFPLAY_TRIAL.md) |
| 現行と一致 | [docs/P5_TARGETS.md](P5_TARGETS.md) |
| 更新 | [docs/P5_VAST_EXECUTION.md](P5_VAST_EXECUTION.md) |
| 更新 | [docs/POST_M6_PLAN.md](POST_M6_PLAN.md) |
| 更新 | [docs/PROJECT_SPEC.md](PROJECT_SPEC.md) |
| 固定した過去記録 | [docs/RELATED_WORK.md](RELATED_WORK.md) |
| 更新 | [docs/RESEARCH.md](RESEARCH.md) |
| 更新 | [docs/ROADMAP.md](ROADMAP.md) |
| 現行と一致 | [docs/RULESET.md](RULESET.md) |
| 固定した過去記録 | [docs/RULE_VARIANTS_RESEARCH.md](RULE_VARIANTS_RESEARCH.md) |
| 更新 | [docs/STATUS.md](STATUS.md) |
| 更新 | [docs/TECH_STACK_RESEARCH.md](TECH_STACK_RESEARCH.md) |
