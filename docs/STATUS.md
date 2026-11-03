# 現在の状態と文書の案内

2026-11-04 JST。[P5-2の自己対局3世代・HF保存・別VM継続](P5_2_COMPLETION.md)と文書PR #116の統合後CIまで確認済み。**Phase5全体や棋力改善の完了を意味しない。** 今回は[次の実行計画](P5_3_PLAN.md)を更新し、GPU・対局・学習は停止を維持する。

## 現在使えるもの

| 対象 | 状態と確認元 |
|---|---|
| 公開Web | [標準1王のAI観戦・人間対AI](https://voxelshogi.yousan-apps.workers.dev)。Easy／Normal、取得済みM6学習モデル3形式、2D／3D、停止・1手送り・速度変更 |
| ルールと探索 | Rust共通エンジンをWASM／Pythonから利用。[標準ルール](RULESET.md)・[M1検証](M1_VALIDATION.md)。人間同士の対局・マルチプレイは対象外 |
| M4データ | 1,800局、有効113,321局面・探索教師36,894件。全検証・全再生成、HF固定revision全1,831対象ファイル照合済み。[完了記録](M4_COMPLETION.md) |
| M5互換性 | 固定した改定後3局145手が一致。全棋譜の完全互換は主張しない。[対象と制約](M5_PLAN.md) |
| M6／Phase4 | RTX5090で3epoch・22,413更新、保存再開・HF復旧、固定評価と3形式公開、実機48条件・40切替・GPU着手・7 E2Eを確認。[完了記録](M6_COMPLETION.md) |
| P5-0 | 開発評価32局・全手再生・凍結コーパス照合を完了。棋力改善の証拠ではない。[固定した結果](P5_PILOT.md) |
| P5-1 | 今回の8対局・35局面候補は採用条件未達で学習不採用。追加教師検証は保留。holdout全履歴の入力IDだけを後続学習から保護。[判断](P5_NEXT_EXECUTION.md) |
| P5-2 | 48対局・3世代の実更新と系譜、全手再生・入力byte hash、HF両公開計3対、別の所有VMでの後続世代を確認。[結果と限界](P5_2_COMPLETION.md) |

公開画面の9王比較室と旧URLの導線は撤去済み。9王の正式採用は行っておらず、標準1王を維持する。[比較当時の研究記録](NINE_KINGS_EXPERIMENT.md)は保持する。

## 公開物・実行環境・費用

M6のFP32・FP16重み／FP32計算・INT8重み／FP32計算は、HFから取得した実ファイルをブラウザで選んで試せる。[取得と実機の対応範囲](M6_PORTABLE.md)。推論ラボは未学習モデルの技術デモであり、学習済みM6と区別する。[M3検証](M3_VALIDATION.md)のFP16×M1 WebGPU基準未達も保持する。

P5-2のデータ／再開状態・保護index・集計reportは、[完了記録の固定revision一覧](P5_2_COMPLETION.md)から取得する。public/manualのダウンロード申請・Community OFF・Card・承認済みlicenseを維持する。データとcheckpointは外部Linuxから直接転送し、Macに中継しない。今回の自己対局stateをWebの変換済みモデルとして扱わない。

最終の所有課金実機・volumeは2026-11-03 17:14 UTCの確認で0。保守的予約は全体US$85／100、Phase5 US$24／配分24、Phase6配分15。追加US$100は未適用。Phase5の配分空きは0で、次回の見積もりではPhase6配分と未予約15を二重計上せず、配分変更または条件付き追加枠の適用をledgerへ記録する。[費用と停止の証拠](P5_2_COMPLETION.md)。Vastの利用可能クレジットは`credit`で確認し、`balance=0`をクレジット不足とする誤りは訂正済み。

Pythonは3.14を基本に、依存未対応時のみ3.13。Macは編集・読み取り・軽量確認、探索・生成・性能計測・学習は承認済みVast.ai／CloudRift、重い回帰はGitHub Actionsで行う。

## 残る課題と停止後の判断

- 棋力改善は未確認。P5-3ではM6／M1／各自己対局世代を固定条件で比較し、勝敗・引分・cutoffと不確実性を報告する。
- 1→2→4GPUの効率・費用・再開、Transformer-Mと構造・複数seed比較は未実施。単GPUの速度をそのまま流用しない。
- 新しい自己対局モデルの固定評価・変換・実機検証・Web採用、モバイル／低性能端末、長時間観戦と表示の理解しやすさは後続の課題。
- 本条件の結果から、必要なら終盤分布・教師・探索・cutoff率を診断する。弱いモデルのまま大きい学習へ自動拡大しない。

次の順序は条件・不足実装の整備→8局の時間試行→4モデル各30局とM1対照30局、合計150局の開発用比較。現行runnerの合法argmaxを共通方式とし、PUCT全体の強さとは分ける。実行・予算・判断の詳細は[P5-3計画](P5_3_PLAN.md)、全体の残課題は[全体計画](OVERALL_PLAN.md)、各フェーズの目的は[ROADMAP](ROADMAP.md)を参照する。

## 過去の課題（C0で対応済み）

M3着手前に確認した3D操作中の探索テストの観測競合は、入力イベント時点の状態を判定する方法へ修正した。[原因・独立検証・固定した公開確認](C0_VALIDATION.md)を保持する。

## 品質と履歴の確認元

ブランチ・PR・main保護・必須8チェックと通常mergeを維持する。PRは影響範囲の短い検証、main／定期は深い回帰を行う。[CIの実行範囲と実測](CI_PERFORMANCE.md)。文書だけのmain更新ではアプリを再配信しないため、公開SHAはmain HEADと異なることがある。[配信手順](DEPLOYMENT.md)。

数値修正の[PR #115](https://github.com/ayutaz/voxelshogi/pull/115)は必須8チェック・関連CI成功後に通常mergeした。統合main `7e44310`の[CI](https://github.com/ayutaz/voxelshogi/actions/runs/41652351549)ではFull Python unit and native integration、学習系変異4シャード、深いQuality・モデル結合・公開検証が成功。[Security](https://github.com/ayutaz/voxelshogi/actions/runs/41652351458)の全4言語も成功した。

完了記録・全Markdown点検の[PR #116](https://github.com/ayutaz/voxelshogi/pull/116)も必須8チェックと関連CI成功後に通常mergeした。統合main `4c84776`の[CI](https://github.com/ayutaz/voxelshogi/actions/runs/41682313021)・[Security](https://github.com/ayutaz/voxelshogi/actions/runs/41682313058)は成功。文書のみのため重い検証・再配信は対象外で、PR #115の実装検証を再実行した記録ではない。今回の計画更新の取り込み・CIは対応するPR／Actionsで確認する。

過去の実測値は取得日と対象SHAを保持する。現在の実装へ過去の計測速度を付け替えない。M0〜M6・C0・R0の固定記録は、[ROADMAP](ROADMAP.md)と各完了／検証文書を参照する。失敗・未達・未対応形式もそのまま保持し、P5-2の完了をPhase5全体や正式公開の達成へ拡張しない。
