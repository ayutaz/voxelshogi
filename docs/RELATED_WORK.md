# 関連研究・先行事例調査（Related Work）

- 外部資料の調査日: 2026-10-25。プロジェクト状況との照合: 2026-10-28
- 対象: VoxelShogi（9×9×9 三次元将棋プラットフォーム。ルールは shogitter.com「三次元将棋」rule id 166 に準拠）
- 方針:
  - 事実には出典 URL を付ける。リポジトリはファイル単位で確認した。
  - 一次情報で確かめられなかった点には **未確認** と書く。
  - shogitter のルール自体の分析は別ドキュメントの範囲なので、ここでは比較の基準として要約を使うだけにする。
  - VoxelShogi 本体は **Apache-2.0**（リポジトリ直下の `LICENSE` / `NOTICE`）。本プロジェクトの配布方針としてGPLのコードは取り込まない。ライセンスのないコードはコピーしない。

---

## 現在の実装との対応

本書の先行リポジトリ・論文・ライセンスは2026-10-25の調査記録であり、外部リポジトリの現況を継続保証するものではない。「採用」は当時の将来設計候補を含む。実装済みはRust／WASM／Web、M0、R0、標準1王のM1全幅探索、M2のWorker探索観戦、M3の未学習Transformerの変換・実機推論・公開まで。M4のPython境界・生成・全件検証・再生成と外部CPUの少量・並列試行も完了。その後、[M4の有効113,321局面の本生成・HF公開・資源終了](M4_COMPLETION.md)と[M5の固定3局の一致](M5_PLAN.md)まで完了した。学習済みモデル・自己対局学習は未実施。現在の確認元は [STATUS](STATUS.md)、進捗・採用予定は [ROADMAP](ROADMAP.md) を正とし、以下の研究候補や第三者コードを導入済みと扱わない。

R0では3つの9王ルールと現行1王をCPUの幅制限探索で比較し、同じ棋譜による観戦表示を公開した。[先行事例の調査](RULE_VARIANTS_RESEARCH.md)・[1,052局の実測](NINE_KINGS_EXPERIMENT.md)。M3では未学習Transformerを実装したが、Gumbel探索・DDP・棋力や構造比較の実証はまだ行っていない。M3検証用の未学習モデル3形式はユーザー承認済みのApache-2.0。M4自作合成データv1は承認済みCC-BY-4.0で公開した。学習済みモデルのライセンスは別途確定し、コードのライセンスを自動適用しない。

## 0. 要約

| 対象 | ライセンス | コード再利用 | アイデア再利用 | 判定 |
|---|---|---|---|---|
| tomikan1208-code/3D_shogi | **なし（全権利留保）** | **不可** | 可（UI・高速化の方針） | 参考のみ |
| m-tatsuto/3dshogi（空将） | MIT 文面の `MITL` ファイル（著作権者表記が不整合、GitHub 上は未検出） | 原則しない | 可（層テーブル・十字ガイド線） | 参考のみ |
| guille0/space-chess | MIT（3D モデルは別ライセンス） | 可能だが不要 | 汎用盤サイズ設定 | 参考のみ |
| AlphaZero / MuZero | 論文 | – | 自己対戦・PUCT・空間的な行動表現 | **採用（基盤）** |
| Gumbel AlphaZero/MuZero | 論文（実装: mctx Apache-2.0 / LightZero Apache-2.0） | 実装参照可 | 少ないシミュレーション数での探索 | **採用（第一候補）** |
| Sampled MuZero（arXiv 2104.06303） | 論文 | – | 巨大な行動空間でのサンプリング | 予備案 |
| KataGo | MIT 系（独自表記） | 参照可 | Playout cap randomization、補助ヘッド、global pooling | **採用** |
| Lc0 BT 系 / Chessformer（arXiv 2605.19091） | lc0 は GPL-3.0、論文は CC BY 4.0 | lc0 のコードは不可 | マス=トークン、from-to 注意ポリシーヘッド、幾何注意バイアス | **採用（中核）** |
| Searchless chess（DeepMind） | Apache-2.0、重みは CC-BY 4.0 | 参照可 | エンジン注釈データの蒸留、価値の bin 分類 | 一部採用 |
| DeepNash | 論文 | – | 不完全情報ゲーム向け | 不採用 |
| NNUE（YaneuraOu 等） | GPL-3.0 | 不可 | 差分更新評価 | 当面は不採用 |
| takedarts/gokaku | MIT（v2.2 以降。v2.1 以前は GPL-3.0） | 参照可 | Gumbel と KataGo 流の RL、ランダム棋譜からの学習 | 参考（強く推奨） |
| foundryside-dev/keisei | MIT | 参照可 | Rust エンジン + PyO3 + PPO、W/D/L ヘッド | 参考 |

**要点**
1. 「9×9×9 の三次元将棋を実装した」こと自体は新規ではない（2013 年の空将、2026 年の tomikan 版がある）。ただし両者とも**駒の動きと初期配置が shogitter 166 と大きく異なる**ので、棋譜もモデルも互換性はない。
2. tomikan 版は MaskablePPO + 3D-CNN で学習を試みている。しかし**ライセンスがなく、学習済み重みも強さの評価結果も公開されていない**。
3. shogitter の飛車・角は「レイ（直線）」ではなく領域型の移動をする。このため、相対方向で手を符号化する方式（AlphaZero 型の 139 平面、tomikan 型の 160 デルタ）は不向き。**Lc0/Chessformer 型の from-to 注意ポリシーヘッド**（729×729 のロジット行列）が自然に合う。
4. Chessformer の GAB（Lc0 の smolgen 系）をそのまま 729 トークンに広げると、出力射影が 729² ≈ 53 万次元になる。**軸ごとに分解するか、静的な 3D 相対バイアスにする必要がある**。ここが VoxelShogi の比較研究の主題になる。

---

## 1. 三次元将棋の先行実装

### 1.1 tomikan1208-code/3D_shogi

URL: https://github.com/tomikan1208-code/3D_shogi

**概要**
- 2026-03-21 に初コミット、最終 push は 2026-10-18。コミットは 4 件、スター 0、README なし（`gh api repos/tomikan1208-code/3D_shogi` で確認）。
- 構成:
  - ブラウザ版: Three.js による 3D 表示、2D 断面表示、ローカル対戦、Socket.io のオンライン対戦、AI 同士の観戦。
  - Python 学習環境: Gymnasium + sb3-contrib MaskablePPO。
  - 高速化の試作: C++ コア（pybind11）、GPU テンソル化。
  - 出典: [FOLDER_STRUCTURE.md](https://github.com/tomikan1208-code/3D_shogi/blob/master/FOLDER_STRUCTURE.md)
- ルールは JS（`js/board.js`, `js/pieces.js`）、Python（`ai_training/shogi_env.py`）、C++（`ai_training/cpp_core/shogi3d_core.cpp`）に**三重に実装**されている。ドキュメント自身も「フロント側ルールと学習環境側ルールがずれると、AIの手が不正になる」と注意している。

**ライセンス**
- **LICENSE ファイルはない**。GitHub API の `license` も `null`。
- **ライセンスがない = all rights reserved（全権利留保）。コードはコピーしない。** 初期配置の表やルール文書の文章も転載しない。

**ルール**（出典: [rules.md](https://github.com/tomikan1208-code/3D_shogi/blob/master/rules.md)、[js/pieces.js](https://github.com/tomikan1208-code/3D_shogi/blob/master/js/pieces.js)、[js/board.js](https://github.com/tomikan1208-code/3D_shogi/blob/master/js/board.js)）
- 座標:
  - x = 歩が並ぶ方向（筋）
  - y = 両玉を結ぶ方向（前後）
  - z = 高さ
  - 先手は y=8 側（0 始まり）から −y 方向へ進む。つまり shogitter の x=筋、y=段、z=層、先手前方 −y と同じ向きに対応づけられる。
- 初期配置（片側 **170 枚**）:
  - 最奥層: 9×9 の同心配置。香 32（外周）、桂 24、内側 5×5 に銀 12・金 12（市松状の混在パターン）、玉 1。
  - 第 2 層: 角 4・飛 4（中心から離れた 8 点）。
  - 第 3 層: 歩 81。
- 成り: 敵陣 3 段で成れる。成ると歩・香・桂・銀は金、飛は竜（飛 + 王）、角は馬（角 + 王）。行き所のない駒は強制的に成る（`shogi_env.py` の `forced_promote`）。
- 二歩は同じ (x, z) 列で判定している。**打ち歩詰めの判定は env 内に見当たらなかった**（grep で確認したのみ。正確には未確認）。
- 終局: 詰み、王の捕獲（`ou_capture`）、千日手（同一局面 4 回で打ち切り、学習上はペナルティ）、10000 手。

**shogitter 166 との差分**（shogitter 側は依頼者による分析の要約。tomikan の座標は shogitter 座標に読み替えて記述）

| 駒 | shogitter 166 | tomikan 版 | 差異 |
|---|---|---|---|
| 歩 | 同じ層で前 1 | (0,前,0) の 1 マス | 同じ |
| 香 | 同じ層で前方へ走る | 前方へ走る | 同じ |
| 桂 | (±1, 前2, ±1) の 4 マス（x と z を同時に ±1、「×」型） | (±1,前2,0) と (0,前2,±1) の 4 マス（「＋」型） | **異なる** |
| 銀 | 前方 9 + 上下層の斜め後ろ 4 = 13 | 前方 9 + 後方 3×3 の中央を除く 8 = **17** | **異なる** |
| 金 | 26 近傍から同じ層の斜め後ろ 2 と上下層の後ろ列 3+3 を除いた **18**（= 前方 9 + 同じ y 面 8 + 真後ろ 1） | 前方 9 + 同じ y 面 8 + 真後ろ 1 = 18 | **同じ集合** |
| 王 | 26 近傍 | 26 近傍 | 同じ |
| 飛 | 原点と少なくとも 1 座標を共有する任意のマス（直方体内に駒があると遮られる） | 6 方向のレイのみ | **大きく異なる**（tomikan 版は部分集合） |
| 角 | 2 軸を同じ距離 a 動き、残り 1 軸は ≤ a（台形領域で遮られる） | 平面斜めの 12 方向レイのみ（立体対角 (±1,±1,±1) は含まない） | **大きく異なる**（tomikan 版は第 3 軸 = 0 の特殊ケースだけ） |
| 初期配置 | 片側 186 枚。7 段目に歩 81、8 段目は 7×7 の環に飛 12 + 角 12、9 段目は玉/金/銀/桂/香の同心正方形 | 片側 170 枚。上記のとおり | **異なる** |

→ 棋譜、学習データ、モデルに**互換性はない**。「三次元将棋」という名前は同じでも別のゲームとして扱う。

**AI**（出典: [ai_training/shogi_env.py](https://github.com/tomikan1208-code/3D_shogi/blob/master/ai_training/shogi_env.py)、[model.py](https://github.com/tomikan1208-code/3D_shogi/blob/master/ai_training/model.py)、[train.py](https://github.com/tomikan1208-code/3D_shogi/blob/master/ai_training/train.py)、[CPP_CORE.md](https://github.com/tomikan1208-code/3D_shogi/blob/master/ai_training/CPP_CORE.md)、[gpu_env_rebuild/README.md](https://github.com/tomikan1208-code/3D_shogi/blob/master/gpu_env_rebuild/README.md)、[tensorization_lab/README.md](https://github.com/tomikan1208-code/3D_shogi/blob/master/tensorization_lab/README.md)）
- **環境**: `Shogi3DEnv(gym.Env)`。1 つの環境で手番が交互に入れ替わり、同じ方策が先後両方を指す（共有方策の自己対戦）。
- **観測**: Dict 空間。
  - `board`: (30, 9, 9, 9) の one-hot（15 駒種 × 先後 2）。**手番から見た相対表現ではなく先後の絶対表現**。
  - `hand_sente(7)`、`hand_gote(7)`、`current_player(1)`。
  - データ型は uint8。
- **行動空間**（2 方式を環境変数で切り替え）:
  1. 既定値（`SHOGI_FIXED_ACTION_SPACE=0`）: `Discrete(1500)`。**その局面の合法手リストへのインデックス**。合法手の並び順に依存するので、同じインデックスでも局面ごとに意味が変わる。1500 手を超えた分は切り捨てられる。
  2. 固定空間（Colab 手順では `--fixed-action-space`）: 移動元 729 × 相対デルタ 160 × 成/不成 2 = 233,280 と、打ち 729 × 7 駒種 = 5,103 で、**計 238,383**。デルタ 160 の内訳は、飛 6 方向 × 距離 8 = 48、角 12 方向 × 8 = 96、立体対角 8（王用）、桂 8（先後両方）。
- **モデル**: `Shogi3DFeaturesExtractor`。Conv3d(k=3) を 3 層（64/128/128 チャネル、ReLU）→ Flatten（128×729 = 93,312 次元）。持ち駒と手番の MLP（15→32）を結合し、Linear で 512 次元にする。方策ヘッドと価値ヘッドは SB3 の既定 MLP と思われる（**未確認**）。
- **学習**: sb3-contrib の `MaskablePPO`（`ProgressMaskablePPO` で拡張）、`SubprocVecEnv`、TensorBoard。報酬はかなり整形されている。
  - 駒取りによる駒価値
  - 浮き駒ペナルティ / タダ取りボーナス
  - 詰み +20、反則 / 合法手なし −20
  - 繰り返しペナルティ、千日手打ち切り −2
- **高速化**:
  - C++ コア（pybind11）: 王手判定、合法手生成、ピン計算。フィルタレベルは 0〜2。
  - `gpu_env_rebuild/`: torch テンソルで盤面をバッチ化する別実装。README によると合法手生成は「Python-loop heavy」で、まだベクトル化されていない。
  - `tensorization_lab/`: conv3d で利きマップを出す試作。打ちと自殺手の除外は未実装。
- **学習済み重み**: `.gitignore` に `models/` が含まれ、Releases は 0 件、Hugging Face 等へのリンクもない → **公開されていない**。
- **強さの証拠**: ランダムプレイヤーとの対戦スクリプト（`eval_vs_random.py`）があるだけで、結果（勝率や Elo）は公開されていない → **強さの証拠はない**。
- その他: Windows のビルド生成物（約 10MB の `.obj`）がコミットされている。

**再利用可能性**
- コード: **不可**（ライセンスなし）。
- アイデア: 可。アイデアそのものは著作権の対象外だが、実装は独自に書く。
- データ: なし（ルールが違うので仮にあっても使えない）。

**VoxelShogi への示唆**
- **ルール実装を一本化する価値**が実例で示されている。tomikan 版は JS/Python/C++ の三重実装で、ずれの危険を自ら認めている。VoxelShogi の「Rust コア 1 つを WASM と PyO3 で共有」という方針は、まさにこの問題を解く。Python と C++ の合法手の等価性を検証するスクリプトを持っている点は参考になる。VoxelShogi では perft とゴールデンテストで同じことをする。
- **行動空間を「合法手リストへのインデックス」にしない**。意味が一定しないので、方策が汎化しにくい。固定の空間表現を使う（4.1 節）。
- **観測は手番視点の相対表現にする**（AlphaZero 流、Keisei も同じ）。先後の対称性を使ってデータを半分に節約できる。
- 報酬整形は使わず、**最終結果（勝/分/負）のみ**を学習信号にする。駒価値の整形は、3D 将棋で何が良い手かという未知の戦略を人間の先入観で歪める恐れがある。
- 3D-CNN の素朴なベースライン（3 層、64/128/128）は先行例として**比較表に引用できる**（構成の参照のみ）。
- UI のアイデア（独自に実装する）:
  - XZ/XY/YZ の 3 種の断面を 2D で切り替える表示
  - 軸ラベルをクリックすると、該当スライスを 3D 上で強調する
  - OrbitControls と NaviCube
  - ホバー時のマーカー
  - 駒の格に応じて形の大きさを変える

**採用・不採用**: コードは**不採用**（ライセンスなし）。ルールも**不採用**（shogitter 166 に準拠するため）。断面 UI と一本化の教訓は**アイデアとして採用**する。

---

### 1.2 m-tatsuto/3dshogi（空将）

URL: https://github.com/m-tatsuto/3dshogi （駒の動きのデモページは README に `http://kusho.knowpic.com/comas/?coma=...` とあるが、現在稼働しているかは**未確認**）

**概要**
- 2013 年 5 月に開発され、2017 年まで更新、2021 年に CNAME を削除。JavaScript と Three.js（`three.min.js` を同梱）。README には「三次元将棋（仮名：空将)」とある。
- 盤の状態は `localStorage` に保存/復元できる。AI はない。

**ライセンス**
- ルートに `MITL` という名前のファイルがあり、中身は MIT License の英文と、EUC-JP で文字化けした日本語訳。
- ただし **Copyright 表記が "Copyright (c) 2013 3dchess developer"** で、本リポジトリの作者名ではない（別プロジェクトの雛形を流用したと推測される）。
- GitHub API では `license: null`（未検出）。
- → **MIT の意思表示はあるが、著作権者の表記が整合していない**。コードを流用する理由はないので、**コードは使わず、アイデアの参照に留める**。同梱の `three.min.js` は three.js 本体（MIT）。

**ルール**（出典: [lib/comaData.js](https://github.com/m-tatsuto/3dshogi/blob/master/lib/comaData.js)、[lib/mainComaSet.js](https://github.com/m-tatsuto/3dshogi/blob/master/lib/mainComaSet.js)、[tmp_source/3dshogi.txt](https://github.com/m-tatsuto/3dshogi/blob/master/tmp_source/3dshogi.txt)。配列は `cell3d[x][前後][層]`）

| 駒 | 空将 | shogitter 166 との比較 |
|---|---|---|
| 歩 | 前 1 **と上下 (0,0,±1)** の 3 マス | 異なる |
| 香 | 前方へ走る | 同じ |
| 桂 | (±1, 前2, ±1) の 4 マス | **同じ** |
| 銀 | 同じ層で前 3 + 斜め後ろ 2、上下層で前 3 + 後ろ 3 ずつ = 17 | 異なる（shogitter は 13） |
| 金 | 前 9 + 同じ前後面 8 + 真後ろ 1 = 18 | **同じ集合** |
| 王 | 26 | 同じ |
| 飛 | 6 方向のレイ | 異なる |
| 角 | **立体対角 8 方向** (±1,±1,±1) のレイのみ | 異なる（shogitter は平面斜めも含む領域型） |
| 竜・馬 | 飛・角 + 王の近傍 | 同じ考え方（基本の動きが違う） |
| 初期配置 | 片側 **166 枚**: 最奥層 81（香 32 / 桂 24 / 銀 16 / 金 8 / 玉 1 の同心正方形）、第 2 層に飛 2・角 2、第 3 層に歩 81 | 最奥層の同心配置は shogitter の 9 段目と同じ形（shogitter の 9 段目の内訳を同心正方形とした場合）。大駒の数（4 対 24）と段の構成が異なる |

**3D 表示・UI のアイデア**（出典: [threeJs_lib/threeJs_main.js](https://github.com/m-tatsuto/3dshogi/blob/master/threeJs_lib/threeJs_main.js)、[threeJs_objectModel.js](https://github.com/m-tatsuto/3dshogi/blob/master/threeJs_lib/threeJs_objectModel.js)、[js/display.js](https://github.com/m-tatsuto/3dshogi/blob/master/js/display.js)、[index.html](https://github.com/m-tatsuto/3dshogi/blob/master/index.html)）
- **9 層を 2D テーブルで並べて同時に表示**し、各セルをクリックして操作する（3D 表示と同期）。視点を先手側/後手側で反転できる。
- 選択したマスを通る **x・y・z の 3 本の十字ガイド線**を盤の端から端まで描く。3D の奥行きの曖昧さを減らす。
- 移動可能なマスは半透明の黄色キューブ、打てるマスは非常に薄い緑（opacity 0.1）で表示する。駒自体も半透明で、奥の駒が見える。
- カメラは中心を軸に回転し、ボタンで距離を変える（左右回転と前後移動）。「先手側」「後手側」のプリセット視点がある。
- 駒ごとの動きを確認する専用ページ（`comas/?coma=...`）がある。

**再利用可能性**: コードは非推奨（ライセンス表記が不整合で、Three.js も旧 API の `THREE.Geometry`）。UI のアイデアは可。データはない。

**VoxelShogi への示唆**:
- 「層テーブルの一覧と 3D の同期」「十字ガイド線」「合法手の半透明ハイライト」「駒の動きの図鑑ページ」は、Web ゲームの初期 UI として有効。
- tomikan 版の XZ/XY/YZ 断面切り替えと組み合わせ、**断面ビュー + 3D ビュー + ガイド線**を基本構成にする。

**採用・不採用**: UI のアイデアは**採用**（独自に実装）。コードとルールは**不採用**。

---

### 1.3 三次元将棋の実装の比較（まとめ）

| 項目 | shogitter 166（VoxelShogi） | tomikan 版 | 空将 |
|---|---|---|---|
| 片側の枚数 | 186 | 170 | 166 |
| 飛 | 1 座標共有の領域型（直方体で遮る） | 6 レイ | 6 レイ |
| 角 | 2 軸等距離 + 第 3 軸 ≤ a（台形で遮る） | 平面斜め 12 レイ | 立体対角 8 レイ |
| 桂 | ×型 4 | ＋型 4 | ×型 4 |
| 銀 | 13 | 17 | 17 |
| 金 | 18 | 18（同じ） | 18（同じ） |
| AI | （VoxelShogi で開発） | MaskablePPO + 3D-CNN（重み・強さは非公開） | なし |
| ライセンス | Apache-2.0 | **なし** | MIT 文面（表記に不整合） |

---

## 2. 三次元チェス

### 2.1 guille0/space-chess

URL: https://github.com/guille0/space-chess

- **概要**:
  - Raumschach（5×5×5、ユニコーン駒あり。[chessvariants](https://www.chessvariants.com/3d.dir/3d5.html)）を AR で実装したもの。Panda3D と OpenCV のマーカーで表示する。
  - AI は minimax + α-β 枝刈り（C++/Cython）。README 自身が「Raumschach では遅い」と書いている。
  - `config.py` で任意の盤サイズ（5×5×3 など）を定義できる。
  - 2019 年以降は更新されていない。
- **ライセンス**: MIT（GitHub API で `MIT` を確認）。ただし README によると、駒の 3D モデルは TurboSquid / free3d から取ったもので、**MIT の範囲外**（各配布元の条件に従う）。
- **再利用可能性**: コードは MIT なので参照できるが、技術スタック（Python/Panda3D）が異なり、実用上の価値は低い。3D モデルは使わない。
- **VoxelShogi への示唆**: 盤サイズを設定可能にしておくと、小さな盤での単体テストやカリキュラム学習（例: 5×5×5 の縮小版で事前学習）に使える。**縮小盤のバリアントを Rust エンジンの設定として持つ**ことは検討に値する（shogitter 166 本体のルールは変えない）。
- **採用・不採用**: コードは不採用。縮小盤のアイデアは**検討する**。

---

## 3. ゲーム AI 研究

### 3.1 AlphaZero

- 出典: Silver et al., "Mastering Chess and Shogi by Self-Play with a General Reinforcement Learning Algorithm", [arXiv:1712.01815](https://arxiv.org/abs/1712.01815)（Science 2018 版あり）
- **概要**: MCTS（PUCT）と ResNet の policy/value を使い、自己対戦のみで学習する。将棋の行動は「移動元 81 × 移動タイプ 139」= **11,259** の空間平面で表す（Keisei の README でも同じ分解を確認: https://github.com/foundryside-dev/keisei ）。
- **ライセンス**: 論文のみ（公式コードは非公開）。
- **再利用可能性**: アイデア。
- **VoxelShogi への示唆**:
  - 自己対戦 → リプレイバッファ → 学習という基本ループを使う。
  - 手番視点の観測を使う。
  - **移動タイプ方式の行動表現は shogitter 型の飛・角に合わない**。飛は 1 座標を共有する任意のマスへ動けるので、相対デルタだけで 17³−16³−1 = **816 通り**ある。角も領域型。「移動元 × 相対デルタ」は 729 × 数千になり、疎で非効率になる（4.1 節）。
- **採用・不採用**: 学習の枠組みは**採用**。139 平面型の行動表現は**不採用**。

### 3.2 MuZero

- 出典: Schrittwieser et al., [arXiv:1911.08265](https://arxiv.org/abs/1911.08265)（Nature 2020）
- **概要**: 環境モデル（表現・遷移・報酬）を学習し、潜在空間で計画する。
- **再利用可能性**: アイデア。
- **VoxelShogi への示唆**: VoxelShogi には**正確で高速なルールエンジン（Rust）がある**ので、遷移モデルを学習する利点は小さい。学習したモデルの誤差がかえって不利になる。
- **採用・不採用**: **不採用**（AlphaZero 系の「真のシミュレータ」を使う）。Gumbel の探索手法だけを取り入れる（3.4 節）。

### 3.3 Sampled MuZero（arXiv 2104.06303）

- 出典: Hubert et al., "Learning and Planning in Complex Action Spaces", [arXiv:2104.06303](https://arxiv.org/abs/2104.06303)（2021）
- **注意**: 依頼文では 2104.06303 を「Policy improvement by planning with Gumbel」としていたが、**実際は Sampled MuZero の論文**である（arXiv の abstract ページで確認）。Gumbel の論文は 3.4 節に記載する。
- **概要**: 行動の部分集合をサンプリングして方策を評価・改善する、汎用の枠組み。巨大な行動空間や連続行動空間に対応する。
- **VoxelShogi への示唆**: 実装後の初期合法手は標準424手、9王試作554手。対局全体の分岐数分布や深いperftは未確定であり、初期値だけで判断しない。根ノードで全合法手を展開するのが重い場合、サンプリングして探索するのが有効。
- **採用・不採用**: **予備案**。Gumbel の Top-k サンプリングでも同じ問題をかなり緩和できるので、まず Gumbel を使う。

### 3.4 Gumbel AlphaZero / Gumbel MuZero

- 出典: Danihelka, Guez, Schrittwieser, Silver, "Policy improvement by planning with Gumbel", ICLR 2022（[OpenReview](https://openreview.net/forum?id=bERaNdoegnO)、[ICLR ページ](https://iclr.cc/virtual/2022/poster/6418)）
- **概要**:
  - 根ノードで Gumbel-Top-k により**非復元抽出**で行動を選び、Sequential Halving で絞り込む。
  - 方策改善が保証される形の更新になり、**シミュレーション数が少なくても学習できる**。
  - 方策の学習目標には completed Q-values を使う。
- **実装**:
  - [google-deepmind/mctx](https://github.com/google-deepmind/mctx)（JAX、Apache-2.0）の `gumbel_muzero_policy`
  - [opendilab/LightZero](https://github.com/opendilab/LightZero)（PyTorch、Apache-2.0）も Gumbel/Sampled 系を実装している（Apache-2.0 は確認済み。収録アルゴリズムの詳細は**未確認**）
- **VoxelShogi への示唆**: 3D 将棋は分岐数が非常に大きく、1 手あたりのシミュレーション数を多く取れない。Vast.ai の GPU 予算も限られている。**Gumbel 型の根ノード探索（例: 16〜64 シミュレーション）**を候補とする。VoxelShogiでの費用対効果は未計測。gokaku（3.11 節）も Gumbel AlphaZero を参考にしている。
- **採用・不採用**: **採用（第一候補）**。Apache-2.0 の実装は参照・移植できる。ただし探索木は Rust 側に置くのが自然。

### 3.5 KataGo

- 出典: D. J. Wu, "Accelerating Self-Play Learning in Go", [arXiv:1902.10565](https://arxiv.org/abs/1902.10565)。abstract は「50x reduction in computation over comparable methods」と主張している。実装は [lightvector/KataGo](https://github.com/lightvector/KataGo)。
- **ライセンス**: リポジトリ本体は MIT 型の許諾文（外部ライブラリは個別ライセンス）。GitHub API の判定は `NOASSERTION`。
- **主な工夫**（論文の本文による。abstract には個別の名前は出てこない）:
  - Playout cap randomization: 一部の手だけ深く探索し、その手だけを方策の学習目標にする。
  - Forced playouts + policy target pruning
  - Global pooling 層
  - 補助学習目標: 所有権、スコア、相手の次の手
- **VoxelShogi への示唆**:
  - Playout cap randomization は Gumbel と併用でき、自己対戦のコストを大きく下げる。
  - 補助ヘッドの候補: **W/D/L 価値**（標準の千日手・上限打ち切り、9王試作の採点同点などを扱うため。持将棋は現行仕様に含めない）、**駒得（スコア）**、**王の周辺 3×3×3 の支配**など。
  - CNN を使う場合は global pooling バイアスを入れる（3D-CNN ベースラインの強化）。
- **採用・不採用**: Playout cap randomization、W/D/L、補助ヘッドは**採用**。所有権ヘッドは囲碁固有なので**不採用**。

### 3.6 Leela Chess Zero（lc0）の Transformer「BT」ネット

- 出典: Lc0 Blog "Transformer Progress"（2024-02-28）https://lczero.org/blog/2024/02/transformer-progress/ 、実装: [LeelaChessZero/lc0](https://github.com/LeelaChessZero/lc0)（**GPL-3.0**）、[lczero-training](https://github.com/LeelaChessZero/lczero-training)（GitHub 上でライセンス未検出。**未確認**）
- **概要**:
  - 64 マスを 64 トークンにした encoder。
  - BT1（2022-08）→ BT4（2024-02）。BT4 は 15 層、埋め込み 1024、FFN 1536、32 ヘッド、191.3M パラメータ。
  - 従来の CNN（T78、194.5M）に比べて、**素の方策で +270 Elo**、演算量はおよそ 6 割（7.6 対 12.45 GFLOPS）。
- **smolgen**:
  - トークンを 32 次元に射影して平坦化し、256 次元に圧縮する。そこからヘッドごとの 256 次元を作り、**モデル全体で共有する 256×4096 の射影**で 64×64 の注意バイアスを生成する。これを softmax の前に加える。
  - ブログによると「50% 大きいモデル相当、スループットの低下は約 10%」。
  - 初期の版では、層ごとに 64×64×h の学習可能な静的バイアスを使っていた。
- **注意ポリシーヘッド**: 移動元マスの query と移動先マスの key のドット積で、**64×64 の from-to ロジット**を作る。プロモーションは最終段の key から駒種ごとの加算バイアスを出して処理する（Chessformer 論文で確認。3.7 節）。
- **VoxelShogi への示唆**:
  - **マス=トークン、from-to 注意ポリシー**は 729 マスにそのまま拡張できる。729×729 のロジット行列を作り、合法手でマスクして softmax をとる。成/不成は加算バイアス、打ちは「持ち駒の駒種トークン × 移動先マス」のロジットで表す。
  - smolgen をそのまま 729 トークンに使うと、共有射影が d3×729² = d3×531,441 になる。d3=256 なら**約 1.36 億パラメータ**で、現実的ではない。軸ごとの分解（b_x(i,j) + b_y(i,j) + b_z(i,j)、それぞれ 9×9）や低ランク化が必要になる。
- **採用・不採用**: アーキテクチャのアイデアは**採用**。コードは GPL-3.0 なので**不採用**（参照もしない）。

### 3.7 Chessformer（= arXiv 2605.19091）

- 出典: Monroe, Eilender, Chalmers, Tang, Anderson, "Chessformer: A Unified Architecture for Chess Modeling", [arXiv:2605.19091](https://arxiv.org/abs/2605.19091)（2026-05-18 投稿、ICLR 2026、論文は CC BY 4.0）。前身は Monroe & Chalmers, "Mastering Chess with a Transformer Model", [arXiv:2409.12272](https://arxiv.org/abs/2409.12272)。Lc0 のブログには「BT4 は Leela-CF と同じネットワーク」とある。
- **概要**:
  - マスをトークンにした encoder-only Transformer。
  - **Geometric Attention Bias（GAB）**: 盤面に応じてヘッドごとに h×64×64 のバイアスを生成する。d3 個のテンプレートを動的に混ぜる形で、smolgen を定式化したものに相当する（論文本文には smolgen の名前は出てこない）。
  - **source-destination 注意ポリシーヘッド**を使う。
- **結果**:
  - Lc0 に組み込むと、同じ時間で CNN 版に対して **+105〜112 Elo**。
  - Maia-3（人間の手の予測）は 57.1% で SOTA。
  - アブレーション（強さの設定）では、GAB-4M が絶対位置埋め込みに対して **+83 Elo**（相対バイアスは +40）。GAB-2.5M は約 6 割の演算量で絶対位置埋め込みと同じ強さ。
  - 論文中の相対バイアスのベースラインは、ヘッドごとの 2D 15×15 テーブル（225 パラメータ/ヘッド）。
- **コード**: 論文ページにリンクはない（**未確認**）。
- **VoxelShogi への示唆**:
  - これは VoxelShogi の比較研究と**最も近い先行研究**。2D チェスでは「絶対位置 < 静的な相対バイアス < 動的な幾何バイアス」の順になった。これを **3D・729 トークン**で検証することが VoxelShogi の研究上の問い。
  - 3D での静的相対バイアスは 17³ = 4,913 エントリ/ヘッド（Video Swin 型の 3D 相対位置テーブルに相当）。動的バイアスは軸分解や低ランク化をしないと計算量で破綻する（3.6 節）。
  - shogitter の飛（1 座標共有）と角（2 軸等距離）は、「2 マス間の相対ベクトルの性質」で決まる。**関係タイプ特徴**（同じ軸線上、同じ平面上、2 軸等距離など）を固定のバイアスとして入れる「ルール幾何バイアス」は自然な追加候補になる。
- **採用・不採用**: **採用（中核の比較対象）**。

### 3.8 Grandmaster-Level Chess Without Search（DeepMind 2024）

- 出典: Ruoss et al., [arXiv:2402.04494](https://arxiv.org/abs/2402.04494)。v1 の題名は "Grandmaster-Level Chess Without Search"、v2 は "Amortized Planning with Large-Scale Transformers: A Case Study on Chess"（NeurIPS 2024）。実装: [google-deepmind/searchless_chess](https://github.com/google-deepmind/searchless_chess)
- **ライセンス**: コードは Apache-2.0、**モデル重みは CC-BY 4.0**（README で確認）。
- **概要**:
  - 最大 270M パラメータの Transformer を ChessBench（約 1000 万局、Stockfish 16 で注釈した約 150 億データ点）で教師あり学習した。
  - 探索なしで Lichess blitz **Elo 2895**。
  - 状態価値、行動価値、behavior cloning を比較している。
  - 入力は FEN を固定長 **77 トークン**にしたもの（`src/tokenizer.py` の `SEQUENCE_LENGTH = 77`）。
  - 論文は「Stockfish の完全な蒸留にはまだ届かない」としている。
- **VoxelShogi への示唆**:
  - 強い教師エンジンがない 3D 将棋では、そのまま真似できない。ただし「**探索付きの自己対戦エンジンの出力を大規模な合成データとして蒸留する**」パイプラインは、VoxelShogi の合成データセットの設計と同じ発想。
  - **価値を bin に分けて分類学習する**手法（論文で採用。詳細な bin 数は**未確認**）と、行動価値ヘッドは、データセット公開の際に注釈形式として採用を検討する。
  - トークン化は FEN 文字列ではなく、**マス=トークン**（Chessformer 方式）を選ぶ。Chessformer は「1D 構造の押し付けは盤の幾何と合わない」と論じている。
- **採用・不採用**: 蒸留とデータセットの考え方は**採用**。FEN トークン化は**不採用**。

### 3.9 DeepNash

- 出典: Perolat et al., "Mastering the Game of Stratego with Model-Free Multiagent Reinforcement Learning", [arXiv:2206.15378](https://arxiv.org/abs/2206.15378)（Science 2022）
- **概要**: 不完全情報ゲームのストラテゴで、R-NaD（Regularized Nash Dynamics）による探索なしのモデルフリー学習を行い、人間の上位層に到達した。
- **VoxelShogi への示唆**: VoxelShogi は完全情報ゲームなので直接は関係しない。探索なしの方策だけで強くなる例として、PPO 系ベースライン（tomikan、Keisei）との比較の文脈で引用する程度。
- **採用・不採用**: **不採用**。

### 3.10 NNUE 系将棋エンジン（YaneuraOu ほか）と既存の DL 将棋

- [yaneurao/YaneuraOu](https://github.com/yaneurao/YaneuraOu): **GPL-3.0**。リポジトリの説明に WCSC29 優勝とある。
- [TadaoYamaoka/DeepLearningShogi](https://github.com/TadaoYamaoka/DeepLearningShogi)（dlshogi）: **GPL-3.0**。
- [kobanium/aobazero](https://github.com/kobanium/aobazero): AlphaZero の将棋実験の追試。分散した参加者で自己対戦し、棋譜を公開している。`license.txt` によると本体の `bin/aobaz` は Leela Zero 由来で GPLv3。
- [official-stockfish/nnue-pytorch](https://github.com/official-stockfish/nnue-pytorch): GPL-3.0。
- NNUE の概要は [chessprogramming wiki: NNUE](https://www.chessprogramming.org/NNUE) を参照。
- **概要**: NNUE は差分更新できる浅い評価関数（HalfKP など、王の位置 × 駒の配置の疎な入力）で、αβ 探索の速度を落とさずに精度を上げる。
- **VoxelShogi への示唆**:
  - 3D に素朴に HalfKP を広げると、王の位置 729 × (729 マス × 約 28 駒種 + 持ち駒) ≈ 1,500 万次元/視点になる。王の位置のバケット化などが必須。
  - さらに、shogitter の飛・角は領域型の利きを持つので、差分更新の対象が広い。
  - 研究の焦点（Transformer の比較）とずれるので、**当面は不採用**。将来、ブラウザ（WASM）上の軽量 AI として αβ + 小さな NNUE を作る余地はある。
  - USI 互換のプロトコル設計（ShogiHome 等との接続）は、3D 座標の表記が必要なので直接は流用できない。
- **採用・不採用**: コードは**不採用**（本プロジェクトの配布方針）。NNUE は将来の検討課題。

### 3.11 takedarts/gokaku

- URL: https://github.com/takedarts/gokaku 、学習の推移: https://takeda-lab.jp/gokaku/
- **ライセンス**: **v2.2 以降は MIT**、v2.1 以前は GPL-3.0（README の License 節）。一部の cmake スクリプトは Apache-2.0。LICENSE は "Copyright (c) 2025 Atsushi TAKEDA"。
- **概要**:
  - **ランダムに生成した棋譜から始める**深層強化学習の将棋 AI で、囲碁 AI「Maru」と兄弟関係にある。
  - モデルは nested-bottleneck 畳み込みと multi-head attention のハイブリッド。学習ページでは「大カーネルの depthwise conv + MHA」と説明している。
  - RL は KataGo と Gumbel AlphaZero に着想を得ている。
  - USI 対応、TensorRT/FP16、Docker で配布。
  - **モデルを Releases で公開**している（v2.3: b4c256 約 9.7MB / b8c384 約 31MB / b12c512 約 72MB）。
  - 学習ページは Gokaku 2.4 の 500 visits で、近い世代の 60 モデルとの対戦から Elo を算出しているとしている。モデルは 4 ブロック/256ch から 20 ブロック/768ch まで段階的に拡大。具体的な Elo の数値と計算資源は**未確認**（ページの本文に数値なし）。
- **再利用可能性**: MIT なので、探索や RL ループの設計は参照・移植できる（著作権表示を残す）。ただし 2D 将棋専用で、Cython/C++ が中心。
- **VoxelShogi への示唆**:
  - 「人間の棋譜なしで、ランダム棋譜から Gumbel と KataGo 流の RL」という**VoxelShogi と同じ前提の実証例**になっている（3D 将棋には人間の棋譜がない）。
  - CNN と attention のハイブリッドが実戦で使われているので、比較研究に「**3D-CNN + attention ハイブリッド**」を追加する根拠になる（ResTNet も同じ。3.13 節）。
  - 学習の推移を Web で公開する見せ方（世代ごとの Elo）は、VoxelShogi の Hugging Face 公開や Web サイトでも参考にする。
- **採用・不採用**: 手法は**参考にして採用**。コードの移植は必要になったときに MIT 表記付きで行う。

### 3.12 foundryside-dev/keisei

- URL: https://github.com/foundryside-dev/keisei
- **ライセンス**: MIT。
- **概要**:
  - Rust の将棋エンジン（`shogi-core`）と RL 環境（`shogi-gym`: VecEnv、観測、行動マッピング）を PyO3 で Python に公開している。
  - Python 側は PPO（KataGo 流の W/D/L + スコアの補助ヘッド）、SE-ResNet（global pooling バイアス）、ResNet/MLP/Transformer のベースライン。
  - 観測は手番視点の 46/50 チャネル（繰り返し回数と王手の平面を含む）。行動は **81 × 139 = 11,259**。
  - SQLite でメトリクスを記録し、Svelte の観戦 WebUI がある。
  - リポジトリの説明に「Built 100% by Claude Code」とあり、README は「Early rebuild」と書いている。Releases は 0 件で、**学習済み重みと強さの公開はない**。
- **VoxelShogi への示唆**:
  - **Rust エンジン + PyO3 + VecEnv** という構成が VoxelShogi とほぼ同じ。API の形（バッチ化した step/reset、合法手マスクの返し方、観戦用データの出力）は参考になる。
  - 合法マスクがすべて 0 のときに softmax が NaN になるのを防ぐ、という運用上の注意も役立つ。
  - アーキテクチャを登録制（registry）にしてモデルを差し替えられる構成は、比較研究（3D-CNN / Full / Axial / Geometry）にそのまま使える設計パターン。
  - PPO のみで探索なしの学習は、tomikan 版と同様に強さの上限が低いと予想される（**未検証**）。VoxelShogiでは将来の自己対局の候補をGumbel探索、比較用の候補をPPOとする案がある。Phase 5着手前にM6の実測を踏まえて確定し、現行M1はαβ探索のままとする。
- **採用・不採用**: 設計パターンは**採用**。コードは MIT なので参照できるが、2D 専用なので流用はしない。

### 3.13 2025〜2026 年の関連研究（Transformer のゲームエージェント、3D・幾何注意）

| 文献 | 内容 | VoxelShogi への関係 |
|---|---|---|
| Ju et al., "Bridging Local and Global Knowledge via Transformer in Board Games"（IJCAI 2025、https://www.ijcai.org/proceedings/2025/0828.pdf 、full: arXiv 2410.05347） | **ResTNet**: 残差ブロックと Transformer ブロックを交互に挟み、AlphaZero 系に組み込む。9×9 囲碁の勝率 54.6%→60.8%、19×19 囲碁 53.6%→60.9%、19×19 Hex 50.4%→58.0%。cyclic-adversary に対する被攻撃率 70.44%→23.91% | **3D-CNN と attention のハイブリッド**を比較対象に加える根拠 |
| Fu, "Do Geometry-Aware Positional Encodings Help Transformers in Spatial Imperfect-Information Games?"（[arXiv 2608.14982](https://arxiv.org/abs/2608.14982)、2026-08） | 六角マップのゲームで HexRoPE / 矩形相対バイアス / グラフバイアス / 位置符号化なしを比較。幾何バイアスは信念推定とデータ効率（1k 局で +4.63pt）を改善したが、**勝率は改善しなかった**（−1.56pt、CI に 0 を含む）。矩形相対バイアスはマップ半径の外挿に失敗した | 「幾何バイアスで精度は上がるが強さには直結しない」可能性を示す。VoxelShogi の比較では**方策精度だけでなく対局 Elo で評価する**必要がある |
| Maia-3 の注意の分析（[arXiv 2609.23917](https://arxiv.org/abs/2609.23917)、2026-09） | Maia-3 のヘッドが意味的注意と GAB 幾何注意を組み合わせることを分析（検索結果の要約に基づく。本文は未確認） | マス=トークン方式は解析しやすい。3D 版の注意の可視化を Web で公開する案 |
| "Tracing the Thought of a Grandmaster-level Chess-Playing Transformer"（[arXiv 2604.10158](https://arxiv.org/abs/2604.10158)、2026） | BT4（15 層、1024 次元、32 ヘッド）の内部を解析 | 解釈性の研究での引用候補（詳細は**未確認**） |
| Axial Attention（Ho et al., [arXiv 1912.12180](https://arxiv.org/abs/1912.12180)。実装 [lucidrains/axial-attention](https://github.com/lucidrains/axial-attention) は MIT） | 多次元テンソルで軸ごとに注意を計算する | 729 トークンを x/y/z 軸ごとの注意にすると、対の数は 729×27 = 19,683/ヘッド（全注意 531,441 の約 1/27） |
| Video Swin Transformer（[arXiv 2106.13230](https://arxiv.org/abs/2106.13230)）、TimeSformer（[arXiv 2102.05095](https://arxiv.org/abs/2102.05095)） | 3D の窓注意と 3D 相対位置バイアステーブル / 空間と時間を分けた注意 | 3D 相対バイアス（(2·9−1)³ = 4,913 エントリ）と分解型注意の、確立された先行例 |

**未発見**: 3D 盤のボードゲームに Transformer（軸注意や幾何バイアス）と自己対戦 RL を組み合わせた研究は、今回の検索範囲では**見つからなかった**（WebSearch の extended モードで 1 回検索しただけなので、網羅性は**未確認**）。

---

## 4. VoxelShogi の設計への示唆（まとめ）

### 4.1 行動空間と方策ヘッド

| 方式 | サイズ | 評価 |
|---|---|---|
| 合法手リストへのインデックス（tomikan の既定） | 1500 固定 | 意味が局面ごとに変わる。**不採用** |
| 移動元 × 相対デルタ × 成（tomikan の固定方式、AlphaZero の 139 平面型） | tomikan ルールで 238,383。shogitter ルールでは相対デルタが最大 17³−1 = 4,912 通り（飛だけで 816）に膨らむ | 領域型の飛・角に合わない。**不採用** |
| **from-to ロジット（注意ヘッド）+ 成バイアス + 打ち（駒種 × 移動先）** | 729×729 = 531,441 + 打ち 729×7 = 5,103（成/不成はロジットの加算で表す） | 移動先は合法手マスクで絞る。Lc0/Chessformer で実証済み。**採用** |

- 学習目標とマスクは、合法手のスパースなリスト（インデックスとロジットの組）として保存する。729² 次元の密なベクトルは保存しない。
- 打ちは「持ち駒種の埋め込み（query）× マス（key）」で、移動と同じ注意ヘッドの枠組みに統一できる。

### 4.2 観測

- 手番視点の相対表現にする（先手/後手を盤ごと反転して正規化する）。
- 入力の候補: 駒種 × 所有者の one-hot、持ち駒、繰り返し回数、王手フラグ、手数。
- 履歴（直前 k 手）の有無はアブレーションの対象にする。

### 4.3 探索と学習

- **Gumbel AlphaZero**（少ないシミュレーション数）+ **Playout cap randomization** + **W/D/L 価値** + 補助ヘッド（駒得など）。
- 報酬は最終結果のみ。駒価値による整形はしない（tomikan 版との違い）。
- 初期は**ランダム棋譜または弱い探索の棋譜**から始める（gokaku の前例あり）。縮小盤でのカリキュラムは任意。
- PPO（MaskablePPO / Keisei 型）は**ベースラインとして**比較表に載せる。

### 4.4 アーキテクチャの比較で注意すること

- **全注意**: 729² ≈ 53 万の対/ヘッド/層。FlashAttention 系を使えば計算はできるが、smolgen/GAB 型の動的バイアスは出力射影が過大になる（3.6 節）。
- **軸注意**: 計算量は約 1/27。軸線上でない関係（角の斜め方向など）は層を重ねて間接的に表すことになる。
- **幾何対応**:
  - 3D 静的相対バイアス（4,913 エントリ/ヘッド）
  - shogitter のルール由来の関係タイプバイアス（同じ軸線上、同じ平面上、2 軸等距離など）
  - 軸ごとに分解した動的バイアス（9×9×3 個のテンプレートを盤面に応じて混ぜる）
- **3D-CNN**: global pooling を入れた ResNet にする。tomikan 型の Flatten → MLP は弱いベースラインとしてだけ使う。
- **ハイブリッド**（gokaku、ResTNet）は第 5 の比較対象の候補。
- 評価は**方策精度だけでなく、同じ FLOPs・同じ学習予算での対局 Elo** で行う（2608.14982 の教訓）。

### 4.5 UI

- 層テーブルの一覧（空将）、XZ/XY/YZ の断面切り替え（tomikan）、3 軸の十字ガイド線（空将）、合法手の半透明ハイライト、駒の動きの図鑑ページ。いずれも独自に実装する。

### 4.6 ライセンス上の注意

- GPL-3.0（lc0、YaneuraOu、dlshogi、nnue-pytorch、AobaZero の本体）は**コードを参照しない・取り込まない**。
- ライセンスのない tomikan 版は**コードを参照しない**（今回はルールと AI の仕様を調べるために閲覧したが、実装には使わない）。
- MIT/Apache-2.0（gokaku v2.2 以降、Keisei、mctx、LightZero、searchless_chess、KataGo 本体）は、移植する場合に著作権表示を `NOTICE` などに残す。searchless_chess の重みは CC-BY 4.0。

---

## 5. VoxelShogi の新規性

**新規性は「世界初の三次元将棋」ではない。** 9×9×9 の三次元将棋は、少なくとも空将（2013 年）、tomikan 版（2026 年）、shogitter.com のルール（rule id 166）として存在する。tomikan 版は 3D-CNN + MaskablePPO による AI 学習も試みている。

VoxelShogi の新規性は次の 2 点にある。

1. **統合されたオープンスタック**
   - shogitter 166 に準拠した**単一の Rust ルールエンジン**（Web では WASM、学習では PyO3 として同じコードを共有）
   - 自己対戦と探索による**合成データセット**（局面、合法手、探索方策、価値注釈）
   - **Transformer の policy/value モデル**
   - **Gumbel 系の探索付き自己対戦**
   - Vast.ai のマルチ GPU による**分散学習**
   - Cloudflare で配信するブラウザゲーム
   - Hugging Face でのモデルとデータセットの公開

   コードはApache-2.0で公開する。モデル・データのライセンスはM3/M4の初回公開前にユーザーと確定する。先行する 3D 将棋の実装には、ライセンス、重み、データセット、強さの評価のいずれかが欠けている（tomikan 版はすべて欠けている）。

2. **729 トークンでのアーキテクチャ比較研究**
   - 同じルール、同じデータ、同じ学習予算のもとで、次の 4 つ（＋ハイブリッド）を**方策精度、価値精度、対局 Elo、FLOPs**で比較する。
     - **3D-CNN**（global pooling 付きの ResNet）
     - **Full-attention Transformer**
     - **Axial（軸分解）Transformer**
     - **Geometry-aware Transformer**（3D 相対バイアス、ルール幾何バイアス、軸分解した動的バイアス）
   - 2D チェスの Chessformer/Lc0 は 64 トークンで「幾何バイアスが効く」ことを示した。一方、六角マップの研究（2608.14982）は「精度は上がっても強さには直結しない」ことを示した。**3 次元・729 トークン・領域型の駒の動き**という、より厳しい条件でこの問いを検証することが研究としての貢献になる。

---

## 付録: 主な参照 URL

- tomikan1208-code/3D_shogi: https://github.com/tomikan1208-code/3D_shogi
- m-tatsuto/3dshogi: https://github.com/m-tatsuto/3dshogi
- guille0/space-chess: https://github.com/guille0/space-chess
- AlphaZero: https://arxiv.org/abs/1712.01815
- MuZero: https://arxiv.org/abs/1911.08265
- Sampled MuZero: https://arxiv.org/abs/2104.06303
- Gumbel AlphaZero/MuZero: https://openreview.net/forum?id=bERaNdoegnO
- mctx: https://github.com/google-deepmind/mctx / LightZero: https://github.com/opendilab/LightZero
- KataGo: https://arxiv.org/abs/1902.10565 / https://github.com/lightvector/KataGo
- Lc0 Transformer Progress: https://lczero.org/blog/2024/02/transformer-progress/
- Chessformer: https://arxiv.org/abs/2605.19091 / 前身: https://arxiv.org/abs/2409.12272
- Searchless chess: https://arxiv.org/abs/2402.04494 / https://github.com/google-deepmind/searchless_chess
- DeepNash: https://arxiv.org/abs/2206.15378
- YaneuraOu: https://github.com/yaneurao/YaneuraOu / dlshogi: https://github.com/TadaoYamaoka/DeepLearningShogi / AobaZero: https://github.com/kobanium/aobazero
- gokaku: https://github.com/takedarts/gokaku / https://takeda-lab.jp/gokaku/
- Keisei: https://github.com/foundryside-dev/keisei
- ResTNet (IJCAI 2025): https://www.ijcai.org/proceedings/2025/0828.pdf
- Geometry-aware PE in hex games: https://arxiv.org/abs/2608.14982
- Axial Attention: https://arxiv.org/abs/1912.12180 / Video Swin: https://arxiv.org/abs/2106.13230 / TimeSformer: https://arxiv.org/abs/2102.05095
