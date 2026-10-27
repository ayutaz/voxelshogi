# CLAUDE.md — VoxelShogi

9×9×9（729マス・372枚）の三次元将棋を題材にした、再現可能な三次元将棋 AI 研究プラットフォームです。対象は、ルールエンジン、ブラウザゲーム、合成データセット、Transformer モデル、分散学習です。

**主用途はAI vs AIの対局を見て・眺める観戦で、そのためのモデル開発と研究を行う。** ゲームの面白さ、初見での分かりやすさ、見映え、モデル比較の再現性を重視する。人間 vs AIは補助的な参加方法とし、人間同士の対局・マルチプレイは対象にしない（2026-10-26 ユーザー指定）。

- 現在地・公開／品質の確認元: `docs/STATUS.md`
- 次の実行計画: `docs/M3_PLAN.md`（ブラウザ推論の環境確認・変換・数値照合・実機計測・公開デモ。計画策定済み、実装未着手）。全体の順序は `docs/ROADMAP.md`。完了したM2の契約・検証・公開実測は `docs/M2_PLAN.md` と `docs/M2_VALIDATION.md`
- 仕様: `docs/PROJECT_SPEC.md`
- ルール（正）: `docs/RULESET.md`
- 計画・進捗（フェーズごとの目的とゴール）: `docs/ROADMAP.md`
- 設計判断: `docs/ARCHITECTURE_DECISIONS.md`、エンジン: `docs/GAME_ENGINE.md`、デプロイ: `docs/DEPLOYMENT.md`
- M1 前の CI/CD 強化計画と検証記録: `docs/CI_CD_PLAN.md`（M0。完了）
- ルール・観戦表示の試作結果: `docs/NINE_KINGS_EXPERIMENT.md`（R0。正式採用は保留）
- 探索AIの実装手順と完了条件: `docs/M1_PLAN.md`（M1完了）、検証・Native計測: `docs/M1_VALIDATION.md`

## 構成

| パス | 役割 |
|---|---|
| `crates/voxelshogi-core` | 純粋Rustのルールエンジン。ブラウザ・Python・GPUには依存しない。**ルールはここにだけ実装する** |
| `crates/voxelshogi-wasm` | wasm-bindgen による薄いラッパー（`Game`／`ExperimentReplay` クラス）。ルールを再実装しない |
| `apps/web` | VoxelShogi Arena（Vite + React + three/R3F）。エンジンの出力をデコードして表示するだけ |
| `docs/` | 仕様・ADR・調査・見積もり・`experiments/` の固定集計 |
| `crates/voxelshogi-core/src/search.rs` | M1の標準1王・全幅αβ探索。WASM `Game.bestMove` を専用Workerで実行 |
| `apps/web/src/ai` | 履歴付きWorker・応答照合・観戦制御。Normalは深さ6／50,000ノード／約1秒が既定 |
| `scripts/experiment-pack.mjs` | R0のJSONLをWASMで再生照合し、集計と代表棋譜を作成 |
| `apps/web/public/experiments` | 400／800手の代表棋譜6件と配信用manifest。学習モデルではない |
| `scripts/build-wasm.sh` | WASM を `apps/web/src/wasm/pkg`（git管理外）にビルドする |
| `scripts/cf.sh` | プロジェクト専用ログイン（`.cloudflare-cli/`、git管理外）で wrangler を起動する（ADR-010） |
| 予定 | `crates/voxelshogi-python`（PyO3）、`training/`、`export/`、`infrastructure/` |

## 開発規約（必読）

- **実装・文書変更の前に必ず作業ブランチを作る。main に直接 commit / push しない。** `AGENTS.md` と `CONTRIBUTING.md` に従い、PR を作成して必須7チェックの成功後に取り込む。main 保護を無効化したり bypass したりしない。
- **TDD を厳守する**（ユーザー指示）。テストを先に書き、失敗（RED）を確認してから最小の実装をする。
  - テストは、空の結果で通ってしまう抜け穴がないように書く。
  - 期待値は「ルール文からの手計算」または「独立した参照実装」で用意する。エンジンの出力をそのまま正解値にしない。
  - 新しいテストを足したら、実装にバグを注入して検出できるか確認する（変異テスト）。
- 参照実装 `crates/voxelshogi-core/tests/common/mod.rs` は、ルール文を素朴に書き写したもの。本実装とアルゴリズムを共有させない。
- ルールの変更・追加は、`docs/RULESET.md` を先に更新する。変更すると既存データと互換性がなくなる場合は、`ruleset_id` を変える。
- Zobristの固定シードとテストの期待値（標準初期値 `043b66e12f6b84fd`）を変えない。棋譜・公開試料・将来のデータセットの再現性に関わる。
- 第三者コード（将棋ったー、tomikan/3D_shogi など）はコピーしない。ライセンスは `docs/RELATED_WORK.md` を参照。
- 秘密情報はコミットしない（`.env*`, `.dev.vars` は gitignore 済み）。費用が発生する操作（GPU レンタル、有料プランなど）は、見積もりを示してユーザーの承認を得てから行う。

## コマンド

```bash
cargo test --locked --workspace            # Rust（core153件＋WASM境界5件、testはopt-level 2）
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo fmt --all
cargo run --locked --release -p voxelshogi-core --example bench   # 合法手生成の速度

cd apps/web
pnpm install --frozen-lockfile
pnpm wasm          # WASM ビルド（wasm32 target と wasm-bindgen-cli 0.2.129 が必要）
pnpm test          # Vitest（実 WASM を Node で読み込む）
pnpm typecheck
pnpm build
E2E_COMMIT="$(git rev-parse HEAD)" pnpm e2e # 全21件。ローカルはChrome、CIはPW_CHANNEL=''でChromium
pnpm dev

# 以下はリポジトリのルートで実行する
cd ../..
# 公開サイト
scripts/cf.sh whoami                                        # 個人アカウントであることを確認
scripts/cf.sh deploy                                        # apps/web/dist を手動デプロイ
published_commit='REPLACE_WITH_PUBLISHED_COMMIT_SHA'
E2E_BASE_URL=https://voxelshogi.yousan-apps.workers.dev E2E_COMMIT="$published_commit" pnpm --dir apps/web e2e
```

## 決定事項（ユーザー確認済み）

- 対局モードはAI vs AI観戦を主とし、人間 vs AIを補助機能とする。人間同士の対局（ローカル・オンライン）とマルチプレイは実装しない。
- GitHub は `ayutaz/voxelshogi`。2026-10-25 に Public 化した。GitHub Actions（Public は無料）を最大限活用し、すべてのテストを CI で回す。
- コードのライセンスは Apache-2.0（Copyright 2026 ayutaz）。モデル・データセットのライセンスは、公開前にユーザーに確認する。
- Python は可能な限り3.14を使い、依存ツールが未対応の場合は3.13にする（ユーザー指定）。現在の固定値は `.python-version`。古い版が必要な場合は理由と対象を記録する。
- 公開 Web デモでは、変換済みモデルそのものを対象実機のブラウザで動かす。FP16化・量子化した公開版も選択して対局・観戦できるようにし、評価した配布ファイルとデモで読むファイルの SHA-256 を一致させる。各版の精度・棋力・速度・サイズを記録する（M3・M6）。
- Hugging Face の名前空間は `ayousanz/`（`ayutaz` という HF ユーザーは存在しない）。
- 標準ルールは将棋ったー三次元将棋の10/17改定後版を独立実装し、未記載の終局条件は同サイトの既定を継承する。実棋譜との互換性検証はM5で未実施。R0の9王試作3ルールは別IDで管理し、標準ルールへ正式採用していない。
- 公開 URL はまず workers.dev を使う。デプロイは GitHub Actions から行う（Cloudflare 側の Git 連携は使わない）。理由は `docs/DEPLOYMENT.md` を参照。
- Cloudflare は、ユーザーの個人アカウント（ka1357amnbpdr@gmail.com）を使う。このマシンの wrangler はグローバルには別アカウントでログインしているため、**必ず `scripts/cf.sh`（プロジェクト専用ログイン）経由で wrangler を使う**。素の `wrangler` は使わない（`apps/web` の `pnpm run deploy` も `scripts/cf.sh` を経由する。`pnpm deploy` は pnpm の組み込みコマンドなので使わない）。
- 将棋ったーの公開棋譜による互換性検証は、ローカルでのみ行う（棋譜はコミットしない）。

## 現在の進捗と次の作業

進捗の詳細と、各フェーズの目的・ゴール（完了条件）は `docs/ROADMAP.md` にある。フェーズを完了とするのは、ゴールの全項目を満たしたときだけ。

- 完了
  - Phase 0: 調査と設計
  - Phase 1: ルールエンジン（標準ルール、VSFEN、棋譜、セッション）
  - Phase 2: Web ゲーム Alpha。https://voxelshogi.yousan-apps.workers.dev に公開し、main への push で CI から自動デプロイされる
  - M0: CI/CD と品質基盤。必須7チェックによるmain保護、公開E2E、隔離復旧訓練、全758変異の調査と分類を確認済み。PR #3の最終文書も取り込み済みで、統合コミット `1ff4e2f` の本番公開・配信SHA・公開E2E 6件まで2026-10-26（JST）に成功した（`docs/M0_VALIDATION.md` の完了時記録）
  - R0: 9王ルール3候補と現行1王の対照、計1,052局の比較・全手照合、同一棋譜のA/B観戦試作を完了。PR #7・必須7チェック・main自動公開・実機Chromeの公開E2E 9件と公開用6棋譜のSHA一致を確認した。正式採用と観戦者による理解度評価は保留（`docs/NINE_KINGS_EXPERIMENT.md`）
  - M1: 探索AI（Rust）。独立参照探索・戦術・上限と再現性、全1,172変異の分類、Native計測を完了（`docs/M1_VALIDATION.md`）
  - M2: 履歴付きWorker探索・両AIのEasy/Normal観戦・中断と再試行・3D分割を完了。PR #13〜#16の必須CIと通常取り込み、最終main `e212ec7` の自動公開・配信SHA・公開E2E、実機Chromeの全21件・固定7局面の計測と配信artifact照合を確認（`docs/M2_VALIDATION.md`）
- **次にやること**: `docs/ROADMAP.md` の「実行計画（マイルストーン）」の順に進める。
  1. M3: `docs/M3_PLAN.md` に従い、Python3.14の環境・入出力契約の確認から始める。モデル実装は未着手
  2. M4: Python バインディングとデータ生成
  3. M5: 将棋ったー棋譜との互換性検証（棋譜がそろい次第、いつでも）
  4. M6: Transformer-S の学習
- ユーザー側の準備事項は、`docs/ROADMAP.md` の「ユーザー側の準備」にある。
