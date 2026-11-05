# P6：学習候補データの分割・保護・採用前監査

2026-11-05。[全1〜6の実行計画](P6_EXECUTION_PLAN.md)の少量2 run・本比較に先立ち、共通データを調整結果から独立させるための契約。
コードと小さい検証の準備であり、実候補全件の監査・教師採用・新しいデータ公開・学習の完了ではない。

## 既存保護を維持する

既存の固定indexはM4／M6の全split、P5-0評価、P5-1 holdoutを含む116,008入力である。
新しい学習のためにM4のtrainだけをこの集合から差し引いたり、古いholdoutの役割を変えたりしない。
そのため、M4 trainを無条件に新しいP6学習へ再投入する計画にはしない。

最初の候補は、固定公開済みのP5自己対局の全世代・全episodeと、保持されたPUCT visits／明示されたValue由来である。
M4のhard-label fitterへvisit分布を単一argmaxとして流し込まない。
候補の全件監査とteacher品質を確認した後、visit損失・新しいdataset binding・固定val評価・保存再開をそろえて実学習へ接続する。
既存Sはこれらの自己対局位置を既に学習しているため、新しく分けたval/testをSの未見評価とは呼ばない。
Mの構造比較は同じデータ・分割・由来の条件を明示し、一般棋力は別の凍結した最終評価で検証する。

データが不足する場合は、必要な局面層・新しいfamily数・教師の計算量・保存費用を見積もり、既存保護と最終評価12 rootを維持して追加生成する。
P5-1の未採用教師を、件数を増やすために混ぜない。

## 分割と重複の契約

`training.research_corpus.family_partition`はside-canonicalな開始rootのinput IDを単位にする。
同じ開始rootの異なる世代・episodeは必ず同じsplitへ置く。
seed67011とSHA-256(`p6-family-split-v1:<seed>:<family>`)の昇順で、最後の4 familyをval2／test2へ固定し、残りをtrainにする。
既存16開始familyがすべて別rootなら12／2／2になる。実際のfamily数はRustで列挙してから記録する。
ハッシュの順位を、モデルの損失・勝敗や採用件数を見てから変えない。

`admit_metadata`は次の順に処理する。

1. 既存保護と新しい最終評価12 root、与えた開発用保護の和集合に含まれる全sampleを除く。
2. 同じcanonical inputがsplit間で重なる場合はtest＞val＞trainの固定優先順位で、低い側を除く。
3. 残ったsplit内で同じinputが重複する場合は、stable sample IDが辞書順で最小の1件を残す。ラベル・勝敗を選択に使わない。
4. raw、保護除外、split間除外、同split重複除外、採用の各件数、family数、Value由来、絶対ply区間を記録する。

metadataのreadinessはtrain256／val64／test64 sample以上、かつ各splitで2 family以上。
これは小さい試験学習を始められる件数のscreenで、十分な教師品質・代表性・棋力を証明しない。
全件除外や不足も件数付きの`usable_for_pilot=false`として残し、空の結果を成功へ変えない。
Valueのterminal／bootstrapを保持し、打切りを自然引分へ変換しない。

## 実データのLinux監査

`audit_selfplay_corpus(folder, protocol, protection, screen, screen_sha256=...)`を外部Linuxで使う。
公開ハーネスで固定revisionの全ファイルを照合した取得元を渡すことが前提で、同API自体はHubの取得・gate設定の検証を代行しない。

- 元datasetのschema・全episode・source／model／actor／訪問数・Value計算を既存のRust再生verifierで検証する。
- 全sampleをもう一度履歴順に列挙し、位置・手番・plyとcanonical input IDを記録する。最後の世代や一部windowだけを候補全体としない。
- 48局比較で固定したconfigのbytes／SHA、conditions hash、全24 rootのRust再生・一意性、最終12 rootの保護リストを確認する。NN推論は行わない。
- 元manifest・episode Parquet・保護file・screen config・protocolが列挙中に変わっていないことを確認し、検証後の別ファイルへ新hashを付け直して承認しない。

このAPIの開発用追加保護は凍結した12開発rootである。別の新規データを採用する際は、今回の全実参照／スコア対象入力との全件照合も別途必要であり、root保護だけで全枝の非重複を主張しない。
実監査・選択したdataset revision・全入力hash・除外数・教師の分布と品質判断をそろえるまで、readinessだけで2 runを始めない。
Macではhand-authored metadataとfake portのみを確認し、実コーパス・モデル・feature cacheを実行／中継しない。
