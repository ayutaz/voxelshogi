# デプロイ（Cloudflare Workers Static Assets）

## 構成

- `apps/web/wrangler.jsonc`: Worker 名 `voxelshogi`。`dist/` を静的アセットとして配信し、SPA へフォールバックする。Worker スクリプトはない。
- `apps/web/public/_headers`: `/assets/*` を immutable キャッシュにする設定と、基本的なセキュリティヘッダー。
- 公開 URL: `https://voxelshogi.<account-subdomain>.workers.dev`（独自ドメインは後で検討。ユーザー決定）。

## 自動デプロイ（GitHub Actions）

`.github/workflows/ci.yml` の流れは次のとおり。

1. `rust`: fmt、clippy、test
2. `web`: WASM のビルド、型チェック、Vitest、ビルド、Playwright
3. `deploy`: main への push 時のみ実行。`web` のビルド成果物で `wrangler deploy` を行い、スモークテストをする

### ユーザーに行ってほしい準備

1. Cloudflare ダッシュボード → My Profile → API Tokens → Create Token で、「Edit Cloudflare Workers」テンプレートからトークンを作成する。
2. GitHub リポジトリ → Settings → Secrets and variables → Actions で、次を登録する。
   - Secrets: `CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`
   - Variables（任意、スモークテスト用）: `WORKERS_SUBDOMAIN`（`<account-subdomain>` の部分）
3. Settings → Environments で、`production` 環境を作成する（承認ルールを付けることもできる）。

Secrets が登録されていない間は、deploy ジョブは「skipped」の notice を出して成功扱いになる。

## 手動デプロイ（ローカル）

```bash
cd apps/web
pnpm wasm && pnpm vite build
CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... pnpm deploy   # pnpm dlx wrangler@4.152.0 deploy
```

## 今後の拡張（Phase 4 以降）

- 25MiB を超える ONNX Runtime の wasm やモデルは、R2 とカスタムドメインから配信する。`r2.dev` は開発用で、レート制限がある。
- マルチスレッド WASM を使う場合は、`_headers` に COOP/COEP を追加する。
- 詳細は `docs/TECH_STACK_RESEARCH.md` §3.4 と §4、`docs/COST_ESTIMATE.md` §5。
