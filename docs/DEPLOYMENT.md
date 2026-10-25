# デプロイ（Cloudflare Workers Static Assets）

## 構成

- `apps/web/wrangler.jsonc`: Worker 名 `voxelshogi`。`dist/` を静的アセットとして配信し、SPA へフォールバックする。Worker スクリプトはない。
- `apps/web/public/_headers`: `/assets/*` を immutable キャッシュにする設定と、基本的なセキュリティヘッダー。
- 公開 URL: **https://voxelshogi.yousan-apps.workers.dev**（2026-10-25 に初回デプロイ。独自ドメインは後で検討。ユーザー決定）。
- デプロイ先は、ユーザーの個人 Cloudflare アカウント（ka1357amnbpdr@gmail.com）。

## 自動デプロイ（GitHub Actions）

`.github/workflows/ci.yml` の流れは次のとおり。トリガーは main への push、PR、手動実行（workflow_dispatch）。

1. `rust`: fmt、clippy、test
2. `web`: WASM のビルド、型チェック、Vitest、ビルド、Playwright（Chromium）
3. `deploy`: main への push 時のみ実行（PR と手動実行では動かない）。`web` のビルド成果物で `wrangler deploy` を行い、スモークテストをする

リポジトリは 2026-10-25 に Public 化した。Public リポジトリの GitHub Actions（標準ランナー）は無料のため、Private 時代に出ていた「Actions budget」による未起動は解消している。同日の初回実行で、`rust`（約40秒）と `web`（約1分20秒、E2E 5件を含む）がともに成功した。

### GitHub の Secrets と Variables

| 名前 | 種類 | 状態 |
|---|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | Secret | 登録済み（2026-10-25） |
| `WORKERS_SUBDOMAIN` | Variable | 登録済み（`yousan-apps`） |
| `CLOUDFLARE_API_TOKEN` | Secret | **未登録（ユーザー作業）** |

`production` 環境は、CI の初回実行で作成済み。必要なら承認ルールを付ける。

`CLOUDFLARE_API_TOKEN` が未登録の間は、deploy ジョブは「skipped」の notice を出して成功扱いになる。登録すると、main への push ごとに自動デプロイされる。

#### `CLOUDFLARE_API_TOKEN` の登録手順（ユーザー作業）

CLI の OAuth ログインは期限付きで、API トークンを作る権限もない。そのため、CI 用のトークンはダッシュボードで作る。

1. 個人アカウントでダッシュボードにログインする。このマシンの Chrome の通常ウィンドウは別アカウントでログインしているため、シークレットウィンドウなどを使う。
2. My Profile → API Tokens → Create Token で、「Edit Cloudflare Workers」テンプレートからトークンを作り、コピーする。
3. 自分のターミナルで次を実行する。トークンの値を画面や会話に出さずに登録でき、最後にクリップボードを空にする。

   ```bash
   pbpaste | gh secret set CLOUDFLARE_API_TOKEN -R ayutaz/voxelshogi && pbcopy < /dev/null
   ```

## 手動デプロイ（ローカル）

このマシンの wrangler は、グローバルには別アカウントでログインしている。このプロジェクトでは、**プロジェクト専用のログイン**を使う。`scripts/cf.sh` は `XDG_CONFIG_HOME` を `.cloudflare-cli/`（gitignore 済み）に向けて wrangler を起動するので、グローバルのログインに影響しない。

```bash
scripts/cf.sh login --browser=false   # 初回のみ。表示された URL を、個人アカウントでログインしたブラウザで開く
scripts/cf.sh whoami                  # ka1357amnbpdr@gmail.com であることを確認する

cd apps/web && pnpm wasm && pnpm vite build && cd ../..
scripts/cf.sh deploy
```

## 公開サイトの検証

E2E テストは、`E2E_BASE_URL` を指定すると、ローカルのプレビューの代わりに公開サイトに対して実行される。

```bash
cd apps/web
E2E_BASE_URL=https://voxelshogi.yousan-apps.workers.dev pnpm e2e
```

2026-10-25 の初回デプロイでは、公開 URL に対して E2E 5件がすべて成功した。HTTP レベルでも次を確認した: HTML、JS、WASM（`application/wasm`）が配信されている、`/assets/*` が immutable キャッシュ、セキュリティヘッダーが付いている、SPA へのフォールバックが効いている。

## 今後の拡張（Phase 4 以降）

- 25MiB を超える ONNX Runtime の wasm やモデルは、R2 とカスタムドメインから配信する。`r2.dev` は開発用で、レート制限がある。
- マルチスレッド WASM を使う場合は、`_headers` に COOP/COEP を追加する。
- 詳細は `docs/TECH_STACK_RESEARCH.md` §3.4 と §4、`docs/COST_ESTIMATE.md` §5。
