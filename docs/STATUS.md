# 現在の状態と文書の案内

**M6／Phase4完了（2026-10-29 UTC）**：[完了記録](M6_COMPLETION.md)。学習・保存再開・HF復旧、全3形式の固定評価・public/manual公開と37ファイル照合、公開catalog差し替えなしの実機48条件・40実切替、3形式のGPU着手・7実モデルE2Eを確認し、全所有GPUの資源解放を確認した。教師模倣精度は向上したが、探索AIに対する棋力向上は未確認。Phase5の[P5-0評価契約](P5_EVALUATION.md)に着手。Phase6〜7は未着手。

**初回本学習の記録**：[FP32変換失敗・Torch固定評価・資源終了](M6_MAIN.md)は過去runの証拠として保持する。本文中の「本学習未実施」等は初回実行前の計画であり、現在地は上記の完了記録を参照。

確認: **2026-10-30（JST）**。M4／Phase3、固定3局のM5、M6-5／Phase4まで完了。[M6完了証拠](M6_COMPLETION.md)。次はPhase5〜7の計画。過去の性能・公開記録は日時と対象SHAを保持し、現在の公開SHAは`build-info.json`と対応する成功CIから確認する。

M2完了時に照合したmain／公開版は `e212ec739aeb23b3dedac83f60b861903d96fbc2`（[最終公開記録](experiments/m2-final-publication.json)）。性能計測の対象 `3a500cd` と最終版の実行ファイルは同一であり、計測JSONの元SHAは保持する。これは固定した検証対象であり、後続の文書PRによる配信SHAとは区別する。現在配信される版は公開 `build-info.json` と対応するmain CIを確認する。M1時点の `2405e86` の記録は後半に保持する。

## 次の実装と文書更新時の照合

次は[POST_M6_PLAN](POST_M6_PLAN.md)の**P5-0：評価契約v2と独立テスト**。評価の感度→教師・長期対局データ→1GPU自己対局→世代比較→複数GPU→構造比較→正式公開の順に、目的・成果物・完了条件を定めた。Phase6までの実行指示を受け、P5-0のmetadata契約・集計・独立テストは[PR #77](https://github.com/ayutaz/voxelshogi/pull/77)で必須・関連CI成功後に取り込み済み。Linux用runner・全手再生も[PR #78](https://github.com/ayutaz/voxelshogi/pull/78)で必須・関連CI成功後に取り込み済み。用途別費用制御を検証中。外部試行、追加生成、GPU学習、Phase6の構造比較は未実施。

文書更新開始時点のmain／公開版は`16b2b2733b74f176ce65a2e0f334edb710db4a71`。[CI](https://github.com/ayutaz/voxelshogi/actions/runs/40943910648)・[Security](https://github.com/ayutaz/voxelshogi/actions/runs/40943910611)は成功、公開catalogは最終HF revisionに一致した（[固定した読取記録](experiments/post-m6-plan-baseline-2026-10-30.json)）。物理計測対象は`564715a`のまま保持し、後続の文書公開へ実測値を付け替えない。最新の配信SHAは公開`build-info.json`を確認する。

## 完了したものと次の作業

| 対象 | 状態・根拠 |
|---|---|
| Phase 0〜2、M0 | 調査・標準ルール・Web Alpha・CI/CDを完了。[M0記録](M0_VALIDATION.md) |
| R0 | 9王3ルール＋標準対照など1,052局を比較し、400／800手の代表6棋譜を公開。正式な9王採用と観戦者の好みの評価は保留。[結果](NINE_KINGS_EXPERIMENT.md) |
| M1 | 標準1王の全幅αβ、評価、反復深化・手の並べ替え・履歴を区別する置換表、深さ／ノード／時間上限を完了。[PR #10](https://github.com/ayutaz/voxelshogi/pull/10)・[#11](https://github.com/ayutaz/voxelshogi/pull/11)、[検証・計測](M1_VALIDATION.md) |
| 現在の公開画面 | 通常画面はEasy/Normalと取得済み学習モデル3形式の観戦・人間対AI。推論ラボはM3の未学習モデル。9王比較室と旧URLの画面は撤去し、研究記録を保持 |
| M2 | 完了。[計画・契約](M2_PLAN.md)・[G1〜G7の照合と実測](M2_VALIDATION.md) |
| C0 | 観測競合の再現、入力イベント時点の判定への修正、変異2件の検出、実機・SwiftShaderの各3回と公開21件を検証。[原因・対策・最終公開の判定条件](C0_VALIDATION.md) |
| M3 | 完了。承認済み3形式を公開、実配信55ファイルとCI成果物を照合。公開E2E・実機48組・WASM／WebGPUで各20実切替を確認。[固定記録と失敗・制約](M3_VALIDATION.md#m3-5公開版の最終検証2026-10-28-jst) |
| M4〜M6完了 | M4の全生成・検証・HF公開、M5固定3局145手の一致、M6の学習・復旧・全3形式・公開実機・資源終了まで完了。[目的とゴール](ROADMAP.md)・[M6証拠](M6_COMPLETION.md) |

M3の実機はApple M1・8 GiB・Chrome156。公開版のWebGPU FP32・INT8重みと、WASMの全3形式が数値基準を満たした。FP16×WebGPUは基準未達として拒否。3DありFP32 WebGPU中央値55.00〜56.95ms、Chrome RSS合計の観測最大約1.36 GiB。未学習モデルの技術デモで、通常の探索対局とは別。HTTP 500を1回観測した失敗・回復も保存、M3では有料GPU・R2を使わなかった。その後のM6学習・公開実GPU検証は[完了記録](M6_COMPLETION.md)を参照。R2は未実施。[全JSON・限界](M3_VALIDATION.md#m3-5公開版の最終検証2026-10-28-jst)

主用途はAI同士を見て眺める観戦と、そのためのモデル研究。人間対AIは補助機能、人間同士の対局・マルチプレイは対象外。Pythonは3.14系を基本、依存が未対応の場合だけ3.13系とする。モデルをFP16化・量子化した場合も、公開する実行可能版を選択して試せることと、評価した配布ファイルとのSHA-256一致をM3・M6で検証する。

## 履歴：PR #45の文書更新時の基準（2026-10-29 JST）

[小さい確認記録](experiments/post-m4-plan-baseline-2026-10-29.json)。PR #45統合のmain `389ba94720dbe5f9b6d13d31f5db4a771d436fd1`で[CI・自動公開](https://github.com/ayutaz/voxelshogi/actions/runs/40746960925)と[Security](https://github.com/ayutaz/voxelshogi/actions/runs/40746962816)が成功し、公開`build-info.json`も同じSHAだった。HFの現在のcommitは本生成公開時と同じで、public/manual・Community OFFを再確認。CloudRiftの稼働中VoxelShogi実機0・永続volume 0件を読み取り確認した。これは後続の文書PRで変わる前の固定した基準である。

M6-5まで完了。固定教師train29,884／val3,421／test3,589、RTX5090で3 epoch／22,413更新を学習し、HFの新run復旧とmodel／optimizer／RNGの完全一致を確認した。初期／Torch／各ONNXの固定評価、FP32・FP16重み・INT8重みのpublic/manual・Community OFF公開と全37ファイル照合、公開catalog差し替えなしの実機48条件／40切替・全3GPU形式の着手・7実モデルE2E、資源解放まで成功。[完了記録](M6_COMPLETION.md)。旧数値・FP16・カメラ操作の失敗は保持し、棋力向上は未確認。

## M4・M5の完了確認（2026-10-29 JST）

[本生成の完了記録](M4_COMPLETION.md)。1,800局・116,921行から重複3,600行を除いた有効113,321局面・探索教師36,894件を全件検証。全再生成のバイト一致後、HF commit `6e7fb29d2469b56a895042fbb089d86e7b4d074f`へ`production-64`とDataset Cardを公開し、対象1,831ファイルの全hashが一致した。public/manual・Community OFF、CC-BY-4.0を確認。実機は終了・資源解放、稼働中VoxelShogi実機0・永続volume 0件。

生成・検証・再生成は約4時間36分、RSS観測最大約589.84 MiB。準備から資源解放まで約5.04時間、時間×単価の参考額約US$5.04（実請求未回収）。過去の上限も保守的に残した予約上限累計US$41・未予約額US$59。M6は基本枠US$24内で予約上限US$20、プロジェクト全体US$61／基本枠100、追加US$100は未使用。GPUは解放済みで、予約上限と実請求は区別する。[M6の費用・終了](M6_COMPLETION.md#費用と資源終了)。HF送信と同目的の所有実機の置き換えは継続承認済み。

実装・公開準備はPR #43、開始記録と継続承認はPR #44を必須8チェック成功後に通常merge。統合後のmain CI・公開検証も成功した。M5は[PR #42・固定3局145手の全件一致](M5_PLAN.md)で、全棋譜の完全互換は主張しない。

## PR #40時点の統合・公開確認（固定した履歴）

[PR #40](https://github.com/ayutaz/voxelshogi/pull/40)を必須8チェック成功後に通常merge。固定した確認元はmain `5065d98685c77e8d50215870555d98e68ddec98c`、[CI](https://github.com/ayutaz/voxelshogi/actions/runs/40669143635)・[Security](https://github.com/ayutaz/voxelshogi/actions/runs/40669143626)は成功。Python3.14.9の129テスト、Pythonモデル16・training35変異、公開21 E2E・C0追加3件・モデル6件、配信55ファイル照合と公開SHA一致を確認した。[小さい固定記録](experiments/m4-next-plan-baseline-2026-10-28.json)。後続の文書PRで公開SHAが変わっても、この検証対象を上書きしない。

以下は本生成開始前の固定記録。試料はHF commit `83dd4523817908770dcaf11319243a5405addf26`に2 configとDataset Cardを公開済み。public/manual・Community OFFを再確認した。これまで使用した4実機は全て`Inactive`・資源解放済み、永続volume 0件。利用上限枠の累計US$5を控除した未予約額はUS$95で、実請求額は未回収。

この時点の次の計画は[M4-5aの起動前準備 → 本生成 → HF公開・資源終了](M4_PLAN.md#次に実行する単位)。本生成の全体上限は12時間／US$12。M4完了後は[M6の教師固定・学習実装 → CUDA試行・本学習・評価 → 変換・モデル観戦](M6_PLAN.md)へ進む。学習ループ・CUDA依存はこれから実装し、現在のCPU版torchや未学習デモを学習済みと扱わない。M5の固定3局の検証は完了（[結果](M5_PLAN.md)）。

## M3完了時の公開・品質の確認元

| 項目 | 固定した確認元 |
|---|---|
| 通常PR・公開 | PR #28・#29を必須8チェック成功後に通常merge。完了時公開 `bca5532` の [main CI](https://github.com/ayutaz/voxelshogi/actions/runs/40530800389)・[Security](https://github.com/ayutaz/voxelshogi/actions/runs/40530800258) が成功 |
| 公開後の回帰 | 既存公開21件（33.5秒、flakyなし）、C0追加3件（44.7秒）、モデル6件（47.6秒）。追加3件・モデル6件はretries=0 |
| 実機の最終確認 | 最終公開モデル6 E2Eが55.1秒・retries=0、M1実WebGPUのFP32／INT8×4局面の全出力8件も成功 |
| 同一性 | 55応答と最終CI artifactの実バイト列を照合。ONNX3形式・checkpoint・入力・ORT・アプリ実行ファイルは性能計測版と同じhash。参照値の一部は再生成で微小に変わったため、最終参照値と再照合した |
| 固定環境・検証 | Rust1.97.1／MSRV1.85、Node24.22.1、pnpm10.32.1、Python3.14.9／uv。Rust core153＋WASM5、Web172、Python48、Node67。既知変異はcore／WASM33・Web50・Python16・CI制御14件 |

## 履歴：M4各段階の達成証拠

| 対象 | 現在の状態・証拠 | 次へ進む条件 |
|---|---|---|
| Python連携・生成実装 | 実装済み。PyO3境界、行動マスク、履歴・教師の全件検証、停止再開、本生成CLI。[契約](M4_DATA_CONTRACT.md)・[検証](M4_VALIDATION.md) | 同じRust coreを共有し、Pythonへルールを再実装しない |
| 初回・代表試行 | 完了。30固定探索、初回102行、64手の1／2／4ワーカー比較と12対局が成功。最大試料は有効769局面・深さ2の探索教師252件。[集計](experiments/m4-cloudrift-representative-2026-10-28.json) | 小標本を10万局面の完了としない。CPU速度をCUDA学習速度へ読み替えない |
| 初回実機の終了 | 07:25 UTCに終了処理。ID指定APIでInactive・resources_released=true、永続volume0を確認。[固定記録](experiments/m4-initial-teardown-2026-10-28.json) | 初回Parquetは当時HF退避できず、その後の再生成・歴史的hash照合とHF公開で回復。Macには小さい記録だけ |
| 試料のHF公開 | ✅ 2 configを公開済み。Dataset Card、public/manual・Community OFF、固定Hub commitで28ファイル全hash一致、実機終了・資源解放を確認。[公開記録](M4_HF_PILOT_RELEASE.md) | 試料の公開は完了。本生成でもカード・Community OFF・全件照合を継続する |
| 有効10万局面 | ✅ 1,800局・有効113,321局面・探索教師36,894件を全検証・全再生成し、HF公開と全1,831対象ファイル照合・実機終了まで完了。[記録](M4_COMPLETION.md) | M6は固定revisionを使用。各splitの探索教師数は学習前に外部Linuxで集計・凍結する |
| 承認・予算 | M4データCC-BY-4.0、M6モデル／再開状態Apache-2.0、HF public/manual・Community OFF。予約上限は全体US$61／100・M6 US$20／24、追加100未使用、実請求未回収 | M6 GPUは資源解放済み。後続段階は見積もり・割当と照合する |
| M5 | ✅ 改定後の固定3局145手、各局面の盤／持ち駒と投了結果が一致。PR #42を必須CI成功後に通常merge。[結果・制約](M5_PLAN.md) | 全棋譜・全終局条件の完全互換は主張しない。原本を学習や公開へ含めない |
| M6 | ✅ 学習・中断再開・HF復旧・固定評価・3形式HF公開・公開実機と資源終了まで完了 | [完了記録](M6_COMPLETION.md)。Phase5〜7の計画へ |

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
| 未導入・保留 | M3の未学習モデル推論は公開済み。学習済みAI対局はM6の対象。R2・COOP/COEPは未導入。M6-2の少量CUDA学習は成功済み。M4でGPUサービスのCPUは利用済み、9王の正式採用は保留 |
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

M1のNative単独計測はApple M1・8 GiB、初期局面の深さ2が約0.33秒、1秒予算で3回とも深さ2を完了。R0の幅制限探索・ブラウザ・GPU学習の速度へ一律換算しない。WASM/WorkerはM2で公開実測済み。M4のCPU生成実測は完了し、M6では別にCUDA学習速度を測る。

## 文書の役割と更新範囲

現状は本書、仕様・フェーズ目標はROADMAP、直近の実行順は[POST_M6_PLAN](POST_M6_PLAN.md)。M6の契約は[M6_PLAN](M6_PLAN.md)、実績は[M6_COMPLETION](M6_COMPLETION.md)に分ける。以下の履歴リンクの件数・価格・日時は当時の記録として読む。

| 文書 | 用途・今回の扱い |
|---|---|
| [README](../README.md)、[CLAUDE](../CLAUDE.md) | 入口・開発時の現在地。M6／Phase4完了、次のP5-0と段階別の費用・検証条件、固定ツール・コマンドへそろえる |
| [PROJECT_SPEC](PROJECT_SPEC.md)、[ROADMAP](ROADMAP.md) | プロジェクト要件、各Phase／Mの目的・ゴール・依存関係・ユーザー準備の正 |
| [M1_PLAN](M1_PLAN.md)、[M1_VALIDATION](M1_VALIDATION.md) | 完了したM1の実装契約と固定した検証記録。M2の契約と結果は [M2_PLAN](M2_PLAN.md)・[M2_VALIDATION](M2_VALIDATION.md)、M3の完了時の契約は [M3_PLAN](M3_PLAN.md) |
| [GAME_ENGINE](GAME_ENGINE.md)、[RULESET](RULESET.md) | 実装済みAPIとルールの正。予定のAPIを現行APIとして記載しない。MaxPlies／Abandonedと検証済み投了結果の保存・履歴移動を明記。M5は固定した改定後3局の全件一致を確認。完全互換は未検証 |
| [CI_CD_PLAN](CI_CD_PLAN.md)、[DEPLOYMENT](DEPLOYMENT.md) | 現行のCI・main保護・認証の配置・配信・復旧手順。過去のrunは固定記録として保持 |
| [ARCHITECTURE_DECISIONS](ARCHITECTURE_DECISIONS.md) | ADR-001〜018は当時の判断。M2のWorker・観戦はADR-018、M3の形式・backend・配信はADR-019、M4のPython境界・外部生成・HF公開はADR-020。後続ADR・現在の仕様を優先し、過去の経緯を現在の未実装事項と混同しない |
| [M0_VALIDATION](M0_VALIDATION.md)、[NINE_KINGS_EXPERIMENT](NINE_KINGS_EXPERIMENT.md) | M0／R0完了時の歴史的記録。旧テスト数・生成コミット・実測値を保持し、現在地への案内を更新 |
| [RULE_VARIANTS_RESEARCH](RULE_VARIANTS_RESEARCH.md) | ルールの先行調査と未実施の継続評価。標準のM1完了と9王への未適用を区別 |
| [RESEARCH](RESEARCH.md)、[RELATED_WORK](RELATED_WORK.md) | 外部資料の調査記録と将来の研究候補。M3未学習とM6学習済みの実績、未実施の自己対局・構造比較・DDPを区別する |
| [TECH_STACK_RESEARCH](TECH_STACK_RESEARCH.md)、[COST_ESTIMATE](COST_ESTIMATE.md) | 固定済み構成と公開実測を更新。初回の外部版・GPU相場・為替・ドメイン価格は取得日付き参考値で、採用／課金時に再取得する |
| [AGENTS](../AGENTS.md)、[CONTRIBUTING](../CONTRIBUTING.md)、[SECURITY](../SECURITY.md)、[PRテンプレート](../.github/pull_request_template.md)、[ci-checks](../.agents/skills/ci-checks/SKILL.md) | ブランチ・TDD・PR・秘密情報・最短10分間隔のCI確認という現行方針と整合を確認。追加の承認フローや人間同士の対局は導入しない |

外部資料は記載の取得日に対する記録であり、全リンク先の最新版や将来の採用版を保証しない。現在の実装・固定版と、M4／M6以降で評価する候補を分けて読む。GPU費の初期予算例は支出の承認ではない。M6-5まで完了し、P5-0の仕様・独立テストと今回の文書更新にユーザー側の追加作業はない。M4データのCC-BY-4.0・費用総枠US$100は承認済み。M6基本枠US$24と不足時の追加GPU予算US$100、対象モデル・再開状態のApache-2.0、別repoへのpublic/manual・Community OFF公開は2026-10-29に個別承認済み。追加枠は不足の実測見積もりを記録後に有効化する。

文書の更新時はコード・設定・実行結果を照合し、ローカルリンク／アンカー、掲載API例とコマンド、数値の出典を確認する。現在はPython CodeQLを含む通常PRの必須8チェック成功後に取り込み、mainの自動公開を確認する。

M4全体は、試料公開に加えて重複除外後113,321局面の実データ・全件検証・全再生成一致・HF照合を確認して完了した。[本生成契約](M4_PRODUCTION.md)・[実行順とゴール](M4_PLAN.md)を確認する。

文書更新[PR #38](https://github.com/ayutaz/voxelshogi/pull/38)も必須8チェック成功後に通常mergeし、統合`b2fbe71284902dc2c93cfaaa02cf5bb0d9ffdfc9`のCI・Security・自動公開・公開SHA・21＋3＋6 E2E・55ファイル照合を確認した。[固定した文書更新の公開記録](experiments/m4-docs-publication-2026-10-28.json)。これはデータセットのHF公開成功を意味しない。
