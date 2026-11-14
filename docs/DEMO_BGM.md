# デモ動画のBGM

2026-11-15 JST。ユーザー指定により、確認済み15秒動画へ軽快なエレクトロのインストBGMを加える。好みの指定はなく、映像に合わせて担当側で選ぶ。WebのSEは[調査・計画](WEB_SOUND_PLAN.md)で別に管理する。

## 目的とゴール

冒頭から動きのある音で9層の盤面に注意を向け、字幕の読解を邪魔せず、最後の「開発したAIと対戦」の案内で締める。15秒本編・3秒A/BにステレオAACを加え、元の映像パケットが完全一致すること、音量・クリッピング・全編デコードとhashを検証する。音の有無による拡散効果を実測したとは扱わない。

## 制作方法

`scripts/demo-bgm.mjs`で128 BPM・8小節・15秒のオリジナルな短いインストを合成する。短いシンセのアルペジオ、柔らかな和音、ベース、軽いドラムを使い、最後は減衰させる。外部の楽曲・録音・学習モデルや有料音楽サービスを使わない。制作ソースはプロジェクトのApache-2.0で管理する。

元動画は公開source `7b364c9`の[確認済み制作run](https://github.com/ayutaz/voxelshogi/actions/runs/43611290885)。3動画の固定SHA-256を入力時に検査し、映像は`-c:v copy`で保持する。各映像の圧縮パケットhash・解像度・fps・frame数を音付け前後で照合するので、今回の編集で字幕・UI・棋譜を再描画しない。

音は48kHz・stereo・AAC 192kbps、目標-18 LUFS・true peak -2dB。2パス正規化後、最終AACの音量・ピーク・長さを測る。15秒本編と3秒2案は別ファイルで納品し、元の無音版も保持する。素材合成・音量解析・mux・全編デコードはLinux CIで実行し、Macには完成MP4と小さいreceiptだけ取得する。

既存`Demo video` workflowの`add_bgm_only=true`で実行する。元artifactは7日保持のため、期限切れ後に再実行する場合は同じhashを持つ保管済み完成物を外部Linuxへ用意するか、新たな検証済み動画のrunと固定hashへ明示更新する。今回はモデル・未編集録画・ユーザー棋譜を取得しない。

## 状態

**制作・客観検査完了。** [Linux run](https://github.com/ayutaz/voxelshogi/actions/runs/43620484463)で15秒本編・3秒2案を制作し、AACの全編デコード、3動画の映像packet不変、bytes／hashを確認した。本編は-18.03 LUFS・true peak -2.56dB。切り替え・字幕・盤の目視証拠は、映像が同じ元動画の21画像を保持する。

納品先は`runs/demo-bgm/final-778cdba/`。`demo-main-bgm.mp4`を投稿用候補とし、無音版は元のフォルダーに保持する。完成動画をユーザーの標準プレイヤーで開いた。機械的な音量検査は済んでいるが、担当エージェントによる実スピーカーでの試聴、X上の再生や拡散効果は未確認。

## 固定した制作記録

artifact `14123917265`、ZIP SHA-256 `c3dd0091b565a5d6cd10bda74524d1f770678601e408b5d2cad7a51f2d807080`。素材・録音・モデルはダウンロードせず、完成MP4とreceiptだけを取得した。

```json
{
  "schema": 1,
  "kind": "voxelshogi-original-demo-bgm",
  "applicationCommit": "7b364c9ad693c35d00ca8edf1c428f19658b8d04",
  "sourceVideoRun": 43611290885,
  "music": {
    "style": "light electronic instrumental",
    "bpm": 128,
    "bars": 8,
    "seconds": 15,
    "sampleRate": 48000,
    "channels": 2,
    "composition": "original procedural score",
    "thirdPartySamples": false,
    "sourceLicense": "Apache-2.0",
    "targetLufs": -18,
    "targetTruePeakDb": -2,
    "wavSha256": "9d3c4ae153053cee80e91d7631263db5621eb135637ef7be2dcdd2db0452a835"
  },
  "files": [
    {
      "path": "demo-main-bgm.mp4",
      "bytes": 2135412,
      "sha256": "3ce3687d080040ca24c50d40d4914ac40c75bb7596ec4b31bcde560a78cb0cfc",
      "durationSeconds": 15,
      "videoPacketsUnchanged": true,
      "fullDecodeValidated": true,
      "loudnessLufs": -18.03,
      "truePeakDb": -2.56
    },
    {
      "path": "hook-a-bgm.mp4",
      "bytes": 997801,
      "sha256": "c5366289193e374546ccfe1cea67d914a3b72ef6b80706c13df2202551bfbccf",
      "durationSeconds": 3,
      "videoPacketsUnchanged": true,
      "fullDecodeValidated": true,
      "loudnessLufs": -18.48,
      "truePeakDb": -3.73
    },
    {
      "path": "hook-b-bgm.mp4",
      "bytes": 1016977,
      "sha256": "b5869b2632bab275d939f2cc63983ed5a17df832832d7946dc8f063d2ea45689",
      "durationSeconds": 3,
      "videoPacketsUnchanged": true,
      "fullDecodeValidated": true,
      "loudnessLufs": -18.48,
      "truePeakDb": -3.73
    }
  ]
}
```
