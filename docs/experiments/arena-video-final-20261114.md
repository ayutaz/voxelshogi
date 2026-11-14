# 新UIの公開版デモ動画の固定記録

2026-11-14。公開source dc0a95fa00d4957b2a4d2712f27a0f469a6c3a7b。

```json
{
  "run": 43577744281,
  "artifact": 14107491791,
  "artifactSha256": "7117b95b347953a6bc76c4dd7816fb61d0d248e89cb72c0641d4b2cc3bcd6c54",
  "receipt": {
    "schema": 1,
    "kind": "voxelshogi-demo-video",
    "appCommit": "dc0a95fa00d4957b2a4d2712f27a0f469a6c3a7b",
    "ruleset": "voxelshogi-standard-v1",
    "candidate": false,
    "agents": [
      "easy",
      "easy"
    ],
    "hookPly": 14,
    "hookMove": "415524",
    "fullRecordReplayedByRust": true,
    "fullDecodeValidated": true,
    "sourceRate": 25,
    "firstContentFrame": 953,
    "outputFps": 30,
    "performanceMeasurement": false,
    "soundRequired": false,
    "recordingScriptSha256": "940d30d6275984f8925ab0a1c089e32fac2ee356513b5cf151835e2a124ec9fc",
    "webLockSha256": "c09f59c577fa6758f4c55ae62875ec5492afe2c1b0aabee4c1866ee12723dafc",
    "ffmpeg": "ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023 the FFmpeg developers",
    "japaneseFontSha256": "faa5f3656a78b2e2d450d27fe8382c778bc2b6bb5ea29c986664a6a435056ceb",
    "files": [
      {
        "path": "demo-main.mp4",
        "bytes": 2841823,
        "sha256": "abdff134c651023046885fd95aa9e9f7caf42df787cd8945aaaad1fc15e436ee"
      },
      {
        "path": "hook-a.mp4",
        "bytes": 1572566,
        "sha256": "cd025e6fb054d03ef8be3e56ef90ed6db951df5717dfcc3a19ecfacc15e06b24"
      },
      {
        "path": "hook-b.mp4",
        "bytes": 1824509,
        "sha256": "267e7457fe47ae5a5d00367923dbcf4403c1081a07bd38b36eb55b24041a7323"
      },
      {
        "path": "poster.png",
        "bytes": 784279,
        "sha256": "ee88760d71d2e108774b3b27d70839404df2be51014a2ce2ad7ccbed17f18a00"
      },
      {
        "path": "ogp.png",
        "bytes": 326244,
        "sha256": "00b469bb3c342960bca525e0b373b7382aa4c924948c8f3268bbfe272b0fbba9"
      },
      {
        "path": "contact-sheet.png",
        "bytes": 1160957,
        "sha256": "13d2a827be6069439e79add913f04aad4255d8c5e10a5ae11bc62129fa0fb9be"
      },
      {
        "path": "source-ai-record.json",
        "bytes": 2857,
        "sha256": "2b45dd23f88c2b9ec73bc88022e8ef38d94367dd9e837cb37cbca6a56004295a"
      },
      {
        "path": "captions.json",
        "bytes": 664,
        "sha256": "1c636e7a5976a9c11356d2156ccaaf12aac263e97b1e631c26d07a750186ca8d"
      }
    ]
  },
  "delivery": {
    "schema": 1,
    "appCommit": "dc0a95fa00d4957b2a4d2712f27a0f469a6c3a7b",
    "run": 43577744281,
    "reviewedAt": "2026-11-14T09:04:29.705Z",
    "allEightHashesVerified": true,
    "metadataReadOnlyOnMac": true,
    "fullDecodeOnLinux": true,
    "probes": {
      "demo-main.mp4": {
        "programs": [],
        "stream_groups": [],
        "streams": [
          {
            "codec_name": "h264",
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
    }
  },
  "visualReview": {
    "nineBrightLayersAtStart": true,
    "realCrossLayerMoveWithinThreeSeconds": true,
    "hookMove": "415524",
    "hookLayers": "V→IV",
    "chosenHook": "A: full nine-layer board, then 1.7x close-up; B: 1.95x alternate",
    "silentCaptionsAndURLReadable": true,
    "contactSheetReviewed": true,
    "ogpReviewed": true,
    "publishedOgpSource": "ff33b0d candidate, deliberately included before final runtime publication; final exported ogp is a separate deliverable",
    "realPhonePlaybackVerified": false,
    "xPosted": false
  }
}
```
