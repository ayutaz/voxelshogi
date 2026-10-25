# デプロイ（Cloudflare Workers Static Assets）

M0-4 の構成を実装し、検証中。調査・計画・検証記録は [CI_CD_PLAN.md](CI_CD_PLAN.md) を参照。本番での確認結果と secrets の移行状態は同書に記録する。

## 構成

- `apps/web/wrangler.jsonc`: Worker 名 `voxelshogi`。`dist/` を静的アセットとして配信し、SPA へフォールバックする。Worker スクリプトはない。
- `apps/web/public/_headers`: `/assets/*` を immutable キャッシュにする設定と、基本的なセキュリティヘッダー。
- 公開 URL: **https://voxelshogi.yousan-apps.workers.dev**（2026-10-25 に初回デプロイ。独自ドメインは後で検討。ユーザー決定）。
- デプロイ先は、ユーザーの個人 Cloudflare アカウント（ka1357amnbpdr@gmail.com）。

## 自動デプロイ（GitHub Actions）

`.github/workflows/ci.yml` の流れは次のとおり。トリガーは main への push、PR、手動実行（workflow_dispatch）。

1. lint、Rust fmt/clippy/test、MSRV 1.85、依存監査。PR では dependency-review も行う
2. `web`: WASM ビルド、型チェック、Vitest、SHA 付き build、Playwright（Chromium、6件）
3. `CI Gate`: 必須ジョブの成功を集約する。main/手動での PR 専用ジョブの省略だけを許容する
4. `deploy`: main の push と Gate 成功時のみ。production のロック取得後に候補 SHA と最新 main を照合し、古い候補は理由を表示して省略する。現行候補は設定を検証し、同じ run の `web-dist` を Wrangler で公開する
5. 配信された `build-info.json` の SHA と対象コミットを有限回の取得で照合し、公開 URL に対して Playwright 6件を実行する

CodeQL は別の Security workflow、カバレッジと変異テストは Quality measurements workflow で実行する。Rust は `rust-toolchain.toml`、Node は `.node-version`、Python は `.python-version`、pnpm は `packageManager`、Wrangler は Web の lockfile に固定する。

リポジトリは 2026-10-25 に Public 化した。Public リポジトリの GitHub Actions（標準ランナー）は無料のため、Private 時代に出ていた「Actions budget」による未起動は解消している。同日の初回実行で、`rust`（約40秒）と `web`（約1分20秒、E2E 5件を含む）がともに成功した。

### GitHub の Secrets と Variables

| 名前 | 種類 | 状態 |
|---|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | production environment Secret | 登録済み（2026-10-25、プロジェクト専用ログインで対象アカウントを照合） |
| `WORKERS_SUBDOMAIN` | Variable | 登録済み（`yousan-apps`） |
| `CLOUDFLARE_API_TOKEN` | production environment Secret | 登録済み（2026-10-25、`voxelshogi-github-production-20261025`） |

`production` 環境は作成済みで、デプロイ元は main に制限済み（M0-4、2026-10-25）。Cloudflare の管理画面で新しい API トークンを発行し、`gh secret set --env production` へ直接登録した。権限は指定の個人アカウントの Workers スクリプト編集、有効期限なし（ユーザー承認済み）。この権限はアカウント内の全 Workers が対象。日常の自動公開に人手の承認待ちは追加しない。

認証情報は会話・ローカルファイル・Actions artifact に保存しない。登録後に本番 CI が成功したことを確認してから、不要になった repository 側の同名 Secrets を削除する。既存の Cloudflare トークン自体は、他の利用先への影響を確認せず失効させない。

main の最新候補は、CI から自動デプロイされる（2026-10-25 に初回の自動デプロイが成功）。本番でトークン・アカウント ID・サブドメインが不足した場合は失敗とする。PR と通常の手動 CI は本番公開しない。実行中の本番公開・公開後検証は次の push で中断しない。

Job Summary には設定検証・公開・配信 SHA 確認・公開 E2E の結果を分けて表示する。公開検証が成功した run は、commit SHA・Cloudflare version ID・run ID の `production-<SHA>` artifact を30日保存する。失敗時は trace と取得できた version ID を7日保存する。

#### `CLOUDFLARE_API_TOKEN` の登録手順（トークンを作り直すとき）

CLI の OAuth ログインは期限付きで、API トークンを作る権限もない。そのため、CI 用のトークンはダッシュボードで作る。

1. ダッシュボードにログインし、対象の個人アカウントであることを確認する。
2. My Profile → API Tokens → Create Token でカスタムトークンを作成する。権限を Account / Workers Scripts / Edit、リソースを対象の個人アカウントに限定して発行し、コピーする。
3. 自分のターミナルで次を実行する。トークンの値を画面や会話に出さずに登録でき、最後にクリップボードを空にする。

   ```bash
   pbpaste | gh secret set CLOUDFLARE_API_TOKEN -R ayutaz/voxelshogi --env production && pbcopy < /dev/null
   ```

## 手動デプロイ（ローカル）

このマシンの wrangler は、グローバルには別アカウントでログインしている。このプロジェクトでは、**プロジェクト専用のログイン**を使う。`scripts/cf.sh` は `XDG_CONFIG_HOME` を `.cloudflare-cli/`（gitignore 済み）に向けて wrangler を起動するので、グローバルのログインに影響しない。

```bash
scripts/cf.sh login --browser=false   # 初回のみ。表示された URL を、個人アカウントでログインしたブラウザで開く
scripts/cf.sh whoami                  # ka1357amnbpdr@gmail.com であることを確認する

cd apps/web && pnpm wasm && pnpm build && cd ../..
scripts/cf.sh deploy
```

## 公開サイトの検証

E2E テストは、`E2E_BASE_URL` を指定すると、ローカルのプレビューの代わりに公開サイトに対して実行される。

```bash
cd apps/web
published_commit='REPLACE_WITH_PUBLISHED_COMMIT_SHA'
E2E_BASE_URL=https://voxelshogi.yousan-apps.workers.dev E2E_COMMIT="$published_commit" pnpm e2e
```

2026-10-25 の初回デプロイでは、公開 URL に対して E2E 5件がすべて成功した。HTTP レベルでも次を確認した: HTML、JS、WASM（`application/wasm`）が配信されている、`/assets/*` が immutable キャッシュ、セキュリティヘッダーが付いている、SPA へのフォールバックが効いている。

M0-4 では SHA 確認を加えた6件に拡張する。`build-info.json` は `Cache-Control: no-store` で配信し、検証の取得にも対象 SHA の query を付ける。`E2E_COMMIT` を省略した手動実行は、SHA 確認だけが skip となるため、版の一致の証拠には使わない。

## 復旧手順

公開前の失敗なら現在のサイトを確認し、失敗した候補の問題を修正する。公開後の SHA 確認・E2E の失敗なら、現在の版が不完全な可能性があるため、次の手順で最後に公開検証が成功した版を選ぶ。

1. 直前の成功した deploy run の `production-<SHA>` artifact から version ID と SHA を確認する。必要なら `scripts/cf.sh deployments list` で Cloudflare の履歴と照合する。
2. プロジェクト専用の認証で `scripts/cf.sh whoami` を実行し、対象アカウントを確認する。
3. **確認した版を明示して** rollback する。引数なしの rollback は使わない。

   ```bash
   # 以下の値を、公開検証が成功した artifact にある実値へ置き換える
   recovery_version='REPLACE_WITH_VERIFIED_VERSION_ID'
   recovery_commit='REPLACE_WITH_VERIFIED_COMMIT_SHA'
   scripts/cf.sh rollback "$recovery_version" --message "Restore verified commit:$recovery_commit"
   E2E_BASE_URL=https://voxelshogi.yousan-apps.workers.dev E2E_COMMIT="$recovery_commit" pnpm --dir apps/web e2e
   ```

4. 復旧後に公開 E2E と配信 SHA を確認し、失敗 run・戻した version ID・確認結果を記録する。問題を直した PR の必須チェック成功後、通常の main の自動公開に戻す。

復旧訓練は、本番を変更せず、成功 run の `web-dist` を一時ディレクトリへダウンロードしてローカルで配信し、同じ6件の E2E と SHA 確認を行う。本番での自動 rollback は導入しない。[Cloudflare の rollback 仕様](https://developers.cloudflare.com/workers/wrangler/commands/workers/#rollback)

## 今後の拡張（Phase 4 以降）

- 25MiB を超える ONNX Runtime の wasm やモデルは、R2 とカスタムドメインから配信する。`r2.dev` は開発用で、レート制限がある。
- マルチスレッド WASM を使う場合は、`_headers` に COOP/COEP を追加する。
- 詳細は `docs/TECH_STACK_RESEARCH.md` §3.4 と §4、`docs/COST_ESTIMATE.md` §5。
