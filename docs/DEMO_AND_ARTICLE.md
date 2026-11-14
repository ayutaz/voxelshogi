# 公開デモと技術記事への案内

2026-11-15。動くSデモと技術検証を現段階の成果とし、追加学習は[一時停止](RESEARCH_CHECKPOINT_20261112.md)する。観戦画面と人間対AIの入口を再設計し、[公開版の検証](ARENA_RELEASE_VALIDATION.md)を更新した。
本書は記事の材料と確認範囲の整理であり、記事の執筆・外部投稿・公開の実施記録ではない。

Webの効果音は[移動・捕獲・節目の音と検証記録](WEB_SOUND_VALIDATION.md)を参照する。動画の撮影sourceは引き続き`7b364c9`で、Webへ後から追加したSEは既存動画へ再収録していない。納品動画は[オリジナルBGM付き](DEMO_BGM.md)を使用する。

## 既存デモを試す

1. [Arena](https://voxelshogi.yousan-apps.workers.dev)を開き、「観戦を開始」を押す。モデル取得なしでNormal同士を眺められる。
   停止・1手送り・速度変更、2D／3Dを使って盤面を追える。「AIと対戦」から先後と相手AIを選んで自分でも指せる。
2. 学習済みSは「AIと対戦」から選ぶ。申請・ログイン・手動ダウンロードは不要で、FP32／FP16重み／INT8重みを選べる。
   [HFの短いモデル説明](https://huggingface.co/voxelshogi/voxelshogi-transformer-s)・[取得条件の変更と公開確認の状態](PUBLIC_S_ACCESS.md)を参照する。
3. [推論ラボ](https://voxelshogi.yousan-apps.workers.dev/?models=1)は未学習モデルの3形式比較である。
   学習済みSの強さを示す画面として紹介しない。

Mの少量学習checkpointは研究保存物であり、Webで読み込む配布パッケージではない。
S推論用だけは2026-11-14の指示で取得ゲートを解除済み。データ・state・Mのmanual gateは維持し、別配布先で迂回しない。
既存の実機検証は[M6完了記録](M6_COMPLETION.md)、今回未実施の確認は[停止時点](RESEARCH_CHECKPOINT_20261112.md)を参照する。
公開source `7b364c9`のUI 53 E2E・カメラ3回・未学習モデル6件に加え、公開S3形式の対戦を含む5件も成功した。[更新済みの動画と証拠](PUBLIC_S_RELEASE_VALIDATION.md)を使う。実スマートフォンの操作は未確認である。

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
