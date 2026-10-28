# 現在の状態と文書の案内

確認: **2026-10-28（JST）**。M3はPR #29の統合・公開確認まで完了し、次はM4。性能計測は `dd3762c`、M3完了時の公開確認は `bca5532` を固定した証拠として保持する。[計測・完了時公開の区別](M3_VALIDATION.md#m3完了時の統合後公開確認bca5532)・[終了時のJSON](experiments/m3-completion-publication.json)。文書PRでも再公開されるため、配信中のSHAは `build-info.json` と対応する成功CIから確認する。

M2完了時に照合したmain／公開版は `e212ec739aeb23b3dedac83f60b861903d96fbc2`（[最終公開記録](experiments/m2-final-publication.json)）。性能計測の対象 `3a500cd` と最終版の実行ファイルは同一であり、計測JSONの元SHAは保持する。これは固定した検証対象であり、後続の文書PRによる配信SHAとは区別する。現在配信される版は公開 `build-info.json` と対応するmain CIを確認する。M1時点の `2405e86` の記録は後半に保持する。

## 完了したものと次の作業

| 対象 | 状態・根拠 |
|---|---|
| Phase 0〜2、M0 | 調査・標準ルール・Web Alpha・CI/CDを完了。[M0記録](M0_VALIDATION.md) |
| R0 | 9王3ルール＋標準対照など1,052局を比較し、400／800手の代表6棋譜を公開。正式な9王採用と観戦者の好みの評価は保留。[結果](NINE_KINGS_EXPERIMENT.md) |
| M1 | 標準1王の全幅αβ、評価、反復深化・手の並べ替え・履歴を区別する置換表、深さ／ノード／時間上限を完了。[PR #10](https://github.com/ayutaz/voxelshogi/pull/10)・[#11](https://github.com/ayutaz/voxelshogi/pull/11)、[検証・計測](M1_VALIDATION.md) |
| 現在の公開画面 | 通常画面はEasy/Normalの探索観戦と人間対AI、比較室は9王の固定棋譜再生、推論ラボは未学習モデル3形式の実行。学習済みモデルによる対局はM6の対象 |
| M2 | 完了。[計画・契約](M2_PLAN.md)・[G1〜G7の照合と実測](M2_VALIDATION.md) |
| C0 | 観測競合の再現、入力イベント時点の判定への修正、変異2件の検出、実機・SwiftShaderの各3回と公開21件を検証。[原因・対策・最終公開の判定条件](C0_VALIDATION.md) |
| M3 | 完了。承認済み3形式を公開、実配信55ファイルとCI成果物を照合。公開E2E・実機48組・WASM／WebGPUで各20実切替を確認。[固定記録と失敗・制約](M3_VALIDATION.md#m3-5公開版の最終検証2026-10-28-jst) |
| 次はM4〜M6 | M4の試料HF公開と有効10万局面の本生成へ進む。M6で学習・棋力評価・全変換版の対局／観戦へ接続する。M5の実棋譜互換性は独立して挿入できる。[各フェーズの目的・ゴール](ROADMAP.md) |

M3の実機はApple M1・8 GiB・Chrome156。公開版のWebGPU FP32・INT8重みと、WASMの全3形式が数値基準を満たした。FP16×WebGPUは基準未達として拒否。3DありFP32 WebGPU中央値55.00〜56.95ms、Chrome RSS合計の観測最大約1.36 GiB。未学習モデルの技術デモで、通常の探索対局とは別。HTTP 500を1回観測した失敗・回復も保存、有料GPU・R2は未使用。[全JSON・限界](M3_VALIDATION.md#m3-5公開版の最終検証2026-10-28-jst)

主用途はAI同士を見て眺める観戦と、そのためのモデル研究。人間対AIは補助機能、人間同士の対局・マルチプレイは対象外。Pythonは3.14系を基本、依存が未対応の場合だけ3.13系とする。モデルをFP16化・量子化した場合も、公開する実行可能版を選択して試せることと、評価した配布ファイルとのSHA-256一致をM3・M6で検証する。

## M3完了時の公開・品質の確認元

| 項目 | 固定した確認元 |
|---|---|
| 通常PR・公開 | PR #28・#29を必須8チェック成功後に通常merge。完了時公開 `bca5532` の [main CI](https://github.com/ayutaz/voxelshogi/actions/runs/40530800389)・[Security](https://github.com/ayutaz/voxelshogi/actions/runs/40530800258) が成功 |
| 公開後の回帰 | 既存公開21件（33.5秒、flakyなし）、C0追加3件（44.7秒）、モデル6件（47.6秒）。追加3件・モデル6件はretries=0 |
| 実機の最終確認 | 最終公開モデル6 E2Eが55.1秒・retries=0、M1実WebGPUのFP32／INT8×4局面の全出力8件も成功 |
| 同一性 | 55応答と最終CI artifactの実バイト列を照合。ONNX3形式・checkpoint・入力・ORT・アプリ実行ファイルは性能計測版と同じhash。参照値の一部は再生成で微小に変わったため、最終参照値と再照合した |
| 固定環境・検証 | Rust1.97.1／MSRV1.85、Node24.22.1、pnpm10.32.1、Python3.14.9／uv。Rust core153＋WASM5、Web172、Python48、Node67。既知変異はcore／WASM33・Web50・Python16・CI制御14件 |

## M4の現在地と次の作業

| 対象 | 現在の状態・証拠 | 次へ進む条件 |
|---|---|---|
| Python連携・生成実装 | 実装済み。PyO3境界、行動マスク、履歴・教師の全件検証、停止再開、本生成CLI。[契約](M4_DATA_CONTRACT.md)・[検証](M4_VALIDATION.md) | 同じRust coreを共有し、Pythonへルールを再実装しない |
| 初回・代表試行 | 完了。30固定探索、初回102行、64手の1／2／4ワーカー比較と12対局が成功。最大試料は有効769局面・深さ2の探索教師252件。[集計](experiments/m4-cloudrift-representative-2026-10-28.json) | 小標本を10万局面の完了としない。CPU速度をCUDA学習速度へ読み替えない |
| 初回実機の終了 | 07:25 UTCに終了処理。ID指定APIでInactive・resources_released=true、永続volume0を確認。[固定記録](experiments/m4-initial-teardown-2026-10-28.json) | 初回ParquetはHF退避できず、再生成が必要。Macには小さい設定・集計・hashだけ |
| 試料のHF公開 | 生成前のHF APIエラーで停止、今回実機も早期終了。認証の追加確認待ち。[公開計画・試行記録](M4_HF_PILOT_RELEASE.md) | 外部Linuxで歴史的hashに一致させ、public/manual・固定Hub commitの全ファイルを照合して完了 |
| 有効10万局面 | 本生成CLIは実装済み、実データは未生成。[最大12時間・US$12の見積もり](M4_PRODUCTION_QUOTE.md) | 総行数・重複除外後の件数・教師内訳・対局分割を確認し、全検証・全再生成・HF照合を行う |
| 承認・予算 | M4合成データv1のCC-BY-4.0、HF public/manual、費用合計US$100は承認済み | 初回上限US$2・試料公開US$1・本生成最大US$12を同じ総枠で管理。未確定の実請求を上限枠で控除し、残額を確認 |
| M5・M6 | 実棋譜互換性、CUDA学習・棋力評価・学習済みモデル対局は未実行 | M5は棋譜がそろい次第独立して実施。M6は同じGPUサービスで学習速度と配布条件を確認 |

Macは編集・読み取り・軽量確認のみ。探索・生成・計測・学習はVast.ai／CloudRift、重い回帰はLinux CIで行う。データと学習checkpointは外部LinuxからHFの`voxelshogi/`配下へ直接送り、Macへ中継しない。public/manualはダウンロード申請を人が承認する設定で、公開自体の再承認待ちではない。M3の既承認配布は維持し、学習済みモデルのライセンスと取得ゲートに沿うWeb配信はM6で別に確定する。

## M4準備の統合・公開基準

[PR #37](https://github.com/ayutaz/voxelshogi/pull/37)は必須8チェック成功後に通常merge済み。統合`37b5bac2db5a1fbdd8b1517ed035460d76d0d504`の[main CI](https://github.com/ayutaz/voxelshogi/actions/runs/40647681139)・[Security](https://github.com/ayutaz/voxelshogi/actions/runs/40647681204)、自動公開・配信SHA一致・公開21 E2E・C0追加3件・モデル6件・配信55ファイル照合を確認した。[固定記録](experiments/m4-pilot-publication-baseline.json)。初回のPython urllib取得403とcurlでの200・SHA一致も保存し、失敗を上書きしない。

同ソースのPython CIは121テスト成功、Pythonモデル16変異・training32変異を検出。Rust core153＋WASM5＋Python境界2、Web172、Node67、既知Rust境界38・Web50・CI制御14変異も通常CIへ含む。M3終了時の旧テスト数や性能値は上の固定記録に保持し、現在のM4実装と区別する。

## M2の実装・公開・品質の確認元

| 項目 | 固定した確認元 |
|---|---|
| 通常PR | #13〜#16の必須7チェック成功後にsquash merge。保護のbypassなし |
| 統合後の自動公開 | [最終main CI 40385647318](https://github.com/ayutaz/voxelshogi/actions/runs/40385647318)：通常検証・生成WASMのジョブ間受け渡し・公開・配信SHA・公開E2E21件が再試行なしで成功。CodeQLは [40385647367](https://github.com/ayutaz/voxelshogi/actions/runs/40385647367) |
| M2完了時のテスト | Rust core153件＋WASM境界5件、Web115件、CI制御Node49件、Native/WASM12fixture、既知core/WASM33変異とWeb29変異、E2E21件。現在の確認元は上のM3表を参照 |
| 実機の公開確認 | Mac M1・8 GiB・Chrome155・Metalで公開E2E21件が再試行／skipなしで成功。最終公開版は22.7秒で全21件が成功（[最終記録](experiments/m2-final-publication.json)）。途中版の [全レポート](experiments/m2-public-e2e.json) とCIでの再試行・修正経緯は [検証記録](M2_VALIDATION.md) に保持 |
| 性能と配信 | Normalは深さ6・50,000ノード・約1秒。初期局面は3回とも深さ2。初回JS255,096 bytes、公開WASM361,183 bytes。[固定7入力・Native比較](experiments/m2-search-browser-public.json)・[同じCI成果物との12ファイル照合](experiments/m2-public-artifact-match.json) |
| 未導入・保留 | M3の未学習モデル推論は公開済み。学習済みAI対局はM6の対象。R2・COOP/COEP・有料GPUは未導入、9王の正式採用は保留 |
| ローカル準備 | 空き容量は2026-10-27確認で約27.2 GiB。[取得記録](experiments/documentation-baseline-2026-10-27.json)。Pythonは3.14.9、依存導入直前に容量と互換性を再確認 |

## 過去の課題：C0で対応済み

以下はM3着手前の履歴で、現在のM4着手を妨げる未解決課題ではない。公開後もC0の追加3回・retries=0を継続している。

文書更新 [PR #17](https://github.com/ayutaz/voxelshogi/pull/17) のCIは必須7チェック・E2E21件が成功したが、統合後のmain `b6cfc93` の [公開CI 40432366163](https://github.com/ayutaz/voxelshogi/actions/runs/40432366163) は20 passed＋1 flaky（1件は再試行で成功）だった。公開SHA照合とdeployは成功し、失敗・skipされた必須チェックはない。M2完了時の `e212ec7` の再試行なしの記録とは別に扱う。

該当は `apps/web/e2e/ai.spec.ts` の3Dカメラ操作後の思考状態確認で、期待「思考中」に対して「一時停止中」になった。`e212ec7` から実行コード・テスト・CI設定に差分はない。この時点では遅延の主因は未切分だった。その後のC0で、入力と描画が思考中でも、後から観測すると実応答が先に到着して失敗する競合を再現した。元の1回のrunner内の遅延源そのものは、詳細な時刻がなく断定しない。

**C0での対応**: ブラウザ内で要求・実Worker応答・入力・draw・中断の時刻を分け、実pointerup時点で判定・中断する形へ修正した。3.3秒の観測遅延を加えたRED/GREEN、カメラ無効化とmain thread停止の変異検出、Metal/local・SwiftShader/publicの各3回と公開21件（いずれも再試行なし）を記録。CIと公開後にも各3回の再試行なし検証を追加した。[C0検証記録](C0_VALIDATION.md)・[固定JSON](experiments/c0-interaction.json) を参照。PR #19とmainの公開後検証まで成功し、C0を完了してM3の実装へ進んだ。

## 文書整備時の旧固定記録（M1・2026-10-26）

以下は `2405e86` を照合した当時の値で、現在のテスト数・サイズ・公開SHAではない。

| 項目 | 今回照合した値・一次資料 |
|---|---|
| 固定ツール | Rust1.97.1／MSRV1.85、Node24.22.1、pnpm10.32.1、Python3.14.9、wasm-bindgen/CLI0.2.129。設定ファイルとlockfileを正とする |
| テスト | Rust150件、Web36件、CI制御Node46件、既知変異21件、実ブラウザE2E9件。Rust/Web/Nodeは文書照合時にも再実行して成功 |
| M1全体変異 | 1,172＝1,075 caught＋89 unviable＋8 reviewed equivalent。欠落・重複・未知の生き残り・timeoutなし。[対象SHAと全分割](experiments/m1-mutations.json) |
| main CI・本番公開 | [CI 40318499296](https://github.com/ayutaz/voxelshogi/actions/runs/40318499296) の通常検証・deploy・配信SHA・公開E2Eが成功 |
| セキュリティ | [Security 40318499415](https://github.com/ayutaz/voxelshogi/actions/runs/40318499415) のCodeQL 3言語が成功。今回確認した未解決CodeQL警告は0件 |
| PR運用 | APIでruleset25816100がactive、必須7チェック（Actions app15368）・strict、CodeQL error/high以上を確認。他者承認0、bypassなし、force push・削除禁止。repoで許可するmerge方式はsquashだけ。設定は [.github/main-ruleset.json](../.github/main-ruleset.json)、運用は [CONTRIBUTING](../CONTRIBUTING.md) |
| 認証の配置・報告経路 | APIでproductionの許可元mainのみ、repository Secrets0件、production Secretsは既存の2名を確認。秘密値は取得していない。Secret scanning・push protection・Dependabot security updates・private vulnerability reportingが有効 |
| 未取り込み依存更新 | [Dependabot PR #1](https://github.com/ayutaz/voxelshogi/pull/1) はopen。mainに採用済みとは扱わず、本更新で依存を変更しない |
| 配信 | WorkerスクリプトなしのStatic Assets。COOP/COEP・R2・NN runtimeは未導入。公開SHA、JS/WASMのサイズ・hash、2 manifestと全6棋譜の照合は [取得記録](experiments/documentation-baseline-2026-10-26.json) |

M1のNative単独計測はApple M1・8 GiB、初期局面の深さ2が約0.33秒、1秒予算で3回とも深さ2を完了。R0の幅制限探索・ブラウザ・GPU学習の速度へ一律換算しない。WASM/WorkerはM2で公開実測済み。M4で生成対象のpilot、M6で学習速度を測る。

## 文書の役割と更新範囲

| 文書 | 用途・今回の扱い |
|---|---|
| [README](../README.md)、[CLAUDE](../CLAUDE.md) | 入口・開発時の現在地。M3完了、次のM4、固定ツールとコマンドへそろえる |
| [PROJECT_SPEC](PROJECT_SPEC.md)、[ROADMAP](ROADMAP.md) | プロジェクト要件、各Phase／Mの目的・ゴール・依存関係・ユーザー準備の正 |
| [M1_PLAN](M1_PLAN.md)、[M1_VALIDATION](M1_VALIDATION.md) | 完了したM1の実装契約と固定した検証記録。M2の契約と結果は [M2_PLAN](M2_PLAN.md)・[M2_VALIDATION](M2_VALIDATION.md)、M3の完了時の契約は [M3_PLAN](M3_PLAN.md) |
| [GAME_ENGINE](GAME_ENGINE.md)、[RULESET](RULESET.md) | 実装済みAPIとルールの正。予定のAPIを現行APIとして記載しない。MaxPlies／Abandonedと検証済み投了結果の保存・履歴移動を明記。M5互換性は未実施 |
| [CI_CD_PLAN](CI_CD_PLAN.md)、[DEPLOYMENT](DEPLOYMENT.md) | 現行のCI・main保護・認証の配置・配信・復旧手順。過去のrunは固定記録として保持 |
| [ARCHITECTURE_DECISIONS](ARCHITECTURE_DECISIONS.md) | ADR-001〜018は当時の判断。M2のWorker・観戦はADR-018、M3の形式・backend・配信はADR-019、M4のPython境界・外部生成・HF公開はADR-020。後続ADR・現在の仕様を優先し、過去の経緯を現在の未実装事項と混同しない |
| [M0_VALIDATION](M0_VALIDATION.md)、[NINE_KINGS_EXPERIMENT](NINE_KINGS_EXPERIMENT.md) | M0／R0完了時の歴史的記録。旧テスト数・生成コミット・実測値を保持し、現在地への案内を更新 |
| [RULE_VARIANTS_RESEARCH](RULE_VARIANTS_RESEARCH.md) | ルールの先行調査と未実施の継続評価。標準のM1完了と9王への未適用を区別 |
| [RESEARCH](RESEARCH.md)、[RELATED_WORK](RELATED_WORK.md) | 外部資料の調査記録と将来の研究候補。M3の未学習Transformerと、未実施のGumbel・構造比較・DDP学習を区別する |
| [TECH_STACK_RESEARCH](TECH_STACK_RESEARCH.md)、[COST_ESTIMATE](COST_ESTIMATE.md) | 固定済み構成と公開実測を更新。初回の外部版・GPU相場・為替・ドメイン価格は取得日付き参考値で、採用／課金時に再取得する |
| [AGENTS](../AGENTS.md)、[CONTRIBUTING](../CONTRIBUTING.md)、[SECURITY](../SECURITY.md)、[PRテンプレート](../.github/pull_request_template.md)、[ci-checks](../.agents/skills/ci-checks/SKILL.md) | ブランチ・TDD・PR・秘密情報・最短10分間隔のCI確認という現行方針と整合を確認。追加の承認フローや人間同士の対局は導入しない |

外部資料は記載の取得日に対する記録であり、全リンク先の最新版や将来の採用版を保証しない。現在の実装・固定版と、M4／M6以降で評価する候補を分けて読む。GPU費の初期予算例は支出の承認ではない。M3は完了し、M4の実装開始にユーザー側の追加準備はなく、モデル／データのライセンスや有料GPUはROADMAP記載の時点で確定する。

文書の更新時はコード・設定・実行結果を照合し、ローカルリンク／アンカー、掲載API例とコマンド、数値の出典を確認する。現在はPython CodeQLを含む通常PRの必須8チェック成功後に取り込み、mainの自動公開を確認する。

M4全体を完了とするには、試料公開だけでなく重複除外後100,000局面の実データ・全件検証・全再生成一致・HF照合が必要。[本生成契約](M4_PRODUCTION.md)・[実行順とゴール](M4_PLAN.md)を確認する。
