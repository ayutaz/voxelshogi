# 最終公開版のPC実操作確認

2026-11-14 JST。公開`c878c6d`で自分の検証用対局だけを操作した。通常のウィンドウ撮影が自動承認レビューに拒否された後、AX情報が回復したため、撮影せずに操作と結果を確認した。初期・開始・停止・1手・Return・層変更・ダウンロード完了・人間対AI・不同意の投了を実操作し、端末JSONのサイズ・18着手・hashを読み取った。

不同意の通信件数はAX確認から推測せず、[公開E2Eと実D1の別検証](../L6_PUBLIC_VALIDATION.md)に分ける。物理スマホとPhase7の60分観戦の証拠ではない。撮影許可を受け取ったとは扱わず、他タブやウィンドウは撮影していない。自分で開いた検証タブだけを終了した。

```json
{
  "schema": 1,
  "kind": "launch-native-final",
  "appCommit": "c878c6d08572caa2da2d0cf654caa85ba7dfd501",
  "at": "2026-11-13T20:25:00Z",
  "environment": {
    "os": "macOS 27.0.1",
    "browser": "Google Chrome 157.0.8103.52",
    "arch": "arm64"
  },
  "observation": "native accessibility tree of public Arena; no window screenshot",
  "ai": "Easy for both sides, no model download or local benchmark",
  "checks": {
    "initialMoveNumber": 1,
    "runningMoveNumberSeen": 2,
    "pausedMoveNumber": 17,
    "singleStepMoveNumber": 18,
    "keyboardStepMoveNumber": 19,
    "keyboardFocusRetained": true,
    "lastWatchMoveText": "☖後手 5二IV→5二III",
    "manualLayerChange": "III to IV",
    "followAfterManualChange": false,
    "download": {
      "bytes": 784,
      "sha256": "3450f41460b7c923a81268b14f5809bcfecd37c0291427ddd88762dadad97364",
      "moves": 18,
      "lastMove": "524523",
      "result": null,
      "termination": null,
      "browserCompletionSeen": true
    },
    "humanVsAi": {
      "humanMove": "5七V→5六V",
      "aiResponse": "5一VII→4二VI",
      "moveNumberAfterResponse": 3
    },
    "nonConsentingResignation": {
      "winner": "white",
      "consent": false,
      "consentDisabledAfterEnd": true,
      "sendButtonDisabled": true
    }
  },
  "limitations": {
    "noScreenshot": true,
    "noNetworkCountInferredFromAx": true,
    "physicalPhoneVerified": false,
    "noWindowScreenshotApprovalAssumed": true
  }
}
```
