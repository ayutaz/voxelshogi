# CLAUDE.md — VoxelShogi

**2026-11-12 JST・現況と次の実測**：[再開計画](docs/P6_RESUMPTION_PLAN.md)を更新した。ブラウザ復旧#160はmain `8b4289f`へ統合済みで、統合sourceのCI／Security確認後に実ブラウザ8ケースを行う。#161は2構造の学習からHF照合・台帳回収・実機解放まで接続済みだが未統合（HEAD `1a3f939`、関連304軽量テスト・新規37変異検出）。#162を含む現行sourceの検証を先に済ませる。実ブラウザ0／8、M少量学習0／2、学習後対局0／48、本比較0／12。次は8ケース→2 run・48局→12 run→Mの3形式配布→実端末60分観戦・正式公開。05:33 JSTの両provider所有実機0、36予約160.75／承認200・未予約39.25、新規課金0。以下は日時付き履歴。

**2026-11-11・再開調査**：[現況と再開計画](docs/P6_RESUMPTION_PLAN.md)を追加した。両providerの所有課金資源0、最新mainの定期CI／Quality／Security成功を確認。前回の実データ監査は11,254件・固定HF全hashまで完了したが、ブラウザ測定はHF前処理のReadTimeoutで0件。M実学習・12 run・新モデルWeb採用・実端末観戦は未完了。累積36予約160.75／承認200、未予約39.25を保持し、今回は新規課金を行っていない。次は前処理修正と実行driverのGit管理→8ケース実ブラウザ→少量2 run→12 run基本案→実モデル配布→正式公開。以下は日時付き履歴。

**2026-11-05・Mのweights評価を統合**：[PR #154](https://github.com/ayutaz/voxelshogi/pull/154)は最新main統合後の必須8チェックと関連PR検証を確認し、main `f3d2d66`へ統合した。4構造の実M weights往復・Rust局面での合法着手・全変異の[Linux全検証](https://github.com/ayutaz/voxelshogi/actions/runs/41987703130)も成功している。[専用metadataと全NN参照監査](docs/P6_MODEL_EVALUATION.md)で、実学習後のargmax／PUCT32評価へつなげる。実M学習・開発用対局・12 run比較は未実行。次は実ブラウザとデータ監査、その結果をレビューして2 runを事前固定する。以下は日時付き履歴。

**2026-11-05・実ブラウザ測定コードを統合**：[PR #152](https://github.com/ayutaz/voxelshogi/pull/152)は必須8チェック・[修正後のLinux全検証](https://github.com/ayutaz/voxelshogi/actions/runs/41987246949)・CodeQL指摘0件を確認し、main `b2c7c09`へ統合した。実Chromiumの専用Worker通信確認は成功したが、4構造×WASM／WebGPUの実測は未実行。統合mainの深いCI後、外部Linuxで実ブラウザと同じホストでのデータ監査を進める。Mモデル評価のPR #154は既存HEADの全検証成功後に最新mainを統合し、再検証中。新規課金資源は作成せず、累積予約158／承認200・未予約42を保持する。以下は日時付き履歴。

**2026-11-05・採用前監査と訪問分布学習を統合**：[PR #153](https://github.com/ayutaz/voxelshogi/pull/153)を必須8チェック・[最新HEADのLinux全検証](https://github.com/ayutaz/voxelshogi/actions/runs/41977701532)成功後にmain `40ba00b`へ統合した。[データ監査](docs/P6_CORPUS_ADMISSION.md)→[train／val特徴量](docs/P6_VISIT_DATA.md)→[固定更新数・保存再開](docs/P6_VISIT_TRAINING.md)が接続済み。重複PR #150／#151は統合済みとして閉じた。実候補データの採用・Mの2 run学習・12 run比較は未実行であり、次は修正したブラウザ検証と実データ監査を外部Linuxで実行する。以下は日時付き履歴。

**2026-11-05 05:06 UTC・4構造の実M GPU／ONNX検証完了**：[実測と固定HF版](docs/P6_OPERATOR_RESULTS.md)で、全4構造の数値照合・batch1／4／8／16の全16組、公開後の全hash・実機解放を確認した。現在は所有課金資源0、累積35予約158／200・未予約42。速度は合成負荷の結果で、実教師学習や総FLOPsとは区別する。次は実ブラウザ、データ監査と訪問分布の2 run試行→12 run基本案→実モデル配布→Phase7。以下は日時付き履歴。 [stateの自主上限32GiBへの移行](docs/P6_STATE_CAPACITY.md)も過去履歴保持・追加購入なしで適用した。

**2026-11-05・評価補強48局完了**：[実行結果と固定HF版](docs/P6_SCREEN_RESULTS.md)で、48局・実NN参照24,579件のRust再生、全入力監査の重複0、別の最終評価12 root、HF全8ファイルの固定revision照合と所有課金資源0を確認した。PUCTの詰み課題改善と中盤の多数打切りを分け、一般棋力・重み改善は未確認。48局完了時点の台帳は34予約156／200、未予約44。4構造・実M計測コードは統合済みで、次は実GPU・ブラウザ検証。学習／保存はPR #147の全1,322件・関連CI後に統合済み、容量移行はPR #148で最新main上のCI検証中。少量2 run→12 run基本案→実モデル配布→Phase7まで継続し、以下の古い数量・停止・「現在」は日時付き履歴として読む。

**2026-11-05・「6まで」着手**：[評価補強から正式公開までの新計画](docs/P6_EXECUTION_PLAN.md)の1〜6（48局→4構造検証→2 run試行→複数seed比較→実モデル配布→Phase7）を今回の対象とする。最初の変更は48局の条件・別の最終評価12 root・family集計の実装と検証であり、実対局・本学習・実機公開の完了ではない。予算は33予約152.50／承認200、未予約47.50。以下の「今回」「次」は各日時の旧範囲を示す。

**2026-11-05 00:13 UTC・P5-4完了**：[同じホストの実1／2／4GPUと各HF保存再開](docs/P5_4_RESULTS.md)を、全3構成・6 state archive・結果datasetの固定版全hashと最後の資源解放まで確認した。今回の「5まで」（評価準備→8局→150局→12局診断→GPU比較）は実行完了。150局の保護入力重複4件と一般棋力改善の未確認は保持し、Phase6の構造比較・新モデルWeb採用は開始していない。以下の日時付き進捗は履歴である。

**2026-11-04 11:45 UTC・P5-3d完了**：[固定重みのargmax／PUCT32診断12局](docs/P5_3_DIAGNOSIS.md)は、全手・13参照履歴のRust再生、全入力重複0、HF固定版、実機解放を確認。先手の詰み成功は1／3対3／3で、同family3局面のため判断は追加測定。実1／2／4GPUと各保存再開はまだ未完了。「5まで」は継続中。以下は日時付きの履歴である。

**2026-11-04 10:17 UTC・P5-3c完了**：[150局・全入力監査・HF固定版・実機解放](docs/P5_3_COMPARISON.md)を確認。保護集合との重複4件をM6の1対局で検出したため、漏洩のない棋力評価とは扱わず全結果を保持する。所有課金資源0、全27予約110／200。次は[同じ第3世代重みのargmax／PUCT32診断12局](docs/P5_3_DIAGNOSIS.md)と実1／2／4GPU・各保存再開。「5まで」は継続中。以下の起動前・8局時点の記録は履歴である。

**2026-11-04・150局の起動準備**：[4試行とSSH設定](docs/P5_3_STARTUP.md)を記録。比較対局は0件で、所有課金資源は解放済み。全26予約106.5／総枠200を保持し、起動時の専用鍵設定を検証する。「5まで」の範囲は150局→診断→実1／2／4GPUまで継続し、起動処理だけで完了としない。

**2026-11-04 05:02 UTC・P5-3b完了**：[時間試行8局](docs/P5_3_TRIAL.md)は、7局のbyte一致復元＋残り1局、全入力重複0・固定HF全hash・実機解放を確認した。次は150局→1要因診断→実1／2／4GPUと各保存再開。今回の「5まで」の目標は継続中であり、150局・DDP・棋力改善はまだ未完了。

**同日05:42 UTC・費用枠更新**：不足見積もりと承認済み追加100を、PR129の修正統合main検証・所有資源0の確認後に実ledgerへ適用した。総枠200・予約92.5・未予約107.5。全22予約を保持し、新規レンタルはまだ行っていない。[適用証跡](docs/P5_3_EXECUTION_BUDGET.md)。

**2026-11-04 JST・実行再開**：ユーザーの「5まで進めて」により、[次の計画](docs/P5_3_PLAN.md)の評価準備→8局試行→150局比較→診断→1／2／4GPU実測までが今回の範囲。P5-2後の停止指示はこの範囲で解除された。Phase6の構造比較・新モデルWeb採用はまだ開始しない。

**2026-11-03 16:56:12 UTC・P5-2の終了と停止**：[本条件3世代48対局・HF保存・別VM後続世代](docs/P5_2_COMPLETION.md)の結果を記録した。使用した所有課金資源は0。棋力改善・P5-3・DDP・Phase6は未完了であり、結果共有後に停止する。

9×9×9（729マス・372枚）の三次元将棋を題材にした、再現可能な三次元将棋 AI 研究プラットフォームです。対象は、ルールエンジン、ブラウザゲーム、合成データセット、Transformer モデル、分散学習です。

**主用途はAI vs AIの対局を見て・眺める観戦で、そのためのモデル開発と研究を行う。** ゲームの面白さ、初見での分かりやすさ、見映え、モデル比較の再現性を重視する。人間 vs AIは補助的な参加方法とし、人間同士の対局・マルチプレイは対象にしない（2026-10-26 ユーザー指定）。

**実行環境（2026-10-28ユーザー指定）**: Macは編集・読み取り・軽量な静的／単体確認のみ。探索・データ生成・性能計測・学習・重い回帰検証はGitHub Actionsまたは承認済みVast.ai／CloudRift上で行う。M4はGPUサーバーのCPU、M6は同じサービスのGPUへつなぐ。[初回試行の構成・見積もり・準備](docs/M4_REMOTE_PLAN.md)。初回利用は2026-10-28に承認され、CloudRift実機の初回・代表計測が成功。Mac計測へ戻さない。

- 現在地・公開／品質の確認元: `docs/STATUS.md`
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
- Cloudflare は、ユーザーの個人アカウント（ka1357amnbpdr@gmail.com）を使う。このマシンの wrangler はグローバルには別アカウントでログインしているため、**必ず `scripts/cf.sh`（プロジェクト専用ログイン）経由で wrangler を使う**。素の `wrangler` は使わない（`apps/web` の `pnpm run deploy` も `scripts/cf.sh` を経由する。`pnpm deploy` は pnpm の組み込みコマンドなので使わない）。
- 将棋ったーの公開棋譜による互換性検証は非公開の作業領域で行う（棋譜をコミット・HF公開しない）。重い検証は承認済み外部Linuxで実行し、Macへ計算を戻さない。

## 現在の進捗と次の判断

今回の「5まで」は、[P5-3計画](docs/P5_3_PLAN.md)の評価準備→8局試行→150局の全入力監査→12局の1要因診断→[実1／2／4GPUと各HF保存再開](docs/P5_4_RESULTS.md)まで実行した。全構成の中間／最終state計6件、測定dataset、全固定HF版のhash・Card、所有実機の解放まで確認済み。科学sourceは`0171a6b7113bc16ed2a0d8b72cebac2ccd96420f`。全33予約152.5／承認200と累積state upload ledgerを保持し、予約を実請求とは扱わない。

- Phase0〜4／M0〜M6、P5-0とP5-2の3世代48対局・保存・別VM後続世代は完了。過去の固定結果・失敗・SHAを保持する。
- 150局の開発用比較は保護入力重複4件を含む。12局診断は関連familyの戦術3件で、argmax／PUCT32の先手詰み成功1／3対3／3。一般棋力改善・独立holdoutは未確認として残す。
- P5-1の未検証教師候補は不採用・残検証保留。既存の保護入力と採用閾値を維持する。
- 今回のGPU比較は同じSモデル・global batch16・FP32の実測。更新部分とReplay検証・特徴量準備・保存・転送を分け、別構造やbatchへ速度比を外挿しない。今回の外部Linux runtime cacheは元と全く同じSamples SHAを全consumerで検査した。更新部分の速度比を全工程の速度と混同しない。
- Phase6の構造・Mモデル・複数seed比較、新モデルの変換／Web採用、観戦の端末検証は残課題。今回の範囲では着手していない。既存のM6 Webモデルを変更しない。
- 主用途はAI vs AI観戦、人間対AIは補助。人間同士・マルチプレイは実装しない。Macは編集・読み取り・軽量確認のみ、重い検証と実学習はCIまたは承認済み外部Linuxを使う。

結果・固定HF版・費用と限界は[GPU比較](docs/P5_4_RESULTS.md)・[起動と失敗の履歴](docs/P5_4_STARTUP.md)、残る課題は[全体計画](docs/OVERALL_PLAN.md)、段階別の目的・数量ゴールは[ROADMAP](docs/ROADMAP.md)を参照する。
