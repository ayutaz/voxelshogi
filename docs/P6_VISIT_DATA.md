# 監査済み自己対局から訪問分布学習への接続

**2026-11-12・一時停止**：既存Sの公開デモと、Mの少量2 run・48局評価を現段階の成果とする。
本比較12 run・MのWeb配布・観戦表示2案／実端末各60分は未完了のまま停止する。
追加GPU・生成・学習を自動再開しない。[停止時点の結果と固定HF版](RESEARCH_CHECKPOINT_20261112.md)を現在の確認元とし、
以下の旧「現在」「次」「予算」は対象時点の記録、実行コマンドは再開後の手順として読む。

2026-11-05。[採用前監査](P6_CORPUS_ADMISSION.md)と[固定更新数の学習](P6_VISIT_TRAINING.md)を接続するAPI。
実データの採用・GPU学習・新しいHF公開の完了記録ではない。

`research_visit_data.encode_corpus`は外部Linuxで元の全世代・全episodeの監査を再実行し、
事前に固定した監査結果のSHA-256と一致することを要求する。
監査のsource／protocol／既存保護／凍結screenのhash、採用可能判定、train／val／testの
選択ID・順序・件数・family・入力の非重複を照合する。既存の保護集合を減らさない。

その後、元の全episodeをRustで再生し、選んだtrain／valだけを特徴量配列へ変換する。
選択ID・family・canonical input・ply・盤面・手番・合法手と再生結果の一致を要求し、
Policyの訪問分布とValueの出所・値をそのままコピーする。単一argmaxへの変換はしない。
testは分割監査の対象に含むが、学習consumerへ渡す特徴量配列にはしない。
開始前・終了後にsourceと監査のhashを確認し、途中で変わったsourceを採用しない。

返す`VisitCorpus`はtrain／valと監査hashを持つ。各splitには元manifest／protocol／
選択集合と選択IDのhashを添え、特徴量全byte・教師・来歴のdigestを確認する。
同じ固定sourceから再生成すれば、保存再開の入力bindingと照合できる。
初期の特徴量byte上限は2GiBで、総process RSSの上限ではない。変更する場合は、
実データ件数と実機のRAM・RSS制限を踏まえて実行前に固定する。

実行driverは固定HF版の全hashと公開設定を先に検証し、教師品質と分布の判断、
実選択数・不足と追加生成の要否、元HF revision・監査・選択IDを公開記録へ残す必要がある。
旧Sが既に学習した自己対局データから切り出したval／testを、Sの未見評価とは呼ばない。
bootstrapや手数打切りを観測した勝敗・引分教師へ変更しない。

軽量テストは手書きの6件で、train／valだけの選択、正確なbyte境界、
hashを再計算した不正な分割・重複も拒否することを確認する。
Linux結合試験は小さい実Rust履歴と合成visit／監査portを使い、正しいIDへの特徴量の対応、
全分布とValue由来の保持、途中source変更の拒否を確認する。実候補全件の監査とは区別する。
