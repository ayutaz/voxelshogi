# 観戦UI再設計の公開確認

2026-11-14 JST。[U2〜U6](design/ARENA_IMPLEMENTATION_PLAN.md)の確認記録。
実装PR [#187](https://github.com/ayutaz/voxelshogi/pull/187)は必須8件・関連CI成功、最新main・CodeQL重大0を確認して通常squash mergeした。
統合sourceは `dc0a95fa00d4957b2a4d2712f27a0f469a6c3a7b`。
mainの[CIと自動公開](https://github.com/ayutaz/voxelshogi/actions/runs/43576006078)、[Security](https://github.com/ayutaz/voxelshogi/actions/runs/43576006045)は成功。公開buildも統合sourceと一致した。**U2〜U6を完了。実ブラウザ→D1照合と公開版一致の最終動画も確認済み。**

## 候補とレビュー

- 最終候補 `24cd545e0b6cef8d4f61f5ef1799b7e520183bd5` の[Linux検証](https://github.com/ayutaz/voxelshogi/actions/runs/43575116945)はUI 53件、未学習モデル6件、Arena実モデル7件、カメラ3回、動画生成が成功。[最終画面の出典／hash](experiments/arena-final-ui-20261114.md)。
- 製品コードが同じ `b0931c6` の[品質検証](https://github.com/ayutaz/voxelshogi/actions/runs/43574179017)はcoverage・既知Web変異210件を含め成功。後続の差分はE2Eの操作順と文書だけ。
- [最終ソースレビュー](reviews/claude-code-arena-final-source-20261114.md)は重大／中0。[画像レビュー](reviews/claude-code-arena-images-20261114.md)の中1件はメッセージを閉じる操作で修正し、[再レビュー](reviews/claude-code-arena-image-fix-20261114.md)で解消した。[修正画像の出典](experiments/arena-review-fixed-images-20261114.md)。
- 390×844／768×1024／1440×900で横はみ出し・盤位置・主要操作の寸法、人間先後×Easy／Normalの開始と再対局、履歴・終局・モデル・中断を検査した。ソース／CI画像のレビューと実スマホの操作を区別する。
- 再レビュー時は終局E2Eが未完了だったが、その後の `24cd545` で3サイズとも成功した。メッセージを閉じた後の持ち駒欄と履歴・終局を最終候補画像でも確認した。

## 公開版と保存

公開URLに対するUI 53件・カメラ3回・未学習モデル6件が成功。同じrunから復元したWASMを使い、配信57ファイルのbytes・hash・MIME・cacheを照合した。
Cloudflare versionは `ba1151bf-307e-45f9-9091-f2a555a7e859`。[配備記録](experiments/arena-deployment-20261114.md)・[配信57ファイル](experiments/arena-public-distribution-20261114.md)。
mainではWeb変異・coverage・Python学習変異8 shardを含む通常の深いGateも成功している。

通常の公開E2Eは収集APIを制御し、大量の合成行を本番D1へ残さない。
別途、実公開ChromiumのNative fetchで人間の実着手→Easy応答→投了を行い、その1対局だけをD1から読んで本文・version・bytes・SHA-256を照合する。
検証行だけを削除し、残存0件を確認する。ユーザーの棋譜は取得しない。
新規201・延長／再送200・競合409・古いsnapshot無視・終局固定は合成HTTP対局で別に確認した。
[実HTTP・D1の記録](experiments/arena-storage-public-20261114.md)は全7要求・保存本文／bytes／hash一致・検証行の削除を確認済み。

[公開ブラウザの実保存](experiments/arena-browser-storage-20261114.md)も成功。通信をinterceptしないLinux Chromiumで5七V→5六V、実Easyの応答、先手の投了を実行し、全2手と結果をRust/WASMで再生した。
初手201・終局200、同じgameIdのversion 3・途中保存2回・本文1,052 bytes、SHA-256 `50b24ee961341e094d561c362acd9d737f7968e8d596cfbb5e10b1e0188fb046`を実D1と照合した。該当検証行の削除後は0件。
CI receiptの`d1ReadbackVerified=false`はCI単体の確認範囲として保持し、別の管理者readback receiptでtrueを記録した。収集行は`received_unverified`であり、今後の全ユーザー対局の合法性を保証するものではない。

## 最終動画

公開sourceに一致する15秒本編・3秒候補2本・ポスター／OGPをLinuxで制作した。
全編デコード、1080×1350／H.264／yuv420p／30fps、450／90 frame、全hashと実棋譜のRust再生を確認し、制作記録を固定した。
0秒から明るい9層盤、3秒以内に中央の実異層着手へ寄る。編集上の拡大をアプリの機能や性能として説明しない。

[最終run 43577744281](https://github.com/ayutaz/voxelshogi/actions/runs/43577744281)は成功。[全hash・ffprobe・目視の記録](experiments/arena-video-final-20261114.md)を固定した。
本編15秒、冒頭A／Bは各3秒、実異層着手は`415524`（V→IV）。Aを既定として、0秒の全9層→1.7倍の拡大で見せる。Bは1.95倍の代替案で、視聴者によるA/Bテスト済みとはしない。
Macには検査済み完成物約8MiBと小さい記録だけを保存し、エンコード／全編デコードはLinuxで行った。実スマホ再生・拡散数は未確認。
artifact `demo-video-dc0a95fa00d4957b2a4d2712f27a0f469a6c3a7b`は7日保持。完成物は作業端末の`runs/arena-redesign-final/dc0a95f/video/`にも保持する。未編集録画・モデル・profileは取得していない。
公開中のOGPは最終収録前に取り込んだ候補`ff33b0d`の実盤面画像。最終動画のOGP書き出しとは別ファイルとして扱い、同hashとは主張しない。

完了文書の後続PRはMarkdownだけで、再デプロイを行わない。main HEADが文書更新で進んでも公開アプリと最終動画のsourceは上記`dc0a95f`を維持する。

## 今回の範囲外

実スマホのタップ／Safari、全対応端末の長時間検証、一般棋力改善は未確認。
設定からAI条件を変えた直後は停止状態になり「再開」で続ける軽微な操作上の制約を保持する。
X投稿・技術記事の外部公開・追加GPU・生成・学習・M配布は実行していない。
研究停止とHFのpublic/manual・Community OFFは維持し、収集棋譜を学習やHFへ自動送信しない。

## 関連文書の現在地

README・CLAUDE・STATUS・ROADMAP、実装計画／進捗、自動保存仕様、動画計画／制作記録、未送信の告知文案を現行公開版へ更新した。
元の[問題整理](design/SPECTATOR_UX_REVIEW.md)・[承認モック](design/ARENA_MOCKUP.md)、[旧公開計画](PUBLIC_LAUNCH_PLAN.md)・[旧レビュー](PUBLIC_LAUNCH_REVIEW.md)・[保存導入前の調査](CLOUDFLARE_GAME_DATA_AUDIT.md)には、当時の記録という区別とこの最新確認への案内を付けた。
[M6の操作案内](M6_ARENA.md)・[取得済みモデルの入口](M6_PORTABLE.md)も現行UIへ合わせた。モデルhash・固定HF版・過去の性能／棋力・失敗やClaude Code回答原文は当時の証拠として保持する。
