# CLAUDE.md — VoxelShogi

9×9×9（729マス・372枚）の三次元将棋を題材にした、再現可能な三次元将棋 AI 研究プラットフォームです。対象は、ルールエンジン、ブラウザゲーム、合成データセット、Transformer モデル、分散学習です。

- 仕様: `docs/PROJECT_SPEC.md`
- ルール（正）: `docs/RULESET.md`
- 計画・進捗（フェーズごとの目的とゴール）: `docs/ROADMAP.md`
- 設計判断: `docs/ARCHITECTURE_DECISIONS.md`、エンジン: `docs/GAME_ENGINE.md`、デプロイ: `docs/DEPLOYMENT.md`

## 構成

| パス | 役割 |
|---|---|
| `crates/voxelshogi-core` | 純粋Rustのルールエンジン。ブラウザ・Python・GPUには依存しない。**ルールはここにだけ実装する** |
| `crates/voxelshogi-wasm` | wasm-bindgen による薄いラッパー（`Game` クラス）。ルールを再実装しない |
| `apps/web` | VoxelShogi Arena（Vite + React + three/R3F）。エンジンの出力をデコードして表示するだけ |
| `docs/` | 仕様・ADR・調査・見積もり |
| `scripts/build-wasm.sh` | WASM を `apps/web/src/wasm/pkg`（git管理外）にビルドする |
| `scripts/cf.sh` | プロジェクト専用ログイン（`.cloudflare-cli/`、git管理外）で wrangler を起動する（ADR-010） |
| 予定 | `crates/voxelshogi-python`（PyO3）、`training/`、`export/`、`infrastructure/` |

## 開発規約（必読）

- **TDD を厳守する**（ユーザー指示）。テストを先に書き、失敗（RED）を確認してから最小の実装をする。
  - テストは、空の結果で通ってしまう抜け穴がないように書く。
  - 期待値は「ルール文からの手計算」または「独立した参照実装」で用意する。エンジンの出力をそのまま正解値にしない。
  - 新しいテストを足したら、実装にバグを注入して検出できるか確認する（変異テスト）。
- 参照実装 `crates/voxelshogi-core/tests/common/mod.rs` は、ルール文を素朴に書き写したもの。本実装とアルゴリズムを共有させない。
- ルールの変更・追加は、`docs/RULESET.md` を先に更新する。変更すると既存データと互換性がなくなる場合は、`ruleset_id` を変える。
- Zobrist ハッシュの固定値（`zobrist::tests::INITIAL_HASH`）を変えると、公開データセットのハッシュがすべて変わる。変えないこと。
- 第三者コード（将棋ったー、tomikan/3D_shogi など）はコピーしない。ライセンスは `docs/RELATED_WORK.md` を参照。
- 秘密情報はコミットしない（`.env*`, `.dev.vars` は gitignore 済み）。費用が発生する操作（GPU レンタル、有料プランなど）は、見積もりを示してユーザーの承認を得てから行う。

## コマンド

```bash
cargo test --workspace                     # Rust（約8秒、プロファイル test は opt-level 2）
cargo clippy --workspace --all-targets -- -D warnings
cargo fmt --all
cargo run --release -p voxelshogi-core --example bench   # 合法手生成の速度

cd apps/web
pnpm install
pnpm wasm          # WASM ビルド（wasm32 target と wasm-bindgen-cli 0.2.129 が必要）
pnpm test          # Vitest（実 WASM を Node で読み込む）
pnpm typecheck
pnpm vite build && pnpm e2e   # Playwright（ローカルはインストール済み Chrome、CI は PW_CHANNEL='' で Chromium）
pnpm dev

# 公開サイト
scripts/cf.sh whoami                                        # 個人アカウントであることを確認
scripts/cf.sh deploy                                        # apps/web/dist を手動デプロイ
E2E_BASE_URL=https://voxelshogi.yousan-apps.workers.dev pnpm e2e   # 公開サイトに E2E を実行
```

## 決定事項（ユーザー確認済み）

- GitHub は `ayutaz/voxelshogi`。2026-10-25 に Public 化した。GitHub Actions（Public は無料）を最大限活用し、すべてのテストを CI で回す。
- コードのライセンスは Apache-2.0（Copyright 2026 ayutaz）。モデル・データセットのライセンスは、公開前にユーザーに確認する。
- Hugging Face の名前空間は `ayousanz/`（`ayutaz` という HF ユーザーは存在しない）。
- ルールは将棋ったー三次元将棋の 10/17 改定後版。未記載の終局条件は将棋ったーの既定を継承する。
- 公開 URL はまず workers.dev を使う。デプロイは GitHub Actions から行う（Cloudflare 側の Git 連携は使わない）。理由は `docs/DEPLOYMENT.md` を参照。
- Cloudflare は、ユーザーの個人アカウント（ka1357amnbpdr@gmail.com）を使う。このマシンの wrangler はグローバルには別アカウントでログインしているため、**必ず `scripts/cf.sh`（プロジェクト専用ログイン）経由で wrangler を使う**。素の `wrangler` は使わない（`apps/web` の `pnpm run deploy` も `scripts/cf.sh` を経由する。`pnpm deploy` は pnpm の組み込みコマンドなので使わない）。
- 将棋ったーの公開棋譜による互換性検証は、ローカルでのみ行う（棋譜はコミットしない）。

## 現在の進捗と次の作業

進捗の詳細と、各フェーズの目的・ゴール（完了条件）は `docs/ROADMAP.md` にある。フェーズを完了とするのは、ゴールの全項目を満たしたときだけ。

- 完了
  - Phase 0: 調査と設計
  - Phase 1: ルールエンジン（全ルール、VSFEN、棋譜、セッション）
  - Phase 2: Web ゲーム Alpha。https://voxelshogi.yousan-apps.workers.dev に公開し、main への push で CI から自動デプロイされる
- **次にやること**: `docs/ROADMAP.md` の「実行計画（マイルストーン）」の順に進める。
  1. M1: 探索AI（Rust）
  2. M2: Web で AI と対局（Normal 難易度、Web Worker）
  3. M3: ブラウザでのモデル推論の検証
  4. M4: Python バインディングとデータ生成
  5. M5: 将棋ったー棋譜との互換性検証（棋譜がそろい次第、いつでも）
  6. M6: Transformer-S の学習
- ユーザー側の準備事項は、`docs/ROADMAP.md` の「ユーザー側の準備」にある。
