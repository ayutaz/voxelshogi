# 公開検証の固定記録

公開run・実配信・画像を確認した値。最終PC操作は撮影の承認待ちで、L6全完了にはしていない。

```json
{
  "schema": 1,
  "kind": "launch-public-validation",
  "at": "2026-11-13T20:16:28.024Z",
  "appCommit": "c878c6d08572caa2da2d0cf654caa85ba7dfd501",
  "publicUrl": "https://voxelshogi.yousan-apps.workers.dev",
  "ci": {
    "url": "https://github.com/ayutaz/voxelshogi/actions/runs/43493744095",
    "conclusion": "success",
    "attempt": 2,
    "prepublication": {
      "webUnit": 498,
      "ordinaryE2E": 33,
      "modelE2E": 6,
      "cameraRepeats": 3,
      "boardPositionTolerancePx": 0.5
    },
    "public": {
      "ordinaryE2E": 33,
      "modelE2E": 6,
      "cameraRepeats": 3,
      "retries": 0
    },
    "firstAttemptFailureRetained": true
  },
  "deployment": {
    "at": "2026-11-13T20:14:22.376Z",
    "build": {
      "http": 200,
      "type": "application/json",
      "commit": "c878c6d08572caa2da2d0cf654caa85ba7dfd501"
    },
    "collection": {
      "http": 200,
      "type": "application/json",
      "json": {
        "enabled": true,
        "consent": "game-research-v1",
        "retentionDays": 30,
        "maxBytes": 262144,
        "privacyPath": "/privacy.html"
      }
    },
    "deployment": {
      "id": "52f404f3-8998-4317-8e8e-4c98633e1b39",
      "source": "wrangler",
      "strategy": "percentage",
      "versions": [
        {
          "version_id": "fcf35534-5e33-4ec6-a214-4e68389befd4",
          "percentage": 100
        }
      ],
      "created_on": "2026-11-13T20:05:50.694281Z"
    },
    "version": "fcf35534-5e33-4ec6-a214-4e68389befd4",
    "sourceCommit": "commit:c878c6d08572caa2da2d0cf654caa85ba7dfd501",
    "bindings": [
      {
        "name": "ASSETS",
        "type": "assets"
      },
      {
        "name": "GAME_COLLECTION_ENABLED",
        "type": "plain_text"
      },
      {
        "name": "GAMES",
        "type": "d1",
        "databaseId": "5b4bfe35-773b-4c08-84f4-8d76f8f939b9"
      }
    ],
    "schedules": {
      "schedules": [
        {
          "cron": "17 * * * *",
          "created_on": "2026-11-13T18:51:07.14144Z",
          "modified_on": "2026-11-13T18:51:07.14144Z"
        }
      ]
    }
  },
  "distributionAudit": {
    "modelId": "voxelshogi-transformer-s-untrained-314159-v1",
    "sameOrigin": true,
    "verifiedAt": "2026-11-13T20:07:53.737Z",
    "verifiedRecords": 57,
    "modelManifestSha256": "c125f2b6712dcf429e99318bf41d47363b85f61c8cc0599a17c107658f4431de"
  },
  "sharing": {
    "http": 200,
    "mime": "image/png",
    "bytes": 283862,
    "sha256": "ad66dde8cfa64ac7ede75abdf7f3fa5b9349baae81aae4b8d4c7424e8368bb71",
    "width": 1200,
    "height": 630
  },
  "layoutImages": [
    {
      "viewport": "390x844",
      "fullPage": true,
      "pngWidth": 390,
      "pngHeight": 2853,
      "bytes": 239544,
      "sha256": "36e89d449e9d86d81a8ab1ab4cb49cebc78b24a1530903586e106c1d2c08c8fb",
      "viewed": true
    },
    {
      "viewport": "768x1024",
      "fullPage": true,
      "pngWidth": 768,
      "pngHeight": 2707,
      "bytes": 249032,
      "sha256": "1d6ee5ce785469e4f9cefcd6c02275487431f269bb9007c409dc3f94b8879b70",
      "viewed": true
    },
    {
      "viewport": "1440x900",
      "fullPage": true,
      "pngWidth": 1440,
      "pngHeight": 900,
      "bytes": 190356,
      "sha256": "c122918b2dd6413ab3d4b9654adb1f92e24b0b3e0fc5b6196fc8bfdb438a824d",
      "viewed": true
    }
  ],
  "nativeFinalReview": {
    "status": "pending-explicit-screenshot-approval",
    "baselineCommit": "2d1d4c93fd0d3138f6f7217402e493f9f5aaf664",
    "finalInitialScreenAxSeen": true,
    "scope": "initial screen only on final commit; full actual interaction proved on baseline; final delta check pending"
  },
  "physicalPhone": {
    "available": false,
    "verified": false
  },
  "scope": {
    "researchPaused": true,
    "xPosted": false,
    "gpuUsed": false
  }
}
```
