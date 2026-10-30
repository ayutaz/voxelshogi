# M6のモデルと観戦制御

AI同士の観戦を主用途、人間対AIを補助用途とするモデル選択・操作・条件付き棋譜を実装済み。実学習・HF公開・公開catalog差し替えなしの実GPU48条件／40切替、3形式の着手・実モデルE2E7件・資源解放も完了（[M6完了記録](M6_COMPLETION.md)）。以下のPR #58〜#59等の記述・テスト件数は初期実装時の履歴で、現在の実機検証と区別する。人間同士の対局は追加しない。

## モデルを識別する

`ModelSeat`はローカルで読み込んだ入力の`sourceId`、model ID・manifest hash・精度・backend、HF repo／固定revision・コードcommit・ライセンスを持つ。フォルダーを選び直した場合は同じmodel hashでも新しいsourceIdを付ける。古いsessionを流用して新しいFileの検査を省略しない。

`ArenaClient`は実際にAIとして選択した最大2席だけを保持し、同じsource・精度・backendなら1つのclientを共有する。通常のEasy／Normalは従来のSearchClientへ送り、モデル用コードはモデル着手の要求時にだけdynamic importする。入力のFile metadataと実行条件は非同期処理の前にコピーする。人間に切り替えた席や外したモデルのclientを解放する。

## 着手と中断

`ArenaController`はモデル選択を設定の識別キーへ含め、変更時には保留中の要求を中断する。同じ盤面でも、モデル・精度・backend・入力sourceが変われば古い応答を使わない。受け取ったmodel条件も選択中の条件と照合してから、GameStoreの局面照合付き着手を呼ぶ。モデルが未選択・未対応・失敗の場合、Normalへ暗黙に切り替えない。

1手送り・一時停止・速度変更・履歴表示の制御を共有する。入力中やdynamic import中の停止では、遅れてできたclientをdisposeし、Workerの推論を開始しない。古い処理のfinallyが新しい保留状態を消さないようにする。既存の探索結果とモデルのPolicy／Value・実行条件は型を分け、モデルに探索ノードや駒得の数値を付けない。

## 検証

Macではfake store／clientを使う新規17テストで、先後のモデル振り分け、source再選択、精度別session、中断と遅延完了、設定違いの拒否、Normalへのfallbackなしを確認した。Rust・モデル計算は実行しない。新規11 Web変異と、モデル用Workerの成果物欠落を検出する2配信制御変異も検出済み。ビルド・公開照合は実際のpolicy Workerファイルを必須にする。Web既知変異は107件になる。既存のNative/WASM制御テスト・全変異・E2EはLinux CIで確認する。

## フォルダーと各AIの設定

「学習済みモデルを読み込む」で配布catalogだけを取得し、固定HF revisionへのリンクとフォルダー選択を表示する。manual取得承認はHFで受ける。ブラウザへ資格情報を入力させたり、重みをサイトへ送信したりしない。初期実装では公開catalogを空にした。現在の登録モデル・固定HF revision・取得条件と実機結果は[M6_PORTABLE](M6_PORTABLE.md)を参照する。

画面ではmanifestと小さいREADME.md／LICENSE／任意のNOTICEだけを照合する。通知文書は各1 MiB以下・最大3個に限定し、モデルを通知文書としてmain threadで読まない。重み・全参照値はAI開始時に専用Workerが検査する。フォルダーは最大4個、実行中のsessionは選択した最大2席に限る。先後のモデル・FP32／FP16／INT8重み版・WASM／WebGPUは独立に指定でき、変更時は停止する。非対応の形式や実行先は理由を表示する。読み込みの取消・パネルを閉じた後の古い完了も無視する。

選択中のモデルを外した席はNormalに戻して停止する。すでにEasy／Normalを選んだ席の難易度は、以前使ったモデルを外しても維持する。読み込み中にライブラリが変わった場合も、完了時は最新の親callbackへ渡し、古い一覧で外したモデルを戻さない。先後両席・遅延完了の回帰テストと3変異を追加し、Web既知変異は124件になる。

## 棋譜と実行条件

通常の「保存」は再読込用のRust棋譜JSON。「棋譜＋AI条件」は棋譜、表示cursor／局面hash、アプリcommit、現在の両席設定、表示cursorまでに実際に適用したAI着手の条件を含む別のJSONを保存する。model ID・manifest hash・精度・backend・HF repo／固定revision・モデル元コード・ライセンス、同形式の全出力照合と実provider、Value・時間を記録する。Easy／Normalには実際のseed・探索上限・完了深さ・ノード数を残す。

human／読込済みの手にはAIの出所を付けない。適用に失敗した応答と破棄した分岐の条件は除外し、新規対局・棋譜読込で記録を消す。後から設定を変えても過去の着手を上書きしない。保存要求時の局面と条件を先に固定し、build-infoの取得中に変わった設定を混ぜない。モデル用のFileや重みは保存JSONに含めない。条件付きJSONを再読込する場合は`record`を取り出すか、通常の「保存」のJSONを使う。

## 追加した検証

Macではモデル計算を行わず、対象の軽量7ファイル45テスト、追加12変異の実行済みassertionによる検出、型・lintを確認した。初回Linux CIはWeb326単体テストと119変異に成功したが、arena E2Eで着手前に停止した。ORT 1.31.1のnative profileは終了時まで記録を出力しないため、全参照局面を照合した後にprofilingを確定し、実providerを確認して同じsessionを対局へ使うよう修正する。profile確定を待つfakeで再現し、専用の2変異も追加する。Web既知変異は121件になる。

Linux CIの`Browser model inference (real WASM)`に6件のarena E2Eを追加し、3形式の先後別推論・全参照照合・合法棋譜・条件保存、準備中の3D操作と中断、破損ローカルONNX、GPUなし時の明示エラーとWASMを選んだ人間対AIを検証する。初回失敗を成功とは数えず、修正後の実ブラウザ検証を通してから取り込む。

profile修正後は3形式の推論・合法手と条件保存、中断・破損拒否・人間対AIが成功。残る自動観戦テストは開始局面の1行を着手に数えていたため、4着手には一覧5行を待つよう補正する。保存した棋譜のRust再生とAI条件の4件以上という検査は維持し、全6件成功まで取り込まない。失敗時の診断も、存在しないエラー表示を待たずDOMから即時取得する。

CIの試験パッケージはM3未学習モデルの実ONNX／参照値と**合成したM6のmetadata receipt**を使う。実学習をした証拠にはしない。Linux CI内の`runs/m6/browser-fixture`だけに生成し、Playwrightがcatalogを試験時だけ差し替える。公開catalog・公開配布物・artifact・HFには含めない。準備中の操作検証はWorker moduleの取得を待たせたもので、推論kernel実行中や物理GPUとの同時描画の性能測定とは区別する。

実学習・各変換版の評価・HF公開・物理GPUブラウザと公開URLの検証を別に完了させる。
