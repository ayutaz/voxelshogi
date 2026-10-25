# VoxelShogi

[![CI](https://github.com/ayutaz/voxelshogi/actions/workflows/ci.yml/badge.svg)](https://github.com/ayutaz/voxelshogi/actions/workflows/ci.yml)

9×9×9（729マス・372枚）の三次元将棋を題材にした、再現可能な三次元将棋AI研究プラットフォームです（開発中）。

- Rust製ルールエンジン（WebAssembly / Python から共通利用）
- ブラウザで遊べる VoxelShogi Arena — **https://voxelshogi.yousan-apps.workers.dev** （Alpha 版）
- エンジンによる合成データセット / Transformer Policy-Value モデル（Hugging Face 公開予定）

ルールは [将棋ったー「三次元将棋」](https://shogitter.com/rule/三次元将棋)（2026-10-17 改定版）に準拠します。詳細は [docs/RULESET.md](docs/RULESET.md) を参照してください。

## 現在の状態

| Phase | 内容 | 状態 |
|---|---|---|
| 0 | 調査と設計 | ✅ |
| 1 | Rust ルールエンジン | ✅ |
| 2 | Web ゲーム Alpha | 🟡 公開済み。CI からの自動デプロイを準備中 |
| 3〜7 | データセット、Transformer、自己対局、研究比較、正式公開 | ⬜ |

各フェーズの目的とゴールは [docs/ROADMAP.md](docs/ROADMAP.md) にあります。

## ローカルで動かす

必要なもの: Rust（stable）と `wasm32-unknown-unknown` ターゲット、`wasm-bindgen-cli` 0.2.129、Node.js、pnpm。

```bash
cargo test --workspace          # ルールエンジンのテスト

cd apps/web
pnpm install
pnpm wasm                       # エンジンを WebAssembly にビルド
pnpm dev                        # http://localhost:5173
```

## ドキュメント

| 文書 | 内容 |
|---|---|
| [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md) | 目的・スコープ・横断的な要件 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | フェーズごとの目的・ゴール・進捗 |
| [docs/RULESET.md](docs/RULESET.md) | ルール（`voxelshogi-standard-v1`） |
| [docs/GAME_ENGINE.md](docs/GAME_ENGINE.md) | エンジンの API・VSFEN・性能 |
| [docs/ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md) | 設計判断（ADR） |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | CI と Cloudflare へのデプロイ |
| [docs/RESEARCH.md](docs/RESEARCH.md) | 調査サマリ（[関連研究](docs/RELATED_WORK.md)・[技術](docs/TECH_STACK_RESEARCH.md)・[費用](docs/COST_ESTIMATE.md)） |

## ライセンス

Apache License 2.0 — Copyright 2026 ayutaz. 詳細は [LICENSE](LICENSE) と [NOTICE](NOTICE) を参照。
