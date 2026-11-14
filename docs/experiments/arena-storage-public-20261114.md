# 公開確認の固定記録

2026-11-14。対象source・確認範囲は以下の記録内に固定する。

```json
{
  "schema": 1,
  "kind": "automatic-storage-public-proof",
  "applicationCommit": "dc0a95fa00d4957b2a4d2712f27a0f469a6c3a7b",
  "gameId": "1b5a9659-9291-46b9-b7c6-34b4fbbaeacc",
  "syntheticOnly": true,
  "receivedUnverified": true,
  "requests": [
    {
      "name": "first",
      "httpStatus": 201,
      "ack": {
        "gameId": "1b5a9659-9291-46b9-b7c6-34b4fbbaeacc",
        "requestId": "ff76474f-fb70-49cc-93ea-0e74604fdfad",
        "version": 1,
        "status": "received_unverified",
        "duplicate": false,
        "ignored": false
      }
    },
    {
      "name": "extend",
      "httpStatus": 200,
      "ack": {
        "gameId": "1b5a9659-9291-46b9-b7c6-34b4fbbaeacc",
        "requestId": "a8fc48b3-14e8-46c3-9b98-88d95f9977e4",
        "version": 2,
        "status": "received_unverified",
        "duplicate": false,
        "ignored": false
      }
    },
    {
      "name": "same body retry",
      "httpStatus": 200,
      "ack": {
        "gameId": "1b5a9659-9291-46b9-b7c6-34b4fbbaeacc",
        "requestId": "a8fc48b3-14e8-46c3-9b98-88d95f9977e4",
        "version": 2,
        "status": "received_unverified",
        "duplicate": true,
        "ignored": false
      }
    },
    {
      "name": "same version conflict",
      "httpStatus": 409,
      "ack": {
        "error": "snapshot_conflict"
      }
    },
    {
      "name": "old version",
      "httpStatus": 200,
      "ack": {
        "gameId": "1b5a9659-9291-46b9-b7c6-34b4fbbaeacc",
        "requestId": "ff76474f-fb70-49cc-93ea-0e74604fdfad",
        "version": 2,
        "status": "received_unverified",
        "duplicate": false,
        "ignored": true
      }
    },
    {
      "name": "finished",
      "httpStatus": 200,
      "ack": {
        "gameId": "1b5a9659-9291-46b9-b7c6-34b4fbbaeacc",
        "requestId": "ff2fad3f-142c-42e4-9c85-8ddb9b21c468",
        "version": 3,
        "status": "received_unverified",
        "duplicate": false,
        "ignored": false
      }
    },
    {
      "name": "late progress",
      "httpStatus": 409,
      "ack": {
        "error": "snapshot_conflict"
      }
    }
  ],
  "startedAt": "2026-11-14T08:51:02.586Z",
  "stored": {
    "version": 3,
    "state": "finished",
    "progressWrites": 2,
    "status": "received_unverified",
    "payloadBytes": 704,
    "payloadSha256": "2e149c47e4452d1ae5c9691a4ff80fddc70c7c87d335028597b7516e5f3fab00",
    "bodyMatches": true
  },
  "complete": true,
  "syntheticRowDeleted": true,
  "finishedAt": "2026-11-14T08:51:08.054Z",
  "scriptSha256": "d3459bfc1cecfdd704d535a5ec453b2ae2c4540f84b05fd564102e207898ade8"
}
```
