# 申請不要Sと公開版一致の最終動画

2026-11-15 JST。Linuxの公開サイト対戦5件・全37ファイル匿名照合、実Worker配信と最終31ファイルのhashを確認した。21画像・ポスター／OGP・3形式の390px画面を目視し、見切れ・字幕重なり・切替途中のCanvasなし。

自動framingのvisualReviewComplete=falseは原本のまま保持し、担当側の目視をdeliveryReviewへ別記する。全450フレームの目視・実スマホ・X上の再生や拡散実績ではない。完成物だけをMacのruns/public-s-release/final-7b364c9/video/へ保存し、モデル・checkpoint・未編集録画は取得していない。artifactは7日保持、完成MP4は同ローカル先にも保持する。

```json
{
  "applicationCommit": "7b364c9ad693c35d00ca8edf1c428f19658b8d04",
  "cloudflareVersion": "0de0b3ef-f816-4dea-bdf5-5ca65c15fd37",
  "mainCi": 43609887815,
  "security": 43609887833,
  "publicSRun": 43611290056,
  "videoRun": 43611290885,
  "artifacts": {
    "production": {
      "id": 14120282468,
      "sha256": "985a4ebc5b7b2548689944d3af2f663c3f6158ca0480f27197e2dc6d9024c3af"
    },
    "publicS": {
      "id": 14120571234,
      "sha256": "e755d0b21d03b94e3b8332dc84104e8ba2a871a4ccf3175bb3b9b29e3a96668d"
    },
    "video": {
      "id": 14120013449,
      "sha256": "c1368e2d1114d01a78885557df1d434ed116e272c9ac2b8dc45b086cb1036d97"
    }
  },
  "publicProofSha256": "d8f80391dc6e1ab34e6e1edf9e7ae3a3d9db7c5550c103716d0a9736b4861173",
  "publicGateway": {
    "schema": 1,
    "kind": "public-s-deployed-gateway",
    "revision": "6ab524574d36536348dbe323a2b779b9cebe37ed",
    "anonymous": true,
    "files": [
      {
        "path": "manifest.json",
        "bytes": 28477,
        "sha256": "9ea2685c1d1cd8529292dbf6a70d4e692bd639bc3425215a8bd5c2b9a888afae"
      },
      {
        "path": "README.md",
        "bytes": 3035,
        "sha256": "3d787303f56b551876ba3cd4a83624b2658b89d9a58eec804dad132583987ce2"
      },
      {
        "path": "LICENSE",
        "bytes": 11358,
        "sha256": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
      }
    ],
    "verified": true,
    "gameWrites": 0
  },
  "videoReceiptSha256": "336e3066153ad0ae52b79f5848c4ecd674a38b31293cf32cab8ff5b5f7ca0f8e",
  "videoReceipt": {
    "schema": 1,
    "kind": "voxelshogi-demo-video",
    "appCommit": "7b364c9ad693c35d00ca8edf1c428f19658b8d04",
    "ruleset": "voxelshogi-standard-v1",
    "candidate": false,
    "captureOrigin": "https://voxelshogi.yousan-apps.workers.dev",
    "agents": [
      "easy",
      "easy"
    ],
    "hookPly": 14,
    "hookMove": "415524",
    "humanModel": {
      "sourceId": "public-1",
      "repo": "voxelshogi/voxelshogi-transformer-s",
      "revision": "6ab524574d36536348dbe323a2b779b9cebe37ed",
      "sourceCommit": "5415899c445b95c5ce19d3a79c1ebb55f48bf642",
      "license": "Apache-2.0",
      "selection": {
        "modelId": "voxelshogi-transformer-s-m6-314159-v1",
        "packageHash": "9ea2685c1d1cd8529292dbf6a70d4e692bd639bc3425215a8bd5c2b9a888afae",
        "precision": "int8",
        "backend": "wasm"
      }
    },
    "humanModelReplyVerified": true,
    "fullRecordReplayedByRust": true,
    "fullDecodeValidated": true,
    "recordedBoundsVerified": true,
    "sourceRate": 25,
    "firstContentFrame": 965,
    "outputFps": 30,
    "performanceMeasurement": false,
    "soundRequired": false,
    "recordingScriptSha256": "cd363ee08920d0ffd660a13f8b3f571a75f73c46c43a1e129fcb3e3f51deadef",
    "webLockSha256": "c09f59c577fa6758f4c55ae62875ec5492afe2c1b0aabee4c1866ee12723dafc",
    "ffmpeg": "ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023 the FFmpeg developers",
    "japaneseFontSha256": "faa5f3656a78b2e2d450d27fe8382c778bc2b6bb5ea29c986664a6a435056ceb",
    "files": [
      {
        "path": "demo-main.mp4",
        "bytes": 1733162,
        "sha256": "da0279fa9fe0fc208881c9e05e6ac12d3bb86ade1fbbbe9c9b793aabc6d87e04"
      },
      {
        "path": "hook-a.mp4",
        "bytes": 917312,
        "sha256": "5dde8830eac92a7b200e60d9fbbc1c48abdc3db75d10ab2610f7f6c209d07324"
      },
      {
        "path": "hook-b.mp4",
        "bytes": 936488,
        "sha256": "db0655886d6551f7ce250b135db5284460656a54ffea1b18a3094a04718eb60a"
      },
      {
        "path": "poster.png",
        "bytes": 765230,
        "sha256": "8e7bc684d0dfa55b5918daeb5e931886785816e9167484a193940979d8a698b1"
      },
      {
        "path": "ogp.png",
        "bytes": 324035,
        "sha256": "648d147b14bf45f90642fc603a31cb918e4a9ac905df84075df53e7ee16534b1"
      },
      {
        "path": "contact-sheet.png",
        "bytes": 659872,
        "sha256": "b4d4827729aadde9b06af88c80c53b8c4a49104cbe61f7aeffbe7bc84b64b826"
      },
      {
        "path": "source-ai-record.json",
        "bytes": 2842,
        "sha256": "0eaf8945a9a69276c5ac135092a895a67773ec21768ff49049dc134d01ff4d1e"
      },
      {
        "path": "source-human-record.json",
        "bytes": 6863,
        "sha256": "1bbd5e51c8d158a6a54741985f08ce902461eadaf0457e551c29bc2be291442b"
      },
      {
        "path": "captions.json",
        "bytes": 703,
        "sha256": "c82912e7d3813272b128da83dc9c435674f6d9645cdbb4d20910921658e26f47"
      },
      {
        "path": "framing.json",
        "bytes": 16492,
        "sha256": "8b56b0c48717dcf09a644a7877648f228df97586838c0851431b5f0258a2f663"
      },
      {
        "path": "review-main-0.png",
        "bytes": 765230,
        "sha256": "8e7bc684d0dfa55b5918daeb5e931886785816e9167484a193940979d8a698b1"
      },
      {
        "path": "review-main-0-4.png",
        "bytes": 853137,
        "sha256": "b04851c941f1a4eedd5a097d3626da2c76bc7b58663e1d18c0a7d06388838330"
      },
      {
        "path": "review-main-0-7.png",
        "bytes": 988171,
        "sha256": "9e41ad50b72d8bfd097ad3f73efacf879987ee3e80636a0d991850b15dd23ac1"
      },
      {
        "path": "review-main-1-5.png",
        "bytes": 1067645,
        "sha256": "4c6acbac01f9f13024f07c86766e740f32f9eca1d3981a8e25a7a4dc5847b694"
      },
      {
        "path": "review-main-2-9.png",
        "bytes": 1044043,
        "sha256": "3850703ef08caaf7a13d1fcffd34924e69bb04c340dc5be33d8d648ab9b1063d"
      },
      {
        "path": "review-main-3.png",
        "bytes": 1043549,
        "sha256": "6dcbe6a8a393f1f09cd3a4158c487a63e59a8da490291bebdac1b7d3dbc2f48d"
      },
      {
        "path": "review-main-3-2.png",
        "bytes": 931044,
        "sha256": "8e0fa604f43593fd94f6b2765db224a6639a55c2870a7e827ade9a00ee294c6b"
      },
      {
        "path": "review-main-6-9.png",
        "bytes": 885611,
        "sha256": "d7198d1a61c22e125da8efcc0858ebbbbc73e065ec3054d7de96419148a0ea0e"
      },
      {
        "path": "review-main-7.png",
        "bytes": 654327,
        "sha256": "319055b7c5906b4f954fb2ec504bff836881a3f1d3750b0751880b1817c90a18"
      },
      {
        "path": "review-main-7-2.png",
        "bytes": 654043,
        "sha256": "be4ced5def2800ae9d72bb2fc3dce6637a62ea80ad796960e7a57187d5e66c3d"
      },
      {
        "path": "review-main-7-5.png",
        "bytes": 647736,
        "sha256": "aa3b9e39a50caefa3c0a090296958d0e43e91fd36de16bae7ea8985c67c8a60c"
      },
      {
        "path": "review-main-10-8.png",
        "bytes": 659491,
        "sha256": "ce0ecf0acb4cf8e08a8ec5a8bad3d6034255ae2479d070c917b7d8d4143e9f7f"
      },
      {
        "path": "review-main-11.png",
        "bytes": 473277,
        "sha256": "3759aad41ed8b483f6f72c2a4cfa8fc8f59d8115a2ee083e6fd363b9711bd894"
      },
      {
        "path": "review-main-11-2.png",
        "bytes": 474295,
        "sha256": "cf9ab2771df2b57544c4c3f2b96005ae94c9486c32f4625dee698ff3abb8521f"
      },
      {
        "path": "review-main-14-9.png",
        "bytes": 470823,
        "sha256": "f722a3dd971a6e4c6d16fea4e6298ba79f8068d123ec78e5a96dd55a8ddde2fe"
      },
      {
        "path": "review-a-0.png",
        "bytes": 765230,
        "sha256": "8e7bc684d0dfa55b5918daeb5e931886785816e9167484a193940979d8a698b1"
      },
      {
        "path": "review-a-1-5.png",
        "bytes": 1067645,
        "sha256": "4c6acbac01f9f13024f07c86766e740f32f9eca1d3981a8e25a7a4dc5847b694"
      },
      {
        "path": "review-a-2-9.png",
        "bytes": 1036902,
        "sha256": "fbfcadd5018a23c1a8202fdda034e8e8939ec5b37f37c6e75590e591fc18b05d"
      },
      {
        "path": "review-b-0.png",
        "bytes": 762179,
        "sha256": "450b8cd07e74ad320358e6aa4c77945fc54fe4e7cf5c1ed08d2902a2845af907"
      },
      {
        "path": "review-b-1-5.png",
        "bytes": 1096671,
        "sha256": "6e5aff9a1ff42ba3604242cc6847da37765f105821782865d2590462a6c77469"
      },
      {
        "path": "review-b-2-9.png",
        "bytes": 1065522,
        "sha256": "e6d62b6b3faf139513bf7278e47443ca311b208473dd26838379e5bf2508f520"
      }
    ]
  },
  "deliveryReview": {
    "schema": 1,
    "applicationCommit": "7b364c9ad693c35d00ca8edf1c428f19658b8d04",
    "videoRun": 43611290885,
    "receiptSha256": "336e3066153ad0ae52b79f5848c4ecd674a38b31293cf32cab8ff5b5f7ca0f8e",
    "visualReviewComplete": true,
    "reviewedImages": [
      {
        "path": "review-main-0.png",
        "bytes": 765230,
        "sha256": "8e7bc684d0dfa55b5918daeb5e931886785816e9167484a193940979d8a698b1"
      },
      {
        "path": "review-main-0-4.png",
        "bytes": 853137,
        "sha256": "b04851c941f1a4eedd5a097d3626da2c76bc7b58663e1d18c0a7d06388838330"
      },
      {
        "path": "review-main-0-7.png",
        "bytes": 988171,
        "sha256": "9e41ad50b72d8bfd097ad3f73efacf879987ee3e80636a0d991850b15dd23ac1"
      },
      {
        "path": "review-main-1-5.png",
        "bytes": 1067645,
        "sha256": "4c6acbac01f9f13024f07c86766e740f32f9eca1d3981a8e25a7a4dc5847b694"
      },
      {
        "path": "review-main-2-9.png",
        "bytes": 1044043,
        "sha256": "3850703ef08caaf7a13d1fcffd34924e69bb04c340dc5be33d8d648ab9b1063d"
      },
      {
        "path": "review-main-3.png",
        "bytes": 1043549,
        "sha256": "6dcbe6a8a393f1f09cd3a4158c487a63e59a8da490291bebdac1b7d3dbc2f48d"
      },
      {
        "path": "review-main-3-2.png",
        "bytes": 931044,
        "sha256": "8e0fa604f43593fd94f6b2765db224a6639a55c2870a7e827ade9a00ee294c6b"
      },
      {
        "path": "review-main-6-9.png",
        "bytes": 885611,
        "sha256": "d7198d1a61c22e125da8efcc0858ebbbbc73e065ec3054d7de96419148a0ea0e"
      },
      {
        "path": "review-main-7.png",
        "bytes": 654327,
        "sha256": "319055b7c5906b4f954fb2ec504bff836881a3f1d3750b0751880b1817c90a18"
      },
      {
        "path": "review-main-7-2.png",
        "bytes": 654043,
        "sha256": "be4ced5def2800ae9d72bb2fc3dce6637a62ea80ad796960e7a57187d5e66c3d"
      },
      {
        "path": "review-main-7-5.png",
        "bytes": 647736,
        "sha256": "aa3b9e39a50caefa3c0a090296958d0e43e91fd36de16bae7ea8985c67c8a60c"
      },
      {
        "path": "review-main-10-8.png",
        "bytes": 659491,
        "sha256": "ce0ecf0acb4cf8e08a8ec5a8bad3d6034255ae2479d070c917b7d8d4143e9f7f"
      },
      {
        "path": "review-main-11.png",
        "bytes": 473277,
        "sha256": "3759aad41ed8b483f6f72c2a4cfa8fc8f59d8115a2ee083e6fd363b9711bd894"
      },
      {
        "path": "review-main-11-2.png",
        "bytes": 474295,
        "sha256": "cf9ab2771df2b57544c4c3f2b96005ae94c9486c32f4625dee698ff3abb8521f"
      },
      {
        "path": "review-main-14-9.png",
        "bytes": 470823,
        "sha256": "f722a3dd971a6e4c6d16fea4e6298ba79f8068d123ec78e5a96dd55a8ddde2fe"
      },
      {
        "path": "review-a-0.png",
        "bytes": 765230,
        "sha256": "8e7bc684d0dfa55b5918daeb5e931886785816e9167484a193940979d8a698b1"
      },
      {
        "path": "review-a-1-5.png",
        "bytes": 1067645,
        "sha256": "4c6acbac01f9f13024f07c86766e740f32f9eca1d3981a8e25a7a4dc5847b694"
      },
      {
        "path": "review-a-2-9.png",
        "bytes": 1036902,
        "sha256": "fbfcadd5018a23c1a8202fdda034e8e8939ec5b37f37c6e75590e591fc18b05d"
      },
      {
        "path": "review-b-0.png",
        "bytes": 762179,
        "sha256": "450b8cd07e74ad320358e6aa4c77945fc54fe4e7cf5c1ed08d2902a2845af907"
      },
      {
        "path": "review-b-1-5.png",
        "bytes": 1096671,
        "sha256": "6e5aff9a1ff42ba3604242cc6847da37765f105821782865d2590462a6c77469"
      },
      {
        "path": "review-b-2-9.png",
        "bytes": 1065522,
        "sha256": "e6d62b6b3faf139513bf7278e47443ca311b208473dd26838379e5bf2508f520"
      }
    ],
    "posterAndOgpReviewed": true,
    "publicModelScreensReviewed": [
      "fp32",
      "fp16",
      "int8"
    ],
    "findings": "21画像で盤・字幕・URL・2D盤・操作欄の見切れ／重なり、切替途中のCanvasなし。3形式の390x844画面も確認。",
    "scope": "全450フレームの目視、実スマホ、X上の再生や拡散実績は未確認。",
    "reviewedAt": "2026-11-14T15:51:34.949Z"
  }
}
```
