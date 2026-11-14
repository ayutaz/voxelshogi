# 学習済みSを申請なしで使う

2026-11-14のユーザー指示：「web版はモデルは誰でも対戦できるように」「huggingfaceも公開」「モデルカードは人間が読めるように簡潔に」。[承認範囲](../export/public-s-approval.json)。

## 目的とゴール

| 段階 | 目的 | 完了条件 | 状態 |
|---|---|---|---|
| 配布 | Sの取得申請をなくす | S推論repoだけpublic・gated=false・Community OFF。短いCardを公開し、固定版の全37ファイルをLinuxから匿名取得してhash一致 | 全37ファイルの匿名hash照合成功 |
| Web | 誰でも既存Sと遊べる | 「AIと対戦」からS・精度形式を選び、フォルダーなしで合法な応答。FP32／FP16重み／INT8重みを実ファイルで検査。中断・再試行を維持 | 公開URLで全5 E2E成功。3形式と中断・破損時を確認 |
| 映像 | 開発したAIと対戦できることを伝える | 実際のS対戦を含む動画に更新。冒頭3秒と安全な字幕領域を維持し、切替境界を含め再確認 | 公開SHA一致の最終31ファイルhash・21画像目視成功 |
| 公開 | 実際に使える状態を届ける | 必須8件と関連CI成功、通常PRマージ・デプロイ、公開URLで匿名S対戦を確認。新しい固定版と証拠を記録 | #192〜#195を通常merge。公開CI・配信・実対戦成功 |

学習・生成・追加GPUは再開しない。データセット、学習再開state、Mの研究保存repoのmanual gateは今回変更しない。旧Sの評価と重みhashは保持する。

## 利用方法

「AIと対戦」→相手のAI「学習済みS」→精度形式→「対戦をはじめる」。公開モデルはCloudflareの同一origin経由で、ブラウザのWorker内へ必要な形式だけ取得し、hashと4局面の同形式参照出力を検査する。ユーザーのログイン・HF token・手動フォルダー取得は不要。先後AIをSにして観戦する場合は「対局設定」で選ぶ。手元のフォルダー読み込みも引き続き利用できる。

実行先の既定はWASM（CPU）。FP16／INT8は重みの圧縮で演算はFP32。教師一致率は勝率ではなく、棋力向上は未確認である。

## 配布と検証

- 新Cardの原本：[public-s-model-card.md](../export/public-s-model-card.md)。来歴・詳細hash・旧評価へリンクし、数字を短く説明する。
- [専用のメタデータ更新](../training/public_s_release.py)は既存SのCardと取得設定のみを変更する。親HF commitを固定し、モデルをMacへstageしない。失敗時に別repoへ送ったり無制限に再試行したりしない。
- [全件匿名照合](../scripts/verify-public-s.mjs)と[実モデル3形式の対戦](../apps/web/public-model-e2e/public-s.spec.ts)をLinuxの`Public trained S` workflowで実行する。認証やモデルmockを使わない。対局保存APIだけは検証用応答にし、本番D1へ試験棋譜を残さない。
- Web catalogは検証済みHF revisionとCardの新hashへ更新する。manifestとONNXの既存hashは変更しない。未完了を配布済み・対戦成功と扱わない。
- MacのPython固定パッチ3.14.9は現在未導入のため、軽量な標準ライブラリ検証は利用可能な3.14.0で実行する。locked依存の全回帰はLinux CIで行い、lockを緩めない。

## Cardの誤配置と復元

最初のHF commit `ae9e9fc4327b79391d1e76c1066e19aa6e42a710`では、手動変異検証のtimestamp型bytecodeが残り、Cardが`fp32.onnx`へ誤配置された。送信成功だけでは完了とせず、直後の匿名hash照合で検出した。この失敗版は使用しない。Web catalogが参照していた旧`f196c75236f0f0cfd028b91661b39a2c64ee448f`は無傷で、失敗版への切り替え・Webデプロイは行っていない。

自分の失敗receipt、全38パスのmetadata、誤配置されたCardのhash、元のFP32のLFS hashを確認し、1回の限定修正を実行した。モデルをMacへ落とさず、HF内の元LFS objectを参照して復元し、READMEを正しいパスへ保存した。修正版は`6ab524574d36536348dbe323a2b779b9cebe37ed`。元の公開版とのmetadata差分がREADMEだけで、Card／manifest／LICENSEの匿名bytes・SHA-256が一致した。全37ファイルの実bytes照合もLinux側で完了した。

再発防止としてCardの書き込み先をadapter内のREADMEへ固定し、公開実行では新しいbytecode領域を使う。手動変異3件はbytecode生成なしでやり直し、各復元後の正常系10テストも成功した。通常のCI変異ハーネスは従来から一時コピーと`PYTHONDONTWRITEBYTECODE=1`を使っており、今回の問題は手動検証側にあった。

完了した公開source・各run・最終動画の納品先は[公開確認](PUBLIC_S_RELEASE_VALIDATION.md)を参照する。
