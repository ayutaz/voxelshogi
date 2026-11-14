# Web SEの実装・公開確認

2026-11-15 JST。ユーザーの「4まで」に基づく[SE計画](WEB_SOUND_PLAN.md)の実行記録。実装と候補検証を進行中で、公開完了とはしない。

| 要件 | 実装・検証先 | 状態 |
|---|---|---|
| 移動／捕獲各2案、採用音の容量・波形 | `scripts/render-game-sounds.mjs`、同じ生成処理を使う`audio/waveform.ts` | Linux生成・試聴待ち |
| 正常着手1回、不正手／stale AIは0回 | `GameStore.subscribePresentation`、`store-presentation.test.ts` | 実WASMの移動・捕獲・打ち・成り・王手・投了の軽量単体が成功 |
| 捕獲・成り・王手・終局の優先、人間側捕獲・勝敗 | `audio/cues.ts`、`sound-cues.test.ts` | 手書き期待値で成功 |
| ミュート・音量保存・120ms制限・最大2音・重複抑止 | `audio/player.ts`、`sound-player.test.ts` | 軽量単体が成功 |
| 音声／storage拒否、非表示、復帰、遅い試聴の取消 | `sound-player.test.ts`、`sound-e2e` | 単体成功、実ブラウザ待ち |
| 開始操作と一つのContext、StrictModeの解放 | `useGameSound.ts`、実ブラウザのContext数・出力graph | 実ブラウザ待ち |
| 390／768／1440pxの44pxボタン・設定 | App、既存表示設定、`sound-e2e` | UI単体成功、寸法・画像待ち |
| Chromium／WebKit、実Safari、公開配信と回帰 | `.github/workflows/web-sound.yml`、通常main CI | 未実行 |

Macでは編集・軽量単体・型・lintと既知バグ注入の検出確認のみ。音の合成・音量／波形検査・実ブラウザE2Eと重い回帰はLinuxで行う。実スマホは未確認であり、390px表示やLinux WebKitをiPhoneの実機検証と読み替えない。

音量設定は端末内のlocalStorageだけに保存する。SEのための音声録音・マイク権限・外部送信・新規GPU・学習は不要。E2Eは既存の収集API制御を使い、本番D1へ合成対局を残さない。
