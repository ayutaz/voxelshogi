# 公開デモと技術記事への案内

2026-11-12。動く既存デモと技術検証を現段階の成果とし、追加学習は[一時停止](RESEARCH_CHECKPOINT_20261112.md)する。
本書は記事の材料と確認範囲の整理であり、記事の執筆・外部投稿・公開の実施記録ではない。

## 既存デモを試す

1. [Arena](https://voxelshogi.yousan-apps.workers.dev)を開き、両AIをEasy／Normalにして観戦する。
   停止・1手送り・速度変更、2D／3Dを使って盤面を追える。人間対AIも提供する。
2. 学習済みSを試す場合は[HF](https://huggingface.co/voxelshogi/voxelshogi-transformer-s)で取得申請し、
   承認後に画面が指定する固定revisionのフォルダー全体を取得して読み込む。
   両AIでFP32／FP16重み／INT8重みとbackendを選べる。[取得手順・対応範囲](M6_PORTABLE.md)を確認する。
3. [推論ラボ](https://voxelshogi.yousan-apps.workers.dev/?models=1)は未学習モデルの3形式比較である。
   学習済みSの強さを示す画面として紹介しない。

Mの少量学習checkpointは研究保存物であり、Webで読み込む配布パッケージではない。
HFのmanual gateは維持し、記事や別サイトへモデルを転載して取得申請を迂回しない。
既存の実機検証は[M6完了記録](M6_COMPLETION.md)、今回未実施の確認は[停止時点](RESEARCH_CHECKPOINT_20261112.md)を参照する。
今回の文書更新では公開E2E・現在の配信SHA・実スマートフォンの動作を新たに検証していない。

## 記事で説明できること

| 題材 | 根拠 |
|---|---|
| RustのルールをWASM／Pythonから共用し、三次元将棋を観戦する | [エンジン](GAME_ENGINE.md)・[ルール](RULESET.md)・[観戦](M6_ARENA.md) |
| 探索教師から学習し、実際の変換版をブラウザで選ぶ | [S学習・配布](M6_COMPLETION.md)・[変換版の結果](M6_PORTABLE.md) |
| 外部GPUで学習し、HFへ直接保存して別実機で再開する | [自己対局3世代](P5_2_COMPLETION.md)・[実1／2／4GPU](P5_4_RESULTS.md) |
| Mモデルの少量学習と再開一致・48局の評価、公開失敗からの退避 | [停止時点の結果・固定HF版](RESEARCH_CHECKPOINT_20261112.md) |
| 動作成功と棋力向上を分けて検証する | [測定値と制約](BENCHMARKS.md)・[評価方針](POST_M6_PLAN.md) |

「Rust／WASMと外部GPUで三次元将棋AIを動かす：学習・保存再開・ブラウザ観戦まで」を題材にできる。
棋力向上、4構造の同条件本比較、Mの3形式公開、全端末対応を達成した記事にはしない。
図や画面を用意する場合も、Sデモ・未学習推論ラボ・M研究結果をそれぞれ識別する。

## 再現・開発へ進む入口

- Web起動と参加方法：[README](../README.md)・[開発手順](../CONTRIBUTING.md)。
- 固定データと公開条件：[M4完了](M4_COMPLETION.md)・[HF公開](HF_PUBLICATION.md)。
- 現在地と将来の研究：[STATUS](STATUS.md)・[ROADMAP](ROADMAP.md)。

Macは編集・読取・軽量確認のみ。学習・生成・計測は再開指示後に承認済み外部Linuxで行う。
人間同士の対局・マルチプレイは対象にしない。
