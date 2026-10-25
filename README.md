# VoxelShogi

[![CI](https://github.com/ayutaz/voxelshogi/actions/workflows/ci.yml/badge.svg)](https://github.com/ayutaz/voxelshogi/actions/workflows/ci.yml)

9×9×9（729マス・372枚）の三次元将棋を題材にした、再現可能な三次元将棋AI研究プラットフォームです（開発中）。

- Rust製ルールエンジン（WebAssembly / Python から共通利用）
- ブラウザで遊べる VoxelShogi Arena — **https://voxelshogi.yousan-apps.workers.dev** （Alpha 版）
- 対局モード: 人間 vs AI（先手・後手）、AI vs AI 観戦
- エンジンによる合成データセット / Transformer Policy-Value モデル（Hugging Face 公開予定）

ルールは [将棋ったー「三次元将棋」](https://shogitter.com/rule/三次元将棋)（2026-10-17 改定版）に準拠します。詳細は [docs/RULESET.md](docs/RULESET.md) を参照してください。

## 現在の状態

| Phase | 内容 | 状態 |
|---|---|---|
| 0 | 調査と設計 | ✅ |
| 1 | Rust ルールエンジン | ✅ |
| 2 | Web ゲーム Alpha | ✅ 公開済み（main への push で自動デプロイ） |
| 3〜7 | データセット、Transformer、自己対局、研究比較、正式公開 | ⬜ |

各フェーズの目的とゴールは [docs/ROADMAP.md](docs/ROADMAP.md) にあります。

M0（CI/CD と品質基盤）を実装中です。固定ツールチェーン、依存監査、CodeQL、品質計測、本番の配信 SHA 照合と公開 E2E、main 保護と正常なPRの取り込み・未完了時の拒否、旧成果物の復旧訓練は確認済みです。変異調査の再検証と統合後の公開結果を追跡しています。M0 完了後に M1（探索AI）へ進みます。[調査結果・実装計画・検証記録](docs/CI_CD_PLAN.md)

人間同士の対局・マルチプレイは実装しません。変更は必ず作業ブランチと PR を使い、必須 CI の成功後に取り込みます。[開発手順](CONTRIBUTING.md)

現在の対戦相手はランダムAIです。M3・M6では、実機のブラウザで動く変換済みモデルをデモに組み込みます。公開する FP16・量子化版なども個別に選択して対局・観戦できるようにし、配信する同じモデルで精度・棋力・速度・サイズを評価します。

## ローカルで動かす

必要なもの: Rust 1.97.1（`rust-toolchain.toml` から rustup が導入）、`wasm-bindgen-cli` 0.2.129、Node.js 24.22.1（`.node-version`）、pnpm 10.32.1。

Python を使う計測・今後の学習環境は3.14系を基本とし、依存が未対応の場合は3.13系を使います。現在の固定値は `.python-version`（3.14.9）です。

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
| [docs/CI_CD_PLAN.md](docs/CI_CD_PLAN.md) | CI/CD の現状調査・M1 前の強化計画と完了条件 |
| [docs/RESEARCH.md](docs/RESEARCH.md) | 調査サマリ（[関連研究](docs/RELATED_WORK.md)・[技術](docs/TECH_STACK_RESEARCH.md)・[費用](docs/COST_ESTIMATE.md)） |

## ライセンス

Apache License 2.0 — Copyright 2026 ayutaz. 詳細は [LICENSE](LICENSE) と [NOTICE](NOTICE) を参照。
