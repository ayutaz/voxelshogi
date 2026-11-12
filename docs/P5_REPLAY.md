# P5-2：完成episodeの検証とReplay Buffer

**2026-11-12・一時停止**：既存Sの公開デモと、Mの少量2 run・48局評価を現段階の成果とする。
本比較12 run・MのWeb配布・観戦表示2案／実端末各60分は未完了のまま停止する。
追加GPU・生成・学習を自動再開しない。[停止時点の結果と固定HF版](RESEARCH_CHECKPOINT_20261112.md)を現在の確認元とし、
以下の旧「現在」「次」「予算」は対象時点の記録、実行コマンドは再開後の手順として読む。

**2026-11-03 16:56:12 UTC・P5-2の終了と停止**：[本条件3世代48対局・HF保存・別VM後続世代](P5_2_COMPLETION.md)の結果を記録した。使用した所有課金資源は0。棋力改善・P5-3・DDP・Phase6は未完了であり、結果共有後に停止する。

2026-10-30。[自己対局Actor](P5_SELFPLAY.md)と学習の間を接続する。
生成・学習・モデル更新の複数世代、別実機での復旧は後続であり、この部品だけで
P5-2全体を完了としない。

## 目的とゴール

中断した対局、履歴を失った対局、別のmodel／source／設定から来たラベルを
学習へ入れない。完成対局の全手をRustで再生し、合法手・訪問分布・Valueの
出所と視点・再開位置を検証できることを、この部品の完了条件とする。

## episode v2

[Actor](../training/selfplay_actor.py)は`voxelshogi-selfplay-episode-v2`を返す。
v1の打切りラベルだけから元の推定値を逆算せず、v2では未割引の最終推定値・
その手番・履歴上のplyを`bootstrap`へ保存する。自然終局なら`bootstrap=null`。
元のmodel hash、source commit、設定とopening全履歴をepisode IDへ結ぶ。
v1を自動でv2と解釈しない。本条件48対局のHF公開・全hash照合と別VM継続は[P5-2完了記録](P5_2_COMPLETION.md)で確認する。

[verify_episode](../training/replay.py)へ、検証済みloaderと固定workloadから得た
期待source・model hash・ActorConfigを渡す。episode自身の宣言値を期待値にしない。

- openingをRustへ復元し、全ての実着手・局面・手番・合法手・sampleの欠落を確認する。
- Policyは合法な訪問回数から確率を再計算し、完了simulation数・seed付き着手と照合する。
- 自然終局はRustの結果から手番別の±1／0を計算する。打切りは最終の生推定値から
  視点・残り手数・discountを用いて独立に再計算し、引分教師へ変換しない。
- source／model／設定・episode ID、論理model呼出数、自然終局／打切りを照合する。

この検証はルールの全手再生とラベル算術・metadata整合性であり、ニューラル探索を
再実行して訪問回数や生推定値を独立測定した証拠とはしない。実際のモデルとruntimeの
対応、世代のlineage、splitと入力漏洩の検査は、後続の実行・学習coordinatorが担う。

## 保存と再開

ReplayBufferはrun ID・source・capacityを固定し、検証済みの完成episodeを
内容のSHA-256で指定するJSONへ保存する。buffer.jsonにslot順・hash・bytes・
期待model／設定と件数を保持し、このatomic indexをcommit点とする。

1. episodeを検証してimmutableファイルを保存する。
2. 連続した次のslotだけをindexへ登録し、その後にcursorが進む。
3. 保存後に停止してindex未登録なら、そのファイルは学習対象にしない。
   同じslot・内容の再試行では再利用し、競合する内容やslotの飛びを拒否する。
4. 再読み込みは全登録ファイルのhashとRust再生を検証する。直近capacity対局を
   学習windowとして選び、過去の登録ファイルは履歴・退避のため保持する。

capacityは選択windowの上限で、ディスク保持量の上限ではない。所有markerと
ファイルlockを使い、無関係な非空ディレクトリやsymlinkを上書きしない。
実データの保存・再生・学習・HF転送は外部Linuxで行う。Macでは手書きのfake portsと
小さい偽episodeのmetadataだけを検証する。

## 検証と残りの接続

手計算の生推定値0.25→先手の割引target−0.125、自然勝敗、prefixを含む履歴、
確率改変、外部bindingを偽る自己整合的metadata、hash改変、index直前の停止と
再開cursorを検証する。新規18変異を実行済み失敗で検出し、通常CIへ含める。
実Rustの打切り・詰み・11手の千日手prefixと保存復元はLinux統合テストで確認する。

Replayからの訪問分布／Value別batch、学習・モデル更新は[世代更新](P5_GENERATIONS.md)、
HFでの両公開は[公開トランザクション](P5_SELFPLAY_RELEASE.md)へ接続済み。
本条件の複数世代と別実機継続の結果を共有して停止し、世代比較は振り返り後に計画する。
