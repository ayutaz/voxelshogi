# デプロイ（Cloudflare Workers Static Assets）

M0-4 の自動公開・配信 SHA・公開 E2E・production Secrets 移行は確認済み。隔離した旧成果物による復旧訓練も実施し、Chrome E2E 6件が成功した（[復旧元の版・手順・検証結果](M0_VALIDATION.md)）。本番rollback自体は実行していない。調査・計画・検証記録は [CI_CD_PLAN.md](CI_CD_PLAN.md) を参照。

更新: 2026-10-28 JST。M3完了時公開版 `bca5532` の [main CI 40530800389](https://github.com/ayutaz/voxelshogi/actions/runs/40530800389) はモデル生成・通常検証・WASM受け渡し・公開・配信SHA・公開21件＋モデル6件・配信55ファイル照合が成功。実機の公開ファイル照合・全48組・切替も [M3最終記録](M3_VALIDATION.md#m3-5公開版の最終検証2026-10-28-jst) に保存した。M2の旧確認元 `e212ec7` と観測競合の修正は [M2記録](M2_VALIDATION.md) に保持。現在配信されるSHAはbuild-info.jsonで確認する。[現在地](STATUS.md)。

## 構成

- `apps/web/wrangler.jsonc`: Worker 名 `voxelshogi`。`dist/` を静的アセットとして配信し、SPA へフォールバックする。Worker スクリプトはない。
- `apps/web/public/_headers`: `/assets/*` とモデル／runtimeのhash付きファイルはimmutable、`/build-info.json`・`/inference-build.json`・モデルindexはno-store、`/experiments/*` はno-cache。基本セキュリティヘッダーあり。COOP/COEPは未設定。
- R0の比較実験: [研究記録](NINE_KINGS_EXPERIMENT.md)を保持する。比較室の公開画面・導線は撤去し、旧`/?experiment=1`も通常の観戦画面を開く。
- 公開 URL: **https://voxelshogi.yousan-apps.workers.dev**（2026-10-25 に初回デプロイ。独自ドメインは後で検討。ユーザー決定）。
- デプロイ先は、ユーザーの個人 Cloudflare アカウント（ka1357amnbpdr@gmail.com）。

## 自動デプロイ（GitHub Actions）

`.github/workflows/ci.yml` の流れは次のとおり。トリガーは main への push、PR、手動実行（workflow_dispatch）。

1. lint、Rust fmt/clippy/test、MSRV 1.85、依存監査、uv／Pythonの契約・モデルテスト、実モデル専用job。PR では dependency-review も行う
2. `web`: WASM ビルド、型チェック、Vitest、Native/WASM照合。承認済みの公開設定からuvで3モデルを生成し、ライセンス・clean source・全形式を検証。SHA付きbuild、モデル6件・既存21件の実E2Eを実行する。配信用 `web-dist` と、E2EがNodeで棋譜を再検証する生成WASM `web-e2e-wasm` を別artifactに保存
3. `CI Gate`: 必須ジョブの成功を集約する。main/手動での PR 専用ジョブの省略だけを許容する
4. `deploy`: main の push と Gate 成功時のみ。production のロック取得後に候補 SHA と最新 main を照合し、古い候補は理由を表示して省略する。現行候補は設定を検証し、同じ run の `web-dist` を Wrangler で公開する。`web-e2e-wasm` も同じrunからdigest照合付きで復元し、公開前に `pnpm e2e --list` で全テストのimportを確認する
5. 配信された `build-info.json` のSHAと対象コミットを有限回の取得で照合し、公開URLに対して既存21件・C0追加3件・モデル6件を実行する。モデル配布物とアプリWorker等の実ファイルを同じCI artifactのmanifestへ照合し、hash・長さ・MIME・cacheを保存する

CodeQL は別の Security workflow、カバレッジと変異テストは Quality measurements workflow で実行する。PR ではCodeQL 4種類、Rust/Webカバレッジと既知変異の3種類も必須とする（CI Gateと計8件）。全体変異調査は週次・手動のみ。Rust は `rust-toolchain.toml`、Node は `.node-version`、Python は `.python-version`、pnpm は `packageManager`、Wrangler は Web の lockfile に固定する。

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

既存の対局E2Eは通常対局5件・配信SHA1件・公開ナビゲーション／旧URL3件とWorker観戦12件の計21件。M3の実モデル6件は別設定で実行し、公開後にも両方とC0追加3件を確認する。ローカルは既存Chrome、CIはubuntu-24.04の実行ライブラリとPlaywrightのChromium本体を使う。以下の2405e86では当時の9件を検証した。M2の公開確認は [別記録](M2_VALIDATION.md) で追う。当時の確認元 `2405e86a0313d4b454119bd472937f2e10622bf5` のmain CIで公開E2Eまで成功し、400／800手の両manifestと全6棋譜のSHAも独立照合した。[サイズ・hash・ヘッダー](experiments/documentation-baseline-2026-10-26.json)。これは確認時点の記録であり、以後の版は配信情報で確認する。

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

4. 復旧先のソースとlockfileを新しい一時ディレクトリへ展開し、その版のE2Eと配信SHAを確認する。現在の21件をM2以前の版にそのまま実行しない。`recovery_commit` がローカルにない場合は、まずoriginからその版を取得する。

   ```bash
   verification_dir=$(mktemp -d "${TMPDIR:-/tmp}/voxelshogi-recovery-tests.XXXXXX")
   git archive "$recovery_commit" | tar -x -C "$verification_dir"
   # 対象版の .node-version / packageManager に合うツールを使う。
   pnpm --dir "$verification_dir/apps/web" install --frozen-lockfile
   # M2以降は、同じ成功runの検証用WASMも復元する。
   recovery_run='REPLACE_WITH_SUCCESSFUL_RUN_ID'
   gh run download "$recovery_run" --repo ayutaz/voxelshogi --name web-e2e-wasm --dir "$verification_dir/apps/web/src/wasm/pkg"
   E2E_BASE_URL=https://voxelshogi.yousan-apps.workers.dev E2E_COMMIT="$recovery_commit" pnpm --dir "$verification_dir/apps/web" e2e
   ```

5. 失敗run・戻したversion ID・検証に使ったソースSHA・結果を記録する。問題を直した PR の必須チェック成功後、通常の main の自動公開に戻す。

復旧訓練は、本番を変更せず、成功 run の `web-dist` を一時ディレクトリへダウンロードしてローカルで配信し、**その成果物の版に対応するE2E**とSHA確認を行う。M0で実施した旧版の訓練は当時の6件。`web-dist` は7日、`production-<SHA>` は30日保存なので、期限切れの場合は別の検証済み成功runを選ぶ。本番での自動 rollback は導入しない。[Cloudflare の rollback 仕様](https://developers.cloudflare.com/workers/wrangler/commands/workers/#rollback)

## M2の公開E2E用WASM受け渡し

M2のE2Eは、実Workerが保存した棋譜をNode側のRust/WASMでも再検証するため、Web buildのdistだけでなく生成pkgも必要である。CIの `Public E2E runtime handoff` はPR／mainの新しいcheckoutで、同じrunの `web-e2e-wasm` だけを復元して実際の全テストを収集する。失敗・中断・欠落はCI Gateを失敗にする。deployでも公開前に同じ収集を行い、公開後に全21件を実行する。

artifactの取得元は同じworkflow runに限定し、digest不一致はエラーとする。PR／forkの成果物をproductionへ渡さず、生成pkgに認証情報を含めない。配信用 `web-dist` の構造は維持し、検証用pkgを公開サイトへ重複配置しない。復旧訓練でM2版のE2Eを使う場合も、対象runの検証用WASMを同様に復元する。

## M3以降の推論配信の拡張

M3は公開・実機検証まで完了。[全配布ファイル・固定実測・制約](M3_VALIDATION.md#m3-5公開版の最終検証2026-10-28-jst)・[ADR-019](ARCHITECTURE_DECISIONS.md#adr-019-m3の精度形式backend配信方式2026-10-27)。承認済みの未学習モデル3形式は同一originのStatic Assetsで配信し、28,747,738 bytesのAsyncify WASMは16 MiB単位に分割する。個別ファイルは全て25 MiB以内。R2は追加していない。

- M6でモデルが大きくなり、分割Static Assetsで不適切になる場合に、軽量build・R2・Worker経由配信等を再評価する。R2の有効化に支払い方法が必要なら、その段階でユーザーに依頼する。
- 実行可能なFP32・FP16・INT8重み版は [公開ラボ](https://voxelshogi.yousan-apps.workers.dev/?models=1) で選択して実行できる。M3は未学習モデルの技術デモ、M6は学習済みモデルの対局・観戦として、同じ実配信hashを評価対象にする。
- マルチスレッド WASM を使う場合は、`_headers` に COOP/COEP を追加する。
- 詳細は `docs/TECH_STACK_RESEARCH.md` §3.4 と §4、`docs/COST_ESTIMATE.md` §5。
