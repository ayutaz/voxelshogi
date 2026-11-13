# 公開確認の固定記録

生のJSONは検証元の実行記録・納品物へ保持し、文書では同じ確認値を掲載する。

```json
{
  "schema": 1,
  "kind": "public-deploy-first-attempt",
  "appCommit": "c878c6d08572caa2da2d0cf654caa85ba7dfd501",
  "run": "https://github.com/ayutaz/voxelshogi/actions/runs/43493744095",
  "runConclusion": "failure",
  "failedJobs": [
    {
      "id": 132128497565,
      "name": "Deploy to Cloudflare",
      "conclusion": "failure"
    }
  ],
  "ordinaryPublicE2E": {
    "passed": 33
  },
  "cameraPublicRegression": {
    "passed": 3,
    "retries": 0
  },
  "publicModelE2E": {
    "passed": 5,
    "failed": 1,
    "failure": "first inference result was not visible within 60000ms in the camera/cancellation case"
  },
  "failureLogRetained": true,
  "rootCause": "not established",
  "targetedRecheckRequested": true
}
```
