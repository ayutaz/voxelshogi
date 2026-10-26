# VoxelShogi

[![CI](https://github.com/ayutaz/voxelshogi/actions/workflows/ci.yml/badge.svg)](https://github.com/ayutaz/voxelshogi/actions/workflows/ci.yml)

9×9×9（729マス・372枚）の三次元将棋を題材にした、再現可能な三次元将棋AI研究プラットフォームです（開発中）。

**AI vs AIの対局を見て・眺める体験を中心に、そのためのモデルを開発・研究します。** ゲームとしての面白さ、分かりやすさ、見映えを重視し、対局する場合は人間 vs AIを用意します。

- Rust製ルールエンジンをWebAssemblyから利用。PythonバインディングはM4で実装予定
- ブラウザで遊べる VoxelShogi Arena — **https://voxelshogi.yousan-apps.workers.dev** （Alpha 版）
- 主用途: AI vs AI 観戦。補助機能: 人間 vs AI（先手・後手）
- エンジンによる合成データセット / Transformer Policy-Value モデル（Hugging Face 公開予定）

標準ルール `voxelshogi-standard-v1` は [将棋ったー「三次元将棋」](https://shogitter.com/rule/三次元将棋)（2026-10-17 改定版）を読解して独立実装しています。公開棋譜による完全互換性の検証はM5で行います。9王の試作3ルールは別IDで管理し、正式採用は保留しています。[ルール仕様](docs/RULESET.md)

## 現在の状態

| Phase | 内容 | 状態 |
|---|---|---|
| 0 | 調査と設計 | ✅ |
| 1 | Rust ルールエンジン | ✅ |
| 2 | Web ゲーム Alpha | ✅ 公開済み（main への push で自動デプロイ） |
| R0 | 9王ルール比較・同一棋譜のA/B観戦試作 | ✅ [比較室を公開](https://voxelshogi.yousan-apps.workers.dev/?experiment=1) |
| 3〜7 | データセット、Transformer、自己対局、研究比較、正式公開 | ⬜ |

各フェーズの目的とゴールは [docs/ROADMAP.md](docs/ROADMAP.md) にあります。

M0（CI/CD と品質基盤）は、PRの取り込み・公開後検証まで完了しました。固定ツールチェーン、依存監査、CodeQL、品質計測、配信 SHA と公開 E2E、main 保護、旧成果物の隔離復旧訓練を確認済みです。M0時点の全758変異を調査し、692件を検出、58件をビルド不能、8件を根拠付きの同値として分類しました。R0追加後の全体調査結果と混同しません。次は M1（探索AI、未着手）です。[M1の実装手順](docs/M1_PLAN.md)・[CI/CDの計画](docs/CI_CD_PLAN.md)・[M0の検証記録](docs/M0_VALIDATION.md)

人間同士の対局・マルチプレイは実装しません。変更は必ず作業ブランチと PR を使い、必須 CI の成功後に取り込みます。[開発手順](CONTRIBUTING.md)

通常画面のライブ対局・観戦はランダムAIです。[9王ルール比較室](https://voxelshogi.yousan-apps.workers.dev/?experiment=1)では、幅を制限したCPU探索AIが生成した棋譜を再生し、400手／800手と全体／注目表示を比較できます。計1,052局を生成・照合し、代表棋譜6件を公開しました。ブラウザ内のライブ探索と学習モデルは未実装です。[実測結果と再現手順](docs/NINE_KINGS_EXPERIMENT.md)

検証はRust 116件、Web単体36件、NodeのCI制御42件、既知変異14件、E2E 9件です（2026-10-26）。PRでは必須7チェックを実行し、main統合後に配信SHAと公開E2Eを確認します。

M3・M6では、実機のブラウザで動く変換済みモデルをデモに組み込みます。公開する FP16・量子化版なども個別に選択して対局・観戦できるようにし、配信する同じモデルで精度・棋力・速度・サイズを評価します。

## ローカルで動かす

必要なもの: Rust 1.97.1（`rust-toolchain.toml` から rustup が導入）、`wasm-bindgen-cli` 0.2.129、Node.js 24.22.1（`.node-version`）、pnpm 10.32.1。

Python を使う計測・今後の学習環境は3.14系を基本とし、依存が未対応の場合は3.13系を使います。現在の固定値は `.python-version`（3.14.9）です。

```bash
cargo test --locked --workspace # 標準・実験ルールと探索試作のテスト

cd apps/web
pnpm install --frozen-lockfile
pnpm wasm                       # エンジンを WebAssembly にビルド
pnpm dev                        # http://localhost:5173
```

ローカルの比較室は `http://localhost:5173/?experiment=1`。E2Eでは `pnpm build` 後に `E2E_COMMIT="$(git rev-parse HEAD)" pnpm e2e` を実行すると、配信SHAの確認も省略されません。ブラウザとCLIの準備・検証コマンドは [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

## ドキュメント

| 文書 | 内容 |
|---|---|
| [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md) | 目的・スコープ・横断的な要件 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | フェーズごとの目的・ゴール・進捗 |
| [docs/M1_PLAN.md](docs/M1_PLAN.md) | 次の探索AIの実装順・テスト・完了条件 |
| [docs/RULESET.md](docs/RULESET.md) | 標準ルールと、別IDの9王試作3ルール |
| [docs/RULE_VARIANTS_RESEARCH.md](docs/RULE_VARIANTS_RESEARCH.md) | 9層同一配置・複数王の先行調査、試作後の実測への案内 |
| [docs/NINE_KINGS_EXPERIMENT.md](docs/NINE_KINGS_EXPERIMENT.md) | R0の1,052局・表示比較・再現と公開検証の記録 |
| [docs/GAME_ENGINE.md](docs/GAME_ENGINE.md) | 標準／実験のRust・WASM API、棋譜形式、性能 |
| [docs/ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md) | 設計判断（ADR） |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | CI と Cloudflare へのデプロイ |
| [docs/CI_CD_PLAN.md](docs/CI_CD_PLAN.md) | 現在のCI運用と、M0強化計画・検証の履歴 |
| [docs/M0_VALIDATION.md](docs/M0_VALIDATION.md) | M0時点の変異分類・保護・復旧訓練の証拠 |
| [docs/RESEARCH.md](docs/RESEARCH.md) | 現在の調査状況と初回調査の要約 |
| [docs/RELATED_WORK.md](docs/RELATED_WORK.md) | 先行事例・論文の調査記録と将来の研究候補 |
| [docs/TECH_STACK_RESEARCH.md](docs/TECH_STACK_RESEARCH.md) | 採用済み構成と、未採用の推論・学習技術の調査記録 |
| [docs/COST_ESTIMATE.md](docs/COST_ESTIMATE.md) | 現在の費用・R0実測、日付付き価格例と承認前の再見積もり |
| [CONTRIBUTING.md](CONTRIBUTING.md) / [SECURITY.md](SECURITY.md) | 開発・CI確認・非公開の脆弱性報告 |

## ライセンス

Apache License 2.0 — Copyright 2026 ayutaz. 詳細は [LICENSE](LICENSE) と [NOTICE](NOTICE) を参照。
