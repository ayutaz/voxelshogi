# VoxelShogi

[![CI](https://github.com/ayutaz/voxelshogi/actions/workflows/ci.yml/badge.svg)](https://github.com/ayutaz/voxelshogi/actions/workflows/ci.yml)

**三次元将棋のAI対局を眺め、AIを作り、比べるためのオープンソースプロジェクトです。**

9×9の盤が9層重なる、729マスの三次元将棋を扱います。ブラウザでの観戦体験と、ルールエンジン・データ・モデルを使った再現可能なAI研究を一緒に開発しています。現在はAlpha版です。

## ブラウザで試す

インストールせずに試せるデモを公開しています。

| デモ | できること |
|---|---|
| **[AI対局を観戦する](https://voxelshogi.yousan-apps.workers.dev)** | 探索AI同士の対局を観戦。一時停止・1手送り・速度変更、2D／3D表示、人間対AIも利用できます |
| [9王ルール比較室](https://voxelshogi.yousan-apps.workers.dev/?experiment=1) | 複数の王を使う実験ルールの棋譜を再生し、表示方法を比べられます |
| [モデル推論ラボ](https://voxelshogi.yousan-apps.workers.dev/?models=1) | FP32・FP16・INT8重み版のモデルを選び、自分の端末で推論と数値比較を実行できます |

通常の対局はEasy（ランダム）とNormal（探索）を選べます。推論ラボは**未学習モデルによる技術デモ**です。検証した端末・精度形式・実行先は [モデルの検証記録](docs/M3_VALIDATION.md) にまとめています。

## このプロジェクトで目指すもの

- **眺めて楽しめる観戦** — 三次元の盤面で起こる攻防を、追いやすく見映えのよい形で届ける。
- **共通のルールエンジン** — Rustで実装したルールをWebAssemblyとPythonから使い、観戦とデータ生成・学習をつなぐ。
- **比較・再現できるAI研究** — 探索条件、モデルの変換方法、検証結果を公開し、同じ条件でモデルを比べられるようにする。

AI同士の観戦を主用途とし、人間対AIも提供します。人間同士の対局・マルチプレイは開発対象に含めません。

### 開発状況

ルールエンジン、ブラウザでの探索AI観戦、未学習モデルのブラウザ推論を公開済みです。

CloudRiftで1,800局を生成し、重複除外後113,321局面・探索教師36,894件の全検証と全再生成一致を確認しました。[HFのデータセットとDataset Card](https://huggingface.co/datasets/voxelshogi/voxelshogi-synthetic-v1)を公開済みです（public・手動取得承認・Community OFF）。[公開対象1,831ファイルの全hash照合と実機終了の記録](docs/M4_COMPLETION.md)も残しています。学習済みモデルの対局・観戦は次のM6で開発します。

詳しい進捗は [現在の状態](docs/STATUS.md)、各段階の目的・完了条件は [ロードマップ](docs/ROADMAP.md) を参照してください。M4と、固定3局145手を照合したM5は完了し、次は[M6の教師・学習・評価・モデル観戦](docs/M6_PLAN.md)へ進みます。

### ルールについて

標準ルールは、[将棋ったー「三次元将棋」](https://shogitter.com/rule/三次元将棋)の2026-10-17改定版を読み解いて独立実装しています。改定後の公開棋譜3局145手で、各手・盤面・持ち駒・投了結果の一致を確認しました（[対象と制約](docs/M5_PLAN.md)）。全棋譜・全終局条件の完全互換は主張していません。9王のルールは比較実験として提供しています。

駒の動きや終局条件は [ルール仕様](docs/RULESET.md)、9王の比較結果は [実験レポート](docs/NINE_KINGS_EXPERIMENT.md) を参照してください。

## ローカルで動かす

用意するもの：

- **rustup** — RustとWASMターゲットは `rust-toolchain.toml` の指定から導入されます。
- **Node.js 24.22.1 / pnpm 10.32.1** — 固定バージョンは `.node-version` と `apps/web/package.json` に記載しています。

```bash
git clone https://github.com/ayutaz/voxelshogi.git
cd voxelshogi

cargo install wasm-bindgen-cli --version 0.2.129 --locked
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web wasm
pnpm --dir apps/web dev
```

[http://localhost:5173](http://localhost:5173) を開くと、探索AIの観戦と人間対AIを試せます。

<details>
<summary>モデル推論ラボもローカルで動かす</summary>

Python 3.14.9とuvを使います。上のWeb起動手順を終えてから、別のターミナルでリポジトリのルートへ移動し、次を実行してください。

```bash
uv sync --locked
uv run --locked python -m export.generate runs/m3/local
node scripts/prepare-inference.mjs runs/m3/local apps/web/public/models/m3 --local
```

[http://localhost:5173/?models=1](http://localhost:5173/?models=1) を開きます。モデルはgitに含まれず、この手順でローカル専用の配布物を生成します。Pythonの依存追加は `uv add`、実行は `uv run --locked` を使います。

</details>

## 開発に参加する

不具合の報告や改善の提案は [GitHub Issues](https://github.com/ayutaz/voxelshogi/issues) へお願いします。コードやドキュメントの修正を送る前に、[開発・テスト・PRの手順](CONTRIBUTING.md) を確認してください。

脆弱性の報告先は [セキュリティポリシー](SECURITY.md) に記載しています。

## ドキュメント

| 知りたいこと | 読むもの |
|---|---|
| 目的・開発範囲 | [プロジェクト仕様](docs/PROJECT_SPEC.md) |
| 今できること・今後の予定 | [現在の状態](docs/STATUS.md) / [ロードマップ](docs/ROADMAP.md) |
| エンジンのAPI・設計 | [ゲームエンジン](docs/GAME_ENGINE.md) / [設計判断](docs/ARCHITECTURE_DECISIONS.md) |
| データ生成・公開 | [M4実行計画](docs/M4_PLAN.md) / [HF公開・保存ルール](docs/HF_PUBLICATION.md) |
| モデルの入出力・検証結果 | [モデル契約](docs/MODEL_CONTRACT.md) / [検証記録](docs/M3_VALIDATION.md) |
| 研究の背景・先行事例 | [調査サマリ](docs/RESEARCH.md) / [関連研究](docs/RELATED_WORK.md) |

## ライセンス

コードは **Apache License 2.0** です。詳細は [LICENSE](LICENSE) と [NOTICE](NOTICE) を参照してください。

公開済みの検証用未学習モデルもApache-2.0です。M4の自作合成データv1はCC-BY-4.0での公開をユーザー承認済みです。学習済みモデルのライセンスは公開前に別途確定し、各配布物に明記します。
