# M6のモデルと観戦制御

AI同士の観戦を主用途、人間対AIを補助用途として、[モデル用Worker](M6_WORKER.md)を既存の観戦制御へ接続する。人間同士の対局は追加しない。現在はroutingと制御API・解析表示の分岐を実装した段階で、モデルフォルダー選択、両AIの設定画面、条件付き棋譜保存、実モデルのarena E2Eは未完了。[M6計画](M6_PLAN.md)の完了とは区別する。

## モデルを識別する

`ModelSeat`はローカルで読み込んだ入力の`sourceId`、model ID・manifest hash・精度・backend、HF repo／固定revision・コードcommit・ライセンスを持つ。フォルダーを選び直した場合は同じmodel hashでも新しいsourceIdを付ける。古いsessionを流用して新しいFileの検査を省略しない。

`ArenaClient`は実際にAIとして選択した最大2席だけを保持し、同じsource・精度・backendなら1つのclientを共有する。通常のEasy／Normalは従来のSearchClientへ送り、モデル用コードはモデル着手の要求時にだけdynamic importする。入力のFile metadataと実行条件は非同期処理の前にコピーする。人間に切り替えた席や外したモデルのclientを解放する。

## 着手と中断

`ArenaController`はモデル選択を設定の識別キーへ含め、変更時には保留中の要求を中断する。同じ盤面でも、モデル・精度・backend・入力sourceが変われば古い応答を使わない。受け取ったmodel条件も選択中の条件と照合してから、GameStoreの局面照合付き着手を呼ぶ。モデルが未選択・未対応・失敗の場合、Normalへ暗黙に切り替えない。

1手送り・一時停止・速度変更・履歴表示の制御を共有する。入力中やdynamic import中の停止では、遅れてできたclientをdisposeし、Workerの推論を開始しない。古い処理のfinallyが新しい保留状態を消さないようにする。既存の探索結果とモデルのPolicy／Value・実行条件は型を分け、モデルに探索ノードや駒得の数値を付けない。

## 検証

Macではfake store／clientを使う新規17テストで、先後のモデル振り分け、source再選択、精度別session、中断と遅延完了、設定違いの拒否、Normalへのfallbackなしを確認した。Rust・モデル計算は実行しない。新規11 Web変異と、モデル用Workerの成果物欠落を検出する2配信制御変異も検出済み。ビルド・公開照合は実際のpolicy Workerファイルを必須にする。Web既知変異は107件になる。既存のNative/WASM制御テスト・全変異・E2EはLinux CIで確認する。

次は利用者が取得したモデルのフォルダー選択、各AIのmodel／精度／backend設定、条件付き棋譜保存、実ONNXのarena E2Eを追加する。その後も実学習・各変換版の評価・HF公開・物理GPUブラウザと公開URLの検証を別に完了させる。
