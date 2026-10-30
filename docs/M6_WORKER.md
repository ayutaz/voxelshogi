# M6のモデル用Worker通信

学習済みモデルの端末内読込と数値検証付きsessionを専用Workerへ接続し、公開catalog・観戦UI・実GPUまで検証済み（[M6完了記録](M6_COMPLETION.md)）。catalogは最終HF revisionを固定しており、空ではない。以下は通信・中断・配信の仕様と初期実装時の検証記録。

## ファイルと実行先

`PolicyClient`はmodel ID・manifest hash・精度・backendと、検証済みmanifestのfixture名へ固定する。最初の要求だけFileと明示した相対パスをWorkerへ渡し、その後は同じWorker／sessionを再利用する。main側はFileの`arrayBuffer()`を呼ばない。[File APIのシリアライズ仕様](https://www.w3.org/TR/FileAPI/#file-section)は非標準の`webkitRelativePath`の引継ぎを保証しないため、Workerでは明示したパスから検査用のadapterを作る。ブラウザ内部でのコピー量やメモリ使用量は実測対象とし、ゼロコピーとは主張しない。

Workerは同じoriginの固定URL `/models/m6/catalog.json`を自分で取得し、承認済みIDとhashを照合する。要求からcatalog／runtimeのURLや承認フラグを受け取らない。HFの資格情報は不要で、catalogはcredentialsなし・redirect拒否で取得する。ファイルの一覧・manifest・Card／LICENSEを照合した後、既存M3の配信用indexからORT runtimeのdescriptorだけを読む。M3の重み・モデル参照は取得しない。モデル本体と照合入力／全出力は利用者の選択したFileから読む。

## 応答の採用と中断

すべての進捗・結果・エラーをrequest IDと局面のrevision／cursor／hash／手番／ruleset、model ID／hash／精度／backendに結び付ける。結果には同じsessionの全fixtureの数値照合と実行providerの証拠を付ける。Clientは期待するfixture集合、誤差基準、全出力の要素数、provider、Valueとcanonical行動IDも検査し、不完全な証拠や形式違いを採用しない。実際の着手は後続arena controllerで現在の局面・設定と再照合する。

同時要求を拒否し、初期化済みWorkerへ別のmodelやファイルを混ぜない。中断・通信失敗・形式違いではWorkerを終了し、保留中のPromiseを拒否する。終了済みWorkerの遅れたcallbackや別IDの重複応答は、次の要求へ作用させない。入力のFile一覧とmetadataもコピーして保持し、呼び出し側の後からの変更を取り込まない。

Worker内部の通常失敗はsessionをdisposeしてエラーとして返す。初期化中のキャンセルでsessionが遅れてできても、指し手推論へ進めず解放する。解放そのものが失敗した場合も成功にはせず、cleanup失敗を含むエラーを返してClientのWorker終了へつなぐ。kernel処理やブラウザの実メモリ解放の挙動は、実機で別に確認する。

## catalogの配信と取得ゲート

`apps/web/public/models/m6/catalog.json`だけをCloudflareへ配信する。ビルドはM6用ディレクトリへ重み等が混ざっていないことを確認し、catalogのbytes・SHA-256を`inference-build.json`へ記録する。catalogは`no-store`、hash付きJS／WASMは従来のimmutable配信とする。公開照合でもCIでテストしたmanifestとcatalogの実bytes・SHA・cache方針を確認する。HFのpublic/manualを別の重みURLで迂回しない。

## 初期実装時の検証と、その後の完了

MacではFileの小さい文字列fixtureとfake portsで、通信・中断・再利用、型／局面／形式／数値証拠の改変、固定catalog URL、初期化失敗・cleanup失敗、配信hashを検証する。関連する純粋テスト157件と配信用Nodeテスト4件、新規Web16変異・配信制御3変異を確認した。Macでモデル・Tensor runtime・探索は実行していない。全96 Web変異と実WASM／既存E2EはLinux CIで検証する。

その後arenaの両AI選択へ接続し、停止・1手送り・速度・人間対AI・モデル切替と棋譜／実行条件の保存を検証した。フォルダーの再選択は同じmodel hashでも新しい入力として扱い、古いWorkerを流用して新しいFileの検査を省略しない。実ブラウザ・数値検証・実学習済みモデルと物理GPUの結果は[M6完了記録](M6_COMPLETION.md)に固定した。
