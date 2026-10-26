# デプロイ（Cloudflare Workers Static Assets）

M0-4 の自動公開・配信 SHA・公開 E2E・production Secrets 移行は確認済み。隔離した旧成果物による復旧訓練も実施し、Chrome E2E 6件が成功した（[復旧元の版・手順・検証結果](M0_VALIDATION.md)）。本番rollback自体は実行していない。調査・計画・検証記録は [CI_CD_PLAN.md](CI_CD_PLAN.md) を参照。

## 構成

- `apps/web/wrangler.jsonc`: Worker 名 `voxelshogi`。`dist/` を静的アセットとして配信し、SPA へフォールバックする。Worker スクリプトはない。
- `apps/web/public/_headers`: `/assets/*` はimmutable、`/build-info.json` はno-store、`/experiments/*` はno-cache。基本セキュリティヘッダーあり。COOP/COEPは未設定。
- R0の比較室: [9王ルール比較室](https://voxelshogi.yousan-apps.workers.dev/?experiment=1)。実際のCPU探索棋譜を再生する。ライブ推論・学習モデルではない。
- 公開 URL: **https://voxelshogi.yousan-apps.workers.dev**（2026-10-25 に初回デプロイ。独自ドメインは後で検討。ユーザー決定）。
- デプロイ先は、ユーザーの個人 Cloudflare アカウント（ka1357amnbpdr@gmail.com）。

## 自動デプロイ（GitHub Actions）

`.github/workflows/ci.yml` の流れは次のとおり。トリガーは main への push、PR、手動実行（workflow_dispatch）。

1. lint、Rust fmt/clippy/test、MSRV 1.85、依存監査。PR では dependency-review も行う
2. `web`: WASM ビルド、型チェック、Vitest、SHA 付き build、Playwright（Chromium、9件）
3. `CI Gate`: 必須ジョブの成功を集約する。main/手動での PR 専用ジョブの省略だけを許容する
4. `deploy`: main の push と Gate 成功時のみ。production のロック取得後に候補 SHA と最新 main を照合し、古い候補は理由を表示して省略する。現行候補は設定を検証し、同じ run の `web-dist` を Wrangler で公開する
5. 配信された `build-info.json` の SHA と対象コミットを有限回の取得で照合し、公開 URL に対して Playwright 9件を実行する

CodeQL は別の Security workflow、カバレッジと変異テストは Quality measurements workflow で実行する。PR では CodeQL 3種類、Rust/Web カバレッジと既知変異の3種類も必須とする。全体変異調査は週次・手動のみ。Rust は `rust-toolchain.toml`、Node は `.node-version`、Python は `.python-version`、pnpm は `packageManager`、Wrangler は Web の lockfile に固定する。

変更は必ず作業ブランチから PR を作成する。main は PR・最新 main に対する必須チェックを要求し、force push・削除・bypass を禁止する。[開発手順](../CONTRIBUTING.md)

リポジトリは 2026-10-25 に Public 化した。Public リポジトリの GitHub Actions（標準ランナー）は無料のため、Private 時代に出ていた「Actions budget」による未起動は解消している。同日の初回実行で、`rust`（約40秒）と `web`（約1分20秒、E2E 5件を含む）がともに成功した。

### GitHub の Secrets と Variables

| 名前 | 種類 | 状態 |
|---|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | production environment Secret | 登録済み（2026-10-25、プロジェクト専用ログインで対象アカウントを照合） |
| `WORKERS_SUBDOMAIN` | Variable | 登録済み（`yousan-apps`） |
| `CLOUDFLARE_API_TOKEN` | production environment Secret | 登録済み（2026-10-25、`voxelshogi-github-production-20261025`） |

`production` 環境は作成済みで、デプロイ元は main に制限済み（M0-4、2026-10-25）。Cloudflare の管理画面で新しい API トークンを発行し、`gh secret set --env production` へ直接登録した。権限は指定の個人アカウントの Workers スクリプト編集、有効期限なし（ユーザー承認済み）。この権限はアカウント内の全 Workers が対象。日常の自動公開に人手の承認待ちは追加しない。

認証情報は会話・ローカルファイル・Actions artifact に保存しない。新しい production Secrets を使った [CI 40170836102](https://github.com/ayutaz/voxelshogi/actions/runs/40170836102) の公開と公開 E2E が成功した後、repository 側の同名 Secrets を削除済み。production 側の2件は保持している。既存の Cloudflare トークン自体は失効させていない。他の利用先への影響を確認せず失効させない。

main の最新候補は、CI から自動デプロイされる（2026-10-25 に初回の自動デプロイが成功）。本番でトークン・アカウント ID・サブドメインが不足した場合は失敗とする。PR と通常の手動 CI は本番公開しない。通常 CI は PR・main とも run ごとに独立して実行する。旧実行の待機中 Gate が新しい実行を止めないよう、workflow 全体の concurrency は設けない。CodeQL と品質計測は PR の旧実行を中断する。本番公開・公開後検証は production のロックで直列化し、次の push で中断しない。

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

pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web wasm
pnpm --dir apps/web build
scripts/cf.sh deploy
```

## 公開サイトの検証

E2E テストは、`E2E_BASE_URL` を指定すると、ローカルのプレビューの代わりに公開サイトに対して実行される。

```bash
cd apps/web
published_commit='REPLACE_WITH_PUBLISHED_COMMIT_SHA'
E2E_BASE_URL=https://voxelshogi.yousan-apps.workers.dev E2E_COMMIT="$published_commit" pnpm e2e
```

現在は通常対局5件・配信SHA1件・R0比較室3件の計9件。ローカルは既存Chrome、CIはインストールしたChromiumを使う。2026-10-26には公開版 `73f4cdc63c44afca80d785bee8281689c0218933` の [main CI 40254365292](https://github.com/ayutaz/voxelshogi/actions/runs/40254365292) で公開E2Eまで成功し、公開manifestと全6棋譜のSHAも独立照合した。これは確認時点の記録であり、以後の版は配信情報で確認する。

以下は過去の公開検証の記録。2026-10-25 の初回デプロイでは、公開 URL に対して E2E 5件がすべて成功した。HTTP レベルでも次を確認した: HTML、JS、WASM（`application/wasm`）が配信されている、`/assets/*` が immutable キャッシュ、セキュリティヘッダーが付いている、SPA へのフォールバックが効いている。

M0-4 では SHA 確認を加えた6件に拡張済み。`0e29eb4` の CI で公開 E2E 6件が成功し、公開 URL の `build-info.json` も同じ完全長 SHA と確認した。人間同士の対局・マルチプレイはなく、人間 vs AI と AI 観戦のみを検証する。`build-info.json` は `Cache-Control: no-store` で配信し、検証の取得にも対象 SHA の query を付ける。`E2E_COMMIT` を省略した手動実行は、SHA 確認だけが skip となるため、版の一致の証拠には使わない。

M0 完了時の公開確認は2026-10-26 00:53 JST。[main CI 40201319748](https://github.com/ayutaz/voxelshogi/actions/runs/40201319748) で commit `1ff4e2fe76b60c470ed57c75c984620dcc8fc7c2` の deploy・配信 SHA・公開 E2E 6件（33.4秒）がすべて成功した。Cloudflare version ID は `ce499132-9c06-4a0c-aea6-8491a10fbfa7`、記録 artifact は `production-1ff4e2fe76b60c470ed57c75c984620dcc8fc7c2`。これは完了時の記録であり、現在の公開版や復旧先を固定するものではない。以後の文書変更も自動デプロイされるため、最新の成功 run と配信中の `build-info.json` を確認する。[詳細](M0_VALIDATION.md)

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
   # 次の手順で、復旧先コミットに対応するテストを実行する。
   ```

4. 復旧先のソースとlockfileを新しい一時ディレクトリへ展開し、その版のE2Eと配信SHAを確認する。現在の9件をR0以前の版にそのまま実行しない。`recovery_commit` がローカルにない場合は、まずoriginからその版を取得する。

   ```bash
   verification_dir=$(mktemp -d "${TMPDIR:-/tmp}/voxelshogi-recovery-tests.XXXXXX")
   git archive "$recovery_commit" | tar -x -C "$verification_dir"
   # 対象版の .node-version / packageManager に合うツールを使う。
   pnpm --dir "$verification_dir/apps/web" install --frozen-lockfile
   E2E_BASE_URL=https://voxelshogi.yousan-apps.workers.dev E2E_COMMIT="$recovery_commit" pnpm --dir "$verification_dir/apps/web" e2e
   ```

5. 失敗run・戻したversion ID・検証に使ったソースSHA・結果を記録する。問題を直した PR の必須チェック成功後、通常の main の自動公開に戻す。

復旧訓練は、本番を変更せず、成功 run の `web-dist` を一時ディレクトリへダウンロードしてローカルで配信し、**その成果物の版に対応するE2E**とSHA確認を行う。M0で実施した旧版の訓練は当時の6件。`web-dist` は7日、`production-<SHA>` は30日保存なので、期限切れの場合は別の検証済み成功runを選ぶ。本番での自動 rollback は導入しない。[Cloudflare の rollback 仕様](https://developers.cloudflare.com/workers/wrangler/commands/workers/#rollback)

## 今後の拡張（M3 の推論検証から）

- M3 で実際の変換済みモデルと runtime のサイズ・対象実機の演算対応を確認し、軽量ビルド・R2公開バケットとカスタムドメイン・Worker経由配信などを比較して決める。初回調査時の25MiB制限を含め、採用時に制限を再確認する。R2 の有効化に支払い方法が必要なら、その段階でユーザーに依頼する。
- 公開する実行可能な FP32・FP16・量子化版を選んで動かせるようにし、評価記録と配布ファイルの SHA-256 を一致させる。M3 は未学習モデルの技術デモ、M6 は学習済みモデルとの対局・観戦として検証する。
- マルチスレッド WASM を使う場合は、`_headers` に COOP/COEP を追加する。
- 詳細は `docs/TECH_STACK_RESEARCH.md` §3.4 と §4、`docs/COST_ESTIMATE.md` §5。
