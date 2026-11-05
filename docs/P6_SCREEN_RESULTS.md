# P6評価補強：同じG2重みの48局比較

2026-11-05。[1〜6の実行計画](P6_EXECUTION_PLAN.md)の**1を完了**した。
48局と実NN参照24,579件のRust再生・全入力監査、別の最終評価12 root、固定HF版の全hash、所有課金資源0まで確認した。
4構造の本学習・新モデルWeb採用・Phase7は未完了で、全体の目標は継続する。
[機械可読の固定証拠](experiments/p6-screen-completion-2026-11-05.json)を併記する。

## 条件と観測結果

科学sourceは`763e1ce451cab2499c168309b9719d790018a421`。
G2重み`bf4fba2699d9d8578a821766b0fcaf861d56aab3effc296d87ec3a4e9408c8a4`を両armで固定し、
Torch CUDA FP32と同じRust M1（深さ3／20,000 nodes／TT4,096）で比較した。
12開始局面×先後2×argmax／PUCT32＝48局。2 processでarmを並行実行した。
PUCTは32 simulations・深さ64・cpuct1・noise／温度／木再利用なし。
駒配置・持ち駒を変えた戦術4件は同じ詰みfamily、少数駒4件も同じmaterial familyとして扱い、標準履歴4件と合わせて6 familyで集計する。

| modelの着手方法 | 対局 | 勝 | 敗 | 自然引分 | 打切り | 実NN参照 | 対局経過秒の合計 |
|---|---:|---:|---:|---:|---:|---:|---:|
| legal argmax | 24 | 0 | 4 | 3 | 17 | 720 | 644.186 |
| PUCT32 | 24 | 4 | 4 | 3 | 13 | 23,859 | 842.617 |

詰みfamilyの8局では、PUCTが4勝4敗、argmaxが0勝4敗4打切りだった。
標準履歴からの中盤8局は両armとも8打切りである。
打切りは得点不明であり、引分教師や確定0.5点には変換しない。
時間は2 armを並行実行した各対局の経過時間で、同じ計算量での比較や純GPU推論時間ではない。

PUCT−argmaxの勝率差は開始局面等重みで+16.67 percentage points、family等重みで+8.33 points。
6 family全体を単位にした10,000回のpaired bootstrap（seed314159）の95%区間は[0,25] points。
family等重みの得点差は打切りを含むため[-77.08,+85.42] pointsの上下限を残す。
**判断は追加測定**。同じ重みの詰み課題で探索の効果を観測したが、一般棋力や重みの改善、PUCTの自動採用は主張しない。

## 再生と入力の監査

- 全48棋譜と全24,579参照履歴をRustで再生し、盤面・手番・物理ID・side-canonicalなNN入力IDを照合した。PUCTの実対局経路外の枝も含む。
- M4全116,921行（unique113,321入力）、公開自己対局全3世代のraw11,534 sample、既存保護116,008入力と照合した。スコア対象経路と実NN参照を合わせたunique18,121入力について、物理・モデル入力とも重複0。
- 学習前に凍結した別の最終評価12 rootは、開発rootと合わせた24 rootの一意性、既存全corpusとの非重複、今回の全スコア対象経路・全NN参照との非重複を確認した。最終評価rootのNN参照は0。
- これは今回の開発比較と12 rootの監査で、将来の最終評価の全枝が未見である保証ではない。最終評価時にも全参照を監査する。

## HFの固定版

Datasetは[voxelshogi-research-screen-v1の固定revision](https://huggingface.co/datasets/voxelshogi/voxelshogi-research-screen-v1/tree/fa3728cc6d362ce6b278ec974bfb2dee13b1c363)。
public/manual・Community OFF、Dataset Cardの4節とCC-BY-4.0、埋め込んだ実行sourceのApache-2.0を確認した。
`matches.parquet`48行、`queries.parquet`24,579行、`roots.parquet`24行とconfig／manifest／validation／Card／licenseの計8ファイルを、外部Linuxから直接転送・固定revisionで全bytesとSHA-256照合した。
plan・receipt・3つのParquetのhashは固定証拠へ記録した。MacへのParquet・checkpoint中継は0。

## 準備・失敗・復旧を含む費用

修正後の科学処理は、固定HF入力のcache再検証2.365秒、3世代の復旧153.063秒、root準備1.792秒、事前全corpus監査180.893秒、48局845.189秒、全参照履歴の再生41.966秒、全入力／新最終root監査185.916秒だった。
HF公開だけの最終復旧は13.483秒。準備・失敗・待ち時間を含むVM作成要求→削除要求は4,982.299秒で、quoteによるcompute／disk見積もりはUS$0.767028。
転送料・確定invoiceと、予約上限US$3.50は別である。

次の失敗は削除せず保持した。

1. 最初の候補は貸出不可を作成前に検出。予約・VM作成とも0。
2. 所有VMの初回workerは、復旧APIへpathの代わりに検証結果のsetを渡して停止。対局・NN参照0で、19分33秒の取得cacheは保持した。
3. 同じVM・同じ期限・同じ科学条件の別出力で48局と監査を完了したが、公開wrapperがkeyword-only APIへdictを位置引数として渡して停止。最初の公開修復もPYTHONPATH不足でimport前に停止し、送信0。
4. 既存の完成Parquet・query trace hash・監査を再確認し、公開だけを復旧した。48局やNN参照の再計算、結果を見てからの局面差替え、新予約、期限延長は0。

Vast VM `59194137`の削除応答と全ページinventoryからの不在、Vast／CloudRiftの全プロジェクト所有資源0を確認した。
全34予約US$156／承認総枠200、未予約44を保持し、失敗予約の取消しや過去履歴の減額は行っていない。
新しいPhase6配分・累積state容量の実台帳移行は、この48局の完了には含めない。

## 次の段階

4構造と実Mの計測コードはPR #143／#145で統合済み。次は関連する統合CIの成功を確認し、[予算配分](P6_RESOURCE_BUDGET.md)を実台帳へ適用して単GPUの実M・ONNX・ブラウザ検証へ進む。
学習・再開対応の[PR #147](https://github.com/ayutaz/voxelshogi/pull/147)と容量移行の[PR #148](https://github.com/ayutaz/voxelshogi/pull/148)は検証中で、必須チェックと実行された関連CIがそろうまで取り込まない。
少量2 run、4構造×3 seedの本比較、FP32／FP16／INT8の実モデル配布、対応端末各60分のPhase7を残す。
