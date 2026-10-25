# CI/CD 調査と強化計画

調査日: 2026-10-25。対象: `ayutaz/voxelshogi`、調査時の main: `cbf14c5`。

**M1（探索AI）の前に、M0 として CI/CD と品質基盤を整える。** 現在はテストから自動デプロイまで動いているが、失敗した変更の main への取り込みを防ぐ設定と、依存関係・秘密情報・公開後の動作を継続的に確認する仕組みが不足している。

本書は調査結果・実装計画・検証記録。M0 を実装中。現行のデプロイ手順は [DEPLOYMENT.md](DEPLOYMENT.md)、実行順と進捗は [ROADMAP.md](ROADMAP.md#実行計画マイルストーン) に記録する。

## 現在の状態

ローカルの設定ファイルと GitHub REST API を照合した。最新コミットの [CI 実行](https://github.com/ayutaz/voxelshogi/actions/runs/40165004515) では Rust・Web・deploy の全ジョブと、本番デプロイ・スモークテストの各ステップが成功している。直近5回の main の push に対する CI はすべて成功している。

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
| M0-1 | CI 自体の誤りと環境のずれを検出する | `ci.yml`、`rust-toolchain.toml`、Web lint 設定、ビルドスクリプト | 固定環境で既存テストが通り、意図した lint・型・テストの失敗を検出する | 🟡 ローカル検証済み、CI 確認待ち |
| M0-2 | 依存関係とコードのセキュリティを継続確認する | `ci.yml`、`dependabot.yml`、`security.yml`、`deny.toml`、`SECURITY.md`、GitHub 設定 | 監査と CodeQL が成功し、更新 PR と非公開報告の経路が使える | 🟡 ローカル監査・保護機能の有効化済み、CI 確認待ち |
| M0-3 | テストの抜けを見えるようにする | `quality.yml`、計測・変異テスト設定 | Rust/Web の計測結果を保存し、既知のバグを再現可能な手順で検出する | ⬜ |
| M0-4 | 公開版を検証し、復旧できるようにする | deploy ジョブ、公開 E2E、ビルド情報、`DEPLOYMENT.md` | 公開版の SHA と対局操作を確認し、設定漏れ・配信障害が失敗になる | ⬜ |
| M0-5 | 失敗した変更の取り込みを防ぐ | main ruleset、`CONTRIBUTING.md`、PR テンプレート | 正常な PR は取り込め、必須チェック失敗の PR は取り込めない | ⬜ |

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
- `wasm-bindgen` 更新時は CLI とセットで検証する。Wrangler は Web の devDependency と lockfile で管理し、CI と `scripts/cf.sh` が同じものを起動する。現在の `npx --yes wrangler@4.152.0` / `pnpm dlx` の実行時解決を解消する。
- Rust は `cargo-deny` で既知の脆弱性・ライセンス・取得元を監査する。Web は `pnpm audit` を開発用依存も含めて実行する。PR/main だけでなく毎週も実行し、コード更新がなくても新規 advisory を拾う。Rust の既知の脆弱性は全件、Web は high/critical を必須チェックの失敗とする。例外は advisory ID・理由・期限を記録し、全体を無効化する回避はしない。[RustSec](https://rustsec.org/)
- 依存監査と dependency-review は `ci.yml` のジョブとして `CI Gate` に結び、週次でも同じ監査コマンドを使う。CodeQL は `security.yml` に分け、M0-5 で別の必須チェックまたは code scanning rule に結ぶ。独立した workflow 間を `needs` で参照する設計にはしない。
- PR では dependency-review で追加・更新された依存関係を確認し、high/critical を失敗にする。fork/Dependabot PR でも secrets なしで動かし、PR へのコメント書き込み権限は不要とする。[Dependency review](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-review)
- CodeQL を Rust・JavaScript/TypeScript・Actions に追加する。現在の公式対応言語に Rust と Actions も含まれる。PR/main/週次で実行し、SARIF のアップロードに必要な権限だけを解析ジョブに付与する。fork PR の権限差も検証する。[CodeQL の対応言語](https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-code-scanning)
- repository の Secret scanning・Push protection と private vulnerability reporting を有効化する。非公開報告が使えることを確認してから、その URL を案内する `SECURITY.md` を追加する。[GitHub の設定ガイド](https://docs.github.com/en/code-security/getting-started/quickstart-for-securing-your-repository)
- `GITHUB_TOKEN` の既定 read 権限を維持する。未信頼の PR コードを secrets や書き込み token と同じ実行環境で動かさず、`pull_request_target` で PR head を実行する構成を導入しない。

**検証**: 通常 PR・Dependabot PR・fork PR の経路を確認する。監査対象に既知の脆弱性を持つ依存を置いた隔離 fixture で監査が失敗することを確かめる。Secret scanning は設定値を再取得して確認し、本物の認証情報をテスト用に push しない。CodeQL は対象言語ごとの解析完了と alert の初回トリアージを確認する。

### M0-3 テスト品質の計測

- Rust は cargo-llvm-cov、Web は Vitest coverage を使い、生成された WASM の JS glue や独立した参照実装などを製品コードの計測対象と区別する。LCOV/HTML と要約を GitHub artifact / Job Summary に保存し、外部サービスを必須にしない。[cargo-llvm-cov](https://github.com/taiki-e/cargo-llvm-cov)
- 最初に現状のカバレッジと所要時間を計測する。割合だけを上げるテストは作らず、未検証の重要分岐から改善する。一律90%などの数値は実測前に必須化しない。
- Rust のルール・終局判定・ハッシュを対象に、既知の変異を検出できる手順を自動化する。cargo-mutants を使う場合も、元コードで成功することを先に確かめ、ビルド不能や timeout を「テストがバグを検出した」と数えない。生き残った変異は、意味が変わらない変異かテスト不足かを確認する。[cargo-mutants](https://github.com/sourcefrog/cargo-mutants)
- カバレッジと小さな変異セットの再現を M0 で確認し、重い全体の変異テストは週次・手動に分ける。M1 の探索コードは追加時に対象へ組み込む。TDD の RED 確認と手計算・参照実装による期待値は、CI に移しても省略しない。

**検証**: 空のテスト対象や欠落したレポートを成功扱いにせず、既知のバグを対象のテストが実際に落とすことをログに残す。M0 完了時に計測値と対象外の範囲を本書に追記する。

### M0-4 デプロイと公開後の検証

- PR はテストのみ、main の push はテスト済みの同じ artifact を公開する構成を維持する。`CI Gate` の成功を deploy の前提にする。artifact と配信ファイルに commit SHA を付け、本番 E2E は配信版が対象 SHA と一致することを先に確認する。
- PR の古い CI は中断してよいが、実行中の本番 deploy と公開検証は次の push で中断しない。workflow 全体の現在の cancel 設定を見直し、deploy〜公開検証を共通の concurrency group で直列化する。ロック取得後に candidate SHA と main の先頭を比較し、古い候補はデプロイせず理由を Summary に記録する。concurrency だけではコミット順の公開は保証できない。[GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- production のデプロイ元を main に限定し、Cloudflare secrets を repository から production environment へ移す。必要なジョブ・ステップにだけ渡す。まず環境側で動作を確認してから repository 側を削除する。対話式の本番承認は日常の自動デプロイに追加しない。[GitHub environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments)
- main の本番 deploy では、API トークン・アカウント ID・サブドメインの不足を明示的に失敗させる。PR と通常の手動 CI が deploy しないことは正常動作として区別する。実装時に ADR-008 の「secrets 未登録ならスキップ」を改訂する。
- 公開 URL に対して、既存5件の Playwright E2E を自動実行する。HTML に加え、JS/WASM のロード、初期表示、着手・AI応答・undo・棋譜入出力を実ブラウザで確認する。反映待ちは有限回・有限時間にし、trace と対象 SHA を失敗 artifact に保存する。テストはブラウザ内の対局状態だけを変更する。
- デプロイに失敗した場合と、デプロイ後の E2E に失敗した場合を区別して Job Summary に表示する。Cloudflare version ID・commit SHA・最後に公開検証が成功した版を記録し、手動の復旧手順を `DEPLOYMENT.md` に加える。公開 E2E の一時的な失敗だけで自動 rollback する仕組みは初期導入に含めない。復旧の実動作は隔離した環境またはローカルの旧 artifact で確認する。[Cloudflare rollback](https://developers.cloudflare.com/workers/wrangler/commands/workers/#rollback)

**検証**: 非本番の検証経路で設定漏れ・誤った配信 SHA・JS/WASM の取得失敗を検出する。近接する2回の main 更新でも deploy が中断・競合せず、最後に最新の成功版が配信されることを確認する。復旧手順では戻す版の明示と復旧後の公開 E2E を必須にする。

### M0-5 PR と main 保護

- M0-1〜4 のチェックが main で成功してから、main の ruleset を設定する。PR 経由・必須 `CI Gate`・最新 main に対する検証を要求し、force push とブランチ削除を禁止する。日常運用の bypass は設けない。[利用できるルール](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- 一人開発でも進められるよう、他者による承認の必須数は0とする。PR 自体と必須チェックは要求する。CodeQL は解析結果を別の必須チェックまたは code scanning rule に結び、解析成功だけで high/critical の alert を見逃さない構成にする。
- 必須 Gate には lint・Rust・Web・依存監査を含め、PR 専用の dependency-review も PR では必須とする。定期品質計測や本番 deploy は PR の Gate に含めない。条件付きのジョブを一律成功扱いにする設計は避ける。
- `CONTRIBUTING.md` と PR テンプレートに、TDD、独立した期待値、変異テスト、ローカル確認コマンド、ドキュメント更新、AI が作った差分も確認することを記載する。`CLAUDE.md` の手順も PR 運用へ変更する。

**検証**: 検証用 PR の必須テストを一時的に失敗させ、merge が許可されないことを API/UI で確認する。修正後にチェックが成功し、自己承認なしで取り込めることを確認する。fork/Dependabot PR に本番 secrets が渡らず、deploy も起動しないことを確認する。必須チェック名・ruleset・production の設定を再取得し、本書に記録する。

## 定常運用

| タイミング | 実行内容 | 役割 |
|---|---|---|
| PR / main push | lint、Rust、WASM、Web、ローカル E2E、依存監査、CodeQL。dependency-review は PR のみ | 取り込み前と統合後の検証 |
| main の検証成功後 | 同じ artifact を deploy、配信 SHA 確認、公開 E2E | 公開版の動作確認 |
| 週次 / 手動 | 依存監査、CodeQL、カバレッジ、変異テスト。Dependabot の更新確認 | コード更新がなくても問題を検出 |

PR の通常 CI は、既存の実行時間（最新 run は Rust 約26秒、Web 約84秒。キュー待ちを除く）を基準に、追加後の時間を計測する。重い品質計測は別 workflow とし、初期の通常 CI は5分程度を目安にする。これは実測前の目標であり、5分を超えたことだけでテストを省略しない。

GitHub Actions の **Public リポジトリの標準 GitHub-hosted runner** は無料で利用できる。M0 は標準 Ubuntu runner を使い、有料の larger runner、外部カバレッジサービス、GPU、R2 を追加しない。artifact は原則7日、重い計測結果は必要なものだけ保存する。[GitHub の料金条件](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

## 後続マイルストーンで追加するもの

| 時期 | 追加する検証・運用 |
|---|---|
| M1 | 高速適用と検証付き適用の一致、手計算評価、少数駒局面の minimax 深さ1〜3との一致、詰み・駒損回避・合法手、固定深さ/ノードの再現性。最適化前後の評価値とノード数を比較。実時間の速さは計測値として保存する |
| M2 | Worker の思考中の UI 操作、中断・新規対局・undo 後の古い応答の破棄、Easy/Normal の合法手、公開 E2E、バンドルサイズの計測 |
| M3 | モデル変換と各 runtime の数値一致、対応演算子と配信上限。WebGPU が使える環境での検証を分離する |
| M4 | Python lint/test、Rust バインディング、少量データの同一 seed 再生成・ハッシュ比較・検証・分割漏れ検出。10万局面の生成は通常 PR CI に入れない |
| M6 | 小さな学習と checkpoint 再開の一致、ONNX 出力の一致。GPU 本学習は見積もり・承認後に実行し、通常 CI と分ける |
| Phase 7 | 複数ブラウザ・モバイル・アクセシビリティ、公開監視、必要になった場合の PR preview と release 自動化 |

M1 では、同じ固定深さ・固定ノード数で同じ結果になることと、時間上限で停止することを別のテストにする。実時間だけの上限では環境負荷により到達深さが変わるため、同じ手を保証する再現性条件には使わない。

M0 の完了は、設定ファイルが存在することではなく、正常時の成功と異常時の検出、取り込み制御、公開後の検証までの確認で判断する。性能の厳密な回帰閾値や全環境のテストを最初から必須にはせず、M1 以降の実測に合わせて増やす。

## 実装と検証の記録

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
