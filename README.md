# VoxelShogi

[![CI](https://github.com/ayutaz/voxelshogi/actions/workflows/ci.yml/badge.svg)](https://github.com/ayutaz/voxelshogi/actions/workflows/ci.yml)

**三次元将棋のAI対局を眺め、AIを作り、比べるためのオープンソースプロジェクトです。**

9×9の盤が9層重なる、729マスの三次元将棋を扱います。ブラウザでの観戦体験と、ルールエンジン・データ・モデルを使った再現可能なAI研究を一緒に開発しています。

## ブラウザで試す

インストールせずに試せるデモを公開しています。

| デモ | できること |
|---|---|
| **[AI対局を観戦・対戦する](https://voxelshogi.yousan-apps.workers.dev)** | 探索AI・学習済みSと対戦、またはAI同士を観戦。一時停止・1手送り・速度変更、2D／3D表示が使えます |
| [モデル推論ラボ](https://voxelshogi.yousan-apps.workers.dev/?models=1) | FP32・FP16・INT8重み版のモデルを選び、自分の端末で推論と数値比較を実行できます |

通常の対局はEasy（ランダム）とNormal（探索）を選べます。推論ラボは**未学習モデルによる技術デモ**です。検証した端末・精度形式・実行先は [モデルの検証記録](docs/M3_VALIDATION.md) にまとめています。

「観戦を開始」でAI同士の対局を始められます。「立体で眺める」で全体を見渡し、「断面を読む」で1層を詳しく読めます。
自分で指す場合は、上部の「AIと対戦」から先手／後手と相手を選び、「対戦をはじめる」を押します。
新画面は公開済みです。[公開版の検証記録](docs/ARENA_RELEASE_VALIDATION.md)を参照してください。

### 学習済みモデルで観戦する

「AIと対戦」→相手のAI「学習済みS」→精度形式→「対戦をはじめる」で遊べます。申請・ログイン・フォルダー取得は不要です。
AI同士を眺める場合は「対局設定」で先手・後手を「学習済みモデル」にし、形式とWASM／WebGPUを選びます。
[HFのモデルと短い説明](https://huggingface.co/voxelshogi/voxelshogi-transformer-s)から直接取得することもできます。手元のフォルダーを使う場合は、上部「モデル」→「学習済みモデルを読み込む」を使います。

FP32、FP16（重み）、INT8（重み）の実ファイルを選んで比較できます。FP16・INT8重み版の計算はFP32です。[取得方法・精度・容量・実機検証](docs/M6_PORTABLE.md)を参照してください。読み込んだモデルは端末内で実行します。

今回の取得条件変更と公開確認の状態は[申請不要のS配布](docs/PUBLIC_S_ACCESS.md)に記録します。

### UIレビューと対局データ

[Claude Codeによるレビューと改修計画](docs/design/ARENA_IMPLEMENTATION_PLAN.md)に沿って、盤中心の観戦画面と人間対AIの入口を公開しました。
目的・実装・検証済みの範囲は[進捗](docs/design/ARENA_IMPLEMENTATION_PROGRESS.md)、映像は[動画制作計画](docs/DEMO_VIDEO_PLAN.md)へ記録します。

新画面で始めた対局は、初手・途中経過・終局をCloudflare D1へ自動保存します。読み込んだ棋譜やその分岐は収集せず、学習・HF公開へ自動利用しません。
「棋譜」の保存は端末へのJSONダウンロードです。[保存内容と期間](https://voxelshogi.yousan-apps.workers.dev/privacy.html)・[実装と運用](docs/AUTOMATIC_GAME_STORAGE.md)を参照してください。
実スマホの操作確認は未完了です。過去の任意送信と旧UIの公開確認は[L6の履歴](docs/L6_PUBLIC_VALIDATION.md)として保持しています。

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

### 自己対局・Mモデルの結果と現在の区切り

[開発用の評価32局と全手再生・既存データ照合](docs/P5_PILOT.md)を完了しました。棋力改善はまだ確認できていません。教師・長期対局の追加試料は採用条件を満たさなかったため学習に使わず、検証済みのデータとモデルから、1GPUでの自己対局・世代更新を先行しました。

自己対局の3世代48対局からモデルを更新し、各世代のデータ・再開状態をHFへ保存しました。元のVMを終了して別VMから復旧し、後続世代を続けられることも確認しました。その後の固定条件による開発用比較と、その限界を以下に示します。

同じ重みの[48局比較](docs/P6_SCREEN_RESULTS.md)では、探索付きAIが詰み課題で改善しました。全棋譜と実推論入力の監査、HF保存、実機解放まで確認済みです。中盤は打切りが多く、一般的な棋力向上はまだ確認できていません。

先行する150局比較には保護入力との重複4件があり、その制約を保持しています。実1／2／4 GPUでの学習と、各構成のHF保存・復元・続行も確認しました。[GPU比較の結果と制約](docs/P5_4_RESULTS.md)を次の規模・費用の見積もりに使います。

4種類の構造の[実GPU・ONNX検証](docs/P6_OPERATOR_RESULTS.md)に続き、Full／GeometryのM規模モデルを各1,024更新し、HF保存からの再開一致と計48局の開発評価を確認しました。各24局は0勝4敗4自然引分16打切りで、棋力改善は未確認です。結果公開処理の失敗も含め、[固定HF版への退避と全hash照合](docs/RESEARCH_CHECKPOINT_20261112.md)を記録しています。

**現在は、動く既存デモと研究基盤を現段階の成果として一区切りにし、追加学習を一時停止しています（2026-11-12）。** 公開デモで試せる学習済みモデルはSです。新しいMは研究保存物であり、まだWebで選べません。4構造×3 seedの本比較、Mの3形式配布、観戦表示と実端末の長時間検証は将来の課題として残します。

[デモの試し方と技術記事の材料](docs/DEMO_AND_ARTICLE.md)、[実測値と制約](docs/BENCHMARKS.md)、[停止時点の成果](docs/RESEARCH_CHECKPOINT_20261112.md)、[残る研究課題](docs/OVERALL_PLAN.md)を参照してください。

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

公開済みの未学習検証モデル、M6と自己対局の学習モデル・再開用状態は **Apache-2.0**、M4と自己対局の合成データ・保護index・集計reportは **CC-BY-4.0** です。各HFリポジトリのCardとライセンスを参照してください。
