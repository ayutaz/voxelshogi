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

| 区分 | 内容 | 状態 |
|---|---|---|
| 0 | 調査と設計 | ✅ |
| 1 | Rust ルールエンジン | ✅ |
| 2 | Web ゲーム Alpha | ✅ 公開済み（main への push で自動デプロイ） |
| M0 | CI/CD・main保護・品質基盤 | ✅ |
| M1 | Rustの全幅探索AI | ✅ [検証・実測](docs/M1_VALIDATION.md) |
| M2 | Web Workerによる探索AI観戦 | ✅ 公開URLで探索AI観戦・中断・実機検証を完了。[計画と完了条件](docs/M2_PLAN.md) |
| R0 | 9王ルール比較・同一棋譜のA/B観戦試作 | ✅ [比較室を公開](https://voxelshogi.yousan-apps.workers.dev/?experiment=1) |
| 3〜7 | データセット、Transformer、自己対局、研究比較、正式公開 | ⬜ |

各フェーズの目的とゴールは [docs/ROADMAP.md](docs/ROADMAP.md) にあります。

M0・R0・M1・M2と、M3のブラウザモデル推論検証を完了しました。M3は未学習の約502万パラメータモデルをFP32・FP16・INT8重みへ変換し、実配信ファイルと実機M1／Chromeで数値・速度・3D同時動作を確認しています。[現在地](docs/STATUS.md)・[M3の固定記録と制約](docs/M3_VALIDATION.md)。次はM4のPythonバインディングとデータ生成です。

人間同士の対局・マルチプレイは実装しません。変更は必ず作業ブランチと PR を使い、必須 CI の成功後に取り込みます。[開発手順](CONTRIBUTING.md)

公開サイトでは、両AIにEasy（ランダム）／Normal（探索）を設定して観戦できます。初期表示は観戦・一時停止・2Dで、再開・1手送り・待ち時間変更・3D表示を使えます。公開SHA・実機計測・検証結果は [段階別記録](docs/M2_VALIDATION.md) に保存しています。[9王ルール比較室](https://voxelshogi.yousan-apps.workers.dev/?experiment=1)はCPU生成済みの固定棋譜を再生する別の試作で、400／800手と全体／注目表示を比較できます。学習済みモデルによる対局はM6の対象です。

PRでは必須8チェックを実行し、main統合後にも配信SHAと公開E2Eを確認します。Rust core153件＋WASM境界5件、Web172件、Python48件、CI制御Node67件、既知変異と既存E2E21件・モデル6件が対象です。[M3検証記録](docs/M3_VALIDATION.md)

[モデル推論ラボ](https://voxelshogi.yousan-apps.workers.dev/?models=1)で、公開した3形式を個別に選んで実行できます。M1／ChromeではFP32・INT8重みはWebGPU／WASM、FP16はWASMが数値基準を満たしました。FP16×WebGPUの基準未達も表示し、別形式へ自動置換しません。未学習モデルのため棋力を示すデモではありません。学習・棋力比較・対局画面への接続はM6で行います。

## ローカルで動かす

必要なもの: Rust 1.97.1（`rust-toolchain.toml` から rustup が導入）、`wasm-bindgen-cli` 0.2.129、Node.js 24.22.1（`.node-version`）、pnpm 10.32.1。

Pythonを使うモデル検証・今後のデータ生成／学習は3.14系を基本とし、依存が未対応の場合は3.13系を使います。現在の固定値は `.python-version`（3.14.9）。Pythonは`uv run --locked`から実行し、依存追加は`uv add`で管理します。

```bash
cargo test --locked --workspace # 標準・実験ルール・M1全幅探索のテスト

cd apps/web
pnpm install --frozen-lockfile
pnpm wasm                       # エンジンを WebAssembly にビルド
pnpm dev                        # http://localhost:5173
```

ローカルの比較室は `http://localhost:5173/?experiment=1`。E2Eでは `pnpm build` 後に `E2E_COMMIT="$(git rev-parse HEAD)" pnpm e2e` を実行すると、配信SHAの確認も省略されません。ブラウザとCLIの準備・検証コマンドは [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

モデル推論ラボは `/?models=1`。モデルはgitに含めないため、ローカルで動かす場合はリポジトリのルートから次を実行します。通常の探索観戦だけならモデル生成は不要です。

```bash
uv sync --locked
uv run --locked python -m export.generate runs/m3/local
node scripts/prepare-inference.mjs runs/m3/local apps/web/public/models/m3 --local
```

その後、上記のWeb開発サーバーを起動します。`--local`はlocalhost専用の配布物を作り、公開済みモデルと区別します。公開版のhash・完了時SHA・参照値の差は [M3最終記録](docs/M3_VALIDATION.md#m3完了時の統合後公開確認bca5532) を参照してください。

## ドキュメント

| 文書 | 内容 |
|---|---|
| [docs/STATUS.md](docs/STATUS.md) | 現在の実装・公開・CIと文書の役割 |
| [docs/M3_PLAN.md](docs/M3_PLAN.md) | 完了したブラウザ推論検証の目的・TDD・実機計測・公開条件 |
| [docs/M2_PLAN.md](docs/M2_PLAN.md) | 完了したWeb探索AI観戦の実装順・TDD・完了条件 |
| [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md) | 目的・スコープ・横断的な要件 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | フェーズごとの目的・ゴール・進捗 |
| [docs/M1_PLAN.md](docs/M1_PLAN.md) | 探索AIの実装順・契約・完了条件 |
| [docs/M1_VALIDATION.md](docs/M1_VALIDATION.md) | M1の参照探索・戦術・変異・Native計測・統合の証拠 |
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
