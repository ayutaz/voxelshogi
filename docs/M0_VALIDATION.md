# M0 残件の検証記録

対象: main `e3f7f7a` からの作業ブランチ `chore/finish-m0-validation`。2026-10-25。

## PR と取り込み制御

[PR #2](https://github.com/ayutaz/voxelshogi/pull/2) は必須7チェックの成功後、保護を迂回せず squash merge した。main は `e3f7f7a392d58ebc167d3f058eaa2f35b2f0f6cc`。未完了時の merge 拒否と、成功時の通常取り込みの両方を確認済み。

- 通常 CI: [40181542610](https://github.com/ayutaz/voxelshogi/actions/runs/40181542610)
- CodeQL: [40181542576](https://github.com/ayutaz/voxelshogi/actions/runs/40181542576)
- 品質計測: [40181542587](https://github.com/ayutaz/voxelshogi/actions/runs/40181542587)
- 統合後の本番公開: [40183599117](https://github.com/ayutaz/voxelshogi/actions/runs/40183599117) を追跡中。

fork PR の実検証は未完了。CLI で利用できるログインは元リポジトリ所有者の `ayutaz` のみ。別の所有先が必要なため、利用してよい組織をユーザーへ確認中。別名の個人所有fork作成APIも、新しい永続的な公開リポジトリの具体的な作成先・名前・公開範囲の承認がないとして自動承認レビューに拒否され、実行されていない。所属しているだけの組織に検証リポジトリを作成しない。Dependabot PR の成功や YAML 上の制限で、この実検証を代用しない。

## 本番を変更しない復旧訓練 — 完了

公開検証が成功した旧 run の成果物を選び、再ビルドせずローカルの loopback で配信した。

| 記録 | 値 |
|---|---|
| 成果物を取得した run | [40170836102](https://github.com/ayutaz/voxelshogi/actions/runs/40170836102) |
| commit | `0e29eb42229ef111494d8d5b73f254729e4df38f` |
| Cloudflare version ID | `afe83bf7-97c2-4f4f-94b5-7f3ab04d0337` |
| metadata artifact | `production-0e29eb42229ef111494d8d5b73f254729e4df38f` |
| 配信 artifact | `web-dist` |
| ローカル配信先 | `http://127.0.0.1:4181` |
| 実ブラウザの検証 | Chrome E2E 6件成功（9.8秒）。配信 SHA、初期表示、人間先手・後手のAI対局、undo、AI観戦、棋譜入出力 |

`deployment-info.json` の commit と `web-dist/build-info.json` が一致した。対象 SHA を `E2E_COMMIT` に指定して、現在のリポジトリの6件を実行した。本番 Worker・デプロイ履歴は変更していない。これは計画どおり旧成果物を隔離配信する訓練であり、Cloudflare の本番 rollback コマンド自体を実行した記録ではない。

再現手順（取得先は新しい一時ディレクトリを使う）:

```bash
gh run download 40170836102 -R ayutaz/voxelshogi -n web-dist -D /tmp/voxelshogi-recovery/web-dist
gh run download 40170836102 -R ayutaz/voxelshogi -n production-0e29eb42229ef111494d8d5b73f254729e4df38f -D /tmp/voxelshogi-recovery/production
# commit / version / run と build-info.json を照合した後、別ターミナルで配信
pnpm --dir apps/web exec vite preview --outDir /tmp/voxelshogi-recovery/web-dist --host 127.0.0.1 --port 4181 --strictPort
E2E_BASE_URL=http://127.0.0.1:4181 E2E_COMMIT=0e29eb42229ef111494d8d5b73f254729e4df38f pnpm --dir apps/web e2e
```

## 変異テストの生き残り分類

以前の調査は core の全ファイルではなく、`piece.rs`・`state.rs`・`zobrist.rs` の232変異が対象だった。元の結果は199 caught、18 missed、15 unviable、timeout 0。ビルド不能は検出成功に数えない。

同じ18件を main `e3f7f7a` の86テストで再実行した結果は9 caught、9 missed。以前追加した6テストの効果を確認した。さらに `tests/state_contracts.rs` の6テストを追加し、残る振る舞いの変化7件が実際にテスト失敗になることをコピー上で確認した。製品コードの変更はない。正常コードの Rust 92テスト、Clippy が成功。

| 以前の missed | 件数 | 分類・検証 |
|---|---:|---|
| 駒index（0/1）、成り状態、駒名（空/xyzzy）、エラー表示、持ち駒数（0/1）、全種類を持つ場合の駒打ち | 9 | 前回追加したテストで caught と再確認 |
| `check_move` の強制成り条件から `!` を削除 | 1 | 両色の歩・香・桂の行き所のない段への移動を、成りあり・なしで検証して caught |
| `is_legal` を常に true / false にする | 2 | 合法・不合法・終局済みの各入力を公開APIで検証して caught |
| 後手の連続王手の判定分岐を削除 | 1 | 両色の連続王手と繰り返し前の1手を含む局面で、王手側の敗北を確認して caught |
| `play` を状態を更新しない `Ok(())` にする | 1 | 手書きの捕獲・成り・持ち駒・手番・手数と、不合法時の非更新を検証して caught |
| 持ち駒ハッシュの XOR を OR / AND にする | 2 | 全7持ち駒・両所有者・両手番について、Zobrist の XOR 合成則で caught |
| 千日手区間の開始を `first + 1` から `first * 1` にする | 1 | 同値変異。first自身と現在の局面は同じ盤面・手番・王手状態。末尾に既に含まれる値を再度含めても `all` / `any` は変わらない。ハッシュ衝突の扱いは元実装と同じ |
| 千日手判定の存在確認 `.any` の手番比較を `==` から `!=` にする | 1 | 同値変異。履歴は合法着手ごとに手番を交代し、4回目の同一手番の出現区間には両方の手番が必ずある。どちらを検索しても `any` は true。王手を判定する `.filter` は変更されない |

同値2件を caught として数えない。全232件の再調査と、core 全体の週次・手動ジョブは別の範囲として結果を記録する。

### 継続実行での同値変異の扱い

`scripts/ci/mutation-report.mjs` が全体調査の出力を照合する。変異を生成対象から除外せず、完了した baseline、空でない inventory と全結果の1対1対応、各変異の build/test 結果を確認する。未知の生き残り、timeout、途中終了、欠落したテスト結果、ツール版の変更は失敗とする。ビルド不能は unviable のままで、caught に含めない。

同値2件は `scripts/ci/equivalent-mutations.json` に理由と対象ソース全体の SHA-256 を保存し、完全一致したものだけ equivalent に分類する。M1等で対象ソースが変わった場合は同値の根拠を再確認する。集計を `review.json` として raw report と一緒に保存する。cargo-mutants の終了コード2（生き残りあり）はこの照合を通った場合だけ成功とする。

集計処理は RED を確認後、6テストが成功した。ソースハッシュ照合を無効にする変異もテストが拒否した。CI制御用テストは計26件。
