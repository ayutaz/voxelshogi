# 2026-11-12：動くデモと研究基盤を残して一時停止

ユーザーの判断により、**既存の公開デモと再現可能な技術検証を現段階の成果として一区切りにする**。
追加GPUの確保・データ生成・本学習・Mモデルの配布は停止する。今回の作業は文書の更新に限る。
元の[1〜6の計画](P6_EXECUTION_PLAN.md)を完了と読み替えず、未達項目は再開候補として残す。

## 利用できるものと研究段階のもの

| 対象 | 到達点 | 区別すること |
|---|---|---|
| 公開Arena | [AI対AI観戦・人間対AI](https://voxelshogi.yousan-apps.workers.dev)。探索AI、取得済みSモデル、2D／3D、停止・1手送り・速度変更 | 学習済みモデルはHFで取得申請し、承認後に固定版フォルダーを利用者が読み込む |
| 公開推論ラボ | [3形式の推論・数値比較](https://voxelshogi.yousan-apps.workers.dev/?models=1) | 未学習モデルの技術デモ。学習済みSの観戦と区別する |
| Sモデル | 学習・HF保存再開・固定test・3形式公開・実GPUブラウザ観戦まで確認 | 教師手再現率約75.6%は勝率ではない。探索AIに対する棋力向上は未確認 |
| Mモデル | Full／Geometry各1,024更新、HF保存からの再開一致、由来別val、計48開発対局まで実行 | 少量・各1 seed。十分な本学習、構造の優劣、一般棋力改善、Mのブラウザ配布は未確認 |
| 研究基盤 | Rust共通ルール、WASM／Python、合成データ、自己対局3世代、実1／2／4GPU保存再開 | 動作・再現性の成功と、モデルの強さの成功を分ける |

既存の公開・実機検証の証拠は[M6完了記録](M6_COMPLETION.md)を参照する。
今回の軽い公開build metadata取得はHTTPErrorで、現在の配信SHAや新しい公開E2E成功は未確認。
過去の動作確認を今回再実行したとは記載しない。

## 今回の少量学習と48局

科学sourceは`91a9f282c3d0f605dcd846f7bfe0e181d7ef72ff`。
Vast.aiのRTX5090を使用し、Python3.14.9／torch2.14.1+cu130／CUDA13.0、FP32、batch16、seed67003。
両構造を各1,024更新し、384更新時点からHF経由で復元して続行した。
連続実行と再開実行のmodel／optimizer／RNG／進捗／履歴、およびlatest／bestは完全一致した。
continuous／interrupted／restoredの計6実行経路は、2つの科学runの再現性検証であり、6 seedではない。

| 指標 | Full | Geometry-Aware |
|---|---:|---:|
| 学習更新数 | 1,024 | 1,024 |
| valで選んだbestの更新位置 | 1,024 | 512 |
| bestのval損失（1,362件） | 4.041610 | 4.048111 |
| 開発対局数 | 24 | 24 |
| 勝／敗／自然引分／打切り | 0／4／4／16 | 0／4／4／16 |
| 連続attemptの準備時間 | 221.55秒 | 219.03秒 |
| 同attemptのfitter呼出し時間 | 172.49秒 | 181.23秒 |

fitter時間には初期化・val・保存を含む。純GPU演算、12 run全体、他構造の所要時間へ比例換算しない。
損失の小差と同じ勝敗件数から構造の優劣は判定しない。1,024更新を十分な本学習とは扱わない。

48局の棋譜と実NN参照1,376件を含む入力監査は完了し、監査対象の保護集合との重複は検出されなかった。
この48局は、[以前のG2評価48局・24,579参照](P6_SCREEN_RESULTS.md)とは別の実験である。
今回の最終holdout評価は0件。開発用の結果を独立した最終評価へ読み替えない。

入力コーパスは11,534件から280重複を除いた11,254件で、train8,381／val1,362／test1,511、family12／2／2。
valはterminal602件・bootstrap760件、testのValueはすべてbootstrapである。
今回のデータ採用判断はpilotだけを対象とし、本比較の教師十分性・代表性は未確認。
bootstrapへの一致は実勝敗の予測精度ではない。追加データの生成は今回行わない。

## HFの固定版と公開処理の失敗

学習stateの公開先は[research-training-state-v1](https://huggingface.co/voxelshogi/voxelshogi-research-training-state-v1)。
以下の各版は外部Linuxで全9ファイルのhashと復元を検証した。

| 保存点 | 固定Hub revision |
|---|---|
| Full・384更新 | `1a7550e252294b6400e99640df45117bf7e5bc50` |
| Full・1,024更新 | `bdf9ee7b1a529a76bafd665ffbb68546e0f86db3` |
| Geometry・384更新 | `32c725706f3b6c1888e95ac60587ef8379b58a58` |
| Geometry・1,024更新 | `a9223c8d932963aaed98ca7353b8174800f27cd5` |

元の結果公開は`ValueError`で失敗した。保存済みのRust再生済みsummaryと、独立に再計算したmetadata summaryを
全体比較した際、両構造とも`verification_scope`の説明文だけが異なっていた。数値・キー集合の違いは観測されていない。
修正用ブランチを作ったところで停止し、修正コード・テスト・PRはまだない。

結果の消失を防ぐ別の退避処理で、原本112ファイルのJSON／JSONLを6,363レコードへ保存した。
**[退避結果の固定版](https://huggingface.co/datasets/voxelshogi/voxelshogi-research-pilot-results-v1/tree/a98f69f6aec4b54cd247e555f4afd9363d339f02)**は
配布7ファイルすべてを外部Linuxで照合済み。
release SHA-256は`ce2a24a6afa67be6644704e0f967412dbcaba66250bd9a9a8f831f19bc835bc8`。
元の公開失敗・科学source・期限を保持し、`preservation_only_recovery=true`、`pipeline_complete=false`のままである。
退避の成功を元workflow全体の成功へ変更していない。

全公開先はvoxelshogi配下、public/manual、Community OFF、Card付き。
結果datasetはCC-BY-4.0、学習stateはApache-2.0。manualはダウンロード申請の手動承認を意味する。
データとcheckpointは外部Linuxから直接転送し、Macには小さい実行記録・receipt・台帳だけを回収した。

## ブラウザ・コード・未完了の範囲

- 4構造のGPU／ONNX・batch1／4／8／16の16組は[実測済み](P6_OPERATOR_RESULTS.md)。
  未学習Mの[ブラウザ8ケース](P6_BROWSER_RESULTS.md)はWASM3／4成功。Axial WASMと全WebGPUは180秒上限。
  段階記録の修正後の再測定は未実施で、WebGPU一般の非対応と断定しない。
- main `5619d18`までに、M読込・公開契約・最終manifest組立・3形式評価driver・module子process所有確認を統合済み。
  実際の最終72局、学習済みMの推論パッケージ公開、Web catalog登録は行っていない。
- [PR #175](https://github.com/ayutaz/voxelshogi/pull/175)は配布42ファイルのstaging、
  [PR #176](https://github.com/ayutaz/voxelshogi/pull/176)は開発時参照集合の最終評価監査。
  13:21 JSTの取得時点で両方ともCIキュー待ち・未マージ。軽量テストの成功をLinux結合試験の成功とは扱わない。
- [文書PR #174](https://github.com/ayutaz/voxelshogi/pull/174)へ今回の停止・実績・文書点検を反映する。
  同時点のmain CI／Securityもキュー待ち。必須・関連CIが未完了なら取り込まない。

## 予算・回収・停止

承認総額US$200、40予約US$174、未予約US$26。Phase6配分44のうち予約18。
保守的予約上限であり、確定請求・消費実績・providerクレジット残高ではない。失敗分の予約も取り消さない。
共通state upload台帳は過去履歴を保持して25予約・3,902,326,849 bytes、自主上限32GiB。
これは累積転送予約であり、HFの実使用量や有料ストレージ購入ではない。

停止済み6実行経路のstate／保存receiptと後続の検証済み結果退避を照合し、回収記録・共通台帳を永続化した。
collection SHA-256は`4f0b32ba883b84a5ea98d26449b304bde7ca266e8e4e240386633f254231ee10`。
回収reviewも`job_complete=false`・`phase6_complete=false`を保持する。
独立期限workflow [43124560476](https://github.com/ayutaz/voxelshogi/actions/runs/43124560476)は12:45 JSTに成功終了。
Vast APIで実機`60282417`の不在を確認したが、local controllerの削除受付receiptはないため、
canonical retirementの`complete=false`を書き換えない。実機の不在とcontroller receiptの完備は別の証拠である。

**13:22 JSTの読取再確認**：Vastの全inventoryでVoxelShogi所有実機0、
CloudRiftのInitializing／Active／Deactivating対象でVoxelShogi所有実機0。
全storage／volume種別を新たに列挙した確認ではない。今回の新規レンタル・予約・学習・公開送信は0。

## 再開候補と技術記事への引継ぎ

再開を指示されるまで自動実行しない。現在の区切りは、動く既存デモと学習・評価基盤の技術成果である。
旧「あと2〜4日」は本比較前の暫定作業見積もりであり、停止後の納期約束には使わない。

| 再開候補 | 目的と残る完了条件 |
|---|---|
| 公開失敗の修正 | 集計値と検証範囲の意味を保った照合へ修正し、TDD・変異・Linux検証を通す。元の失敗履歴は残す |
| ブラウザ・教師判断 | 8ケースの失敗段階を特定し、WASM4／4とWebGPUの実対応範囲を記録。教師の十分性と必要な追加分布を判断 |
| 本比較 | 共通計算量・十分な更新数・データ・費用を事前固定し、4構造×3 seed＝12 runと不確実性・負の結果を報告 |
| M配布 | 同じ元重みの3形式を各24局、計72局で評価・監査し、HF固定版・Web・同じbytesの実機操作を確認 |
| 観戦・正式公開 | 同一棋譜の2表示案、対応実端末セル各60分、人間対AI先後、公開hash／E2E、再現・復旧手順を確認 |

デモと記事で説明できる範囲は[案内](DEMO_AND_ARTICLE.md)、評価値の比較上の注意は[BENCHMARKS](BENCHMARKS.md)、
全Markdownの点検範囲は[文書点検記録](DOCUMENTATION_AUDIT_20261112.md)を参照する。
証拠元はGit管理外の`runs/p6/research-pilot3-control/`にある`outcomes-1794454499.json`、
`preservation-recovery-receipt.json`、`publication-summary-difference.json`、`collection-review.json`、
`reconstructed-terminal-provenance.json`、`manual-preserved-retirement.json`、および共通予算台帳。
13:21 JSTのGitHub一括取得と13:22 JSTのprovider読取も小さい記録として保持する。
固定されたHFの全bytes照合は外部Linuxでの当時の検証であり、今回Macで再ダウンロードした記録ではない。
