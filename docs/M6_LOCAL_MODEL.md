# M6の端末内モデル読み込み

HFから取得したモデルフォルダーの検査は実装済み。現在は学習済み3形式を公開catalogへ登録し、数値照合・Worker・観戦・実機検証まで完了している（[M6完了記録](M6_COMPLETION.md)）。以下は読込境界の仕様と初期実装時の検証記録。初期のテスト件数を現在の総数と混同しない。

## 目的とゴール

HFのmanual取得ゲートを守りながら、取得済みの実ONNXと同形式の照合入力／全出力をブラウザで使う。モデルの資格情報や重みをサイトへ送信せず、公開catalogでレビューしたmodel ID・manifest hash・ライセンス・元コード・固定Hub revisionに一致するものだけを観戦へ渡す。最終ゴールには専用Workerでの数値検証・合法手選択と、両AIのモデル切替・停止・解放・実機検証が必要で、この読み込み処理の成功だけでM6-5完了とはしない。

## 実装した境界

`apps/web/src/inference/local-model.ts`の`parseTrainedCatalog`は、承認済みのmodel ID・ライセンス・コードcommit、`voxelshogi/`配下のrepo・固定Hub revision、manifestとCard／LICENSEのbytes・SHA-256を読む。空catalogを許可し、未承認の成果物を自動登録しない。初期実装では学習済みモデルを登録しなかった。現在の配布・catalog登録と検証状態は[M6_PORTABLE](M6_PORTABLE.md)を参照する。

`indexLocalFolder`はdirectory pickerから来るFileのパス・サイズだけで一覧を作る。同じrootからの安全な相対パスに限定し、重複・不正なパス・過大な件数／サイズを拒否する。最大512ファイル、1ファイル64 MiB、合計512 MiB。モデルの本体はWorkerが必要になった時だけ読み、読み込み前のサイズと実bytes・SHA-256を検査する。中断済みなら読み込み前、進行中の中断なら読み込み・hash照合後に停止する。

`loadLocalModel`は最初にmanifest hashを照合し、その後で学習済みの来歴を検査する。教師36,894件の全split、valで選んだ完了epoch、正式評価60局、評価した重みのhash・コード・seed等を確認する。完全な学習契約は公開前のPython検査で確認し、ブラウザはレビュー済みmanifest全体のhashにも固定する。M3の既存parserは引き続き未学習だけを受け付ける。

CardとLICENSEは本体の利用前にhash照合する。全variantのONNXと、全fixtureの入力／各同形式出力が存在し、宣言サイズに一致することを確認する。その後は一覧にあるdescriptorと一致する要求だけを受け付ける。返された表示用metadataが書き換わっても、検査に使うdescriptorのコピーは変わらない。`.env`等の無関係なファイルは読まず、`fetch`も呼ばない。資格情報を含むフォルダーを転送する機能はない。

## 初期実装時の検証と、その後の接続

小さい不透明な文字列とメタデータだけで、hash改変、未承認catalog、教師・選択元の改変、不足ファイル、descriptor競合と変更、path traversal、サイズ上限、中断を検証する。fixtureの30,000／3,000／3,894という分割は架空であり、実教師のsplit集計ではない。モデル・Tensor・探索は実行しない。Macでは関連64テストとTypeScript／ESLintを確認し、新規9変異が実行済みassertionで検出されることを確認した。全59 Web変異と既存WASM／E2EはLinux CIに任せる。

初期実装後、この読込APIを専用Workerのsessionへ接続し、固定入力の全出力を同形式参照と比較した。そのsessionでRustの合法手へpolicyを絞り、手番側のcanonical IDで同点処理を行う構成を完成した。公開・実機の証拠は[M6完了記録](M6_COMPLETION.md)に集約する。
