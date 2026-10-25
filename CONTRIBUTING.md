# 開発手順

## ブランチと PR

1. `git status` で既存の変更を確認する。main から新しい作業を始める場合は `git switch main`、`git pull --ff-only` の後、**変更前に** `git switch -c <種別>/<作業名>` を実行する。
2. 作業ブランチで変更・検証・commit を行い、`git push -u origin HEAD` で公開する。既存の変更を混ぜず、履歴の書き換えや force push は行わない。
3. main 向けの PR を作り、目的、変更後の動作、検証結果、残る制約を記載する。AI が作成した差分も内容を確認する。
4. 必須チェックがすべて成功し、最新 main に対する検証が済んでから GitHub の squash merge を行う（リポジトリで許可された取り込み方式）。main が進んだら `git fetch origin` と `git merge origin/main` で取り込み、再検証する。

main は PR 必須、force push・削除禁止、bypass なし。他者承認の必須数は0。チェックの失敗・中断・欠落を、保護の解除や管理者権限で回避しない。設定の正は `.github/main-ruleset.json`、確認記録は [CI_CD_PLAN.md](docs/CI_CD_PLAN.md)。

CI の状態取得は原則5分間隔とし、利用者への報告は状態が変わったときに行う。runner のキュー待ちとジョブの実行時間を区別し、待機だけを理由に実行中の workflow を中断・再実行しない。失敗を検知した後の原因調査や、取り込み直前の最終確認は必要に応じて行う。

## 実装と検証

- 仕様・ルールを確認し、テストを先に書いて RED を確認してから実装する。期待値は手計算か独立した参照実装で用意し、空の結果で通らないようにする。
- 新しいテストが対象のバグを検出することを、変異の注入で確認する。一時的な変異は成果物に残さない。
- ルール変更は `docs/RULESET.md` を先に更新し、互換性に応じて `ruleset_id` を変更する。進捗・完了条件は `docs/ROADMAP.md` に反映する。
- Python は `.python-version`（3.14系）を使い、依存が未対応の場合のみ3.13へ切り替える。さらに古い版が必要なら理由・対象・解消条件を記録する。
- 秘密情報を commit・ログ・会話・artifact に含めない。Cloudflare のローカル操作は `scripts/cf.sh` を使う。費用の発生する操作は見積もりと事前承認が必要。

変更に関連する検証を実行する。Rust、Node、pnpm、wasm-bindgen の版はリポジトリの固定値に合わせる。

```bash
cargo fmt --all --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked --workspace
node --test scripts/ci/*.test.mjs
actionlint
shellcheck scripts/*.sh

cd apps/web
pnpm install --frozen-lockfile
pnpm lint
pnpm wasm
pnpm typecheck
pnpm test
pnpm build
pnpm e2e
```

## PR と公開の自動チェック

PR では docs のみの変更でも、通常 CI、CodeQL、Rust/Web カバレッジ、既知の9変異の回帰検証を実行する。必須チェックは次の7件。

- `CI Gate`（lint、Rust、MSRV、WASM/Web/実ブラウザ E2E、依存監査、PR の dependency-review の成功を集約）
- `CodeQL (rust)`、`CodeQL (javascript-typescript)`、`CodeQL (actions)`
- `Rust core coverage`、`Web unit coverage`、`Known mutation regressions`

GitHub Actions が発行したチェックだけを受理し、CodeQL の error と high/critical セキュリティ警告も取り込みを止める。カバレッジは測定とレポートの保存を必須とし、一律の割合基準は設けない。全体の cargo-mutants 調査は週次・手動で行う。

PR・fork・Dependabot には production の Cloudflare Secrets を渡さず、本番 deploy は実行しない。main の push では統合後の通常 CI が成功した後、同じ run のビルド成果物を公開し、配信 SHA と公開 E2E を検証する。[デプロイと復旧手順](docs/DEPLOYMENT.md)
