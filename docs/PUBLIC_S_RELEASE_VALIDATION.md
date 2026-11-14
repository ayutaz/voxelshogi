# 申請不要の学習済みS：公開確認

本書はsource `7b364c9`時点の公開・動画の固定記録。後続のWeb SEと現在の公開確認は[SE検証記録](WEB_SOUND_VALIDATION.md)を参照する。モデルの固定版は維持している。

2026-11-15 JST。**公開・最終動画・確認を完了。** 実装[#192](https://github.com/ayutaz/voxelshogi/pull/192)、検証修正[#193](https://github.com/ayutaz/voxelshogi/pull/193)、同一origin配信[#194](https://github.com/ayutaz/voxelshogi/pull/194)、隔離コピー修正[#195](https://github.com/ayutaz/voxelshogi/pull/195)を必須8件・関連CI成功後に通常mergeした。公開sourceは`7b364c9ad693c35d00ca8edf1c428f19658b8d04`。

## HFと実モデル

[S推論用repo](https://huggingface.co/voxelshogi/voxelshogi-transformer-s)はpublic・取得gateなし・Community OFF。固定版は`6ab524574d36536348dbe323a2b779b9cebe37ed`。Model Cardは日本語3,035 bytesへ簡潔にし、教師一致率を勝率と区別した。Apache-2.0とデータの帰属、モデルの制約は維持する。

[Linux検証](https://github.com/ayutaz/voxelshogi/actions/runs/43598286857)で、全37ファイルを認証なしで取得してbytes／SHA-256が一致した。独立したproofのSHA-256は`d8f80391dc6e1ab34e6e1edf9e7ae3a3d9db7c5550c103716d0a9736b4861173`。期待値は[公開plan](../export/public-s-release.json)の既存固定hashを使い、Card以外の元ファイルは変えていない。

同じLinux実ブラウザで、SのFP32／FP16重み／INT8重みをそれぞれ自動取得し、人間側の一手に合法な応答が返ることを確認した。全4局面の同形式参照出力・実CPU provider・選んだ形式と保存棋譜を検証し、モデル準備中の操作／中断、破損時にNormalへ代替せずエラーになることも成功した（全5件）。390×844の3形式の画面を保存した。実スマホや新しいGPU計測ではない。

実モデル5件は候補source `7ff599a`のPR merge tree `6b553f0f17ff78db6029e8baf2fe8fcf0fc93262`で実行した。当時の#192統合source `417b286`との`apps/web`・`crates`・`export`の差分は0だった。公開確認では配信SHA・catalog・ファイルhashと公開UIのE2Eを併せて確認し、候補localhostの実対戦を公開ドメインでの再実行と読み替えない。

## CIと公開

候補の必須8件と関連CI、CodeQLの集約チェックが成功して通常squash mergeした。
[CI](https://github.com/ayutaz/voxelshogi/actions/runs/43598272255)・[Security](https://github.com/ayutaz/voxelshogi/actions/runs/43598272256)・[Quality](https://github.com/ayutaz/voxelshogi/actions/runs/43598272264)。省略対象の週次検証は実行済みとしない。

最初の[main CI](https://github.com/ayutaz/voxelshogi/actions/runs/43599508038)は、Python変異の隔離環境にM6の公開記録がないことと、Webの`human-first-model-seat`指定が旧コードを指していることで失敗した。Gateがデプロイを停止し、失敗を無視した公開は行っていない。
記録ファイル2件の明示コピー、隔離環境で実Card planを準備する独立テスト、変異指定の更新を行った。全Python883件・Web215件の指定も軽量に検査し、曖昧・欠落0。手動の既知バグ注入は一時コピーで検出し、各復元後の正常系を確認した。後続の最終mainでは全8shard・Web219変異・coverageが成功し、Gateとデプロイも成功した。
公開Sのworkflowは手動実行で本番URLを直接検証でき、全ケースの開始時に期待した配信SHAを要求する。データ保存APIの契約は変更しておらず、[以前の実ブラウザ→D1照合](ARENA_RELEASE_VALIDATION.md)を保持する。

## 公開後に見つかったCORSと配信の修正

[#193の事前深いCI](https://github.com/ayutaz/voxelshogi/actions/runs/43601508565)と、統合後の全8shard・Quality・Securityは成功した。続く[main run](https://github.com/ayutaz/voxelshogi/actions/runs/43602932972)では配信自体は成功し、公開E2Eは50成功・3失敗だった。失敗は公開originからHF manifestを読む際のCORSエラーで、localhost候補には出なかった。後のHTTP再確認では両originに許可ヘッダーが返ったため、恒久的なorigin拒否とは断定しない。

公開ブラウザは`/api/models/s/<固定HF版>/...`を使い、Cloudflareが固定Sの34推論ファイルだけを取得・キャッシュする。repo・revision・パスはコードの許可リストから選び、Cookie／Authorizationを渡さず、checkpoint・dataset・任意URLは拒否する。ブラウザのbytes／SHA-256と同形式の全参照値の検証は維持する。ローカル開発はHF直接取得を残す。

マージ前にLinuxの実WorkerでCard・manifest・LICENSEの匿名hashを確認した。デプロイ後もこの3件を確認してから公開E2Eを進め、S5 E2Eを本番URLで実行した。最終動画も本番サイトを直接撮影し、試験用の収集APIだけを置き換えてD1に合成棋譜を残していない。[最終main CI](https://github.com/ayutaz/voxelshogi/actions/runs/43609887815)と[Security](https://github.com/ayutaz/voxelshogi/actions/runs/43609887833)が成功。公開UI 53件・カメラ3回・未学習モデル6件、配信59ファイルとgatewayの3メタデータhashが一致した。Cloudflare versionは`0de0b3ef-f816-4dea-bdf5-5ca65c15fd37`。

## 公開URLでのS対戦

[本番S検証](https://github.com/ayutaz/voxelshogi/actions/runs/43611290056)は公開URLへ接続し、各ケースの配信SHA一致を要求して全5件が成功した（40.5秒）。FP32／FP16重み／INT8重みで、人間側382→373への合法な実モデル応答、全4参照局面・CPU provider・形式と棋譜を確認。中断で遅い着手を防ぎ、破損した重みでは代替着手を行わない。全37ファイルの匿名bytes／hash照合も同runで再成功した。

390×844の3形式画像を目視し、盤・形式ラベル・主要操作の見切れなし。これはLinux Chromiumの狭幅表示であり、実スマホ操作や新しいWebGPU性能の検証ではない。モデル・ブラウザ通信は実物、収集APIだけは制御しD1へ合成棋譜を残していない。既存の実公開ブラウザ→D1照合は前回の証拠として保持する。

## 動画

[候補制作](https://github.com/ayutaz/voxelshogi/actions/runs/43598286617)で、15秒本編の11〜15秒を「開発したAIと、あなたが対戦。」へ更新し、実際に人間側から指した一手とSのINT8重み版の応答を別棋譜で証明した。0〜11秒のEasy観戦をSの棋力映像とは説明しない。

候補の全31納品ファイルhash、両棋譜のRust再生、全編デコードと境界検査が成功。切替・字幕・2D盤と390pxのS画面を目視した。最終公開版も制作・確認済み。以下を納品物として使用する。

### 最終納品

[最終動画run](https://github.com/ayutaz/voxelshogi/actions/runs/43611290885)は公開originを直接撮影し、appCommitと配信SHAが同じ`7b364c9`、candidate=false。15秒・1080×1350・H.264・yuv420p・30fps、冒頭A／Bは各3秒。全編デコード・2棋譜のRust再生・境界検査、全31ファイルのbytes／hashが成功した。

本編は`runs/public-s-release/final-7b364c9/video/demo-main.mp4`（1,733,162 bytes）。冒頭候補は`hook-a.mp4`／`hook-b.mp4`、ポスター／OGPも同じフォルダー。21画像を個別に目視し、字幕・URL・盤・操作の見切れ／重なり、切替途中のCanvasなし。自動framingの目視フラグは変更せず、別receiptへ確認を記録した。全450フレームの目視、実スマホ・X上での再生・拡散実績は未確認。

[固定したrun・全hash・目視記録](experiments/public-s-final-20261115.md)。動画は7日保持のCI artifactと、上記のMac完成物に保持する。モデル・checkpoint・未編集録画はMacへ取得していない。文書のみの最終PRでは再デプロイを省略し、公開版と動画のSHAを維持する。

## 履歴と範囲

初回のCard誤配置と元FP32復元は[経緯](PUBLIC_S_ACCESS.md#cardの誤配置と復元)を保持する。失敗HF版はWebへ配布していない。
データセット・学習再開state・Mのmanual gateは維持する。新規GPU・学習・データ生成は0。X投稿は行っていない。

追加の失敗履歴：`47a019c`の[main run](https://github.com/ayutaz/voxelshogi/actions/runs/43607765418)では、新しい設定テストが隔離環境の`playwright.config.ts`を読めずbaselineで停止し、デプロイも止まった。#195で明示コピーを1件追加し、[事前全219変異](https://github.com/ayutaz/voxelshogi/actions/runs/43608922095)と最終mainの再成功を確認した。アプリや検査の成功条件は変えていない。
