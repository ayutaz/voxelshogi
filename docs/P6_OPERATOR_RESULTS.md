# 実Mの4構造：単GPU・ONNX検証結果

**2026-11-12・一時停止**：既存Sの公開デモと、Mの少量2 run・48局評価を現段階の成果とする。
本比較12 run・MのWeb配布・観戦表示2案／実端末各60分は未完了のまま停止する。
追加GPU・生成・学習を自動再開しない。[停止時点の結果と固定HF版](RESEARCH_CHECKPOINT_20261112.md)を現在の確認元とし、
以下の旧「現在」「次」「予算」は対象時点の記録、実行コマンドは再開後の手順として読む。

2026-11-05。[全1〜6の実行計画](P6_EXECUTION_PLAN.md)の2のうち、
4構造の実M・ONNX数値照合・単GPUの合成負荷計測・HF固定版全hash・実機解放を完了した。
実ブラウザ、実教師による学習、12 run比較、新モデルWeb配布とPhase7は未完了。
[機械可読の固定証拠](experiments/p6-operator-completion-2026-11-05.json)を併記する。

## 条件と結果

科学sourceは`80eb3b1a0456cbde73cbaa150232a51eb84ead13`。
同sourceの必須CI・全Native 1,291件・4変異shard・Security成功後に実行した。
Vast.aiのRTX5090×1、Python3.14.9、Torch2.14.1+cu130、CUDA13.0、driver595.99.02を使用。
実効CPU15.36、コンテナmemory上限64,403,537,920 bytesを確認した。

4構造は未学習seed66001の初期重みで、実Mのparameter数は以下のとおり。
ONNX opset18・固定batch1の全Policy 1,067,985要素／Value 1要素を、
凍結fixture0／3でCUDA FP32・Torch CPU・ORT CPU間で比較し、全32数値比較と合法手argmaxが一致した。
Policy atol／rtol1e-4、Valueは両方1e-5を変更していない。
Geometryの初期biasは0なので、初期出力のFullとの一致は構造の効果を示す結果ではない。

| 構造 | parameter数 | batch16 合成例/秒 | peak allocated GiB | ONNX MB（10進） |
|---|---:|---:|---:|---:|
| Full | 25,783,688 | 185.52 | 5.851 | 103.54 |
| Axial | 25,783,688 | 164.19 | 5.392 | 104.25 |
| Geometry-Aware | 26,098,120 | 169.08 | 5.888 | 138.88 |
| 3D-CNN | 28,606,344 | 206.62 | 1.137 | 114.69 |

各構造でbatch1／4／8／16、8 warmup＋32実測更新の全16組を完走した。
TF32を無効にし、測定区間の前後でCUDAを同期した。実更新は別のmodelで行い、その重みは破棄した。
公開した重みとONNXは更新前の初期重みである。

**この速度は実教師の学習速度ではない。** 合成負荷は密な全行動CE＋ゼロValue MSEと
既定AdamWであり、後続の合法手訪問分布・出所別batch・foreach/fused無効の学習処理とは異なる。
forward dense-MACのFLOPsはbackward・正規化・softmax・activation・IOを含む総学習FLOPsではない。
本学習の所要時間と共通計算予算は少量学習で別に測定・固定する。

## HF固定版と全hash

[operatorモデルの固定revision](https://huggingface.co/voxelshogi/voxelshogi-research-operator-probe-v1/tree/3874eae8754d94fc991873587c065ebaeee35451)へ、
4構造の初期weights・ONNX・全参照とCard／license／設定／manifest／検証を外部Linuxから直接保存した。
release SHAは`025abf923857ffac3c3ff6f6a1e456dae0008d80032cbc13d33a4bbf05c3758e`。
固定revisionの公開対象全ファイルのbytes・SHA-256、public/manual・Community OFFを照合した。
Apache-2.0、未学習であること・合成負荷の定義・数値許容差・未検証事項をCardで確認した。
Macには小さいmetadataだけを保存し、モデル・参照tensor・データの中継は0。

## 全工程と費用・解放

4構造の演算と数値照合は52.197秒、公開と固定revision全hash照合は137.735秒、
worker全体は192.103秒だった。観測したprocess群RSS最大は3,931,799,552 bytesで、
device memoryと区別し、未観測の瞬間peakとは扱わない。
環境導入・起動待ち・終了確認を含む作成要求→削除要求は1,252.329秒。
quoteによるcompute／disk見積もりはUS$0.202537で、転送料・確定invoice・予約上限US$2とは別である。

Vast実機`59207472`の削除応答、全inventoryからの不在、Vast／CloudRiftの全プロジェクト所有資源0を確認した。
local guardは終了し、不要になった専用independent deadlineの取消要求を送った。
累積35予約US$158／承認総枠200、未予約42を保持し、過去予約を減額していない。
用途別配分は既存枠内のPhase5=95／Phase6=44。無料HF保存の追加契約は行っていない。

## 次にすること

同じONNXとCUDA全参照を使う実ブラウザのWASM／WebGPU照合、実データの採用前監査と
訪問分布の特徴量cache、対照＋候補の2 run学習へ進む。
本比較の4構造×3 seed、選定した実学習モデルのFP32／FP16重み／INT8重みの配布、
観戦表示2案・実端末の各対応セル60分・公開E2Eまで、全1〜6の範囲を維持する。
