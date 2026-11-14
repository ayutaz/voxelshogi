# Web SEの実装・公開確認

2026-11-15 JST。ユーザーの「4まで」に基づく[SE計画](WEB_SOUND_PLAN.md)の実行記録。実装[#199](https://github.com/ayutaz/voxelshogi/pull/199)は必須8件・関連CI成功後に通常merge済み。公開sourceは`ba9767aba9e282cdc259f461b7a9a79e93a17732`。公開ブラウザ検証は完了。物理スピーカーでの聴感・実スマホは未確認。

| 要件 | 実装・検証先 | 状態 |
|---|---|---|
| 移動／捕獲各2案、採用音の容量・波形 | `scripts/render-game-sounds.mjs`、同じ生成処理を使う`audio/waveform.ts` | Linux生成・10ファイルのhash一致、採用8音のWAV合計84,144 bytes |
| 正常着手1回、不正手／stale AIは0回 | `GameStore.subscribePresentation`、`store-presentation.test.ts` | 実WASMの移動・捕獲・打ち・成り・王手・投了の軽量単体が成功 |
| 捕獲・成り・王手・終局の優先、人間側捕獲・勝敗 | `audio/cues.ts`、`sound-cues.test.ts` | 手書き期待値で成功 |
| ミュート・音量保存・120ms制限・最大2音・重複抑止 | `audio/player.ts`、`sound-player.test.ts` | 軽量単体が成功 |
| 音声／storage拒否、非表示、復帰、遅い試聴の取消 | `sound-player.test.ts`、`sound-e2e` | 単体・候補・公開の実ブラウザで成功 |
| 開始操作と一つのContext、StrictModeの解放 | `useGameSound.ts`、実ブラウザのContext数・出力graph | Chromium／WebKitでContext 1個、実出力に非ゼロ信号 |
| 390／768／1440pxの44pxボタン・設定 | App、既存表示設定、`sound-e2e` | 両ブラウザで寸法成功、候補6画像を目視。設定内は縦スクロール |
| Chromium／WebKit、実Safari、公開配信と回帰 | `.github/workflows/web-sound.yml`、通常main CI | 候補・公開各22件成功。Safari 27.0.1で試聴WAVの再生状態と公開設定操作を確認 |

## 採用音と操作

移動・捕獲のA／B各2案を作り、周波数が低いAを採用した。移動80ms、捕獲130msで、捕獲は余韻を少し長くする。人間側捕獲140ms、成り170ms、王手220ms、中立終局360ms、勝敗各400msの計8音。初期音量35%、上部のスピーカーボタンでミュート、表示設定の「サウンド」で音量とテスト音を操作できる。

自作合成音のソースはApache-2.0、第三者の録音素材は使わない。同じPCM生成処理をJSに含め、必要時に生成・再利用するため追加の音源通信はない。84,144 bytesは試聴用PCM16 WAVの合計であり、ブラウザのFloat32メモリ使用量やJS転送量ではない。各WAVのSHA-256・長さ・ピークはLinuxの`samples.json`に固定した。

Safariの試聴ページではA／Bの再生ボタンから一時停止状態への遷移を確認した。これはデコード／再生操作の確認であり、物理スピーカーの音質・耳障りさ・Bluetooth遅延の聴感評価を証明するものではない。Aの採用は、短い木質音を控えめに鳴らす設計判断として記録する。

## 候補検証

- 軽量単体53件、型・lint、追加8件の既知バグ注入が成功。実WASMで受理された移動・打ち・捕獲・成り・王手・投了を検査した。
- [Linux Quality](https://github.com/ayutaz/voxelshogi/actions/runs/43628379282)で全227件のWeb変異、coverage、既知回帰が成功。後続変更はE2Eの操作順・設定・証拠保存だけで、製品ソースは同じ。
- [最終候補のWeb sound](https://github.com/ayutaz/voxelshogi/actions/runs/43632250539)：source `ca65b9bd6acfcd28ec858a6d60827a8608b73096`、Chromium／WebKit各11件、計22件成功、retries=0。各テストの配信SHA一致を要求した。
- 実AudioContextの出力へAnalyserを接続し、試聴・捕獲・人間と実Easy AIの応答で非ゼロ信号を確認。captureは1音、人間とAIは2着手2音、開始前／音声拒否／検索取消は0音。タブ非表示は状態を模擬しており、OSの実バックグラウンド試験とは区別する。
- artifact `14128836447`のZIP SHA-256は`24c6b1fbc9487847853ddb1979d35a19d622e997a4c5113ba13ff647c013d0be`。22件の測定JSON、10試聴WAVの全hash、6サイズ画像を含む。小さい完成物と記録だけをMacへ取得した。

最初の候補は30／33件成功で、終局パネルに隠れたメッセージを先に閉じる履歴テストが失敗した。パネルを先に閉じ、設定の重複Chromium projectも解消した。次の候補では、捕獲確認中に実AIが応答する競合があった。着手のReact更新を待つmicrotaskを挟んで同じbrowser turn内で一時停止し、2手目・一時停止状態・捕獲1音の期待値を維持して解消した。失敗を再試行成功で隠していない。

## 公開とSafari

[main CI](https://github.com/ayutaz/voxelshogi/actions/runs/43633234278)・[Security](https://github.com/ayutaz/voxelshogi/actions/runs/43633234292)は成功。Python全8 shardとWeb全227変異を含む統合検証後に公開した。Cloudflare versionは`f4a4f1e0-49d2-4cdf-ab27-2d1a0c8cb069`、`build-info.json`は公開sourceと一致した。

同じmain runの公開UI 53件、カメラ／探索回帰3回、モデル6件はすべて成功し、配信59ファイルと匿名S gatewayの3メタデータのhashも一致した。モデルの固定配布revision `6ab524574d36536348dbe323a2b779b9cebe37ed`は維持している。

[公開Web sound](https://github.com/ayutaz/voxelshogi/actions/runs/43635157136)は同じsourceの本番URLへ接続し、Chromium／WebKit各11件、全22件が成功した（retries=0）。全テストで`build-info.json`の一致を要求。捕獲は両ブラウザで1音、実出力peakは両方0.078508。人間と実Easy AIの2着手は各2音・Context 1個、peakは0.055020／0.088116だった。artifact `14129687816`のZIP SHA-256は`ed7ccb84b9e3f1d434129e8fd701440c37df41efd94e71eeb1b7dc5cc1126018`。公開の6画像も目視し、音量・試聴・閉じる操作の見切れや横溢れはなかった。[44件の候補／公開測定と素材hashの固定記録](experiments/web-sound-public-20261115.md)を保存した。

Macの実Safari 27.0.1でも公開URLを開き、2D表示へ切り替え、試聴ボタン、音量35%→50%、ミュートで試聴を無効化、reload後のOFF／50%保持、ヘッダーでONへ戻す操作を確認した。対局は開始せず、Macで探索・モデル推論を実行していない。これは実Safariの操作確認であり、Linux WebKitの自動テストや物理スピーカーの聴感確認とは別の証拠である。

Macは編集・軽量単体・型・lint・既知バグ注入の検出確認と、短い完成素材の再生／公開SafariのUI操作だけに使用した。音の合成・音量／波形検査・自動ブラウザE2Eと重い回帰はLinuxで行った。実スマホは未確認であり、390px表示やLinux WebKitをiPhoneの実機検証と読み替えない。

音量設定は端末内のlocalStorageだけに保存する。SEのための音声録音・マイク権限・外部送信・新規GPU・学習は不要。E2Eは既存の収集API制御を使い、本番D1へ合成対局を残さない。
