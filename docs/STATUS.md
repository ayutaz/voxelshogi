# 現在の状態と文書の案内

2026-11-14更新。**研究実行の停止を維持し、公開準備L1〜L6の実装を開始。**
追加GPU・研究データ生成・学習・Mの公開は行わない。[公開準備の進捗](PUBLIC_LAUNCH_PROGRESS.md)を参照する。
詳しい結果・固定HF版・未達項目は[停止時点の記録](RESEARCH_CHECKPOINT_20261112.md)を正とする。

## 公開準備の計画（2026-11-13）

[公開準備計画](PUBLIC_LAUNCH_PLAN.md)の各フェーズに目的・ゴール・完了条件を明記した。観戦の入口→着手追跡→狭幅と誤操作対策→同意制の棋譜保存→**L5デモ動画制作**→公開確認→X告知の順に進める提案。
レビュー文書PR #177は必須8件・関連CI成功後にmain `6d1e2a9`へ通常merge済み。
計画PR #178は必須・関連CI成功後、main `460c641`へ通常merge済み。L1〜L3のUI実装・軽量テストを進めており、公開URLでの確認は未完了。
L4の[同意制保存](GAME_DATA_COLLECTION.md)では受信API・専用D1・同意UIを実装し、実DBの合成保存と再送・競合・削除を確認。公開URLのHTTP確認は未完了で、実ユーザーの収集はまだ始めていない。
告知・動画の本制作は未着手。[デモ動画制作計画](DEMO_VIDEO_PLAN.md)で冒頭3秒の候補2本と15秒MP4本編1本を定義した。初手は「将棋、9層にした。」と実際の異層着手で見せる構成。
GPU・本比較・M配布・再学習は再開しない。
以前の14〜24時間という未計測の概算は納期の根拠に使わない。最初のUI変更後、保存API・動画を分け、実作業とCI待ちを区別して見積もり直す。

## 公開前のUI/UX・対局保存調査（2026-11-12）

ユーザー指定のClaude Codeで[公開前レビュー](PUBLIC_LAUNCH_REVIEW.md)を実施した。
初見の観戦開始・別層への着手追従・狭幅での盤面優先を改善候補とし、UIの修正はまだ行っていない。
[対局データ保存の調査](CLOUDFLARE_GAME_DATA_AUDIT.md)では、棋譜は端末内で保持・手動JSON保存、
現行Cloudflare versionのstorage bindingは0件で、サーバーへの棋譜自動保存は未実装と確認した。
現行配信sourceは`f3d2d66`でmainと異なるが、レビュー対象の主要UI・保存処理・wrangler設定は一致する。
X投稿・対局収集・追加学習・GPU利用・新デプロイは行っていない。研究実行の停止を維持する。

## 現在使えるもの

| 対象 | 状態と確認元 |
|---|---|
| 公開Arena | [標準1王のAI対AI観戦・人間対AI](https://voxelshogi.yousan-apps.workers.dev)。Easy／Normal、取得済みSの3形式、2D／3D、停止・1手送り・速度変更 |
| 未学習推論ラボ | [FP32／FP16／INT8の推論比較](https://voxelshogi.yousan-apps.workers.dev/?models=1)。学習済みSの観戦とは別 |
| 共通エンジン | Rustルール／探索をWASM／Pythonから利用。[標準ルール](RULESET.md)・[M1検証](M1_VALIDATION.md) |
| M4データ・M5 | 1,800局、有効113,321局面・探索教師36,894件の全検証・再生成・HF全1,831ファイル照合。[M4](M4_COMPLETION.md)。実棋譜は固定3局145手一致、完全互換は未検証。[M5](M5_PLAN.md) |
| S学習・公開 | 3epoch・22,413更新、保存再開・固定評価・3形式HF公開・実機48条件／40切替・7 E2E。[M6完了](M6_COMPLETION.md) |
| 自己対局・GPU | 3世代48対局・HF両公開・別VM後続世代。[P5-2](P5_2_COMPLETION.md)。実1／2／4GPU・各保存再開。[P5-4](P5_4_RESULTS.md) |
| 評価補強 | G2固定重みの48局・24,579 NN参照・全入力監査。[結果](P6_SCREEN_RESULTS.md) |
| Mの少量研究 | Full／Geometry各1,024更新、HF復元再開の完全一致、由来別val、開発48局・1,376 NN参照監査。[結果](RESEARCH_CHECKPOINT_20261112.md) |

Sの固定test教師手再現率約75.6%は、勝率ではない。Mの48局は各モデル0勝4敗4自然引分16打切り。
**動く学習済みモデルはあるが、強いと確認できた新モデルはまだない。**
9王比較室は公開画面から撤去済み。標準1王を維持し、対人・マルチプレイは対象外。

## 未完了として残すこと

| 対象 | 残る検証・作業 |
|---|---|
| 結果公開処理 | summaryの`verification_scope`不一致の修正。結果は別の退避でHF全hash照合済みだが、元workflow全体の成功にはしない |
| Mブラウザ | 未学習MのWASMは3／4成功。Axial WASMと全WebGPUは180秒上限。修正後の再測定と学習済みMの対応確認は未実施 |
| 本比較 | 教師十分性・共通計算量・十分な更新数・費用の固定、4構造×3 seed＝12 run、独立最終評価 |
| M配布 | 3形式計72局・全参照監査、HF推論パッケージ、Web登録・同じファイルの中断／切替／解放 |
| 観戦・正式公開 | 同じ棋譜の表示2案、対応実端末セル各60分、人間対AI先後、配信hash／E2E、再現・復旧手順 |

MのcheckpointはHFの研究保存物であり、現行Webの選択肢へ追加していない。
P5-3の[150局](P5_3_COMPARISON.md)に含まれた保護入力重複4件と、[12局診断](P5_3_DIAGNOSIS.md)の小標本の制約も保持する。
停止は未完了項目の撤回や、Phase6／7の完了ではない。

## 保存・費用・資源

結果datasetは[固定HF版](https://huggingface.co/datasets/voxelshogi/voxelshogi-research-pilot-results-v1/tree/a98f69f6aec4b54cd247e555f4afd9363d339f02)へ退避済み。
原本112ファイル・6,363レコード、配布7ファイルの全hashを外部Linuxで照合した。
元の公開失敗を保持し、`pipeline_complete=false`のまま。学習stateも4固定版で復元照合済み。
public/manual・Community OFF・Card・licenseを維持し、データ／checkpointをMacへ中継していない。

承認総額US$200、40予約US$174、未予約US$26。予約は実請求額・サービス残高ではない。
state upload台帳は25予約・3,902,326,849 bytes／自主上限32GiB。
13:22 JSTの読取再確認でVast所有実機0、CloudRiftのInitializing／Active／Deactivating対象所有実機0。
元controllerの削除受付receipt欠落と`complete=false`は保持し、不在確認とは区別する。

## Git・CI・公開状態

確認済みmainは`5619d18`。13:21 JSTの取得ではmain CI／SecurityとPR #174〜#176がキュー待ち。
実行時間の長さとrunner開始待ちは分ける。必須8件・関連CI未完了でmergeしない。
今回の文書更新は[PR #174](https://github.com/ayutaz/voxelshogi/pull/174)、配布stagingは[#175](https://github.com/ayutaz/voxelshogi/pull/175)、
開発参照監査は[#176](https://github.com/ayutaz/voxelshogi/pull/176)に分かれている。
統合済みコードだけで、実Mの最終評価・公開まで完了したとは扱わない。

最新の公開build metadataの軽い取得はHTTPError。今回、現在の配信SHA・新たな公開E2E・実機動作を検証したとは主張しない。
[既存の公開検証](M6_COMPLETION.md)と[公開手順](DEPLOYMENT.md)を参照する。
文書のみのmain更新では再デプロイを省略するため、main HEADと公開SHAは一致しない場合がある。

## 文書の読み方

- デモ・技術記事の入口：[案内](DEMO_AND_ARTICLE.md)。技術記事の執筆・外部投稿は未実施。
- 数値とその限界：[BENCHMARKS](BENCHMARKS.md)。
- 現在の方針と将来の候補：[全体計画](OVERALL_PLAN.md)・[ROADMAP](ROADMAP.md)。
- 旧計画の数量・完了条件：[全1〜6](P6_EXECUTION_PLAN.md)。自動再開の指示ではない。
- 全Markdownの分類と点検範囲：[今回の文書点検](DOCUMENTATION_AUDIT_20261112.md)。

対象日・source・HF revision付きの過去記録は当時の証拠として保持する。
古い「現在」「次」「未実行」や予算を現在へ付け替えない。以前のSTATUS全文はGit履歴から参照できる。

## 過去の課題（C0で対応済み）

M3着手前の3D操作中の探索テストの観測競合は、入力イベント時点の状態を判定する方法へ修正済み。
[原因・独立検証・固定した公開確認](C0_VALIDATION.md)を保持する。新しいMブラウザの時間上限とは別の課題である。
