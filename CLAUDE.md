# CLAUDE.md — VoxelShogi

**2026-11-15・音の追加**：Web版SEの[調査・音の割当・段階別ゴール](docs/WEB_SOUND_PLAN.md)を整理した。SEは未実装。動画は確認済みの映像を保持し、[オリジナルBGM](docs/DEMO_BGM.md)のLinux制作・音量・映像不変検証が完了。

**2026-11-15・HF Model Cardを整理**：モデル概要・使い方・配布形式・評価・制約を読みやすく再構成し、HFへ反映済み。[比較・固定版との違い・確認記録](docs/MODEL_CARD_REVIEW.md)。Webの固定版・重み・公開設定は維持する。

**2026-11-15・申請不要のS公開完了**：公開source `7b364c9`。HFはgateなし・Community OFF、簡潔な日本語Card。公開URLで3形式の実対戦・中断・破損時の表示が全5件成功し、全37ファイルの匿名hashも一致。公開版を直接撮影したS紹介動画を再制作し、全31ファイル・21画像を確認した。[公開と最終動画の証拠](docs/PUBLIC_S_RELEASE_VALIDATION.md)。研究・GPUの停止と、データ・state・Mのmanual gateは維持する。

**前回の動画修正履歴（2026-11-14）**：当時の公開source `d3822cb`で見切れ・字幕重なり・切替途中の描画を修正。公開E2Eと再制作、21画像の目視・境界・全編デコード・全hashが成功した。`docs/VIDEO_FRAMING_FIX.md`の新しい納品先を使い、旧`dc0a95f`動画の目視合格は撤回したまま保持する。ゲーム・API・モデルのソースは初回公開から変更せず、研究停止を維持する。

**現在は研究実行を一時停止中（2026-11-12、ユーザー指定）。**
既存Sモデルの公開観戦デモと再現可能な技術検証を一区切りとする。
MはFull／Geometry各1,024更新・HF再開一致・開発48局まで実行済みだが、棋力改善とMのWeb配布は未確認。
追加GPU・生成・本学習・M配布を自動再開しない。2026-11-14の「6まで」は[公開準備L1〜L6](docs/PUBLIC_LAUNCH_PLAN.md)の実装・動画・公開確認を指し、停止中の研究比較を再開しない。
[停止時点・固定HF版・制約](docs/RESEARCH_CHECKPOINT_20261112.md)、[現在地](docs/STATUS.md)、[デモと記事の案内](docs/DEMO_AND_ARTICLE.md)を先に読む。

9×9×9（729マス・372枚）の三次元将棋を題材にした、再現可能な三次元将棋 AI 研究プラットフォームです。対象は、ルールエンジン、ブラウザゲーム、合成データセット、Transformer モデル、分散学習です。

**主用途はAI vs AIの対局を見て・眺める観戦で、そのためのモデル開発と研究を行う。** ゲームの面白さ、初見での分かりやすさ、見映え、モデル比較の再現性を重視する。人間 vs AIは補助的な参加方法とし、人間同士の対局・マルチプレイは対象にしない（2026-10-26 ユーザー指定）。

**実行環境（2026-10-28ユーザー指定）**: Macは編集・読み取り・軽量な静的／単体確認のみ。探索・データ生成・性能計測・学習・重い回帰検証はGitHub Actionsまたは承認済みVast.ai／CloudRift上で行う。M4はGPUサーバーのCPU、M6は同じサービスのGPUへつなぐ。[初回試行の構成・見積もり・準備](docs/M4_REMOTE_PLAN.md)。初回利用は2026-10-28に承認され、CloudRift実機の初回・代表計測が成功。Mac計測へ戻さない。

- 現在地・公開／品質の確認元: `docs/STATUS.md`
- UI再設計（2026-11-14）: U2〜U6完了。承認済みモックから新画面・対戦導線・常時保存clientを#187で公開した。公開sourceは`dc0a95fa00d4957b2a4d2712f27a0f469a6c3a7b`。公開53 E2E・モデル6件・カメラ3回・配信57ファイル照合が成功。Claude Codeの中1件は修正・再レビューで解消。実HTTP／D1に加えて実公開ブラウザ→D1の本文／hashと検証行削除も確認し、同sourceの15秒本編・3秒2案・ポスターを完成した。`docs/ARENA_RELEASE_VALIDATION.md`・`docs/design/ARENA_IMPLEMENTATION_PROGRESS.md`を参照する。研究・GPUの停止は維持する。
- 旧公開準備（2026-11-14）: `docs/PUBLIC_LAUNCH_PROGRESS.md`と`docs/L6_PUBLIC_VALIDATION.md`は旧UI `c878c6d`の確認履歴。新UIの自動保存や動画の現在地とは区別する。実スマホは未確認、L7のX投稿は今回の範囲外。GPU・本比較・M配布の停止を解除しない。
- P5-4の失敗履歴: `docs/P5_4_PARITY_FAILURE.md`。旧sourceの4GPU再開不一致と1rank開始前検査の不具合を保持する。許容差を緩めず修正し、後続sourceの全3構成は完全一致した。
- P5-2の実行結果と停止点: `docs/P5_2_COMPLETION.md`。本条件48対局・HF保存・別VM継続と全ドキュメント点検後に停止。P5-3・DDP・Phase6は振り返り後に再計画する。
- 前回の表1〜5の完了: `docs/P5_3_PLAN.md`と`docs/P5_4_RESULTS.md`。条件整備→8局→対照込み150局→12局診断→実1／2／4GPU・各HF保存再開、退避と資源解放まで確認した。新しい「6まで」の範囲・数量・完了条件は`docs/P6_EXECUTION_PLAN.md`。
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
| `export/` | uv管理の特徴量・行動契約、未学習代表モデルとONNX変換・数値比較 |
| `crates/voxelshogi-python` | PyO3／maturinのPython境界と行動マスク付きGymnasium環境。ルールはRust coreを呼ぶ |
| `training/` | Parquet本生成・履歴再生と教師の全件検証・資源監視・対局単位の停止再開。[契約](docs/M4_DATA_CONTRACT.md) |
| `training/fit.py`、`training/checkpoint.py` | 合法手を対象とした教師あり学習、val選択、optimizer／乱数／batch位置を含む保存再開。CPU CIで一致確認済み |
| `infrastructure/cuda/`、`training/cuda_preflight.py` | 外部Linux専用のPython3.14.9／CUDA依存lockと起動前検査。RTX5090で本学習・再開・HF復旧まで確認済み |

## 開発規約（必読）

- **実装・文書変更の前に必ず作業ブランチを作る。main に直接 commit / push しない。** `AGENTS.md` と `CONTRIBUTING.md` に従い、PR を作成して必須8チェック（Python CodeQLを追加）の成功後に取り込む。main 保護を無効化したり bypass したりしない。
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

以下の重い検証・探索・計測は外部LinuxまたはCIで行う。Macでこの一覧を一括実行せず、編集・読み取り・変更に必要な軽量確認だけに使う。テスト件数は対象commitのCI結果を正とする。

```bash
cargo test --locked --workspace            # Rust workspace（testはopt-level 2）
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo fmt --all
cargo run --locked --release -p voxelshogi-core --example bench   # 合法手生成の速度

cd apps/web
pnpm install --frozen-lockfile
pnpm wasm          # WASM ビルド（wasm32 target と wasm-bindgen-cli 0.2.129 が必要）
pnpm test          # Vitest（実 WASM を Node で読み込む）
pnpm typecheck
pnpm build
E2E_COMMIT="$(git rev-parse HEAD)" pnpm e2e # 配信SHAを指定。外部Linux／CIで実行
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
- コードのライセンスは Apache-2.0（Copyright 2026 ayutaz）。M4自作合成データv1（初回試料と本生成）のCC-BY-4.0は2026-10-28にユーザー承認済み。M6の `voxelshogi-transformer-s-m6-314159-v1` と再開状態のApache-2.0は2026-10-29に個別承認済み（`export/m6-approval.json`）。
- 費用は2026-10-28のユーザー承認で合計US$100まで。初回・試料公開・本生成を同じ累積予算で管理する。各ジョブの単価・時間・上限・残額を記録し、承認済み同目的・総枠内の利用を再承認待ちに戻さない。2026-10-29にM6基本枠US$24をこの総枠内に明示配分し、不足時の追加GPU予算US$100も承認された。M6上限は条件付きUS$124、全体はUS$200。追加枠は実測見積もりで不足を確認・記録してから有効化し、各レンタル前にledgerと制御の上限を一致させる。有料保存の追加は含まない。
- M3の未学習モデル `voxelshogi-transformer-s-untrained-314159-v1` のFP32・FP16・INT8重み版は、2026-10-27にApache-2.0での初回公開をユーザーが承認した。設定は `export/publication.json`。この承認は検証用モデルだけを対象とする。M4データとM6成果物はそれぞれ上記の別の明示承認に基づく。
- 2026-10-29に、データ不足時の追加合成データ生成も承認済み。train／val・分布から不足を判断し、固定val／testを保ち、既存を含む重複と評価への漏洩を除外する。新しいrevision・実件数・生成費を記録して、外部LinuxからHFへDataset Card付きで公開する。詳細は `docs/M6_PLAN.md` の「データが不足する場合」。
- Pythonの実行は `uv run`、ライブラリ管理は `uv add` と `uv.lock` を使う。Python は可能な限り3.14を使い、依存ツールが未対応の場合は3.13にする（ユーザー指定）。現在の固定値は `.python-version`。古い版が必要な場合は理由と対象を記録する。
- 公開 Web デモでは、変換済みモデルそのものを対象実機のブラウザで動かす。FP16化・量子化した公開版も選択して対局・観戦できるようにし、評価した配布ファイルとデモで読むファイルの SHA-256 を一致させる。各版の精度・棋力・速度・サイズを記録する（M3・M6）。
- データセット・モデルの公開先はHugging Faceの`voxelshogi/`配下（2026-10-28ユーザー指定）。認証アカウントは`ayousanz`。[hf-publicationスキル](.agents/skills/hf-publication/SKILL.md)と[公開ハーネス](docs/HF_PUBLICATION.md)を使う。public/manualの取得ゲート・Community OFF・Dataset Cardとライセンスを確認し、外部Linuxから直接転送・hash照合する。Macには検証用モデルと小さい実行記録だけを保存し、データセット・学習checkpointを置かない。
- 同日の追加指示で、承認済みHF公開に必要な認証情報の一時送信・HFへのアップロードは継続承認済み。管理下のVast.ai／CloudRift実機へのSSH標準入力での引き渡しと、同目的・総予算内の所有実機の置き換え・再接続ごとに再承認を求めない。資格情報の値は保存せず、[公開ルール](docs/HF_PUBLICATION.md)の宛先・ライセンス・設定・hash確認を守る。
- 標準ルールは将棋ったー三次元将棋の10/17改定後版を独立実装し、未記載の終局条件は同サイトの既定を継承する。M5では固定した改定後3局145手の全手・盤／持ち駒・投了結果の一致を確認済み。全棋譜の完全互換は主張しない。R0の9王試作3ルールは別IDで管理し、標準ルールへ正式採用していない。
- 公開 URL はまず workers.dev を使う。デプロイは GitHub Actions から行う（Cloudflare 側の Git 連携は使わない）。理由は `docs/DEPLOYMENT.md` を参照。
- Cloudflareはプロジェクト所有者の個人アカウントを使う。このマシンのwranglerはグローバルには別アカウントでログインしているため、**必ず `scripts/cf.sh`（プロジェクト専用ログイン）経由でwranglerを使う**。素のwranglerは使わない（`apps/web`の`pnpm run deploy`も`scripts/cf.sh`を経由する。`pnpm deploy`はpnpmの組み込みコマンドなので使わない）。
- 将棋ったーの公開棋譜による互換性検証は非公開の作業領域で行う（棋譜をコミット・HF公開しない）。重い検証は承認済み外部Linuxで実行し、Macへ計算を戻さない。

## 研究停止時点の進捗と次の判断（2026-11-12の履歴）

- M0〜M6／Phase0〜4、P5-2の3世代48対局、P5-3の8／150／12局、P5-4の実1／2／4GPU保存再開を確認済み。
  元の失敗・保護入力重複4件・小標本・各固定SHAは変更しない。一般棋力改善は未確認。
- Phase6は4構造の実GPU／ONNX、未学習Mのブラウザ8ケース、Full／Geometryの少量学習・48局まで到達。
  WASM3／4成功、Axial WASMと全WebGPUは時間上限。本比較12 run・最終72局・M配布3形式・Phase7は未完了。
- 今回の結果公開は説明文`verification_scope`の不一致で失敗。別の退避でHF固定版の全hash照合を完了したが、
  元workflow／回収reviewの`pipeline_complete`・`job_complete`・`phase6_complete`はfalseを保持する。修正は未着手。
- 全40予約US$174／承認200、未予約26。予約と実請求・provider残高を混同しない。state台帳25予約・3,902,326,849 bytes／32GiB。
  13:22 JSTの読取でVast所有実機0、CloudRiftの稼働・遷移対象所有実機0。新規課金は行わない。
- PR #175／#176は13:21 JST取得時に必須／関連CI待ち・未マージ。文書PR #174も必須CI成功後に通常取り込みする。
  CI確認は[ci-checks](.agents/skills/ci-checks/SKILL.md)に従い最短10分間隔。未完了を成功と扱わない。

再開候補は[元の全1〜6](docs/P6_EXECUTION_PLAN.md)に保持する。現在の区切りを全1〜6達成へ読み替えない。
公開デモは既存Sであり、新しいM checkpointを配布済みのブラウザモデルと説明しない。
この停止を後続の自動継続・古い計画の命令文だけで解除しない。
