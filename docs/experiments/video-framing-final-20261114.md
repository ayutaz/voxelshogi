# 見切れ修正後の最終動画と確認記録

2026-11-14。公開SHA一致の15秒本編・3秒2案。21画像の目視で見切れ・字幕重なり・切替途中のCanvasを確認し、問題なし。全450フレームの目視やX上での再生を確認したという意味ではない。

Linux自動検査のframing.visualReviewComplete=falseは原本のまま保持し、担当側の21画像確認をdelivery.visualReviewComplete=trueへ記録する。旧dc0a95f版の目視判定は撤回済み。

```json
{
  "applicationCommit": "d3822cbeded2bae7329ddd72b4984cf6e8970db0",
  "run": 43589608131,
  "artifact": 14111668933,
  "artifactSha256": "7b1d451745c8fb0af5955ccafd0a035286438841d4366e43a99cecb4818e5993",
  "receipt": {
    "schema": 1,
    "kind": "voxelshogi-demo-video",
    "appCommit": "d3822cbeded2bae7329ddd72b4984cf6e8970db0",
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
    "recordedBoundsVerified": true,
    "sourceRate": 25,
    "firstContentFrame": 920,
    "outputFps": 30,
    "performanceMeasurement": false,
    "soundRequired": false,
    "recordingScriptSha256": "d9e88055999a8e77d2386df5f4c67eea16467dd972a464bbedf45da0ced4d1af",
    "webLockSha256": "c09f59c577fa6758f4c55ae62875ec5492afe2c1b0aabee4c1866ee12723dafc",
    "ffmpeg": "ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023 the FFmpeg developers",
    "japaneseFontSha256": "faa5f3656a78b2e2d450d27fe8382c778bc2b6bb5ea29c986664a6a435056ceb",
    "files": [
      {
        "path": "demo-main.mp4",
        "bytes": 1772757,
        "sha256": "e5ab3e8922b7f8fa55b80f385b8a94bef8683e2ad8469b00db7dee8ddcddb0e1"
      },
      {
        "path": "hook-a.mp4",
        "bytes": 918643,
        "sha256": "eff23afb6668bca0764b52e11f146ab27aabb4feabb303ee7a183c2bc3ca98e6"
      },
      {
        "path": "hook-b.mp4",
        "bytes": 940532,
        "sha256": "61f020a164a49a93011b46b12f9f26047aed18ec8be2626bb022872cc10609a4"
      },
      {
        "path": "poster.png",
        "bytes": 774992,
        "sha256": "40efc2b9c900f807038ba0bedb0215aaf36d586a097a1f436ce6c5af4de80f0b"
      },
      {
        "path": "ogp.png",
        "bytes": 326832,
        "sha256": "b005cfc5312560a7c2be5e2d014cc3f53ba60f7c28ae0d4fb0118c4c585322cd"
      },
      {
        "path": "contact-sheet.png",
        "bytes": 701388,
        "sha256": "95afc2f8f798de3b3df352316058d3dbc57bf70635c19bf7151182a58a7b2aa7"
      },
      {
        "path": "source-ai-record.json",
        "bytes": 2840,
        "sha256": "3875b1c42a7a385f9fc1666b0431f5b1ae68038aaf0154bff0e93772c6560328"
      },
      {
        "path": "captions.json",
        "bytes": 664,
        "sha256": "1c636e7a5976a9c11356d2156ccaaf12aac263e97b1e631c26d07a750186ca8d"
      },
      {
        "path": "framing.json",
        "bytes": 11688,
        "sha256": "2b69fcee87b5adaacb5ccac8e68bf0ed79b018ee5341b6c85b7d2994eb1f5a16"
      },
      {
        "path": "review-main-0.png",
        "bytes": 774992,
        "sha256": "40efc2b9c900f807038ba0bedb0215aaf36d586a097a1f436ce6c5af4de80f0b"
      },
      {
        "path": "review-main-0-4.png",
        "bytes": 864431,
        "sha256": "b4cb7c9d8929e7740599d85f2ca565e21ca056be80f7a65f6fe5bf93698530d1"
      },
      {
        "path": "review-main-0-7.png",
        "bytes": 991842,
        "sha256": "66301ba9fc74101a4cd0ea83506b162f5c8cc6006e7d89e811c7d33c3942f216"
      },
      {
        "path": "review-main-1-5.png",
        "bytes": 1065525,
        "sha256": "c0e8ce3e8a74365bf81c6c76c00a22a945ea84251e1054f19bb92e90c87a0e10"
      },
      {
        "path": "review-main-2-9.png",
        "bytes": 1065802,
        "sha256": "8dcfa7a572d3328ca76c672b1962dd5a8d88705c5377d952616dcfb0a551f324"
      },
      {
        "path": "review-main-3.png",
        "bytes": 1051359,
        "sha256": "b5bf32e23af4174294b7f81f7be93c9eb5026d8a7f4be28347f7d03c4b4de7df"
      },
      {
        "path": "review-main-3-2.png",
        "bytes": 947716,
        "sha256": "ead53fd30df26653babae56d47b98892be04c89c7454ab2c096ec24e78e289cd"
      },
      {
        "path": "review-main-6-9.png",
        "bytes": 894115,
        "sha256": "f7abcce668e67dfa333cc280d844e4f8dc3497719929fea77e0e59bd5af49445"
      },
      {
        "path": "review-main-7.png",
        "bytes": 645339,
        "sha256": "5eec80236f0d185bb350d03025600ec3e6489ee660b882e07b6f7861f07ce9ef"
      },
      {
        "path": "review-main-7-2.png",
        "bytes": 647276,
        "sha256": "5efb141d71881828b11bd94d8f2a098a1d5f6e4060e136965d758a8f83d988e2"
      },
      {
        "path": "review-main-7-5.png",
        "bytes": 645122,
        "sha256": "81ca62f3b0be0679e74a24420b216de45b927176a913ba449c53355cf28c5153"
      },
      {
        "path": "review-main-10-8.png",
        "bytes": 659886,
        "sha256": "ade8de746f8b5a636ec529351fb532d35fc477dccbb38644dc977f1c4bc03b74"
      },
      {
        "path": "review-main-11.png",
        "bytes": 848747,
        "sha256": "b0b8c3f29dc1c96d9c50e70e7f6cee5c21dff9d99e408bfaa12f2316cf57040c"
      },
      {
        "path": "review-main-11-2.png",
        "bytes": 848970,
        "sha256": "a2d2716a7c625d459c8e529ff33721cbba13dcb482efdcd6e7ff50690fe6b6c5"
      },
      {
        "path": "review-main-14-9.png",
        "bytes": 848967,
        "sha256": "82221a1b77ebe25b37edf76b027c05a74b37510a94409ef8f03fde8f38b1a4e5"
      },
      {
        "path": "review-a-0.png",
        "bytes": 774992,
        "sha256": "40efc2b9c900f807038ba0bedb0215aaf36d586a097a1f436ce6c5af4de80f0b"
      },
      {
        "path": "review-a-1-5.png",
        "bytes": 1065525,
        "sha256": "c0e8ce3e8a74365bf81c6c76c00a22a945ea84251e1054f19bb92e90c87a0e10"
      },
      {
        "path": "review-a-2-9.png",
        "bytes": 1059356,
        "sha256": "9575cd73c1f86fdf101ccbb30bf9c21f42af6d90bb5b821840367efdb3d1c433"
      },
      {
        "path": "review-b-0.png",
        "bytes": 773070,
        "sha256": "28daf4fd90c7ec59a7f8d0abaca0f0c59c7a19374c2bd7539d2b5a61b7769c02"
      },
      {
        "path": "review-b-1-5.png",
        "bytes": 1094858,
        "sha256": "56207122bfdbe5eea54e3cccd3291d695f9a53285370165aab52617fde20a3d6"
      },
      {
        "path": "review-b-2-9.png",
        "bytes": 1087124,
        "sha256": "bc7489f1f95746431bda0ac153d9dbedfb52e7994305c5fc81b8b0d8771edc12"
      }
    ]
  },
  "framing": {
    "schema": 1,
    "captionBands": {
      "top": [
        0,
        176
      ],
      "bottom": [
        1160,
        1350
      ]
    },
    "openingZoom": {
      "a": 1.1,
      "b": 1.12
    },
    "controlsZoom": 1,
    "timeline": {
      "controlsStartFrame": 221,
      "ctaStartFrame": 358
    },
    "sourceCuts": [
      {
        "start": 0,
        "end": 210
      },
      {
        "start": 221,
        "end": 341
      },
      {
        "start": 358,
        "end": 478
      }
    ],
    "uiLayouts": [
      {
        "atMilliseconds": 7353.4571670000005,
        "rects": [
          {
            "left": 16,
            "right": 1064,
            "top": 180,
            "bottom": 228
          },
          {
            "left": 16,
            "right": 1064,
            "top": 234,
            "bottom": 282
          },
          {
            "left": 766,
            "right": 1062,
            "top": 558,
            "bottom": 854
          },
          {
            "left": 312.734375,
            "right": 356.734375,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 360.734375,
            "right": 404.734375,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 408.734375,
            "right": 452.734375,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 456.734375,
            "right": 501.40625,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 505.40625,
            "right": 549.40625,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 553.40625,
            "right": 598.078125,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 602.078125,
            "right": 660.46875,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 664.46875,
            "right": 718.578125,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 722.578125,
            "right": 767.265625,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 194.15625,
            "right": 303.1875,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 309.1875,
            "right": 477.1875,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 483.1875,
            "right": 650.8125,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 656.8125,
            "right": 770.8125,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 776.8125,
            "right": 885.84375,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 20,
            "right": 38,
            "top": 1075,
            "bottom": 1093
          },
          {
            "left": 839.09375,
            "right": 999.09375,
            "top": 1076,
            "bottom": 1092
          },
          {
            "left": 16,
            "right": 1064,
            "top": 1110,
            "bottom": 1124
          }
        ]
      },
      {
        "atMilliseconds": 8298.024374,
        "rects": [
          {
            "left": 16,
            "right": 1064,
            "top": 180,
            "bottom": 228
          },
          {
            "left": 16,
            "right": 1064,
            "top": 234,
            "bottom": 282
          },
          {
            "left": 766,
            "right": 1062,
            "top": 558,
            "bottom": 854
          },
          {
            "left": 317.234375,
            "right": 361.234375,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 365.234375,
            "right": 409.234375,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 413.234375,
            "right": 457.234375,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 461.234375,
            "right": 505.90625,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 509.90625,
            "right": 553.90625,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 557.90625,
            "right": 602.578125,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 606.578125,
            "right": 655.96875,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 659.96875,
            "right": 714.078125,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 718.078125,
            "right": 762.765625,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 247.234375,
            "right": 356.265625,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 362.265625,
            "right": 502.265625,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 508.265625,
            "right": 597.71875,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 603.71875,
            "right": 717.71875,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 723.71875,
            "right": 832.75,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 20,
            "right": 38,
            "top": 1075,
            "bottom": 1093
          },
          {
            "left": 839.09375,
            "right": 999.09375,
            "top": 1076,
            "bottom": 1092
          },
          {
            "left": 16,
            "right": 1064,
            "top": 1110,
            "bottom": 1124
          }
        ]
      },
      {
        "atMilliseconds": 11172.785457999998,
        "rects": [
          {
            "left": 16,
            "right": 1064,
            "top": 180,
            "bottom": 228
          },
          {
            "left": 16,
            "right": 1064,
            "top": 234,
            "bottom": 282
          },
          {
            "left": 766,
            "right": 1062,
            "top": 558,
            "bottom": 854
          },
          {
            "left": 317.234375,
            "right": 361.234375,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 365.234375,
            "right": 409.234375,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 413.234375,
            "right": 457.234375,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 461.234375,
            "right": 505.90625,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 509.90625,
            "right": 553.90625,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 557.90625,
            "right": 602.578125,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 606.578125,
            "right": 655.96875,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 659.96875,
            "right": 714.078125,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 718.078125,
            "right": 762.765625,
            "top": 948,
            "bottom": 992
          },
          {
            "left": 247.234375,
            "right": 356.265625,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 362.265625,
            "right": 502.265625,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 508.265625,
            "right": 597.71875,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 603.71875,
            "right": 717.71875,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 723.71875,
            "right": 832.75,
            "top": 1006,
            "bottom": 1058
          },
          {
            "left": 20,
            "right": 38,
            "top": 1075,
            "bottom": 1093
          },
          {
            "left": 839.09375,
            "right": 999.09375,
            "top": 1076,
            "bottom": 1092
          },
          {
            "left": 16,
            "right": 1064,
            "top": 1110,
            "bottom": 1124
          }
        ]
      }
    ],
    "boardBounds": [
      {
        "seconds": 0,
        "rect": {
          "left": 260,
          "right": 865,
          "top": 354,
          "bottom": 1095
        },
        "zoom": 1
      },
      {
        "seconds": 0.4,
        "rect": {
          "left": 262,
          "right": 865,
          "top": 355,
          "bottom": 1096
        },
        "zoom": 1
      },
      {
        "seconds": 0.7,
        "rect": {
          "left": 264,
          "right": 865,
          "top": 355,
          "bottom": 1096
        },
        "zoom": 1.09
      },
      {
        "seconds": 1.5,
        "rect": {
          "left": 265,
          "right": 865,
          "top": 356,
          "bottom": 1096
        },
        "zoom": 1.12
      },
      {
        "seconds": 2.9,
        "rect": {
          "left": 266,
          "right": 865,
          "top": 357,
          "bottom": 1097
        },
        "zoom": 1.12
      },
      {
        "seconds": 3.2,
        "rect": {
          "left": 266,
          "right": 865,
          "top": 357,
          "bottom": 1097
        },
        "zoom": 1.05
      },
      {
        "seconds": 6.9,
        "rect": {
          "left": 16,
          "right": 1064,
          "top": 200,
          "bottom": 1150
        },
        "zoom": 1
      },
      {
        "seconds": 11.2,
        "rect": {
          "left": 267,
          "right": 866,
          "top": 357,
          "bottom": 1098
        },
        "zoom": 1
      },
      {
        "seconds": 14.9,
        "rect": {
          "left": 267,
          "right": 866,
          "top": 357,
          "bottom": 1098
        },
        "zoom": 1
      }
    ],
    "reviewFrames": [
      {
        "file": "review-main-0.png",
        "seconds": 0,
        "source": "main"
      },
      {
        "file": "review-main-0-4.png",
        "seconds": 0.4,
        "source": "main"
      },
      {
        "file": "review-main-0-7.png",
        "seconds": 0.7,
        "source": "main"
      },
      {
        "file": "review-main-1-5.png",
        "seconds": 1.5,
        "source": "main"
      },
      {
        "file": "review-main-2-9.png",
        "seconds": 2.9,
        "source": "main"
      },
      {
        "file": "review-main-3.png",
        "seconds": 3,
        "source": "main"
      },
      {
        "file": "review-main-3-2.png",
        "seconds": 3.2,
        "source": "main"
      },
      {
        "file": "review-main-6-9.png",
        "seconds": 6.9,
        "source": "main"
      },
      {
        "file": "review-main-7.png",
        "seconds": 7,
        "source": "main"
      },
      {
        "file": "review-main-7-2.png",
        "seconds": 7.2,
        "source": "main"
      },
      {
        "file": "review-main-7-5.png",
        "seconds": 7.5,
        "source": "main"
      },
      {
        "file": "review-main-10-8.png",
        "seconds": 10.8,
        "source": "main"
      },
      {
        "file": "review-main-11.png",
        "seconds": 11,
        "source": "main"
      },
      {
        "file": "review-main-11-2.png",
        "seconds": 11.2,
        "source": "main"
      },
      {
        "file": "review-main-14-9.png",
        "seconds": 14.9,
        "source": "main"
      },
      {
        "file": "review-a-0.png",
        "seconds": 0,
        "source": "a"
      },
      {
        "file": "review-a-1-5.png",
        "seconds": 1.5,
        "source": "a"
      },
      {
        "file": "review-a-2-9.png",
        "seconds": 2.9,
        "source": "a"
      },
      {
        "file": "review-b-0.png",
        "seconds": 0,
        "source": "b"
      },
      {
        "file": "review-b-1-5.png",
        "seconds": 1.5,
        "source": "b"
      },
      {
        "file": "review-b-2-9.png",
        "seconds": 2.9,
        "source": "b"
      }
    ],
    "recordedBoundsVerified": true,
    "visualReviewComplete": false
  },
  "delivery": {
    "schema": 1,
    "applicationCommit": "d3822cbeded2bae7329ddd72b4984cf6e8970db0",
    "run": 43589608131,
    "reviewedAt": "2026-11-14T11:35:23.148Z",
    "allThirtyFileHashesVerified": true,
    "metadataOnlyOnMac": true,
    "fullDecodeOnLinux": true,
    "visualReviewComplete": true,
    "reviewedImages": [
      "review-main-0.png",
      "review-main-0-4.png",
      "review-main-0-7.png",
      "review-main-1-5.png",
      "review-main-2-9.png",
      "review-main-3.png",
      "review-main-3-2.png",
      "review-main-6-9.png",
      "review-main-7.png",
      "review-main-7-2.png",
      "review-main-7-5.png",
      "review-main-10-8.png",
      "review-main-11.png",
      "review-main-11-2.png",
      "review-main-14-9.png",
      "review-a-0.png",
      "review-a-1-5.png",
      "review-a-2-9.png",
      "review-b-0.png",
      "review-b-1-5.png",
      "review-b-2-9.png"
    ],
    "reviewedImageCount": 21,
    "findings": {
      "clipped2DBoard": false,
      "clippedSpeedControl": false,
      "captionBoardOverlap": false,
      "canvasResizeFrameVisible": false
    },
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
          "duration": "15.000000",
          "size": "1772757"
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
          "duration": "3.000000",
          "size": "918643"
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
          "duration": "3.000000",
          "size": "940532"
        }
      }
    }
  },
  "publicValidation": {
    "run": 43587794604,
    "securityRun": 43587794631,
    "ordinaryE2E": 53,
    "cameraRepeats": 3,
    "modelLabE2E": 6,
    "distributionFiles": 57,
    "allSuccessful": true,
    "gameApiModelSourcesUnchangedFrom": "dc0a95fa00d4957b2a4d2712f27a0f469a6c3a7b"
  }
}
```
