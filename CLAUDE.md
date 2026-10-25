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
```

## 決定事項（ユーザー確認済み）

- GitHub は `ayutaz/voxelshogi`。2026-10-25 に Public 化した。GitHub Actions（Public は無料）を最大限活用し、すべてのテストを CI で回す。
- コードのライセンスは Apache-2.0（Copyright 2026 ayutaz）。モデル・データセットのライセンスは、公開前にユーザーに確認する。
- Hugging Face の名前空間は `ayousanz/`（`ayutaz` という HF ユーザーは存在しない）。
- ルールは将棋ったー三次元将棋の 10/17 改定後版。未記載の終局条件は将棋ったーの既定を継承する。
- 公開 URL はまず workers.dev を使う。デプロイは GitHub Actions から行う（Cloudflare 側の Git 連携は使わない）。理由は `docs/DEPLOYMENT.md` を参照。
- 将棋ったーの公開棋譜による互換性検証は、ローカルでのみ行う（棋譜はコミットしない）。

## 現在の進捗と次の作業

進捗の詳細と、各フェーズの目的・ゴール（完了条件）は `docs/ROADMAP.md` にある。フェーズを完了とするのは、ゴールの全項目を満たしたときだけ。

- 完了
  - Phase 0: 調査と設計
  - Phase 1: ルールエンジン（全ルール、VSFEN、棋譜、セッション）
- 進行中
  - Phase 2: Web ゲーム Alpha。ゴールのうち、残りは Cloudflare Secrets の登録（ユーザー作業）と公開 URL でのスモークテスト
- **次にやること（優先順）**
  1. **探索AI（αβ探索、駒得評価）を Rust に実装し、Web の Worker で動かす**。理由: Web の Normal 難易度と、Phase 3 の Search Dataset の教師に必要。
  2. **将棋ったーの公開棋譜を使った互換性検証**（`docs/RULESET.md` §9）。理由: ルール準拠の主張を裏付けるため。
  3. **PyO3 バインディングとデータ生成（Parquet）**。理由: Phase 3 の本体。
  4. **ONNX/WebGPU の早期検証**。ランダム重みの小型 Transformer で行う。理由: 本格学習の前に変換・推論の可否を確認する（`docs/TECH_STACK_RESEARCH.md` §3.4）。
  5. **Cloudflare の Secrets 登録**（ユーザー作業）→ 自動デプロイ → Phase 2 完了。
