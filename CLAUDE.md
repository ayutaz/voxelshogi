# CLAUDE.md — VoxelShogi

**M6最新追記（2026-10-29 UTC）**：[初回本学習・Torch固定評価・HF再開状態保存とFP32変換失敗の記録](docs/M6_MAIN.md)。3 epochの本学習は完了し、val Policy Top-1は77.609%、testは75.592%。対局の勝利はなく、棋力改善は未確認。初回GPUは終了・資源解放済み。以下の「本学習未実行」や最大8時間の記述は初回実行前の計画として保持する。次は数値契約のCI検証後、暫定3時間・最大4時間／US$4の再試行。学習済み推論公開・実モデルのブラウザ検証は未完了。

9×9×9（729マス・372枚）の三次元将棋を題材にした、再現可能な三次元将棋 AI 研究プラットフォームです。対象は、ルールエンジン、ブラウザゲーム、合成データセット、Transformer モデル、分散学習です。

**主用途はAI vs AIの対局を見て・眺める観戦で、そのためのモデル開発と研究を行う。** ゲームの面白さ、初見での分かりやすさ、見映え、モデル比較の再現性を重視する。人間 vs AIは補助的な参加方法とし、人間同士の対局・マルチプレイは対象にしない（2026-10-26 ユーザー指定）。

**実行環境（2026-10-28ユーザー指定）**: Macは編集・読み取り・軽量な静的／単体確認のみ。探索・データ生成・性能計測・学習・重い回帰検証はGitHub Actionsまたは承認済みVast.ai／CloudRift上で行う。M4はGPUサーバーのCPU、M6は同じサービスのGPUへつなぐ。[初回試行の構成・見積もり・準備](docs/M4_REMOTE_PLAN.md)。初回利用は2026-10-28に承認され、CloudRift実機の初回・代表計測が成功。Mac計測へ戻さない。

- 現在地・公開／品質の確認元: `docs/STATUS.md`
- 次の実行計画: `docs/M6_TRIAL.md` の本学習・評価・公開観戦。M4・M5は完了。M6の学習／再開、固定評価・変換、HF公開profile、Workerと観戦UI、費用・終了制御はPR #47〜#63の必須CI成功後に取り込み済み。M6-2の実RTX5090試行では教師train29,884／val3,421／test3,589を監査し、batch4約185局面/秒、CUDA再開とHFからの新run復旧・継続一致、Linuxブラウザの物理GPU利用を確認。試行実機は終了・資源解放済み。本学習・最終評価・学習済み推論公開・Arenaの実機検証は未実施。M6基本枠US$24、成果物Apache-2.0・別HF repo再開状態公開、不足時の追加GPU予算US$100・追加合成データ生成はPR #64に記録済み。追加枠はまだ未使用。詳細は `export/m6-approval.json`、`docs/M6_PLAN.md`。
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
| `infrastructure/cuda/`、`training/cuda_preflight.py` | 外部Linux専用のPython3.14.9／CUDA依存lockと起動前検査。RTX5090で少量学習・再開まで確認済み |

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

```bash
cargo test --locked --workspace            # Rust（core153件＋WASM境界5件、testはopt-level 2）
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo fmt --all
cargo run --locked --release -p voxelshogi-core --example bench   # 合法手生成の速度

cd apps/web
pnpm install --frozen-lockfile
pnpm wasm          # WASM ビルド（wasm32 target と wasm-bindgen-cli 0.2.129 が必要）
pnpm test          # Vitest（実 WASM を Node で読み込む）
pnpm typecheck
pnpm build
E2E_COMMIT="$(git rev-parse HEAD)" pnpm e2e # 全21件。ローカルはChrome、CIはPW_CHANNEL=''でChromium
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
- Cloudflare は、ユーザーの個人アカウント（ka1357amnbpdr@gmail.com）を使う。このマシンの wrangler はグローバルには別アカウントでログインしているため、**必ず `scripts/cf.sh`（プロジェクト専用ログイン）経由で wrangler を使う**。素の `wrangler` は使わない（`apps/web` の `pnpm run deploy` も `scripts/cf.sh` を経由する。`pnpm deploy` は pnpm の組み込みコマンドなので使わない）。
- 将棋ったーの公開棋譜による互換性検証は非公開の作業領域で行う（棋譜をコミット・HF公開しない）。重い検証は承認済み外部Linuxで実行し、Macへ計算を戻さない。

## 現在の進捗と次の作業

進捗の詳細と、各フェーズの目的・ゴール（完了条件）は `docs/ROADMAP.md` にある。フェーズを完了とするのは、ゴールの全項目を満たしたときだけ。

- 完了
  - Phase 0: 調査と設計
  - Phase 1: ルールエンジン（標準ルール、VSFEN、棋譜、セッション）
  - Phase 2: Web ゲーム Alpha。https://voxelshogi.yousan-apps.workers.dev に公開し、main への push で CI から自動デプロイされる
  - M0: CI/CD と品質基盤。必須7チェックによるmain保護、公開E2E、隔離復旧訓練、全758変異の調査と分類を確認済み。PR #3の最終文書も取り込み済みで、統合コミット `1ff4e2f` の本番公開・配信SHA・公開E2E 6件まで2026-10-26（JST）に成功した（`docs/M0_VALIDATION.md` の完了時記録）
  - R0: 9王ルール3候補と現行1王の対照、計1,052局の比較・全手照合、同一棋譜のA/B観戦試作を完了。PR #7・必須7チェック・main自動公開・実機Chromeの公開E2E 9件と公開用6棋譜のSHA一致を確認した。正式採用と観戦者による理解度評価は保留（`docs/NINE_KINGS_EXPERIMENT.md`）
  - M1: 探索AI（Rust）。独立参照探索・戦術・上限と再現性、全1,172変異の分類、Native計測を完了（`docs/M1_VALIDATION.md`）
  - M2: 履歴付きWorker探索・両AIのEasy/Normal観戦・中断と再試行・3D分割を完了。PR #13〜#16の必須CIと通常取り込み、最終main `e212ec7` の自動公開・配信SHA・公開E2E、実機Chromeの全21件・固定7局面の計測と配信artifact照合を確認（`docs/M2_VALIDATION.md`）
  - M3: 未学習の約502万パラメータ・全3変換・専用Workerを公開。性能計測 `dd3762c` の48組・各backendで20実切替と、完了時公開 `bca5532` のCI・公開E2E・55ファイル照合・最終参照値での実機再照合を確認。モデル・実行コードのhashは同一、再生成参照値の微小差は固定誤差基準内。FP16×M1 WebGPUの基準未達、HTTP 500の失敗と回復も保持（`docs/M3_VALIDATION.md`、`docs/experiments/m3-completion-publication.json`、2026-10-28 JST）
  - M4 / Phase 3: 1,800局・有効113,321局面・探索教師36,894件を全検証・全再生成し、HFの`production-64`へDataset Card付きで公開。固定Hub commitの全1,831対象ファイルが一致し、実機終了・資源解放・volume 0を確認（[完了記録](docs/M4_COMPLETION.md)、2026-10-29 JST）。
  - M5: 固定した改定後3局145手の合法性・盤／持ち駒・投了結果が一致。PR #42を必須CI成功後に通常merge。全棋譜の完全互換は主張しない（[記録](docs/M5_PLAN.md)）。
- **次にやること**: `docs/ROADMAP.md` の「実行計画（マイルストーン）」の順に進める。
  1. M6: [M6_PLAN](docs/M6_PLAN.md)のM6-0〜1で教師・評価条件と学習／再開を実装。その後、承認済みの最大4時間／US$4のCUDA試行を実測し、本学習・評価・変換・HF公開・ブラウザ観戦へ進む。通常CIはCPU版torchを維持し、CUDA用の別lock・検査器・少量学習と再開は実RTX5090で成功済み。M6の個別承認と実測見積もりを使い、追加GPU枠は不足時だけ有効化する。
- ユーザー側の準備事項は、`docs/ROADMAP.md` の「ユーザー側の準備」にある。
