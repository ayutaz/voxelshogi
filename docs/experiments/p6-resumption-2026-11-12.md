# 2026-11-12 再開調査の記録

APIの読取結果と小さい実行記録だけを保存する。データ・モデル・認証情報は含まない。
今回の計画更新は文書だけのため、以下は実行入力ではなく取得日時付きの証拠である。

```json
{
  "schema": "voxelshogi-resumption-planning-audit-v2",
  "checked_at_utc": "2026-11-11T20:35:39.760056+00:00",
  "main": {
    "date": "2026-11-11T19:41:13Z",
    "sha": "8b4289ff0b3354633d271627580480de8170bfcd"
  },
  "read_only_external_audit": {
    "checked_at_utc": "2026-11-11T20:33:31.663360+00:00",
    "read_only": true,
    "resource_mutations": 0,
    "budget": {
      "approved_total_usd": 200,
      "reservations": 36,
      "reserved_usd": 160.75,
      "remaining_unreserved_usd": 39.25
    },
    "vast": {
      "project_instances": [],
      "complete_inventory": true
    },
    "cloudrift": {
      "project_active_instances": 0,
      "scope": "Personal Initializing/Active/Deactivating project-tagged instances"
    },
    "public_build": {
      "verified": false,
      "error_type": "HTTPError"
    },
    "public_build_retry": {
      "verified": false,
      "http_status": 403,
      "scope": "Metadata read failed; no public E2E performed, site availability not established"
    }
  },
  "github": {
    "prs": {
      "161": {
        "observed_head": "1a3f9393543c9686e59f3bfcb0aa6fdf0691b555",
        "state": "OPEN",
        "merge_state": "BLOCKED",
        "missing_required": [
          "CI Gate",
          "CodeQL (actions)",
          "CodeQL (javascript-typescript)",
          "CodeQL (python)",
          "CodeQL (rust)",
          "Known mutation regressions",
          "Rust core coverage",
          "Web unit coverage"
        ],
        "all_required_success": false
      },
      "162": {
        "observed_head": "0024b5b6e34fb009548caf8fbcf8cbf774ab4cc7",
        "state": "OPEN",
        "merge_state": "DIRTY",
        "missing_required": [
          "CI Gate"
        ],
        "all_required_success": false
      },
      "163": {
        "observed_head": "2abb3e8fd20bca32b8b387b2a5f7e89dcf1066fe",
        "state": "OPEN",
        "merge_state": "DIRTY",
        "missing_required": [
          "CI Gate",
          "CodeQL (javascript-typescript)",
          "CodeQL (python)",
          "CodeQL (rust)",
          "Known mutation regressions"
        ],
        "all_required_success": false
      }
    },
    "open_pr_numbers": [
      163,
      162,
      161,
      158,
      157,
      156,
      155,
      95
    ],
    "main_validation": [
      {
        "conclusion": "",
        "createdAt": "2026-11-11T19:41:17Z",
        "databaseId": 43089512598,
        "event": "push",
        "headSha": "8b4289ff0b3354633d271627580480de8170bfcd",
        "status": "queued",
        "url": "https://github.com/ayutaz/voxelshogi/actions/runs/43089512598",
        "workflowName": "CI"
      },
      {
        "conclusion": "",
        "createdAt": "2026-11-11T19:41:17Z",
        "databaseId": 43089512550,
        "event": "push",
        "headSha": "8b4289ff0b3354633d271627580480de8170bfcd",
        "status": "queued",
        "url": "https://github.com/ayutaz/voxelshogi/actions/runs/43089512550",
        "workflowName": "Security"
      }
    ],
    "manual162_fresh_read_verified": false,
    "manual162_note": "The individual manual run read did not succeed in this batch. No fresh success claim; previous pending observation remains historical.",
    "fetch_interval_seconds": 645.929049
  },
  "implementation_evidence": {
    "source_commit": "1a3f9393543c9686e59f3bfcb0aa6fdf0691b555",
    "component_commit": "68f54bc",
    "related_lightweight_tests_passed": 304,
    "new_mutants_caught": 37,
    "equivalent_not_counted": 1,
    "catalog_unique_names_and_anchors": 767,
    "tree_unchanged_by_main_merge": true,
    "scope": "Recorded lightweight fake/pure validation, not rerun as model/CUDA or native integration during this planning review."
  },
  "actual_progress": {
    "historical_development_games": 48,
    "historical_nn_queries_audited": 24579,
    "gpu_onnx_architectures": 4,
    "audited_pilot_samples": 11254,
    "new_browser_cases": 0,
    "planned_browser_cases": 8,
    "m_pilot_runs": 0,
    "planned_m_pilot_runs": 2,
    "post_training_development_games": 0,
    "planned_post_training_development_games": 48,
    "main_comparison_runs": 0,
    "planned_main_comparison_runs": 12,
    "trained_m_formats_validated_and_web_published": 0,
    "planned_trained_m_formats": 3,
    "physical_phone_secured": false
  },
  "next_execution": {
    "order": [
      "integrated browser source CI/Security admission and pilot-driver validation",
      "8 actual browser cases",
      "2 Full/Geometry pilots, CUDA/HF parity and development48",
      "freeze equal-compute 4 architectures x 3 seeds after actual cost and teacher diagnosis",
      "3 actual trained M formats, individual evaluation and identical Web bytes",
      "2 displays on same games, supported actual device cells each60min, public SHA/E2E and reproduction"
    ],
    "browser_quote_proposal": {
      "estimated_seconds": 5160,
      "maximum_seconds": 10800,
      "maximum_usd": 2.75
    },
    "pilot_quote_proposal": {
      "estimated_seconds": 11400,
      "maximum_seconds": 14400,
      "maximum_usd": 3.5,
      "updates_each": 1024,
      "batch_size": 16,
      "seed": 67003,
      "interruption_update": 384
    },
    "quotes_are_not_fresh_market_prices_or_delivery_deadlines": true,
    "twelve_run_total_time_and_cost_not_yet_established": true
  },
  "limitations": [
    "Public metadata retry returned HTTP403; no fresh site SHA or public E2E, no claim the entire site is down.",
    "No new rental, budget reservation, publication, data/model execution, final holdout query or actual device validation in this review.",
    "PR163 observations refer to the pre-update source, not approval of the upcoming documentation commit.",
    "Historical audit/learning results are not evidence of general strength improvement."
  ]
}
```


## 06:37 JST追補：統合main成功と未統合の配布実装

CIは06:32:48 JSTの取得済み結果を再利用し、10分以内の再取得は行っていない。
両providerは06:36:49 JSTに読取専用で再確認した。費用予約・作成・公開の変更は0。
以下のPR #163のHEADはこの文書更新前の観測値であり、更新後のCI成功を示すものではない。

```json
{
  "schema": "voxelshogi-resumption-planning-supplement-v3",
  "recorded_at_utc": "2026-11-11T21:38:19.957932+00:00",
  "github_observed_at_utc": "2026-11-11T21:32:48.692739+00:00",
  "ci_cached_result_reused": true,
  "ci_status_refetches_this_update": 0,
  "main_source": "8b4289ff0b3354633d271627580480de8170bfcd",
  "main_ci": {
    "id": 43089512598,
    "attempt": 2,
    "status": "completed",
    "conclusion": "success",
    "native_full_executed": true,
    "training_mutation_shards_success": 8,
    "research_worker_channel_success": true,
    "security_run": 43089512550,
    "security_conclusion": "success",
    "blocking_codeql_alerts": 0
  },
  "main_public_deployment": {
    "job_id": 130796650651,
    "conclusion": "success",
    "executed_successfully": [
      "Verify published commit",
      "Public E2E",
      "Repeat public search and camera regression without retries",
      "Audit exact public application, model and runtime files",
      "Public model E2E on the exact approved distribution"
    ],
    "scope": "Existing published application/models, not trained-M release or physical mobile validation"
  },
  "source_admitted_stages": [
    "research-browser",
    "research-corpus"
  ],
  "prs": {
    "161": {
      "observed_head": "1a3f9393543c9686e59f3bfcb0aa6fdf0691b555",
      "state": "OPEN",
      "merge_state": "BLOCKED",
      "missing_required": [
        "CI Gate"
      ],
      "pending_related": [],
      "failures": []
    },
    "163": {
      "observed_head": "ef8ec1901997299f58c91eaa9fb036f1c29b0939",
      "state": "OPEN",
      "merge_state": "BLOCKED",
      "missing_required": [
        "CI Gate",
        "CodeQL (actions)",
        "CodeQL (javascript-typescript)",
        "CodeQL (python)",
        "CodeQL (rust)",
        "Known mutation regressions",
        "Rust core coverage",
        "Web unit coverage"
      ],
      "pending_related": [],
      "failures": []
    },
    "164": {
      "observed_head": "2ebbd2ed9962dea1aeb5612ed2fc2a2851e2f3f9",
      "state": "OPEN",
      "merge_state": "CLEAN",
      "missing_required": [],
      "pending_related": [
        "Browser model inference (real WASM)"
      ],
      "failures": []
    },
    "165": {
      "observed_head": "f37c95322c3115424bfdd00fbffc3cf9fd74a71d",
      "state": "OPEN",
      "merge_state": "BLOCKED",
      "missing_required": [
        "CI Gate",
        "CodeQL (rust)",
        "Known mutation regressions",
        "Rust core coverage",
        "Web unit coverage"
      ],
      "pending_related": [
        "scope / scope",
        "CodeQL (rust)",
        "Python engine and model contracts",
        "Browser model inference (real WASM)"
      ],
      "failures": []
    }
  },
  "read_only_external_audit": {
    "checked_at_utc": "2026-11-11T21:36:49.822425+00:00",
    "read_only": true,
    "resource_mutations": 0,
    "vast": {
      "complete_inventory": true,
      "project_instances": []
    },
    "cloudrift": {
      "project_active_instances": 0,
      "scope": "Personal Initializing/Active/Deactivating project-tagged instances"
    },
    "budget": {
      "approved_total_usd": 200,
      "reservations": 36,
      "reserved_usd": 160.75,
      "remaining_unreserved_usd": 39.25
    }
  },
  "implementation_evidence": {
    "distribution": {
      "source_commit": "2ebbd2ed9962dea1aeb5612ed2fc2a2851e2f3f9",
      "related_light_tests_passed": 169,
      "new_mutants_caught": 20,
      "changed_existing_mutants_caught": 2,
      "actual_trained_m_browser_inference": 0
    },
    "conversion": {
      "source_commit": "f37c95322c3115424bfdd00fbffc3cf9fd74a71d",
      "related_light_tests_passed": 138,
      "new_mutations_caught": 37,
      "linux_native_tests_added": 2,
      "linux_native_tests_executed_on_mac": false,
      "actual_M_conversion_runs": 0
    }
  },
  "actual_progress": {
    "historical_development_games": 48,
    "historical_nn_queries_audited": 24579,
    "gpu_onnx_architectures": 4,
    "audited_pilot_samples": 11254,
    "actual_browser_cases": 0,
    "planned_browser_cases": 8,
    "actual_m_pilot_runs": 0,
    "planned_m_pilot_runs": 2,
    "actual_post_training_development_games": 0,
    "planned_post_training_development_games": 48,
    "actual_main_comparison_runs": 0,
    "planned_main_comparison_runs": 12,
    "actual_trained_m_format_publications": 0,
    "planned_trained_m_formats": 3,
    "physical_phone_secured": false
  },
  "new_resource_requests": 0,
  "new_budget_reservations": 0,
  "new_hf_publications": 0
}
```


## 2026-11-12 07:12 JST追補：実ブラウザ起動と少量学習sourceの許可

統合mainの完了済み検証と、稼働中の実測の部分観測を区別する。新しい課金予約はブラウザ3回目のUS$2.75だけ。元の失敗・旧PRの検証履歴を消さず、包含が確認できたPRは重複として閉じた。

```json
{
  "schema": "voxelshogi-resumption-running-supplement-v4",
  "recorded_at_utc": "2026-11-11T22:12:17.714014+00:00",
  "pilot_source_admission": {
    "verified": true,
    "source_commit": "1a4c4a00798d2ad62a9de5d4269eaefdb51bf55e",
    "source_tree": "ccab3372631de36348b17f1103c72a992782f525",
    "allowed_stages": [
      "research-pilot"
    ],
    "checked_at": 1794434685.067681,
    "evidence": "runs/p6/restart-implementation/integrated-pilot-ci-1794434685",
    "ci_run": 43105576755,
    "security_run": 43105576599,
    "reason": "Exact integrated main1a4 tree includes pilot driver, M reader and3format converter; actual canonical full/native/8shard/worker/Security/public checks succeeded. Actual M pilots remain0; guard/quote/owner/deadlines must be newly frozen.",
    "integrated_main_ancestor": true,
    "all_required_success": true,
    "native_full_executed": true,
    "native_job": 130808091590,
    "required_validation_conclusion": "success",
    "ci_conclusion": "success",
    "security_conclusion": "success",
    "training_mutation_shards_success": 8,
    "research_worker_channel_success": true,
    "main_blocking_codeql_alerts": 0,
    "public_deployment_success": true
  },
  "merged_implementation_pr": 165,
  "included_prs_closed": [
    161,
    162,
    164
  ],
  "publication_role_pr": 166,
  "publication_role_source": "68a766cea6a0c13668c6e93e7b85fb1fd4eae16f",
  "publication_role_light_tests": 106,
  "publication_role_new_mutants_caught": 31,
  "browser": {
    "attempt": 3,
    "instance_id": 60266373,
    "source_commit": "8b4289ff0b3354633d271627580480de8170bfcd",
    "collection_observed_at_utc": "2026-11-11T22:12:08.457810+00:00",
    "matrix_complete": false,
    "rows": [
      {
        "name": "full",
        "backend": "wasm",
        "status": "success",
        "error_message": null
      },
      {
        "name": "full",
        "backend": "webgpu",
        "status": "failed",
        "error_message": "page.evaluate: Error: research case timed out\n    at eval (eval at evaluate (:370:30), <anonymous>:3:70)"
      },
      {
        "name": "axial",
        "backend": "wasm",
        "status": "failed",
        "error_message": "page.evaluate: Error: research case timed out\n    at eval (eval at evaluate (:370:30), <anonymous>:3:70)"
      },
      {
        "name": "axial",
        "backend": "webgpu",
        "status": "failed",
        "error_message": "page.evaluate: Error: research case timed out\n    at eval (eval at evaluate (:370:30), <anonymous>:3:70)"
      },
      {
        "name": "geometry",
        "backend": "wasm",
        "status": "success",
        "error_message": null
      },
      {
        "name": "geometry",
        "backend": "webgpu",
        "status": "failed",
        "error_message": "page.evaluate: Error: research case timed out\n    at eval (eval at evaluate (:370:30), <anonymous>:3:70)"
      },
      {
        "name": "cnn",
        "backend": "wasm",
        "status": "running",
        "error_message": null
      }
    ],
    "scope": "Partial running observations, not a validated/published result or learned-M inference"
  },
  "budget": {
    "approved_total_usd": 200,
    "reservations": 37,
    "reserved_usd": 163.5,
    "remaining_unreserved_usd": 36.5,
    "new_reservation_browser3_usd": 2.75,
    "not_actual_invoice_or_provider_credit": true
  },
  "actual_M_pilot_runs": 0,
  "actual_post_training_games": 0,
  "actual_main12_runs": 0,
  "actual_M_inference_publications": 0
}
```
