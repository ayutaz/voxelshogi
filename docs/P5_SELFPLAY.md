# Phase5自己対局：探索とActorの契約

2026-10-30。[P5-2](POST_M6_PLAN.md#phase5)に向け、最初の探索方式を
PUCTに固定する。[探索核](../training/selfplay_search.py)は手書きの木で
数式と停止を検証する部分で、実モデルの自己対局を完了した記録ではない。

## 探索

局面adapterは`fork()`、`snapshot()`、`legal_actions()`、`play()`を提供する。
実対局のadapterはRustの履歴付きGameを使い、王手・終局・合法手・千日手を
Pythonへ再実装しない。VSFENだけから複製して履歴を落とす方法は使わない。
`Game.fork()`はRustの`Session::clone`を呼び、反復履歴・記録・外部停止状態を
独立して複製する。`Game.from_record`の全手再生やVSFENからの作り直しは行わない。
外部Linuxで、11手の反復履歴を複製して12手目の千日手を検証し、
元の局面・別の着手分岐との独立性、MaxPlies／Abandonedの保持を確認する。
実モデルの読み込みと確率・Valueの境界は、下のevaluatorで確認する。

evaluatorは全合法actionだけの事前確率と、現在の手番視点の有限なValue
`[-1,1]`を返す。確率は非負、合計1（絶対誤差1e-6以内）。
終局はRustの実結果を使い、モデルを呼ばない。

選択は`Q + c_puct * P * sqrt(max(1, N_parent)) / (1 + N_child)`。
未訪問のQは0、訪問済みQは子の平均Valueを親の手番視点へ変換する。
同点はaction IDの小さい方を選ぶ。初期の既定値は32 simulation、
最大深さ64、`c_puct=1`。構成はsimulation 1〜100000、深さ1〜256、
`c_puct`が有限な`(0,100]`であることを検査する。
本試行にはこれより小さい具体的上限・モデル・seedを事前固定する。

1 simulationごとにrootの履歴付き複製からたどり、未展開の葉を1つ評価する。
各祖先の手番と葉の手番を照合してValueの符号を変換し、訪問数を1増やす。
rootの初回モデル評価をsimulationには数えない。
モデル呼び出しは最大`simulations + 1`回。
深さ上限の葉は明示的なモデル推定値を使い、引分扱いしない。

実行ごとに新しい木を作り、木や推論cacheを次の呼び出しへ持ち越さない。
モデル・履歴・rulesetの異なる呼び出しを盤面hashだけで共有しない。
同じ入出力・構成・中断なしの探索は同じ結果を返す。
推論backend自体の再現性は別途、固定した実機・依存・モデルhashで確認する。
Actorの温度付き着手やseed付き探索ノイズは、この決定的な核の外側に置く。

## 結果・中断

結果は全root合法手の訪問数、最多訪問のaction、完了simulation数、
root平均Value、モデル評価回数、到達深さ、停止理由を返す。
最多訪問の同点もaction ID昇順で決める。
自然終局rootは着手なし・実結果Valueを返す。
打切りや結果のない外部停止を自然終局へ変換しない。

時間上限・終了signalは監督側の`stop_requested`で渡す。
評価中の中断を確認したsimulationは訪問数・平均へ加算しない。
それまでに完了したsimulationは保持し、`interrupted`として返す。
完了数0なら着手とroot平均は`None`で、ランダムな手を補わない。
Actorは途中結果を完成教師に使わず、停止と保存を処理する。
Policy教師への変換は[ラベル契約](P5_TARGETS.md)に従う。

## Seed付きActor

[Actor](../training/selfplay_actor.py)は、履歴付きrootを複製して、
PUCT→温度付き着手→Rustでの適用を繰り返す。各サンプルには実際に適用した
action／move、開始棋譜からの絶対ply、手番、VSFEN、全合法action、
完了訪問分布と探索統計を保存する。開始履歴の手数を追加手数上限へ数えない。
1対局の既定値は追加256手、最初の16手を温度1、以降は最多訪問・同点ID昇順。
温度が正なら訪問数の`1 / temperature`乗を重みにして抽選する。
ゼロ訪問の手は着手候補に含めない。

各探索のrootだけにDirichletノイズを混ぜる。既定は`alpha=0.3`、割合0.25。
action昇順のGamma(alpha,1)から正規化したノイズを作り、
`(1 - fraction) * prior + fraction * noise`とする。
温度・ノイズはActorの構成に明示し、比較対局で無表示に使わない。
手計算の例では、事前確率`[3/4,1/4]`、ノイズ`[1/5,4/5]`、割合1/4を
混ぜると`[0.6125,0.3875]`になる。

乱数はseed・モデルSHA-256・完全な現在棋譜・用途名のcanonical JSONを
SHA-256で束ねた値から、呼び出し専用の`random.Random`を作る。
rootノイズと着手抽選で用途を分け、周囲の乱数状態を読んだり変更したりしない。
実行Pythonは固定する。対局IDは生成元commit・全Actor／探索構成・開始棋譜・
モデルhashへ結び付ける。ここでのhash／commitは形式を検査する宣言値で、
実際のclean source・重み・backendとの一致は後続の実行driverが確認する。

自然終局なら、全サンプルへ各手番視点の実結果ラベルを付ける。
最後の許可手で自然終局した場合も、実結果を優先する。
追加手数上限では棋譜の外部停止をMaxPliesとし、最後の未終局局面のモデル評価を
明示的なbootstrap教師にする。割引は既定1で、実行前に固定する。
bootstrapを含めたモデル評価呼び出し総数と、そのうちのbootstrap回数も保存する。
打切りを自然終局の引分教師へ変換しない。

探索中・bootstrap中の中断は`InterruptedError`とし、完成episodeを返さない。
保存対象は全手を検証した完成episodeだけにする。最初の保存再開単位は
完成episodeで、中断したepisodeは同じ開始棋譜・seed・モデル・構成から再実行する。
episode内の任意の手からの再開は、このActorでは実装しない。
バッファと世代controllerでは、完成データと次のseed／カーソルを原子的に保存し、
別実機での復旧時に未完成データを完成教師へ混ぜない。

## 独立検証と実装の残り

### 実モデルのevaluator

[Policy／Value evaluator](../training/policy_value.py)は既存Studentと
特徴量・出力の検査を共有し、全合法手だけでsoftmaxした確率と、
現在の手番視点のValueを返す。Valueを反転・clampしない。
推論はeval／inference modeで行い、推論モデルの勾配を無効にする。
現在のファイルloaderはFP32のTransformer-Sだけを扱う。

`load_policy_value`には期待するSHA-256とCPU／CUDAを明示する。
通常ファイル・safetensors形式・512MiB以下を要求し、読み込み前後のhash、
全重みのFP32／finite、全state keyとshapeの一致を検査する。
検証した重みから別の推論モデルを作り、artifact hash・構造・backend・
compute dtypeをbindingに保存する。rawモデルのconstructorはbindingを持たない。
CPUへの自動切替は行わず、要求したCUDAが使えなければエラーにする。

生成時と呼び出し時に決定的演算を有効にし、TF32を無効、
float32 matmulをhighestに設定する。CUDAは実行前の
`CUBLAS_WORKSPACE_CONFIG=:4096:8`を要求する。
M6のValueは探索スコア由来の尺度であり、勝率を表さない。
実行driverは引き続きclean sourceとepisodeのsource／model hashを照合する。

[外部Linuxの機能確認](experiments/p5-policy-value-functional.json)では、
固定したM6実重みをCPU／RTX5090 CUDAの先後2局面ずつへ読み込み、
合法確率・Value範囲・既存argmaxとの一致を確認した。
この2局面では既存モデルと同様に詰み手を選ばなかった。
同じVMで評価と機能確認を併走しており、専有性能の測定には使わない。
14件の新しい単体・既存Studentの2件と、新規12・既存2変異も検証する。
重みやデータ本体をMacへ中継しない。

### 探索とActorの独立検証

2手の終局木を手計算し、simulation4回・`c_puct=4`で訪問数3対1、
root平均0.5になることを先後両視点で検査する。
2階層の木で平均−0.625、深さ1では−0.25となることも手計算で検査する。
新しいモデル事前確率、自然終局、中断時の未完了訪問の除外、
不正な確率・Value・上限の拒否を確認する。
手番変換・Qの使用・同点・探索項・回数・深さ・終局値・中断の9変異をCIへ含める。

Actorは手書きportで温度のCDF、rootノイズ、自然終局／bootstrap、手番、
追加手数、中断、乱数の独立性、sourceとID、呼び出し回数を検査する。
これらの14変異を通常CIへ含める。外部Linuxでは、Rustの実局面を使い
先後の1手詰め、11手の履歴からの千日手、MaxPlies棋譜の再生も確認する。
ここでのモデルは手書きの既知policy／valueで、学習済みモデルの性能評価ではない。

この後、evaluatorとActorを完成episodeの検証・保存・読み込み、
[全合法手を分母にする疎な損失](P5_TARGETS.md)と、Replay Buffer・世代更新・保存再開を接続する。
外部Linuxで複数世代を実行し、別実機での復旧・固定評価まで通してP5-2〜3を判定する。
この小さい参照木のテストを、実3D将棋の自己対局実績と読み替えない。
