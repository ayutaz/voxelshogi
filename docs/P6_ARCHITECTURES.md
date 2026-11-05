# Phase6：4構造の初期実装契約

2026-11-05。4構造の演算・モデル境界を用意する段階であり、学習比較や棋力改善の結果ではない。
M6の5Mモデル・checkpoint・配布物・数値許容差は変更しない。
`export/research_contract.py`に不変の設定、`export/research_model.py`に別のfactoryを置く。
モデルの構築・実行・ONNX変換はLinux CI／外部Linuxのみで行う。

## モデルの定義

| 構造 | 幅 | block数 | heads | FFN幅 | trainable parameter数 |
|---|---:|---:|---:|---:|---:|
| Full Attention | 512 | 8 | 8 | 2048 | 25,783,688 |
| Axial Attention | 512 | 8 | 8 | 2048 | 25,783,688 |
| Geometry-Aware Attention | 512 | 8 | 8 | 2048 | 26,098,120 |
| 3D-CNN | 256 | 8 | attentionなし | FFNなし | 28,606,344 |

上表はコードと手計算の期待値であり、各実モデルのparameter数はLinuxのNativeテストで照合する。
同じparameter数でも同じFLOPs・速度にはならない。異なる幅や構造も実験条件に明記する。

共通の入力は既存の`[batch,729,43]`、x-fastの9×9×9 token。
線形入力と学習可能な729位置embedding、最後のLayerNorm、既存のfrom/to・成り・打ちPolicy Headを使う。
Policy rank64、Valueは平均pool→幅64 GELU→scalar tanh。
出力は既存の1,067,985 actionと`[batch,1]` Valueで、ルールはRustだけが判定する。
Valueの教師・尺度は別の学習protocolで固定し、tanhだけを理由に勝率とは呼ばない。

- Fullは既存の明示QK／softmax／AVのAttentionを再利用し、pre-LayerNorm residualとFFN residualを持つ。
- Axialはx→y→zの順に長さ9のline Attentionを3回適用し、その合成結果をblockの外側でresidualへ加える。
  **3軸のQKV／outは共有**する。軸ごとの個別projection・residualを持つ別方式とは区別する。
  同じprojectionを3回使うため、projection FLOPsを1回分へ減らして数えない。
- GeometryはFullの各headへ学習可能なsigned 3D相対biasを加える。
  query−keyの各軸−8〜8、17³＝4,913 entry／head／block。x-fastでindex化する。
  表のindexは固定buffer、bias自体は学習parameter。距離の絶対値や全head共通biasへ置換しない。
- CNNはLayerNorm→3³ Conv→GELU→LayerNorm→3³ Conv→residualのblockを8回使う。
  Convはstride1・zero padding1、batch,z,y,x,channelの座標を保持する。
  BatchNormの統計やattention FFNは追加せず、全幅を混合するdense Convとする。

## 計算量の記録

`forward_matmul_flops`は、1 multiply-add＝2 FLOPsの**forward dense MAC部分**を計算する。
入力線形、QKV／out、QK／AV、FFN、Policy／Value head、paddingを含むdense Convを数える。
backward、LayerNorm、GELU／softmax、bias加算、index、IOは含まない。
Geometryのbias加算やAxialのreshape／permuteも総計測から省略してよい、という意味ではない。

この値単独を「学習全体のFLOPs」「実GPU性能」「実行時間」として使わない。
本比較の前にbackward・その他演算を含めた算定方法、学習量、同予算の許容差、batch／蓄積と精度を固定する。
4構造を同じepochだけ学習して同じ計算量と称することはしない。

## 検証と未完了の範囲

純粋metadataテストではM規模parameter数の手計算、極小形状のMAC FLOPsとsigned index、設定の不変性と不正値拒否を確認する。
Nativeテストでは、scalar Pythonの独立Attention、明示的なx／y／z line走査、手書きの+x畳み込みで演算を照合する。
さらに全4構造のblock実行・勾配・seed再現・呼び出し側乱数の保持、実M parameter数を確認する。
極小形状の4構造は実ONNXを生成し、ORT CPUとTorchを異なる2入力で照合する。
これらをMacで実行せず、Linux CIで検証する。

極小形状のONNX成功は、729 token・Mモデルの配布・WebGPU対応や速度の証拠ではない。
続く外部試行で、実M形状の正しさとONNX全出力、実ブラウザWASM／WebGPU、VRAM、更新と全工程の時間を測る。
学習loader・checkpoint binding・配布catalogへは、構造と設定を明示して接続する。
既存M6 loaderで新構造を黙って読み込ませない。
本学習・複数seed・評価・HF公開・正式な端末対応は未完了として残す。
