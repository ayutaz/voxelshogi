# Web SEの固定検証記録

2026-11-15 JST。[説明と制約](../WEB_SOUND_VALIDATION.md)。数値はLinux CIの実AudioContext graphの測定で、物理スピーカーの証明ではない。非表示は状態の模擬。録音・個人の棋譜・モデル重みは含まない。

```json
{
  "schema": 1,
  "kind": "web-sound-public-release",
  "publicCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
  "pr": 199,
  "candidateRun": 43632250539,
  "publicRun": 43635157136,
  "mainCi": 43633234278,
  "security": 43633234292,
  "artifacts": {
    "candidate": {
      "id": 14128836447,
      "sha256": "24c6b1fbc9487847853ddb1979d35a19d622e997a4c5113ba13ff647c013d0be"
    },
    "public": {
      "id": 14129687816,
      "sha256": "ed7ccb84b9e3f1d434129e8fd701440c37df41efd94e71eeb1b7dc5cc1126018"
    }
  },
  "physicalSpeakerQualityVerified": false,
  "actualMobileVerified": false,
  "safari": "27.0.1 UI and WAV playback-state check, not hardware audio analysis",
  "samples": {
    "schema": 1,
    "kind": "voxelshogi-original-game-sounds",
    "rate": 22050,
    "channels": 1,
    "sourceLicense": "Apache-2.0",
    "thirdPartySamples": false,
    "selectedVariant": "a",
    "selectedPcmWavBytes": 84144,
    "browserDelivery": "same deterministic PCM generated lazily from bundled source; no audio network requests",
    "files": [
      {
        "cue": "move",
        "variant": "a",
        "path": "move-a.wav",
        "bytes": 3572,
        "seconds": 0.08,
        "peakDb": -6.773112181392702,
        "sha256": "388d23884078ec29278fb870f7888e95f749f534e3c21dd2499fb42acba15dac"
      },
      {
        "cue": "capture",
        "variant": "a",
        "path": "capture-a.wav",
        "bytes": 5778,
        "seconds": 0.13002267573696144,
        "peakDb": -7.768981147501127,
        "sha256": "f01f02d0778d4198bdecbe4f80b2f167ff63ea45b29a35ffb96cfea177d94588"
      },
      {
        "cue": "capture-against",
        "variant": "a",
        "path": "capture-against-a.wav",
        "bytes": 6218,
        "seconds": 0.14,
        "peakDb": -7.088055408540321,
        "sha256": "281efbaab0f5304037fb8d13f6bf4db87a15e06f9274d984a8e74267570a1f98"
      },
      {
        "cue": "promotion",
        "variant": "a",
        "path": "promotion-a.wav",
        "bytes": 7542,
        "seconds": 0.17002267573696145,
        "peakDb": -8.0213529807682,
        "sha256": "fa7951a5e1d04af26efd44ee0c6678147c6a862b5e67f066f61319d36bea73b1"
      },
      {
        "cue": "check",
        "variant": "a",
        "path": "check-a.wav",
        "bytes": 9746,
        "seconds": 0.22,
        "peakDb": -8.0213529807682,
        "sha256": "4781cbac82dc46561877fd221d9729c29deb0b3b95f568064c099eeecb31403d"
      },
      {
        "cue": "end",
        "variant": "a",
        "path": "end-a.wav",
        "bytes": 15920,
        "seconds": 0.36,
        "peakDb": -8.0213529807682,
        "sha256": "c8a000d9becaabcb37c89e8cda3295070b3eb7ba7bfeb455afa5c75960a5d2ee"
      },
      {
        "cue": "win",
        "variant": "a",
        "path": "win-a.wav",
        "bytes": 17684,
        "seconds": 0.4,
        "peakDb": -8.0213529807682,
        "sha256": "0a0d3a4f27f9173fa9390a46829ee3c11820a51e88133a6cc4a68549c6e8ca12"
      },
      {
        "cue": "defeat",
        "variant": "a",
        "path": "defeat-a.wav",
        "bytes": 17684,
        "seconds": 0.4,
        "peakDb": -8.0213529807682,
        "sha256": "87e6fd4a2ac7d33dd420100395df90ac27dde8ca02e14ab5d22e80065ed560e2"
      },
      {
        "cue": "move",
        "variant": "b",
        "path": "move-b.wav",
        "bytes": 3572,
        "seconds": 0.08,
        "peakDb": -7.281201831479054,
        "sha256": "405ccac6685d22e5d3ca4a024726d510401229ba8be7bd5e39d1950b1d21629b"
      },
      {
        "cue": "capture",
        "variant": "b",
        "path": "capture-b.wav",
        "bytes": 5778,
        "seconds": 0.13002267573696144,
        "peakDb": -7.266891924569401,
        "sha256": "84ad0013ee6a87552ee43b4b817206c41125db4fc2f3f32564ee1a2b86575dc5"
      }
    ]
  },
  "measurements": {
    "candidate": [
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "chromium",
        "test": "a human normal move and a real Easy reply each reach the output once",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.08,
          0.08
        ],
        "stops": 0,
        "peak": 0.08811619877815247
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "chromium",
        "test": "accepted live capture produces one heavier cue and rejected clicks produce none",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.13002267573696144
        ],
        "stops": 0,
        "peak": 0.07222633063793182
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "chromium",
        "test": "cancelling a real search never produces a late move sound",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "chromium",
        "test": "hidden state suppresses sound and returning does not replay its backlog",
        "visibilityMayBeSimulated": true,
        "contexts": 1,
        "starts": [
          0.08,
          0.08
        ],
        "stops": 1,
        "peak": 0.030526069924235344
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "chromium",
        "test": "import and backward history are silent; explicit forward has only the capture cue",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.13002267573696144
        ],
        "stops": 1,
        "peak": 0.06436067074537277
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "chromium",
        "test": "mute stops playback, persists with volume, and can be enabled again",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.08
        ],
        "stops": 0,
        "peak": 0.20977649092674255
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "chromium",
        "test": "no audio before activation; test cue reaches the real output graph once",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.08
        ],
        "stops": 0,
        "peak": 0.12236960977315903
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "chromium",
        "test": "sound controls fit 1440x900",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "chromium",
        "test": "sound controls fit 390x844",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "chromium",
        "test": "sound controls fit 768x1024",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "chromium",
        "test": "unavailable audio and denied storage do not prevent human and real Easy AI moves",
        "visibilityMayBeSimulated": false,
        "contexts": 0,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "webkit",
        "test": "a human normal move and a real Easy reply each reach the output once",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.08,
          0.08
        ],
        "stops": 0,
        "peak": 0.12236960977315903
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "webkit",
        "test": "accepted live capture produces one heavier cue and rejected clicks produce none",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.13002267573696144
        ],
        "stops": 0,
        "peak": 0.06436067074537277
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "webkit",
        "test": "cancelling a real search never produces a late move sound",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "webkit",
        "test": "hidden state suppresses sound and returning does not replay its backlog",
        "visibilityMayBeSimulated": true,
        "contexts": 1,
        "starts": [
          0.08,
          0.08
        ],
        "stops": 1,
        "peak": 0.16047686338424683
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "webkit",
        "test": "import and backward history are silent; explicit forward has only the capture cue",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.13002267573696144
        ],
        "stops": 1,
        "peak": 0.08817030489444733
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "webkit",
        "test": "mute stops playback, persists with volume, and can be enabled again",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.08
        ],
        "stops": 0,
        "peak": 0.15105634927749634
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "webkit",
        "test": "no audio before activation; test cue reaches the real output graph once",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.08
        ],
        "stops": 0,
        "peak": 0.12236960977315903
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "webkit",
        "test": "sound controls fit 1440x900",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "webkit",
        "test": "sound controls fit 390x844",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "webkit",
        "test": "sound controls fit 768x1024",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ca65b9bd6acfcd28ec858a6d60827a8608b73096",
        "browser": "webkit",
        "test": "unavailable audio and denied storage do not prevent human and real Easy AI moves",
        "visibilityMayBeSimulated": false,
        "contexts": 0,
        "starts": [],
        "stops": 0,
        "peak": 0
      }
    ],
    "public": [
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "chromium",
        "test": "a human normal move and a real Easy reply each reach the output once",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.08,
          0.08
        ],
        "stops": 0,
        "peak": 0.055020108819007874
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "chromium",
        "test": "accepted live capture produces one heavier cue and rejected clicks produce none",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.13002267573696144
        ],
        "stops": 0,
        "peak": 0.0785079225897789
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "chromium",
        "test": "cancelling a real search never produces a late move sound",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "chromium",
        "test": "hidden state suppresses sound and returning does not replay its backlog",
        "visibilityMayBeSimulated": true,
        "contexts": 1,
        "starts": [
          0.08,
          0.08
        ],
        "stops": 1,
        "peak": 0.039237286895513535
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "chromium",
        "test": "import and backward history are silent; explicit forward has only the capture cue",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.13002267573696144
        ],
        "stops": 1,
        "peak": 0.06595083326101303
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "chromium",
        "test": "mute stops playback, persists with volume, and can be enabled again",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.08
        ],
        "stops": 0,
        "peak": 0.20977649092674255
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "chromium",
        "test": "no audio before activation; test cue reaches the real output graph once",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.08
        ],
        "stops": 0,
        "peak": 0.12236960977315903
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "chromium",
        "test": "sound controls fit 1440x900",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "chromium",
        "test": "sound controls fit 390x844",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "chromium",
        "test": "sound controls fit 768x1024",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "chromium",
        "test": "unavailable audio and denied storage do not prevent human and real Easy AI moves",
        "visibilityMayBeSimulated": false,
        "contexts": 0,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "webkit",
        "test": "a human normal move and a real Easy reply each reach the output once",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.08,
          0.08
        ],
        "stops": 0,
        "peak": 0.08811619877815247
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "webkit",
        "test": "accepted live capture produces one heavier cue and rejected clicks produce none",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.13002267573696144
        ],
        "stops": 0,
        "peak": 0.0785079225897789
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "webkit",
        "test": "cancelling a real search never produces a late move sound",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "webkit",
        "test": "hidden state suppresses sound and returning does not replay its backlog",
        "visibilityMayBeSimulated": true,
        "contexts": 1,
        "starts": [
          0.08,
          0.08
        ],
        "stops": 1,
        "peak": 0.12236960977315903
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "webkit",
        "test": "import and backward history are silent; explicit forward has only the capture cue",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.13002267573696144
        ],
        "stops": 1,
        "peak": 0.09073388576507568
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "webkit",
        "test": "mute stops playback, persists with volume, and can be enabled again",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.08
        ],
        "stops": 0,
        "peak": 0.27510321140289307
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "webkit",
        "test": "no audio before activation; test cue reaches the real output graph once",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [
          0.08
        ],
        "stops": 0,
        "peak": 0.12236960977315903
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "webkit",
        "test": "sound controls fit 1440x900",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "webkit",
        "test": "sound controls fit 390x844",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "webkit",
        "test": "sound controls fit 768x1024",
        "visibilityMayBeSimulated": false,
        "contexts": 1,
        "starts": [],
        "stops": 0,
        "peak": 0
      },
      {
        "expectedCommit": "ba9767aba9e282cdc259f461b7a9a79e93a17732",
        "browser": "webkit",
        "test": "unavailable audio and denied storage do not prevent human and real Easy AI moves",
        "visibilityMayBeSimulated": false,
        "contexts": 0,
        "starts": [],
        "stops": 0,
        "peak": 0
      }
    ]
  }
}
```
