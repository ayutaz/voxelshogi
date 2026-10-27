# CI/CD 調査と強化計画

調査日: 2026-10-25。対象: `ayutaz/voxelshogi`、調査時の main: `cbf14c5`。

**M1（探索AI）の前に、M0 として CI/CD と品質基盤を整えた。** 調査開始時の不足と、実装後の状態を分けて記録する。

本書は調査結果・実装計画・検証記録。M0-1〜5は最終文書の取り込み・公開後検証まで完了した（[M0_VALIDATION.md](M0_VALIDATION.md)）。現行のデプロイ手順は [DEPLOYMENT.md](DEPLOYMENT.md)、実行順と進捗は [ROADMAP.md](ROADMAP.md#実行計画マイルストーン)、M1探索の実装手順は [M1_PLAN.md](M1_PLAN.md)、検証結果は [M1_VALIDATION.md](M1_VALIDATION.md) に記録する。

## 現在の状態

2026-10-28（JST）。M3完了時公開版 `bca5532` のモデル生成・公開・配信55ファイル照合・公開E2Eまで確認。性能計測の`dd3762c`と最終参照値の差は [終了時の証拠](experiments/m3-completion-publication.json) に保持する。[現在地](STATUS.md)・[M3最終記録](M3_VALIDATION.md#m3-5公開版の最終検証2026-10-28-jst)を参照。M2最終版 `e212ec7` とM1時点 `2405e86` の記録は各検証文書へ保持し、後続文書PRの配信SHAと区別する。

| 項目 | 現在の確認結果・設定の根拠 |
|---|---|
| mainのCI・公開 | [CI 40530800389](https://github.com/ayutaz/voxelshogi/actions/runs/40530800389)：通常CI・実モデル・WASM受け渡し・deploy・公開21件＋モデル6件・C0追加3件・配信55ファイル照合が成功。[Security 40530800258](https://github.com/ayutaz/voxelshogi/actions/runs/40530800258) の4言語解析も成功 |
| 品質の継続検証 | Rust core153＋WASM境界5件、Web172件、Python48件、CI制御Node67件、Native/WASM12fixture、既知core/WASM33・Web50・Python16・CI制御14変異。M1の全1,172変異とM0の全758変異は各段階の固定記録 |
| main保護 | 定義は [.github/main-ruleset.json](../.github/main-ruleset.json)：PR必須・最新main検証・必須8チェック（M3でPython CodeQL追加）・Actions App15368・CodeQL error/high以上・force push/削除禁止・bypassなし。他者承認0。実設定と拒否／成功の検証は各段階の記録 |
| 本番認証 | main限定のproduction environmentを使用し、PR／fork／DependabotへCloudflare Secretsを渡さない。配置のAPI確認はM0／M1の固定記録。今回秘密値は取得・変更していない |
| 進捗と次の作業 | M0・R0・M1・M2・M3は完了。次はM4のPythonバインディングとデータ生成。Python3.14・uv、特徴量／行動契約とモデルCIを引き継ぐ |

公開版は固定されないため、以後は `build-info.json` と対応する成功runを確認する。CI取得は最短10分間隔でまとめ、短いwaitも反復しない。

## M0完了時の記録

2026-10-26（JST）更新。PR #3の最終コミット `ee7b102` は必須7チェックが成功し、通常の squash merge 後の `1ff4e2f` で本番公開まで成功した。下表は各検証時点の記録であり、現在の公開版の識別には配信中の `build-info.json` と対応する main の CI を使う。

| 項目 | 現況・証拠 |
|---|---|
| 通常 CI と本番公開 | 最終文書の [PR CI 40194273936](https://github.com/ayutaz/voxelshogi/actions/runs/40194273936) が成功し、PRのdeploy省略を確認。統合後の [main CI 40201319748](https://github.com/ayutaz/voxelshogi/actions/runs/40201319748) で lint・Rust・MSRV・Web・監査・Gate・deploy が成功。配信 SHA `1ff4e2fe76b60c470ed57c75c984620dcc8fc7c2` の照合と公開 E2E 6件（33.4秒）も成功 |
| セキュリティ | 最終文書の [PR Security 40194273973](https://github.com/ayutaz/voxelshogi/actions/runs/40194273973) と統合後の [main Security 40201319737](https://github.com/ayutaz/voxelshogi/actions/runs/40201319737) の CodeQL 3言語が成功。M0検証時の未解決 code scanning alerts は0件。Secret scanning・Push protection・非公開脆弱性報告は有効 |
| 依存更新 PR | [Dependabot PR #1](https://github.com/ayutaz/voxelshogi/pull/1) は作成・CI 成功を確認済み、未マージ。自動マージは導入しない |
| 品質計測 | [Quality 40187911530](https://github.com/ayutaz/voxelshogi/actions/runs/40187911530) の Rust/Web カバレッジと既知の9変異が成功。Rust coreの行カバレッジ95.92%、Web単体35.37%。[全体調査40187925728](https://github.com/ayutaz/voxelshogi/actions/runs/40187925728) も8分割すべて成功し、全758件を692 caught・58 unviable・8 equivalentに分類。全結果と保存レポートを照合済み |
| production 認証 | 新規 API トークンとアカウント ID を environment Secrets に直接登録し、本番公開で使用済み。成功確認後、旧 repository Secrets の2件を削除し、repository 側は空、production 側の2件は保持と API で確認 |
| main 保護 | ruleset `25816100` を active に設定し、`protected: true` を確認。PR 必須、最新 main 検証、必須7チェック、CodeQL の error / high以上、force push・削除禁止、bypass なし。他者承認0件。定義は `.github/main-ruleset.json` |
| PR 保護の検証 | [PR #2](https://github.com/ayutaz/voxelshogi/pull/2) は必須7チェック成功後、bypass なしで squash merge 済み（main `e3f7f7a`）。未完了時の通常 merge 拒否と正常時の取り込みを確認 |
| 復旧訓練 | 成功runの旧 `web-dist` を再ビルドせず loopback 配信し、Chrome E2E 6件が成功。本番は変更していない。[証拠と手順](M0_VALIDATION.md) |
| 次の作業 | M0-1〜5は取り込み・公開後検証まで完了。当時はM1未着手。その後のM1〜M3完了と次のM4は [現在地](STATUS.md)・[実行計画](ROADMAP.md) を参照。fork実検証は外部からの開発参加時に追加する |

人間同士の対局・マルチプレイは後続フェーズでも実装しない。Python は3.14を基本に、依存が未対応の場合のみ3.13を使う（現在 `.python-version` は3.14.9）。

## 調査開始時の状態（変更前の記録）

以下は main `cbf14c5` 時点の調査であり、現在の不足一覧ではない。当時の [CI 実行](https://github.com/ayutaz/voxelshogi/actions/runs/40165004515) では Rust・Web・deploy とスモークテストが成功していた。

| 項目 | 確認結果 | 不足・影響 |
|---|---|---|
| CI の起動 | main の push、PR、手動実行。通常ブランチの push 単独では起動しない | 実装ブランチでは PR を開いて検証する運用が必要 |
| Rust | fmt・clippy（警告をエラー化）・workspace test | `--locked`、固定 Rust ツールチェーン、宣言する最低 Rust バージョンの検証がない |
| Web | 実 WASM のビルド・型チェック・Vitest・Vite build・Chromium E2E | ESLint、カバレッジ計測がない。現行の厳格な型チェックは維持する |
| テストの検出力 | 独立した Rust 参照実装あり。手動の変異テスト実績を記録済み | 変異テストの継続実行は CI にない。カバレッジだけではルールの正しさを保証できない |
| ビルド成果物 | 同じ run の `web-dist` を deploy で再利用、保存7日 | 配信された版とコミットの照合がない |
| 公開後の検証 | HTML に `VoxelShogi Arena` が含まれるかを curl で確認 | JS/WASM や対局操作の破損を検出できない。公開 E2E は手動実行できるが CI にはない |
| 設定漏れ | API トークンがなければ deploy は notice 付き成功。URL 変数がなければ smoke を省略 | デプロイ・検証されていなくても緑になる |
| デプロイの同時実行 | ワークフロー全体が ref 単位で `cancel-in-progress: true` | 次の main push で実行中の deploy や公開検証も中断され得る |
| main 保護 | `protected: false`、rulesets は空 | CI が失敗する変更も直接 push できる |
| Actions の権限 | YAML は `contents: read`、既定 token 権限も read、PR の承認権限なし | 良い設定。Actions は全許可で SHA 固定の強制なし。各 Action は可変タグ参照 |
| production 環境 | 存在するが保護ルールなし、デプロイ元ブランチの制限なし | YAML 以外でも本番への経路を制限する必要がある |
| Cloudflare 認証 | repository secrets に API トークンとアカウント ID、repository variable にサブドメイン。production secrets は空 | 環境単位の secrets へ移す計画。値や Cloudflare 側のトークン権限は今回の調査対象外 |
| Dependabot | alerts 有効（API は204）、security updates 有効、未解決 alerts は0件 | `.github/dependabot.yml` がなく、定期的なバージョン更新 PR は未設定。alerts 0件は網羅的な監査の代わりにはならない |
| Secret scanning / Push protection | repository の設定値はいずれも `disabled` | 明示的に有効化し、状態を再確認する。GitHub が提供する公開リポジトリ向け検知と、この設定値は区別する |
| CodeQL | default setup は `not-configured`、解析結果なし | ソース・Actions のセキュリティ解析を追加する |
| 脆弱性の報告 | private vulnerability reporting は無効、`SECURITY.md` なし | 非公開の報告経路を先に整える |

確認に用いた API は、repository、main branch、rulesets、Actions runs/jobs・permissions、environment、Actions/environment secrets の**名前のみ**、variables の名前のみ、vulnerability-alerts、Dependabot alerts、CodeQL default-setup/analyses、private-vulnerability-reporting。秘密情報の値は取得していない。

## M0 の実装順と完了条件

M0-1〜5 を順番に、小さな変更単位で進める。GitHub の設定変更は、必要なワークフローと報告経路が main で動いてから行う。各項目は実装・検証ログと該当 run/PR を本書に追記して完了とする。

| 順 | 目的 | 主な変更先 | 完了条件 | 状態 |
|---|---|---|---|---|
| M0-1 | CI 自体の誤りと環境のずれを検出する | `ci.yml`、`rust-toolchain.toml`、Web lint 設定、ビルドスクリプト | 固定環境で既存テストが通り、意図した lint・型・テストの失敗を検出する | ✅ main の検査と Gate 成功、異常系検証済み |
| M0-2 | 依存関係とコードのセキュリティを継続確認する | `ci.yml`、`dependabot.yml`、`security.yml`、`deny.toml`、`SECURITY.md`、GitHub 設定 | 監査と CodeQL が成功し、更新 PR と非公開報告の経路が使える | ✅ 監査・3言語解析・通常/更新 PR・報告経路を確認済み |
| M0-3 | テストの抜けを見えるようにする | `quality.yml`、計測・変異テスト設定 | Rust/Web の計測結果を保存し、既知のバグを再現可能な手順で検出する | ✅ CI計測・既知の9変異・全758件の調査と分類が成功。保存した全結果を照合済み |
| M0-4 | 公開版を検証し、復旧できるようにする | deploy ジョブ、公開 E2E、ビルド情報、`DEPLOYMENT.md` | 公開版の SHA と対局操作を確認し、設定漏れ・配信障害が失敗になる | ✅ 本番 SHA・公開 E2E・環境 Secrets 移行・隔離復旧訓練・古い候補の公開省略・統合後の公開を確認 |
| M0-5 | 失敗した変更の取り込みを防ぐ | main ruleset、`CONTRIBUTING.md`、PR テンプレート | 正常な PR は取り込め、必須チェック失敗の PR は取り込めない | ✅ PR #2で拒否と全必須チェック成功後の通常取り込みを確認。有効な保護ルールも再確認済み |

以下のM0各節は実装時の計画と検証の履歴を保存したもの。現在の必須チェック数・テスト件数は上記の現況と [開発手順](../CONTRIBUTING.md) を使う。

### M0-1 CI の再現性と静的検査

- CI で成功する Rust のバージョンを `rust-toolchain.toml` に固定する。`cargo build/test/clippy` に `--locked` を付ける。最低 Rust バージョンは `Cargo.toml` の `rust-version = "1.85"` で実際に検証し、依存関係が非対応なら対応版への調整または最低バージョンの引き上げを、理由付きで決める。
- Node は CI とローカル手順を 24 系にそろえ、採用する patch を固定する。pnpm は既存の `packageManager` と frozen lockfile を使う。`wasm-bindgen` の Cargo・CLI のバージョン一致も機械的に確認する。
- Actions を公式リポジトリの完全長 commit SHA に固定し、読みやすいバージョンコメントを添える。可変の toolchain action 参照も対象にする。GitHub は完全長 SHA の固定を推奨している。[公式ガイド](https://docs.github.com/en/actions/reference/security/secure-use)
- actionlint で YAML の式・ジョブ参照を、ShellCheck でシェルを検査する。Web は TypeScript・React Hooks を対象に ESLint を追加し、既存コードが通る最小構成から始める。大量の整形変更は別作業とする。[actionlint](https://github.com/rhysd/actionlint)
- 各ジョブに timeout を設け、失敗した E2E の trace とレポートを保存する。最初は lint/Rust 10分、Web 15分を上限とし、実測して調整する。
- 必須ジョブの結果を集約する `CI Gate` を作る。`always()` で結果を確認し、必要なジョブの failure・cancelled・想定外の skipped を成功扱いにしない。docs だけの PR でもチェックが終了する構成にする。

**検証**: ロックファイル更新が必要な状態、壊した workflow の式、lint 違反、型エラー、失敗するテストの各ケースを一時的に作り、対応する検査と Gate が失敗することを確認する。検証後の成果物には正常な状態だけを残す。

### M0-2 依存関係とセキュリティ

- Dependabot を週次で設定する。対象は Cargo（`/`）、npm/pnpm（`/apps/web`）、GitHub Actions（`/`）。patch/minor をまとめ、major は分け、各 ecosystem の同時 PR 数を3件までにする。自動マージは初期導入に含めない。pnpm は Dependabot 上では `npm` ecosystem を使う。[設定仕様](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference)
- `wasm-bindgen` 更新時は CLI とセットで検証する。Wrangler は Web の devDependency と lockfile で管理し、CI と `scripts/cf.sh` が同じものを起動する。調査開始時の `npx --yes wrangler@4.152.0` / `pnpm dlx` の実行時解決は解消済み。
- Rust は `cargo-deny` で既知の脆弱性・ライセンス・取得元を監査する。Web は `pnpm audit` を開発用依存も含めて実行する。PR/main だけでなく毎週も実行し、コード更新がなくても新規 advisory を拾う。Rust の既知の脆弱性は全件、Web は high/critical を必須チェックの失敗とする。例外は advisory ID・理由・期限を記録し、全体を無効化する回避はしない。[RustSec](https://rustsec.org/)
- 依存監査と dependency-review は `ci.yml` のジョブとして `CI Gate` に結び、週次でも同じ監査コマンドを使う。CodeQL は `security.yml` に分け、M0-5 で別の必須チェックまたは code scanning rule に結ぶ。独立した workflow 間を `needs` で参照する設計にはしない。
- PR では dependency-review で追加・更新された依存関係を確認し、high/critical を失敗にする。fork/Dependabot PR でも secrets なしで動かし、PR へのコメント書き込み権限は不要とする。[Dependency review](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-review)
- CodeQL を Rust・JavaScript/TypeScript・Actions に追加する。現在の公式対応言語に Rust と Actions も含まれる。PR/main/週次で実行し、SARIF のアップロードに必要な権限だけを解析ジョブに付与する。fork PR の実行時の権限差は外部からの開発参加時に追加検証する。[CodeQL の対応言語](https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-code-scanning)
- repository の Secret scanning・Push protection と private vulnerability reporting を有効化する。非公開報告が使えることを確認してから、その URL を案内する `SECURITY.md` を追加する。[GitHub の設定ガイド](https://docs.github.com/en/code-security/getting-started/quickstart-for-securing-your-repository)
- `GITHUB_TOKEN` の既定 read 権限を維持する。未信頼の PR コードを secrets や書き込み token と同じ実行環境で動かさず、`pull_request_target` で PR head を実行する構成を導入しない。

**検証**: 通常 PR・Dependabot PR の経路を確認する。fork PR の実検証は、外部からの開発参加を受け入れる際に追加する（2026-10-25、ユーザーの必要性確認を受けて計画を見直し）。監査対象に既知の脆弱性を持つ依存を置いた隔離 fixture で監査が失敗することを確かめる。Secret scanning は設定値を再取得して確認し、本物の認証情報をテスト用に push しない。CodeQL は対象言語ごとの解析完了と alert の初回トリアージを確認する。

### M0-3 テスト品質の計測

- Rust は cargo-llvm-cov、Web は Vitest coverage を使い、生成された WASM の JS glue や独立した参照実装などを製品コードの計測対象と区別する。LCOV/HTML と要約を GitHub artifact / Job Summary に保存し、外部サービスを必須にしない。[cargo-llvm-cov](https://github.com/taiki-e/cargo-llvm-cov)
- 最初に現状のカバレッジと所要時間を計測する。割合だけを上げるテストは作らず、未検証の重要分岐から改善する。一律90%などの数値は実測前に必須化しない。
- Rust のルール・終局判定・ハッシュを対象に、既知の変異を検出できる手順を自動化する。cargo-mutants を使う場合も、元コードで成功することを先に確かめ、ビルド不能や timeout を「テストがバグを検出した」と数えない。生き残った変異は、意味が変わらない変異かテスト不足かを確認する。[cargo-mutants](https://github.com/sourcefrog/cargo-mutants)
- カバレッジと小さな変異セットの再現を M0 で確認し、重い全体の変異テストは週次・手動に分ける。M1 の探索コードは追加時に対象へ組み込む。TDD の RED 確認と手計算・参照実装による期待値は、CI に移しても省略しない。

**検証**: 空のテスト対象や欠落したレポートを成功扱いにせず、既知のバグを対象のテストが実際に落とすことをログに残す。M0 完了時に計測値と対象外の範囲を本書に追記する。

### M0-4 デプロイと公開後の検証

- PR はテストのみ、main の push はテスト済みの同じ artifact を公開する構成を維持する。`CI Gate` の成功を deploy の前提にする。artifact と配信ファイルに commit SHA を付け、本番 E2E は配信版が対象 SHA と一致することを先に確認する。
- 通常 CI は PR・main とも run ごとに独立させ、旧実行の待機中 Gate が新しい実行を止めないようにする。CodeQL と品質計測は古い PR 実行を中断する。実行中の本番 deploy と公開検証は次の push で中断しない。deploy〜公開検証を共通の concurrency group で直列化し、ロック取得後に candidate SHA と main の先頭を比較する。古い候補はデプロイせず理由を Summary に記録する。concurrency だけではコミット順の公開は保証できない。[GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- production のデプロイ元を main に限定し、Cloudflare secrets を repository から production environment へ移す。必要なジョブ・ステップにだけ渡す。まず環境側で動作を確認してから repository 側を削除する。対話式の本番承認は日常の自動デプロイに追加しない。[GitHub environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments)
- main の本番 deploy では、API トークン・アカウント ID・サブドメインの不足を明示的に失敗させる。PR と通常の手動 CI が deploy しないことは正常動作として区別する。実装時に ADR-008 の「secrets 未登録ならスキップ」を改訂する。
- 公開 URL に対して、対局操作5件と配信 SHA 確認1件の Playwright E2E を自動実行する。JS/WASM のロード、初期表示、着手・AI応答・undo・棋譜入出力を実ブラウザで確認する。反映待ちは有限回・有限時間にし、trace と対象 SHA を失敗 artifact に保存する。テストはブラウザ内の対局状態だけを変更する。
- デプロイに失敗した場合と、デプロイ後の E2E に失敗した場合を区別して Job Summary に表示する。Cloudflare version ID・commit SHA・最後に公開検証が成功した版を記録し、手動の復旧手順を `DEPLOYMENT.md` に加える。公開 E2E の一時的な失敗だけで自動 rollback する仕組みは初期導入に含めない。復旧の実動作は隔離した環境またはローカルの旧 artifact で確認する。[Cloudflare rollback](https://developers.cloudflare.com/workers/wrangler/commands/workers/#rollback)

**検証**: 非本番の検証経路で設定漏れ・誤った配信 SHA・JS/WASM の取得失敗を検出する。近接する2回の main 更新でも deploy が中断・競合せず、最後に最新の成功版が配信されることを確認する。復旧手順では戻す版の明示と復旧後の公開 E2E を必須にする。

### M0-5 PR と main 保護

- main での通常 CI・CodeQL・品質計測・公開 E2E の成功を確認し、ユーザー指示により復旧訓練・全体変異分類と並行して main の ruleset を設定する。PR 経由・必須 `CI Gate`・最新 main に対する検証を要求し、force push とブランチ削除を禁止する。管理者を含め bypass は設けない。[利用できるルール](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- 一人開発でも進められるよう、他者による承認の必須数は0とする。PR 自体と必須チェックは要求する。CodeQL は解析結果を別の必須チェックまたは code scanning rule に結び、解析成功だけで high/critical の alert を見逃さない構成にする。
- 必須 Gate には lint・Rust・MSRV・WASM/Web/E2E・依存監査を含め、dependency-review も PR では必須とする。CodeQL 3種類と Rust/Web カバレッジ・既知変異の3種類を、別の必須チェックとして追加する。docs のみでも全7チェックを実行する。全体変異調査と本番 deploy は PR の必須チェックに含めない。
- `CONTRIBUTING.md` と PR テンプレートに、TDD、独立した期待値、変異テスト、ローカル確認コマンド、ドキュメント更新、AI が作った差分も確認することを記載する。`CLAUDE.md` の手順も PR 運用へ変更する。

**検証**: Gate の単体テストで failure・cancelled・skipped・欠落を拒否することを確認し、GitHub では必須チェックが未完了の PR の通常 merge を拒否することを確認する。壊したテストを push して検証する方法は使わない。正常系では全チェックが成功して取り込み可能になることと、自己承認なしで取り込めることを確認する。通常/Dependabot PR のdeploy省略と、production Secretsの保存先・main限定ポリシーを確認する。fork PR の実検証は外部からの開発参加時に追加する。必須チェック名・ruleset・production の設定を再取得し、本書に記録する。

## 定常運用

| タイミング | 実行内容 | 役割 |
|---|---|---|
| PR / main push | lint、Rust、WASM、Web、ローカル E2E、依存監査、CodeQL。dependency-review は PR のみ | 取り込み前と統合後の検証 |
| PR | Rust/Web カバレッジ、既知のcore/WASM33変異とWeb29変異の回帰検証 | レポート保存と既知の検出力を取り込み前に確認。Web変異は必須のWebカバレッジjobで実行 |
| main の検証成功後 | 同じ artifact を deploy、配信 SHA 確認、公開 E2E | 公開版の動作確認 |
| 週次 / 手動 | 依存監査、CodeQL、カバレッジ、変異テスト。Dependabot の更新確認 | コード更新がなくても問題を検出 |

M0計画時には通常CIのRust約26秒・Web約84秒（キュー待ちを除く）を基準にした。R0以後はソース・テストが増えており、現在の所要時間は対象runの実行時間とキュー待ちを分けて確認する。重い品質計測は別 workflow とし、初期の通常 CI は5分程度を目安にする。これは実測前の目標であり、5分を超えたことだけでテストを省略しない。

GitHub Actions の **Public リポジトリの標準 GitHub-hosted runner** は無料で利用できる。M0 は標準 Ubuntu runner を使い、有料の larger runner、外部カバレッジサービス、GPU、R2 を追加しない。artifact は原則7日、重い計測結果は必要なものだけ保存する。[GitHub の料金条件](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

## 公開E2Eの安定性に関する追記（2026-10-27）

文書更新後の [main CI 40432366163](https://github.com/ayutaz/voxelshogi/actions/runs/40432366163) は公開・配信SHA・公開E2Eまで最終結果successだったが、カメラ操作テスト1件が初回失敗・再試行成功となった。実行コードとCI設定はM2完了版から変えていない。再試行なしで通った固定記録を上書きせず、この結果も残す。当初はCI設定を変えず、C0として切り分けを計画した。その後 [C0](C0_VALIDATION.md) で観測競合を再現し、E2Eを入力イベント時点の判定へ変更。通常のWeb CIとmain公開後に、対象テストの各3回・retries=0を追加した。失敗はCI Gate／公開jobを失敗させる。製品コード・探索上限は変更していない。

## 段階ごとの検証（実施済みと追加予定）

| 時期 | 追加する検証・運用 |
|---|---|
| M1（完了） | 高速適用と検証付き適用の一致、手計算評価、少数駒局面の minimax 深さ1〜3との一致、詰み・駒損回避・合法手、固定深さ/ノードの再現性。最適化前後の評価値とノード数を比較。実時間の速さは計測値として保存する |
| M2（完了） | AI同士のEasy/Normal対局の自動進行、両AIの設定の識別、一時停止・1手送り・速度変更、Worker思考中のUI操作、中断・新規対局・undo後の古い応答の破棄、公開E2E、バンドルサイズ。人間対AIも補助機能として検証 |
| M3 | FP32と作成したFP16・量子化版ごとに、同じ変換版の基準実装との数値比較、対応演算子・backend・配信上限を検証する。公開技術デモの配信SHA-256とロード・推論を確認し、WebGPU推論と3D観戦表示の同時実行は対象実機の検証として別に記録する |
| M4 | Python lint/test、Rust バインディング、少量データの同一 seed 再生成・ハッシュ比較・検証・分割漏れ検出。10万局面の生成は通常 PR CI に入れない |
| M6 | 小さな学習とcheckpoint再開、各公開変換版の数値・精度・棋力評価、配布ファイルと評価記録のSHA-256一致、両AIのモデル・変換版の選択と観戦操作の公開E2E、人間対AIの補助機能。モデル・条件・結果を記録し、3D表示と推論の同時動作・速度・メモリを実機でも測る。GPU本学習は見積もり・承認後に実行し、通常CIと分ける |
| Phase 7 | 複数ブラウザ・モバイル・アクセシビリティ、公開監視、必要になった場合の PR preview と release 自動化 |

M1では、同じ固定深さ・固定ノード数で同じ結果になることと、時間上限で停止することを別のテストで確認した。実時間だけの上限では環境負荷により到達深さが変わるため、同じ手を保証する再現性条件には使わない。

M0 の完了は、設定ファイルが存在することではなく、正常時の成功と異常時の検出、取り込み制御、公開後の検証までの確認で判断する。性能の厳密な回帰閾値や全環境のテストを最初から必須にはせず、M1 以降の実測に合わせて増やす。

## M1後の継続検証

全体変異のテスト段階は `scripts/ci/mutation-cargo.sh` で有限の座標契約を先に確認し、成功時は元の全テストへ進む。座標変異による飛び駒ループのメモリ増加を防ぐためで、caughtの判定基準は変えない。固定Rust toolchainと実Cargoを明示して起動する。CIのShellCheckは `scripts/*.sh scripts/ci/*.sh` を対象とし、既知21変異・全1,172変異の分類は [M1記録](M1_VALIDATION.md) を参照。

M2ではWeb単体115件、Rustはcore153件＋WASM境界5件、CI制御Node49件、E2E21件。Webジョブは12個の固定fixtureでNativeと実WASMの全探索結果を照合する。既知core/WASM33変異とWeb29変異も必須品質チェックで実行する。[検証記録](M2_VALIDATION.md)。Web・deployのrunnerはubuntu-24.04とし、Chromium本体をPlaywrightから導入する。既存ライブラリ／追加フォントのapt取得が15分上限で中断したため、runnerにある実行ライブラリを使い、実際の起動と全E2Eの成功を必須とする。公開確認も [M2検証](M2_VALIDATION.md) の最終版まで完了した。次のPython/export比較・WASM／実機GPU検証の追加条件は [M3計画](M3_PLAN.md) を参照。

## 実装と検証の記録

以下は各段階の記録。テスト件数・設定の現況は冒頭の「現在の状態」を優先する。末尾を含む以下の記録はM0当時の値。

各段階の「未実施」「確認後に追記」はその時点の状態を示す。復旧訓練・全体変異分類・最終取り込み・公開確認の完了結果は [M0_VALIDATION.md](M0_VALIDATION.md) に集約した。fork の実検証は引き続き未実施。

### M0-1 ローカル検証

2026-10-25: Rust 1.97.1、Node 24.22.1、pnpm 10.32.1 に固定。Rust の最低バージョン1.85でも workspace のビルドと80テストが通ることを確認した。Actions は公式参照先の完全長 SHA に固定し、workflow・shell・Web lint と `CI Gate`、ジョブの時間上限を追加した。

- 正常系: Rust fmt/clippy と80テスト、Web lint/typecheck、WASM build、Vitest 33テスト、Chrome E2E 5テストが成功。
- 異常系: 不正な Actions 式、React Hooks 違反、TypeScript 型エラー、Vitest の失敗、lockfile 欠落を各検査が拒否した。一時ファイルは検証後に除去した。
- `CI Gate` はテストを先に追加して未実装の失敗を確認し、その後7テストが成功。必須結果の failure/cancelled/skipped/欠落を拒否し、失敗を成功扱いする変異も検出した。
- GitHub の main 保護やセキュリティ設定は、この段階では未変更。CI の実行結果は確認後に追記する。

### M0-2 監査と報告経路

2026-10-25: Dependabot を Cargo・npm/pnpm・Actions の週次更新として設定。Rust の cargo-deny と Web の pnpm audit、PR の dependency-review を `CI Gate` に追加した。CodeQL は Rust・JavaScript/TypeScript・Actions の3言語を独立した workflow で解析する。週次監査は通常 CI と同じ reusable workflow を使う。

- GitHub 設定を有効化し、API で Secret scanning / Push protection が `enabled`、private vulnerability reporting が `true` と確認。初回確認時の未解決 Secret scanning alerts は0件。非公開報告 URL を `SECURITY.md` に記載した。
- Wrangler 4.152.0 を lockfile で管理し、CI・ローカルとも同じバイナリを実行する。認証情報は deploy ステップだけに渡す。
- Wrangler → miniflare → undici に high 1件・moderate 2件を検出。`miniflare>undici` を修正版7.30.1に限定する override で解消し、再監査は0件。次回 Wrangler 更新時に override なしで修正版が解決されるか確認する。[修正版の根拠](https://github.com/advisories/GHSA-xjj6-f33q-929c)
- Rust は workspace 依存のバージョンを明記して、脆弱性・ライセンス・取得元・禁止依存の監査がすべて成功。advisory の無視設定は追加していない。
- 隔離 fixture の undici 7.30.0 と lz4-sys 1.9.3 を監査が拒否し、それぞれ GHSA-xjj6-f33q-929c / RUSTSEC-2022-0051 を検出した。fixture の依存コードは実行していない。
- 依存変更後も Web lint/typecheck・33単体テスト・build・Chrome E2E 5件が成功。Gate は追加した RED 3件を確認後、9件が成功。PR の dependency-review 省略を許さず、push/手動時の正常な省略だけを許可する。
- CodeQL の実行結果、更新 PR、fork/Dependabot PR の動作は GitHub での確認後に追記する。

### M0-3 初回計測

2026-10-25: `quality.yml` に Rust/Web カバレッジと既知の変異9件を週次・手動実行として追加。一般的な変異の調査は cargo-mutants 27.1.0 で core 全体を8分割し、週次または `full_mutations: true` で実行する。これらは PR の必須 Gate から分離する。

| ローカル実測 | 結果 | 対象 |
|---|---|---|
| Rust 行カバレッジ | 93.94%（1427 / 1519） | core。`tests/` の独立参照実装・統合テストと `examples/` を計測値から除外。WASM ラッパーは対象外 |
| Web 単体の行カバレッジ | 35.37%（127 / 359） | 未importの UI/3D ソースも含む。生成 WASM glue とブラウザ E2E の計測値は含まない |
| 既知の変異 | 9 / 9 をテスト失敗で検出 | 先手の前進方向、詰みの勝者、Zobrist seed、駒index、成り状態、駒名、エラー表示、持ち駒数、全7種類の持ち駒からの駒打ち |

Web の UI/3D は単体テストの未計測領域として残す。既存の実ブラウザ E2E 5件の成功と、単体テストのカバレッジは別の証拠として扱う。割合を上げる目的で対象ソースを除外しない。

変異スクリプトは元コードを一時領域にコピーし、baseline 成功後に1件ずつ変更する。元のワークツリーは変更しない。テスト0件・ビルド不能・timeout は検出成功に数えず失敗とする。この判定は RED 確認後に2テストが成功し、timeout を検出成功扱いする変異もテストが拒否した。通常 CI の制御用テストは計11件。

LCOV・HTML・JSON と変異ログを7日保存し、レポート欠落や計測行0件を成功扱いにしない。M0-1 の GitHub 初回実行では actionlint の導入Actionが未対応と判明したため、公式の1.7.12配布を固定 SHA256 で検証する導入に修正した（`c29432f`）。GitHub 実行結果と、全体変異調査の生き残りの分類は確認後に追記する。

ユーザー指定により Python は3.14系を基本とし、未対応の依存に限って3.13系を使う。現在は `.python-version` で3.14.9に固定し、計測ジョブにも setup-python を明示した。ローカルの集計処理は3.14.9で実行し、計測行0件を拒否する異常系も確認した。[Python 3.14.9](https://www.python.org/downloads/release/python-3149/)

広い変異調査で駒index・未成駒の成り判定・日本語駒名・エラー表示・持ち駒数・全7種類の持ち駒からの駒打ちの検証不足を発見し、手書きの期待値による6テストを追加した。追加したテストが各変異を拒否することを、コピー上で再現した。Rust は計86テスト。一般的な変異調査の生き残りを除外して数値だけを改善する設定は追加していない。

改善前の Rust 行カバレッジは92.56%だった。表の93.94%は最初の4テスト追加後（84テスト時）の計測値。計測用には test の最適化を0にし、最適化2で発生した LLVM の関数データ不一致の警告を解消した。通常の Rust テストは最適化2を維持する。

### GitHub での初回検証

- main の [CI run 40167203527](https://github.com/ayutaz/voxelshogi/actions/runs/40167203527): lint・Rust・MSRV・Web・依存監査・CI Gate が成功。PR 専用の dependency-review は意図した省略。
- main の [Security run 40167203380](https://github.com/ayutaz/voxelshogi/actions/runs/40167203380): Rust・JavaScript/TypeScript・Actions の CodeQL が成功。API で未解決 code scanning alerts は0件と確認。
- [Dependabot PR #1](https://github.com/ayutaz/voxelshogi/pull/1): 更新 PR の作成と、dependency-review・依存監査・全テスト・CodeQL・CI Gate の成功、本番 deploy の省略を確認。
- main でも PR 専用ジョブの省略が deploy に伝わる問題を発見したため、成功した Gate と非キャンセル状態を明示する条件に修正（`944c337`）。本番 deploy・公開後検証の追跡は M0-4 で行う。

### M0-4 公開版の確認と環境の制限

2026-10-25: `pnpm build` で commit SHA を `build-info.json` に保存し、同一 run の artifact を公開する。production の共通ロックを取得後に main の先頭と照合し、古い候補は公開しない。本番設定の不足を失敗とし、公開後は有限回の SHA 確認と E2E 6件を実行する。公開検証が成功した Cloudflare version ID と SHA は30日、失敗 trace は7日保存する。

- ローカルの Web lint・33単体テスト・型チェック付き build・Chrome E2E 6件が成功。JS/WASM の取得失敗をブラウザで注入して初期化の失敗を検出し、異なる公開 SHA も E2E が拒否した。一時検証ファイルは除去済み。
- デプロイ制御の9テストは RED 確認後に成功。設定不足、秘密値を含まないエラー表示、古い候補、誤った公開 SHA、HTML fallback、HTTP/通信障害、Cloudflare version ID の欠落・重複を検証した。古い候補や誤った配信版を許す変異もテストが検出した。CI 制御用テストは計20件。
- production の branch policy を設定し、許可元が `main` の1件だけであることを API で確認。承認者と待機時間は追加していない。
- Cloudflare の管理画面で、ユーザーが承認した `voxelshogi-github-production-20261025` を発行した。対象は指定の個人アカウントの全 Workers スクリプトの編集、有効期限なし。`gh secret set --env production` の標準入力へ直接登録し、値は会話・ローカルファイル・artifact に出していない。アカウント ID もプロジェクト専用ログインで照合して直接登録し、API で production の登録名と更新日時を確認した。
- 認証情報を artifact 経由で移行する workflow と、その暗号化用依存は、workflow の実行履歴が0件であることを確認して削除した。
- 新しい production Secrets を使った [本番 CI 40170836102](https://github.com/ayutaz/voxelshogi/actions/runs/40170836102) で公開・SHA 確認・E2E が成功。旧 repository Secrets の2件を削除し、production 側の2件が保持されていることを API で確認した。既存の Cloudflare トークン自体は失効させていない。復旧訓練は未実施。

### 2026-10-25 再確認と次の順序

- 品質計測 run `40168054255` の保存レポートを再取得し、Rust core 行カバレッジ94.27%（1432 / 1519）、Web 単体35.37%（127 / 359）を確認した。これは同 run のコミット `69e2904` の値で、未計測の後続変更まで保証するものではない。
- 人間同士の対局モードを削除した `0e29eb4` では、Vitest 33件・E2E 6件と公開 E2E が成功した。Rust は86件、CI 制御用テストは20件。画面は人間先手・人間後手の AI 対局と AI 観戦のみ（ADR-012）。
- 作業前のブランチ作成と PR を必須化した（ユーザー指定）。`AGENTS.md`、`CONTRIBUTING.md`、PR テンプレートを追加し、`.github/main-ruleset.json` を GitHub に適用した。API の有効ルールが定義中の全フィールドと一致することも確認した。
- [PR #2](https://github.com/ayutaz/voxelshogi/pull/2) の初回コミット `5b66f9a` で通常 CI・CodeQL・品質計測の起動を確認。品質計測を一度中断し、同じ run を再実行した。必須チェック未完了時に、リポジトリで許可された通常の squash merge を API へ要求したところ、7チェック未成功と CodeQL 結果待ちのため HTTP 405 で拒否され、`merged: false` と `mergeable_state: blocked` を確認した。失敗結果を Gate が拒否することは、ローカルの20テストでも検証済み。最新コミットの実行結果は PR の Checks に記録する。
- PR 更新時に、中断済みの上流ジョブを集約する `always()` Gate だけがキューに残り、新実行が workflow のロックを待つことを確認した。失敗・中断の検出を保つため Gate は維持し、通常 CI 全体の concurrency を外した。本番 deploy の production ロックと最新 SHA 確認は維持している。

2026-10-26（JST）: PR #3の最終文書 `ee7b102` も必須7チェック（通常CI・CodeQL・[Quality 40194273928](https://github.com/ayutaz/voxelshogi/actions/runs/40194273928)）が成功し、通常取り込み後のmain `1ff4e2f` で配信SHA・公開E2E 6件まで成功した。Cloudflare version IDは `ce499132-9c06-4a0c-aea6-8491a10fbfa7`。これをもってM0を完了した。[最終証拠](M0_VALIDATION.md)。その後のR0は冒頭の現況を参照し、当時は次の本格探索を [M1のTDD手順](M1_PLAN.md) とした。M1・M2はその後完了し、現在はM3の計画を策定済み。CIの状態取得は最短10分間隔、報告は状態変更時とし、CI待ちだけの短いwaitの反復も行わない。スキルとhookの運用は [開発手順](../CONTRIBUTING.md#ci-確認のスキルとhook) に従う。
