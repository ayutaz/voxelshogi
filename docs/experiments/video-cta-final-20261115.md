# 最後の字幕を簡素化した動画の固定記録

2026-11-15 JST。[修正内容と納品先](../VIDEO_CTA_FIX.md)。Linux receiptは画像目視前の`visualReviewComplete: false`を原本どおり保持し、以下の`visualReview`が同じhashの7画像の後続目視記録である。

```json
{
  "schema": 1,
  "kind": "voxelshogi-video-cta-final-review",
  "run": 43663011178,
  "artifact": {
    "id": 14140479064,
    "sha256": "e949f29a8b36f3e88c54799d97e7f6fcbacea4765651a0a27f8a791027d8448d"
  },
  "linuxReceipt": {
    "schema": 1,
    "kind": "voxelshogi-closing-caption-revision",
    "editCommit": "9c3ea7ddb739daf78095937b2ba5a51afd954c4f",
    "applicationCommit": "7b364c9ad693c35d00ca8edf1c428f19658b8d04",
    "sourceRun": 43620484463,
    "sourceSha256": "3ce3687d080040ca24c50d40d4914ac40c75bb7596ec4b31bcde560a78cb0cfc",
    "removed": "／申請・ログイン不要",
    "replacementNote": "学習済みS・INT8（重み）",
    "editedSeconds": [
      11,
      15
    ],
    "editedRectangle": {
      "x": 0,
      "y": 1240,
      "width": 1080,
      "height": 90
    },
    "audioPacketsUnchanged": true,
    "audioPacketHash": "SHA256=5e10f77546c76149d2065fc21c65e07f3e26fb2a030c4d1f40b6e04966af756f",
    "videoReencoded": true,
    "gameRerecorded": false,
    "outsideCaptionSsim": 0.99903,
    "openingSsim": 0.998772,
    "closingCaptionSsim": 0.849829,
    "fullDecodeValidated": true,
    "visualReviewComplete": false,
    "japaneseFontSha256": "faa5f3656a78b2e2d450d27fe8382c778bc2b6bb5ea29c986664a6a435056ceb",
    "files": [
      {
        "path": "demo-main-bgm.mp4",
        "bytes": 3675160,
        "sha256": "f54d6dcb10fcda39beacd8b01a606c3e27272e4c1ade5503965ee5c1c2f54c3c"
      },
      {
        "path": "review-0.png",
        "bytes": 746802,
        "sha256": "d3af39fb2b60b26ed470ed07e4175ca8ce5946fd8efe2e4d5227e4dcc918bc54"
      },
      {
        "path": "review-3.png",
        "bytes": 1060283,
        "sha256": "d3c5304239f2dc50efa183fae3a5f040e6e80c76ad5c71390079f28817989178"
      },
      {
        "path": "review-10-8.png",
        "bytes": 642696,
        "sha256": "06de1d2f1f4dbfaf81407ead58f1b37063d99273a4665ed07d86bfe05166d69f"
      },
      {
        "path": "review-10-96.png",
        "bytes": 643019,
        "sha256": "2389d0a77e24f6304e364c23857e02de5e35e351c3d3e643416e2a829020f07b"
      },
      {
        "path": "review-11.png",
        "bytes": 443162,
        "sha256": "5370e0839f59c72a5ff28aac3a412355750eb2d0ba2f451715eab2809578345e"
      },
      {
        "path": "review-11-2.png",
        "bytes": 444672,
        "sha256": "80a7eb059cdbacfcfb60bc5c9bc959bda1621ef04ca197ebf6a5a0a8ffe74d1b"
      },
      {
        "path": "review-14-9.png",
        "bytes": 440111,
        "sha256": "738b3504e656a0df28d00d0068406ca616bfb8909f068419057d8d07286c2b94"
      }
    ]
  },
  "visualReview": {
    "complete": true,
    "reviewer": "Codex",
    "frames": [
      {
        "path": "review-0.png",
        "sha256": "d3af39fb2b60b26ed470ed07e4175ca8ce5946fd8efe2e4d5227e4dcc918bc54"
      },
      {
        "path": "review-3.png",
        "sha256": "d3c5304239f2dc50efa183fae3a5f040e6e80c76ad5c71390079f28817989178"
      },
      {
        "path": "review-10-8.png",
        "sha256": "06de1d2f1f4dbfaf81407ead58f1b37063d99273a4665ed07d86bfe05166d69f"
      },
      {
        "path": "review-10-96.png",
        "sha256": "2389d0a77e24f6304e364c23857e02de5e35e351c3d3e643416e2a829020f07b"
      },
      {
        "path": "review-11.png",
        "sha256": "5370e0839f59c72a5ff28aac3a412355750eb2d0ba2f451715eab2809578345e"
      },
      {
        "path": "review-11-2.png",
        "sha256": "80a7eb059cdbacfcfb60bc5c9bc959bda1621ef04ca197ebf6a5a0a8ffe74d1b"
      },
      {
        "path": "review-14-9.png",
        "sha256": "738b3504e656a0df28d00d0068406ca616bfb8909f068419057d8d07286c2b94"
      }
    ],
    "findings": [
      "Opening board and controls remain visible",
      "10.96s preceding shot and 11s closing shot are settled",
      "Application/login wording absent at 11, 11.2 and 14.9 seconds",
      "Retained model label, URL and title are readable, without clipping or a visible edit-band seam"
    ]
  }
}
```
