# 公開確認の固定記録

生のJSONは検証元の実行記録・納品物へ保持し、文書では同じ確認値を掲載する。

```json
{
  "schema": 1,
  "kind": "voxelshogi-demo-video",
  "appCommit": "2d1d4c93fd0d3138f6f7217402e493f9f5aaf664",
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
  "firstContentFrame": 257,
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
      "bytes": 1398299,
      "sha256": "67a3b30dfcb1ac84b555096d52ddc47f9cbabd466a448e71fdb4ac52d38d8c41"
    },
    {
      "path": "hook-a.mp4",
      "bytes": 488352,
      "sha256": "41ae8eac17698031935d82a7af9441d28e6aee9760f633b3bc36da2f106e3da9"
    },
    {
      "path": "hook-b.mp4",
      "bytes": 550700,
      "sha256": "151aa8393d2f507b152c4fa69b7d5bc6ad69d84feabf6de339acf35ed0b0399a"
    },
    {
      "path": "poster.png",
      "bytes": 615846,
      "sha256": "db227cc6f115a74254ac34f7505102f1db24803e707d18a28c9bc37818e4371e"
    },
    {
      "path": "ogp.png",
      "bytes": 285034,
      "sha256": "d07defcdc57f8a723ecf344b48c6621b518f322a58ef78f2d53915384f0dd614"
    },
    {
      "path": "contact-sheet.png",
      "bytes": 587752,
      "sha256": "d1fb68128b77a0debeabe00f9b10921adb5957ac85b0cc378177c29bea5d2440"
    },
    {
      "path": "source-ai-record.json",
      "bytes": 8057,
      "sha256": "fd0af9708d575f220882a8e86e08be5c54064d080e57d700f08142697919121e"
    },
    {
      "path": "captions.json",
      "bytes": 601,
      "sha256": "552b612bc3339a25aac40f685a175fbc7d6411f6f55aa657c5f44430fbc1cd20"
    }
  ],
  "run": "https://github.com/ayutaz/voxelshogi/actions/runs/43484288004",
  "deliveryReview": {
    "at": "2026-11-13T18:39:59.450Z",
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
    "nativePlayback": {
      "browser": "Google Chrome",
      "observedTimeSeconds": 8,
      "durationSeconds": 15,
      "visibleRealControls": true,
      "scope": "local final MP4 playback; not the published app"
    },
    "publicUiMatchedCommit": "2d1d4c93fd0d3138f6f7217402e493f9f5aaf664",
    "supersededByLayoutFix": true
  }
}
```
