# P5-3：150局比較の起動とSSH設定

## 目的と完了条件

固定した150局を外部Linuxで実行できる状態にする。起動API・鍵登録の成功だけで準備完了とはせず、実際のSSH接続、固定sourceのbootstrap、CPU／RAMとCUDAの検査を通してから対局を開始する。目標は引き続き4モデル各30局＋M1対照30局であり、今回の起動確認を対局数に含めない。

## 起動時に確認したこと

2026-11-04の[4試行の固定記録](experiments/p53-comparison-startup-2026-11-04.json)では、比較対局・bootstrap・新しい科学データの転送は0件だった。

- 実機59071179は、表面の`actual_status=loading`だけでは見えないDockerfile書き込みエラーを状態メッセージで確認し、解放した。
- 次の要求はHTTP400で拒否された。全件一覧で同じラベルが繰り返し不在であることを調べ、同じ要求は再送しなかった。作成していない実機の削除ACKは作らない。
- 実機59073662と59076895は起動したが、専用公開鍵を提示してもSSH認証が拒否された。専用鍵の事前登録、実機だけの関連付け更新、前者での1回の再起動でもアクセスは確立しなかった。両実機は解放した。

最後の全件確認では、このプロジェクトのVast.ai実機とCloudRift資源は0で、別作業の実機には触れていない。全26予約・US$106.5／承認済み200を保持する。4試行の各3.5は保守的予約であり、実請求額ではない。未予約は93.5。8局試行の完了・HF固定版は従来の記録を保持する。

## 起動処理の変更と検証

[公式create API](https://docs.vast.ai/api-reference/instances/create-instance)の`onstart`で、所有するCUDAコンテナの`/root/.ssh`と`authorized_keys`を準備する。[共通処理](../training/vast_rental_control.py)は専用公開鍵をshell用にquoteし、既存の鍵を保持して未登録の場合だけ追記する。directoryは700、fileは600にする。複数行の鍵を拒否し、秘密鍵・provider APIキー・HF tokenを送らない。M6とPhase5／6のVast作成処理へ接続し、予算・単価・source・所有照合・独立guard・重複作成の制約は維持する。

[小さいshell／fake-portテスト](../training/tests/test_vast_ssh_startup.py)では、宛先だけを一時directoryへ置き換えて実際のshellを2回実行する。手で用意した既存鍵＋専用鍵1行、700／600の権限を期待値にし、quoteを含むcommentがコマンドとして実行されないことも確かめる。fake providerに渡ったM6／research両payloadも同じfilesystemで確認する。新規7テストのREDから実装し、関連metadata139件が成功した。新しい5変異はすべて検出し、catalog455件のanchor一意性を確認した。全Linux CIは別に必要である。

この検証はshellと要求内容の検証であり、実GPUへのSSH成功や元の認証拒否の原因を確定した証拠ではない。関連CI成功後、別の有料単位を固定し、実SSH・bootstrap・host検査を確認してから150局へ進む。起動失敗を未完了対局やcutoffに変換せず、診断・実1／2／4GPUも未完了のまま保持する。
