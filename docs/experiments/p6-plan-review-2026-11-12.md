# 2026-11-12 09:00 JST 現況調査と計画の根拠

小さいAPI結果と実行metadataを照合した記録。秘密情報・実データ・checkpointは含まない。
CI取得は前回から10分以上空けた一括取得。完了済みsourceのCI証拠を再利用し、新mainの深い検証と区別する。
PR169の取り込みは既存承認に基づく通常squash merge。PR170の成功は取得時baseに限り、最新mainで再検証してから取り込む。
公開build読取のHTTPErrorをサイト全体の停止や公開E2E失敗と同一視しない。今回の公開状態は未検証とする。

```json
{
  "schema": "voxelshogi-current-plan-review-v1",
  "checked_at_utc": "2026-11-11T23:58:54.122955+00:00",
  "scope": "Read-only review plus separately approved merge169; no new rental/training/upload",
  "audit": {
    "checked_at": 1794441534.122955,
    "main": {
      "sha": "6468b94eec566e43b13818779276a9704e8acc0d"
    },
    "resources": {
      "checked_at": 1794441535.7736351,
      "vast_project_instances": [],
      "vast_inventory_complete": true,
      "cloudrift_project_active_instances": 0,
      "resource_mutations": 0
    },
    "public-build": {
      "unverified": true,
      "error_type": "HTTPError"
    },
    "prs": [
      {
        "number": 170,
        "head": "b96664d001234d779300a265a7abeec922a04949",
        "base": "6468b94eec566e43b13818779276a9704e8acc0d",
        "merge_state": "CLEAN",
        "missing_required_success": [],
        "pending": [],
        "failed": []
      },
      {
        "number": 169,
        "head": "5b037f85b3b096a1125eb36a9553b7bb4b5a6d14",
        "base": "6468b94eec566e43b13818779276a9704e8acc0d",
        "merge_state": "CLEAN",
        "missing_required_success": [],
        "pending": [],
        "failed": []
      },
      {
        "number": 158,
        "head": "a8e36c587a2647c6ea62840c7be9a1b47e1b175b",
        "base": "8d27a32d7a560f67a23b5e5fdfa348fcc0e2ec1c",
        "merge_state": "UNKNOWN",
        "missing_required_success": [],
        "pending": [],
        "failed": []
      },
      {
        "number": 157,
        "head": "af5e17ba88e74cf3137e40ab6e0fc0fe725cd9c2",
        "base": "8d27a32d7a560f67a23b5e5fdfa348fcc0e2ec1c",
        "merge_state": "UNKNOWN",
        "missing_required_success": [],
        "pending": [],
        "failed": []
      },
      {
        "number": 156,
        "head": "86fb5f5fc3040cbef3d1ac7af2cd76a16818f73f",
        "base": "8d27a32d7a560f67a23b5e5fdfa348fcc0e2ec1c",
        "merge_state": "UNKNOWN",
        "missing_required_success": [],
        "pending": [],
        "failed": []
      },
      {
        "number": 155,
        "head": "a310d420746efb2c924a841b351d909b4d99465b",
        "base": "8d27a32d7a560f67a23b5e5fdfa348fcc0e2ec1c",
        "merge_state": "UNKNOWN",
        "missing_required_success": [
          "CI Gate"
        ],
        "pending": [],
        "failed": [
          "Web (wasm, unit, build, e2e)",
          "CI Gate"
        ]
      },
      {
        "number": 95,
        "head": "37e90b93111f909a2a8559cda91f52f2d1f2c2cf",
        "base": "327c8e346cf35b5419eb8a197e5d21e270eda879",
        "merge_state": "UNKNOWN",
        "missing_required_success": [],
        "pending": [],
        "failed": []
      }
    ],
    "pr169-blocking-alerts": 0,
    "pr170-blocking-alerts": 0,
    "pilot2-guard": {
      "databaseId": 43120027697,
      "status": "in_progress",
      "conclusion": ""
    }
  },
  "main_after_approved_merge": "91a9f282c3d0f605dcd846f7bfe0e181d7ef72ff",
  "new_main_deep_validation": "not yet verified",
  "reused_terminal_source_admission": {
    "verified": true,
    "source_commit": "6468b94eec566e43b13818779276a9704e8acc0d",
    "source_tree": "a8ca7873350b4a9100c435af7b7b7ea6fa45ffa7",
    "allowed_stages": [
      "research-pilot"
    ],
    "checked_at": 1794440437.486239,
    "evidence": "runs/p6/pilot2-admission-1794440437",
    "ci_conclusion": "success",
    "security_conclusion": "success",
    "required_validation_conclusion": "success",
    "all_required_success": true,
    "native_full_executed": true,
    "native_job": 130854440608,
    "training_mutation_shards_success": 8,
    "research_worker_channel_success": true,
    "main_blocking_codeql_alerts": 0,
    "public_deployment_success": true,
    "ci_run": 43118999898,
    "security_run": 43119000330
  },
  "budget": {
    "approved_total_usd": 200,
    "reservations": 39,
    "reserved_total_usd": 170.5,
    "remaining_unreserved_usd": 29.5,
    "phase6_limit_usd": 44,
    "phase6_reserved_usd": 14.5,
    "scope": "Conservative reservations; not provider credit or invoiced spend"
  },
  "scientific_completion": {
    "pilot_runs": 0,
    "pilot_goal": 2,
    "pilot_development_games": 0,
    "pilot_development_goal": 48,
    "main_runs": 0,
    "main_goal": 12,
    "published_m_formats": 0,
    "published_m_formats_goal": 3,
    "browser_wasm_success": 3,
    "browser_webgpu_success": 0
  },
  "pilot2": {
    "source": "6468b94eec566e43b13818779276a9704e8acc0d",
    "offer_id": 60100138,
    "create_result": "HTTP400",
    "raw_error_body_preserved": false,
    "rent_response_present": false,
    "instance_id": null,
    "learning_started": false,
    "reservation_retained_usd": 3.5,
    "exact_label_instances": [],
    "canonical_termination_complete": false,
    "note": "No confirmed identity exists. Live complete inventory is the absence evidence; no fabricated deletion acknowledgment or terminal success."
  }
}
```
