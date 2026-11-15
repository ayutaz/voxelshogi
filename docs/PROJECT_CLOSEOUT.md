# 公開・作業終了時の保存先

2026-11-15 JST。ユーザーからX公開済みの報告を受け、このプロジェクトの開発作業を終了する。投稿URL・実投稿本文の独立照合は行っていない。既存のデモと研究基盤を成果とし、棋力向上・Mの本比較やWeb配布の未達は[研究停止時点](RESEARCH_CHECKPOINT_20261112.md)の記録に保持する。

## GitHubに残すもの

- 公開コードと文書は[リポジトリ](https://github.com/ayutaz/voxelshogi)のmainが正
- 完成動画、告知文案、元BGM動画・確認画像、ローカルの過去履歴と未コミットUI試作は[公開時点の保存版](https://github.com/ayutaz/voxelshogi/releases/tag/publication-20261115)へ保管
- `historical-local-revisions.bundle`は、squash後にブランチが削除され通常のmain取得では戻らない過去の作業履歴を保存するGit bundle
- `ui-prototype.zip`は旧UI作業フォルダーの21ファイルの中間状態。現在の公開版へ取り込む変更ではなく、復元用の歴史資料
- `archive-manifest.json`に完成物・bundle・ZIPのbytes／SHA-256を記録。bundleを別の一時bare repoへ復元してGitの到達性を検査し、UI試作21ファイルはSHA-256とGit blob IDまで照合した

過去のローカル固有コミット398件・453 blobについて既知の認証情報パターンを確認し、検出0件。APIキー・秘密鍵・ローカルデータを公開用ファイルに混ぜていない。`node_modules`／WASM生成物への一時シンボリックリンクは保存対象外。

## モデル・データ・実行資源

HFの公開名前空間を読み取り確認し、モデル／学習状態7 repoとデータセット13 repoを確認した。[モデル](https://huggingface.co/voxelshogi/voxelshogi-transformer-s)は申請不要、それ以外の学習状態とデータのmanual gateは維持している。Macへ学習checkpointやデータセットを再ダウンロードしていない。

2026-11-15 02:08〜02:11 UTCのプロバイダー照会で、VoxelShogiラベルのVast.aiインスタンスは0件、CloudRiftのInitializing／Active／Deactivating状態のインスタンスは0件。他用途と明示されたVast.ai資源は変更していない。GPU制御workflowは手動起動で、自動で学習を再開しない。

公開アプリsource `e9b37d2f92254d6ac1031f7febb98a278d9400ea`の[main CI](https://github.com/ayutaz/voxelshogi/actions/runs/43665030525)と[Security](https://github.com/ayutaz/voxelshogi/actions/runs/43665030439)は成功し、配信SHAも一致した。

未統合の研究案#175／#176と依存更新PRはGitHubに保持する。研究案を公開版へ取り込んだり、追加研究・GPU利用を自動再開したりしない。

## ローカルフォルダーを削除するとき

プロジェクトの外に`~/Desktop/voxelshogi-archive-20261115/`を作り、公開用の完成物を`public/`、`.env`・プロジェクト専用Cloudflareログイン・終了済み実機の鍵・小さいローカル試料を`private/`へ退避した。非公開領域はディレクトリ0700・ファイル0600とし、GitHubへ送らない。

GitHubへの最終push・必須CI成功と保存版の照合後は、元の`voxelshogi`フォルダーを削除しても公開サイト・GitHub・HFの保存物は継続する。この終了作業では元フォルダーを削除しない。外側のアーカイブは保持する。

登録済みworktreeは96件あり、19件が実在、77件は一時フォルダーが既にない参照だった。実在する作業フォルダーは上記UI試作以外に未保存のソース変更がなく、依存・ビルド用リンクだけが残っていた。元の`.git`を削除すると一時worktreeのGit操作はできなくなるため、必要な履歴・試作を保存版から復元する。

再開時は通常どおりGitHubからcloneし、必要なモデル／データをHFから取得する。過去の中間状態が必要な場合だけbundleとUI試作を使う。公開サービスはCloudflareとHF上で動き、Macのフォルダーを実行環境にしていない。
