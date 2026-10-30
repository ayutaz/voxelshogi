# 開発手順

## ブランチと PR

1. `git status` で既存の変更を確認する。main から新しい作業を始める場合は `git switch main`、`git pull --ff-only` の後、**変更前に** `git switch -c <種別>/<作業名>` を実行する。
2. 作業ブランチで変更・検証・commit を行い、`git push -u origin HEAD` で公開する。既存の変更を混ぜず、履歴の書き換えや force push は行わない。
3. main 向けの PR を作り、目的、変更後の動作、検証結果、残る制約を記載する。AI が作成した差分も内容を確認する。
4. 必須チェックがすべて成功し、最新 main に対する検証が済んでから GitHub の squash merge を行う（リポジトリで許可された取り込み方式）。main が進んだら `git fetch origin` と `git merge origin/main` で取り込み、再検証する。

main は PR 必須、force push・削除禁止、bypass なし。他者承認の必須数は0。チェックの失敗・中断・欠落を、保護の解除や管理者権限で回避しない。設定の正は `.github/main-ruleset.json`、確認記録は [CI_CD_PLAN.md](docs/CI_CD_PLAN.md)。

CI の状態取得は最短10分間隔とし、利用者への報告は状態が変わったときに行う。CI待ちだけの短いwait/sleepやタイマー出力の再取得も繰り返さない。継続が必要な場合は、新しい入力で中断できる10分以上の待機を一度使い、1分刻みへ分割しない。runner のキュー待ちとジョブの実行時間を区別し、待機だけを理由に実行中の workflow を中断・再実行しない。失敗を検知した後のログ調査は進めてよい。

## CI 確認のスキルとhook

[ci-checks](.agents/skills/ci-checks/SKILL.md) をCIの確認・取り込み時に使う。`.codex/hooks.json` の SessionStart が方針を案内し、PreToolUse が認識できる `gh` の再取得・短いwatch・CI文脈でのwaitを拒否する。独自クライアントや一部のツール経路を完全には制限できないため、スキルも併用する。通常のビルド待ちや失敗ログ調査は妨げない。

初回は Codex CLI の `/hooks` で、このリポジトリの2件を確認して信頼する。公式仕様では、新規・変更されたhookは定義の信頼前にはスキップされる。信頼設定の手書きやbypassで有効化したことにはしない。[公式Hooks仕様](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks)

状態は git 管理外の `.codex/.local/ci-poll-guard/` に保存する。取得時刻と待機中セッションだけを記録し、コマンド・出力・認証情報は保存しない。ローカル状態の破損・残存lockがある場合は、監視が停止していることを確認してこのディレクトリを除去し、次回の単発確認で再作成する。テストは通常CIの `node --test scripts/ci/*.test.mjs` に含まれる。

## 実装と検証

- 仕様・ルールを確認し、テストを先に書いて RED を確認してから実装する。期待値は手計算か独立した参照実装で用意し、空の結果で通らないようにする。
- 新しいテストが対象のバグを検出することを、変異の注入で確認する。一時的な変異は成果物に残さない。
- ルール変更は `docs/RULESET.md` を先に更新し、互換性に応じて `ruleset_id` を変更する。進捗・完了条件は `docs/ROADMAP.md` に反映する。
- Python は `.python-version`（3.14系）を使い、依存が未対応の場合のみ3.13へ切り替える。さらに古い版が必要なら理由・対象・解消条件を記録する。
- Pythonの実行は `uv run --locked`、依存追加は `uv add`（開発用は `uv add --dev`）。`uv.lock` をcommitし、CIで `uv sync --locked`・`uv audit --locked`・Pythonテストと既知変異を実行する。LinuxのtorchはCPU専用indexを使う。
- Python境界はuv workspaceの`crates/voxelshogi-python`をmaturinでビルドする。ビルドは1ジョブ、ソース・Cargo.lockをuvのcache keyへ含める。少量データ生成・単独検証は [M4の負荷上限付きCLI](docs/M4_DATA_CONTRACT.md#実行と制限) を使い、本生成をMacで行わない。
- この作業環境のエージェントはMacで探索・生成・計測・学習・重い回帰検証を行わない。Macは編集・読み取り・軽量な確認のみとし、フル検証はCI、実機計測と学習は承認済みVast.ai／CloudRiftで実行する。[現在の運用](docs/M4_REMOTE_PLAN.md)。CIの性能を外部GPU実機の性能と読み替えない。
- 秘密情報を commit・ログ・会話・artifact に含めない。Cloudflare のローカル操作は `scripts/cf.sh` を使う。費用の発生する操作は見積もりと事前承認が必要。

文書のみの変更は、実装・設定との照合、リンク、記載したコマンドやAPI例、実測値の出典を検証する。過去の検証記録は日時と対象コミットを残し、現況と区別する。文章の変更のためだけに製品コードへ変異を入れたり、文章を写しただけのテストを追加したりしない。現在地と文書の役割は [STATUS.md](docs/STATUS.md)、M6の実績は [M6_COMPLETION.md](docs/M6_COMPLETION.md)、次の目的・作業・完了条件は [POST_M6_PLAN.md](docs/POST_M6_PLAN.md) を参照する。[M3_PLAN.md](docs/M3_PLAN.md) は完了した技術検証の契約として保持する。

変更に関連する検証を実行する。Rust、Node、pnpm、wasm-bindgenの版は固定値に合わせる（`rust-toolchain.toml`、`.node-version`、Webの `packageManager` / lockfile）。Pythonは `.python-version` を使う。ローカルE2Eは既存Chrome、CIは `PW_CHANNEL=''` でChromiumを使う。

```bash
cargo fmt --all --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked --workspace
node --test scripts/ci/*.test.mjs
node scripts/ci/mutation-controls.mjs
actionlint
shellcheck scripts/*.sh scripts/ci/*.sh

cd apps/web
pnpm install --frozen-lockfile
pnpm lint
pnpm wasm
pnpm typecheck
pnpm test
pnpm build
E2E_COMMIT="$(git rev-parse HEAD)" pnpm e2e
```

`E2E_COMMIT` を指定すると配信SHAを含む全21件を検証する。省略した実行ではSHAの1件がskipになる。公開先へ実行する場合は、ローカルHEADではなく対象の公開SHAを指定する。

## PR と公開の自動チェック

PR では docs のみの変更でも、通常 CI、CodeQL、Rust/Web カバレッジ、既知の39変異（coreとWASM／Python境界）・Web142変異・Pythonモデル23変異・Python境界／データ／資源監視／pilot／HF公開／本生成／棋譜変換／本生成公開・終了制御／M6教師契約・読み込み／損失・保存再開・CUDA起動前・固定評価・学習済み変換・Vast.ai・共有IP制御／評価v2の契約・runner／Phase5〜6費用制御／評価局面・漏洩照合／研究ラベル・自己対局探索・履歴複製・疎損失・Actor・Policy/Value・paired教師・Replay266変異・CI制御45変異の回帰検証を実行する。Pythonジョブは実Rust拡張をビルドし、少量データの生成・全件検証・停止再開もテストする。Webジョブは実WASM単体に加えて `node scripts/ci/search-parity.mjs` でNativeとの全探索結果を照合する。`Web unit coverage` は `node scripts/ci/mutation-web.mjs` でも既知のWorker・観戦・描画準備のバグを注入する。必須チェックは次の8件（M3でPython CodeQLを追加）。

- `CI Gate`（lint、Rust、MSRV、WASM/Web/実ブラウザ E2E、公開E2E用WASMのジョブ間受け渡し、依存監査、PR の dependency-review の成功を集約）
- `CodeQL (rust)`、`CodeQL (javascript-typescript)`、`CodeQL (actions)`、`CodeQL (python)`
- `Rust core coverage`、`Web unit coverage`、`Known mutation regressions`

M3の `Browser model inference (real WASM)` もCI Gateへ必須の依存として含める。uvから3形式を生成してlocalhostで実際に読み込み、専用Worker・全出力照合・描画と中断・破損／未対応表示の6 E2Eを行う。GPUを持たないCIは実機GPUの証拠にはしない。モデルのライセンス確定までは、生成物をこのジョブ内だけに置き、モデルやtraceをartifactへ公開しない。

モデル公開の設定は `export/publication.json`。M3検証用IDは承認済みで`approved=true`・`license=Apache-2.0`。新しい未承認のモデルは承認が得られるまで`approved=false`・`license=null`を維持する。承認の対象はこのIDの未学習モデルだけで、M6の学習済みモデルへ拡大しない。公開時はclean source・全3形式・ライセンスとModel Cardを検証し、実モデルE2Eを通った同じ配布物を公開する。公開後は `scripts/verify-model-distribution.mjs` がアプリのWorker・モデル・参照値・ORT全ファイルの実配信SHA、サイズ、MIME、cacheを確認する。アプリの実ファイル一覧はbuild時の `inference-build.json` に保存する。承認待ちの条件分岐がskipされたことを、公開経路の成功とは数えない。

実機検証の再現コマンド（事前にWASMビルド・依存導入を行う）：

```bash
uv run --locked python -m export.generate runs/m3/local
node scripts/prepare-inference.mjs runs/m3/local apps/web/public/models/m3 --local
pnpm --dir apps/web build
pnpm --dir apps/web exec playwright test -c model-playwright.config.ts
# 別ターミナルでpnpm --dir apps/web preview --port 4173を起動してから実行する
node scripts/measure-browser-models.mjs runs/m3/browser-measurement.json
```

計測は3Dあり／なし・各4入力・3形式・WASM／WebGPUを対象に、初回、準備10回＋測定30回、20回のモデル切替を保存する。取得可能なmain JS heapとChrome所有プロセスのRSS、管理tensor量を区別し、GPU総量は取得不可の理由を残す。Macでは計測プロセスの実行中だけアイドル休止を抑止する。観測が5秒を超えて途切れた試行は成功に含めない。`--smoke` は短い動作確認であり、M3完了の計測には数えない。公開前のモデル生成に `--license` を勝手に追加しない。

切替は初回ロードを除き、直前と異なる形式を20回選ぶ。`--switches-only` はこの資源解放の追加検証だけを行い、全48組の性能計測完了とは表示しない。

`--switches-only --switch-backend=webgpu` はWebGPUで数値検証済みのFP32とINT8重み版を20回交互に切り替える。既定のWASMでは全3形式を対象にする。FP16×M1 WebGPUの数値基準未達は全組計測へ残し、この切替検証で対応済みと読み替えない。

GitHub Actions が発行したチェックだけを受理し、CodeQL の error と high/critical セキュリティ警告も取り込みを止める。カバレッジは測定とレポートの保存を必須とし、一律の割合基準は設けない。全体の cargo-mutants 調査は週次・手動で行う。

PR・fork・Dependabot には production の Cloudflare Secrets を渡さず、本番 deploy は実行しない。main の push では統合後の通常 CI が成功した後、同じ run のビルド成果物を公開し、配信 SHA と公開 E2E を検証する。[デプロイと復旧手順](docs/DEPLOYMENT.md)

C0のカメラ／探索回帰は通常Web CIと公開後に各3回・1 worker・retries=0で追加検証する。通常E2Eの再試行成功だけでこの反復検証の失敗を取り込まない。診断JSONは対象テストのattachmentとCIログに記録する（[原因・再現手順](docs/C0_VALIDATION.md)）。

## Hugging Face公開と保存場所

repo作成・公開は[hf-publication](.agents/skills/hf-publication/SKILL.md)と[公開ハーネス](docs/HF_PUBLICATION.md)を使う。生成物をMacへ中継せず、外部Linuxから`voxelshogi/`配下へ送信する。public/manual・Community OFF・Dataset Card・ライセンス・ファイル一覧とhashを検査し、固定Hub revisionでの全件照合後に転送完了とする。純粋テストと既知変異はCIへ含めるが、CIで実repoを作成したりデータを公開したりしない。
