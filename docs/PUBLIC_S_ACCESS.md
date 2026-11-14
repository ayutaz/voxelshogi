# 学習済みSを申請なしで使う

2026-11-14のユーザー指示：「web版はモデルは誰でも対戦できるように」「huggingfaceも公開」「モデルカードは人間が読めるように簡潔に」。[承認範囲](../export/public-s-approval.json)。

## 目的とゴール

| 段階 | 目的 | 完了条件 | 状態 |
|---|---|---|---|
| 配布 | Sの取得申請をなくす | S推論repoだけpublic・gated=false・Community OFF。短いCardを公開し、固定版の全37ファイルをLinuxから匿名取得してhash一致 | HF再ログイン待ち |
| Web | 誰でも既存Sと遊べる | 「AIと対戦」からS・精度形式を選び、フォルダーなしで合法な応答。FP32／FP16重み／INT8重みを実ファイルで検査。中断・再試行を維持 | 実装・軽量検証中 |
| 映像 | 開発したAIと対戦できることを伝える | 実際のS対戦を含む動画に更新。冒頭3秒と安全な字幕領域を維持し、切替境界を含め再確認 | 未着手 |
| 公開 | 実際に使える状態を届ける | 必須8件と関連CI成功、通常PRマージ・デプロイ、公開URLで匿名S対戦を確認。新しい固定版と証拠を記録 | 未完了 |

学習・生成・追加GPUは再開しない。データセット、学習再開state、Mの研究保存repoのmanual gateは今回変更しない。旧Sの評価と重みhashは保持する。

## 利用方法

「AIと対戦」→相手のAI「学習済みS」→精度形式→「対戦をはじめる」。モデルはブラウザのWorker内で必要な形式だけ取得し、hashと4局面の同形式参照出力を検査する。ユーザーのログイン・HF token・手動フォルダー取得は不要。先後AIをSにして観戦する場合は「対局設定」で選ぶ。手元のフォルダー読み込みも引き続き利用できる。

実行先の既定はWASM（CPU）。FP16／INT8は重みの圧縮で演算はFP32。教師一致率は勝率ではなく、棋力向上は未確認である。

## 配布と検証

- 新Cardの原本：[public-s-model-card.md](../export/public-s-model-card.md)。来歴・詳細hash・旧評価へリンクし、数字を短く説明する。
- [専用のメタデータ更新](../training/public_s_release.py)は既存SのCardと取得設定のみを変更する。親HF commitを固定し、モデルをMacへstageしない。失敗時に別repoへ送ったり無制限に再試行したりしない。
- [全件匿名照合](../scripts/verify-public-s.mjs)と[実モデル3形式の対戦](../apps/web/public-model-e2e/public-s.spec.ts)をLinuxの`Public trained S` workflowで実行する。認証やモデルmockを使わない。対局保存APIだけは検証用応答にし、本番D1へ試験棋譜を残さない。
- Web catalogは検証済みHF revisionとCardの新hashへ更新する。manifestとONNXの既存hashは変更しない。未完了を配布済み・対戦成功と扱わない。
- MacのPython固定パッチ3.14.9は現在未導入のため、軽量な標準ライブラリ検証は利用可能な3.14.0で実行する。locked依存の全回帰はLinux CIで行い、lockを緩めない。
