# P6：4構造の教師あり学習と専用の再開状態

**2026-11-12・一時停止**：既存Sの公開デモと、Mの少量2 run・48局評価を現段階の成果とする。
本比較12 run・MのWeb配布・観戦表示2案／実端末各60分は未完了のまま停止する。
追加GPU・生成・学習を自動再開しない。[停止時点の結果と固定HF版](RESEARCH_CHECKPOINT_20261112.md)を現在の確認元とし、
以下の旧「現在」「次」「予算」は対象時点の記録、実行コマンドは再開後の手順として読む。

2026-11-05。これは学習・保存のコード契約であり、実M学習、12 run、本モデルの公開完了の記録ではない。
対象と完了条件は[P6実行計画](P6_EXECUTION_PLAN.md)の1〜6を維持する。

## 学習と再開

`training.research_fit.ResearchRunConfig`は既存の`RunConfig`を継承し、
`export.research_contract.ResearchConfig`の全寸法と専用schemaを`config`へ含める。
`fit_research(cache, folder, config=..., source_commit=..., resume=...)`は
指定した構造・seedで実モデルとAdamWを作り、既存の決定的FP32 fitterへ渡す。
構造、寸法、seed、epoch数、batch、optimizer、cache hash、source、実行環境が保存と再開のbindingに入る。
M6の固定モデルとloaderは変更しない。valでbestを選び、testを学習中に読まない。

Linux CIではside2・幅4の小さな4構造を実行し、全6更新と3更新後の中断→typed archive→別folder復元→後半3更新を比較する。
model、AdamW、乱数、進捗は完全一致を要求し、更新回数・実際のoptimizer state・学習ID列・val回数も確認する。
この小さなCPU検証を、M規模・CUDAの保存再開成功とは扱わない。
Macではmetadataとfake portの確認だけを行い、モデル構築前に実行を拒否する。

`epochs`が全体の学習scheduleで、`max_new_steps`は一度のattemptの中断上限である。
異なる構造で同じepoch数を指定しても、総FLOPsが等しいとは主張しない。
実GPUの演算・教師データthroughput・全工程の実測後、少量2 runと本比較の計算量・更新数・評価時点を事前固定する。
実行driverは、全corpus・val/test・新しい最終評価rootに対する役割を分けたデータ採用監査と費用上限を先にそろえる。
このAPIの存在だけを、未監査cacheで本比較を始める許可とはしない。

## HFの専用archive

`training.resume_archive`の`profile="research"`は
`voxelshogi-research-resume-archive-v1`を使い、研究用configと既存の教師label契約を検査する。
JSONとsafetensorsでlatestとval選択bestのmodel・optimizer・乱数・進捗・履歴を運ぶ。
通常モデル配布、旧M6、自己対局、分散学習のarchiveとはschemaとprofileを分ける。

公開は[HF公開ハーネス](HF_PUBLICATION.md)の
`artifact_role="research-training-state"`、
`voxelshogi/voxelshogi-research-training-state-v1`（model、Apache-2.0）を使う。
既存の研究実行・state公開承認を参照し、public/manual・Community OFF・4節のState Card・固定revision全hashを確認する。
通常重みrepoへのarchive混入と、旧S専用state repoへの代替公開は拒否する。
データとcheckpointは外部Linuxから直接送信し、Macへ中継しない。

MのAdamW状態はSの64MiB/fileを超えるため、この専用roleだけstate tensorを512MiB/file、archive全体を2GiBまで許す。
config等は64MiB/fileのままとし、旧stateとWeb推論packageの制限は変更しない。
これは1個のartifactの検査上限であり、共通upload ledgerの累積2GiBを増やす操作ではない。
実byte・保存点数・失敗時の退避を見積もって履歴を保持する版付き容量移行を行い、その後に実uploadを予約する。
HFの無料public枠とGPU課金のUS$200は別々に管理し、有料storageを購入しない。
