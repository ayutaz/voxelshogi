# VoxelShogi

[![CI](https://github.com/ayutaz/voxelshogi/actions/workflows/ci.yml/badge.svg)](https://github.com/ayutaz/voxelshogi/actions/workflows/ci.yml)

**三次元将棋のAI対局を眺め、AIを作り、比べるためのオープンソースプロジェクトです。**

9×9の盤が9層重なる、729マスの三次元将棋を扱います。ブラウザでの観戦体験と、ルールエンジン・データ・モデルを使った再現可能なAI研究を一緒に開発しています。現在はAlpha版です。

## ブラウザで試す

インストールせずに試せるデモを公開しています。

| デモ | できること |
|---|---|
| **[AI対局を観戦する](https://voxelshogi.yousan-apps.workers.dev)** | 探索AI同士・取得済み学習モデルの対局を観戦。一時停止・1手送り・速度変更、2D／3D表示、人間対AIも利用できます |
| [モデル推論ラボ](https://voxelshogi.yousan-apps.workers.dev/?models=1) | FP32・FP16・INT8重み版のモデルを選び、自分の端末で推論と数値比較を実行できます |

通常の対局はEasy（ランダム）とNormal（探索）を選べます。推論ラボは**未学習モデルによる技術デモ**です。検証した端末・精度形式・実行先は [モデルの検証記録](docs/M3_VALIDATION.md) にまとめています。

### 学習済みモデルで観戦する

1. [Hugging Faceのモデルページ](https://huggingface.co/voxelshogi/voxelshogi-transformer-s)で取得を申請します。
2. 承認後、観戦画面の「学習済みモデルを読み込む」にある固定revisionのフォルダー全体を取得し、同じ画面でフォルダーを選びます。
3. 先手・後手のAIを「学習済みモデル」にし、形式とWASM／WebGPUを選び、1手送りや自動再生で観戦します。

FP32、FP16（重み）、INT8（重み）の実ファイルを選んで比較できます。FP16・INT8重み版の計算はFP32です。[取得方法・精度・容量・実機検証](docs/M6_PORTABLE.md)を参照してください。読み込んだモデルは端末内で実行します。

## このプロジェクトで目指すもの

- **眺めて楽しめる観戦** — 三次元の盤面で起こる攻防を、追いやすく見映えのよい形で届ける。
- **共通のルールエンジン** — Rustで実装したルールをWebAssemblyとPythonから使い、観戦とデータ生成・学習をつなぐ。
- **比較・再現できるAI研究** — 探索条件、モデルの変換方法、検証結果を公開し、同じ条件でモデルを比べられるようにする。

AI同士の観戦を主用途とし、人間対AIも提供します。人間同士の対局・マルチプレイは開発対象に含めません。

### 開発状況

標準ルールのエンジン、探索AIと学習済み3形式の観戦、未学習モデルの推論ラボを公開済みです。

CloudRiftで1,800局を生成し、重複除外後113,321局面・探索教師36,894件の全検証と全再生成一致を確認しました。[HFのデータセットとDataset Card](https://huggingface.co/datasets/voxelshogi/voxelshogi-synthetic-v1)を公開済みです（public・手動取得承認・Community OFF）。[公開対象1,831ファイルの全hash照合と実機終了の記録](docs/M4_COMPLETION.md)も残しています。

CloudRiftのRTX 5090で最初の教師ありモデルを学習し、[Hugging FaceにModel Card付きで公開](https://huggingface.co/voxelshogi/voxelshogi-transformer-s)しました。取得にはHFでの申請と承認が必要です。教師手の再現精度は固定testで約75.6%ですが、今回の対局評価では探索AIに対する棋力向上は確認できていません。[評価結果と制約](docs/M6_COMPLETION.md)を公開しています。

観戦画面には[取得済みモデルの読み込み・両AIの形式選択・AI条件付き棋譜保存](docs/M6_ARENA.md)があります。ブラウザ向けの全3形式をHFで公開し、固定revisionとファイルhashをモデル一覧に登録しました。Linux実GPUで公開後の全48条件・40回の形式切替、各形式の実着手・7件の実モデルE2Eを確認し、GPUの資源解放まで完了しました（[M6完了記録](docs/M6_COMPLETION.md)）。初回の混合精度FP16と計測手順の失敗も[記録](docs/M6_PORTABLE.md)へ残しています。

詳しい進捗は [現在の状態](docs/STATUS.md)、各段階の目的・完了条件は [ロードマップ](docs/ROADMAP.md) を参照してください。M4と、固定3局145手を照合したM5は完了しています。M6／Phase4は[学習・再開・評価・3形式公開と実機観戦](docs/M6_COMPLETION.md)まで完了しました。計算とモデルの転送は外部Linuxで行い、Macでは編集と軽量な確認を行います。

### 次に進めること

[開発用の評価32局と全手再生・既存データ照合](docs/P5_PILOT.md)を完了しました。棋力改善はまだ確認できていないため、次は[教師の探索深さと長期対局データの比較](docs/P5_DATA_PLAN.md)を行います。その後、1GPUでの複数世代の自己対局と再開、世代比較、複数GPU、モデル構造の比較へ進みます。[各段階の目的・ゴール](docs/POST_M6_PLAN.md)をまとめています。

### ルールについて

標準ルールは、[将棋ったー「三次元将棋」](https://shogitter.com/rule/三次元将棋)の2026-10-17改定版を読み解いて独立実装しています。改定後の公開棋譜3局145手で、各手・盤面・持ち駒・投了結果の一致を確認しました（[対象と制約](docs/M5_PLAN.md)）。全棋譜・全終局条件の完全互換は主張していません。9王の比較実験は研究コード・記録として残し、公開画面から比較室は外しています。標準1王の正式ルールは変更していません。

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
<summary>モデル推論ラボの開発環境を作る（生成は外部Linux）</summary>

モデル生成はVast.ai／CloudRift等の外部Linuxで行います。Python 3.14.9とuvを使い、上のWeb起動手順を終えてから、Linuxのリポジトリルートで次を実行します。Macは編集と軽量な確認に使います。

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
| 今できること・今後の予定 | [現在の状態](docs/STATUS.md) / [ロードマップ](docs/ROADMAP.md) / [M6後の実行計画](docs/POST_M6_PLAN.md) |
| エンジンのAPI・設計 | [ゲームエンジン](docs/GAME_ENGINE.md) / [設計判断](docs/ARCHITECTURE_DECISIONS.md) |
| データ生成・公開 | [M4実行計画](docs/M4_PLAN.md) / [HF公開・保存ルール](docs/HF_PUBLICATION.md) |
| モデルの入出力・検証結果 | [モデル契約](docs/MODEL_CONTRACT.md) / [検証記録](docs/M3_VALIDATION.md) |
| 研究の背景・先行事例 | [調査サマリ](docs/RESEARCH.md) / [関連研究](docs/RELATED_WORK.md) |

## ライセンス

コードは **Apache License 2.0** です。詳細は [LICENSE](LICENSE) と [NOTICE](NOTICE) を参照してください。

公開済みの未学習検証モデル、M6の学習済みモデルと再開用状態は **Apache-2.0**、M4の自作合成データv1は **CC-BY-4.0** です。各HFリポジトリのCardとライセンスを参照してください。
