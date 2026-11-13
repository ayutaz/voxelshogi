# 公開確認の固定記録

生のJSONは検証元の実行記録・納品物へ保持し、文書では同じ確認値を掲載する。

```json
{
  "schema": 1,
  "kind": "voxelshogi-demo-video",
  "appCommit": "c878c6d08572caa2da2d0cf654caa85ba7dfd501",
  "ruleset": "voxelshogi-standard-v1",
  "candidate": false,
  "agents": [
    "easy",
    "easy"
  ],
  "hookPly": 3,
  "hookMove": "797786",
  "fullRecordReplayedByRust": true,
  "fullDecodeValidated": true,
  "sourceRate": 25,
  "firstContentFrame": 218,
  "outputFps": 30,
  "performanceMeasurement": false,
  "soundRequired": false,
  "recordingScriptSha256": "6c2ae2af8f08f5d96eb91f29770bb86d0011106e34a5f6f51a0161a818a2b8a7",
  "webLockSha256": "c09f59c577fa6758f4c55ae62875ec5492afe2c1b0aabee4c1866ee12723dafc",
  "ffmpeg": "ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023 the FFmpeg developers",
  "japaneseFontSha256": "faa5f3656a78b2e2d450d27fe8382c778bc2b6bb5ea29c986664a6a435056ceb",
  "files": [
    {
      "path": "demo-main.mp4",
      "bytes": 1218044,
      "sha256": "f99b158279fb3fc0bee2f6486308a6c4a69f0ce08cab8d243e7c8c18e02b40a3"
    },
    {
      "path": "hook-a.mp4",
      "bytes": 419228,
      "sha256": "fd88e1cf352526091d3efb56f9c4415fbcef2e14b23e398a25f6178013e76f50"
    },
    {
      "path": "hook-b.mp4",
      "bytes": 494377,
      "sha256": "da630cd072452326d998c0e44a8f1e7636ba8f5e9c3bfa1968a532d553c2c4df"
    },
    {
      "path": "poster.png",
      "bytes": 602845,
      "sha256": "b5f2aa1ad8508b55375d836668edbdad7e0f51b92df345484ab67b1fc423e250"
    },
    {
      "path": "ogp.png",
      "bytes": 279681,
      "sha256": "c0c9df89ee96555a2212f0054c70197b68efd4ae4af35102e43202ebe9c3dff0"
    },
    {
      "path": "contact-sheet.png",
      "bytes": 592551,
      "sha256": "8e8849ac90f928aa82c36c900d851fe53915431cf6bd7cd85fa070620bdd6aee"
    },
    {
      "path": "source-ai-record.json",
      "bytes": 8060,
      "sha256": "4ab39f58ead6168f25f7a39e0fdb9dbaafc9b503eb7a362e1d08619c8d7a6fd6"
    },
    {
      "path": "captions.json",
      "bytes": 601,
      "sha256": "552b612bc3339a25aac40f685a175fbc7d6411f6f55aa657c5f44430fbc1cd20"
    }
  ],
  "run": "https://github.com/ayutaz/voxelshogi/actions/runs/43493747343",
  "deliveryReview": {
    "at": "2026-11-13T19:50:30.874Z",
    "allFileHashesVerified": true,
    "metadataReadOnlyOnMac": true,
    "probes": {
      "demo-main.mp4": {
        "programs": [],
        "stream_groups": [],
        "streams": [
          {
            "codec_name": "h264",
            "codec_type": "video",
            "width": 1080,
            "height": 1350,
            "pix_fmt": "yuv420p",
            "avg_frame_rate": "30/1",
            "nb_frames": "450"
          }
        ],
        "format": {
          "duration": "15.000000"
        }
      },
      "hook-a.mp4": {
        "programs": [],
        "stream_groups": [],
        "streams": [
          {
            "codec_name": "h264",
            "codec_type": "video",
            "width": 1080,
            "height": 1350,
            "pix_fmt": "yuv420p",
            "avg_frame_rate": "30/1",
            "nb_frames": "90"
          }
        ],
        "format": {
          "duration": "3.000000"
        }
      },
      "hook-b.mp4": {
        "programs": [],
        "stream_groups": [],
        "streams": [
          {
            "codec_name": "h264",
            "codec_type": "video",
            "width": 1080,
            "height": 1350,
            "pix_fmt": "yuv420p",
            "avg_frame_rate": "30/1",
            "nb_frames": "90"
          }
        ],
        "format": {
          "duration": "3.000000"
        }
      }
    },
    "contactSheetViewed": true,
    "captionOverlap": false,
    "hookChoice": "A",
    "publicUiMatchPending": false,
    "matchedPublicCommit": "c878c6d08572caa2da2d0cf654caa85ba7dfd501",
    "matchedAt": "2026-11-13T20:03:01.561Z"
  }
}
```
