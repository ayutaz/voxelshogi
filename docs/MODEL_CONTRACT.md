# M3 モデル入出力契約 v1

2026-10-27。M3-0で固定する比較条件。標準1王 `voxelshogi-standard-v1` を対象とし、9王の正式採用は意味しない。ルールと合法手はRustで検証し、ここでは特徴量と出力ラベルだけを定義する。Pythonは3.14.9、依存追加は `uv add`、実行は `uv run --locked`、依存解決の正は `uv.lock`。

## 入力

- schema: `voxelshogi-standard-features-v1`。
- `features`: float32、shape `[batch,729,43]`。batch=1を必須とし、batch=8は追加測定。マス番号は `z*81+y*9+x`、x/y/zはいずれも0〜8。
- 手番が先手ならそのまま。後手なら全軸を反転（マス番号は `728-index`）し、先後の所有を交換する。出力は常に手番側の視点。絶対的な先後は別metadataに残す。
- channel 0〜28：空、手番側14駒種、相手側14駒種のone-hot。駒種順は `P,L,N,S,G,B,R,K,+P,+L,+N,+S,+B,+R`。成りは独立channel。
- channel 29〜35：手番側の持ち駒、36〜42：相手の持ち駒。順序 `P,L,N,S,G,B,R`。各カウントを標準駒集合の総数 `[162,64,48,32,16,24,24]` で割り、全729マスへ同じ値をbroadcastする。
- Pythonのエンコーダはshape・整数・範囲を検証する。駒配置の合法性、二歩、王手などを再実装しない。M3は手作りの固定fixtureも使い、M4でRust検証済みの局面へ接続する。

## Policy / Value

Policyはsoftmax前のfloat32 logits、shape `[batch,1067985]`。合法手集合の生成とマスク適用はRust由来の合法手を用い、モデル出力だけで着手しない。標準の全幅探索とは別の出力である。

| 指し手 | 手番側へ変換した後のindex |
|---|---|
| 通常移動 | `2*(from*729+to)+promote`。promoteは0か1。0〜1062881 |
| 駒打ち | `1062882+kind*729+to`。kindはP,L,N,S,G,B,Rの0〜6。1062882〜1067984 |

例：先手のfrom=0→to=728は1456、成りなら1457。後手のfrom=728→to=0も同じラベルになる。先手の歩打ちto=0は1062882、飛打ちto=728は1067984。移動不能なマスや同一マスも出力空間に含まれるが、合法手マスクで除外する。

Valueはfloat32、shape `[batch,1]`、手番側の勝ちを+1・負けを−1とするtanh出力。未学習のM3では勝率や棋力の指標として表示しない。教師ラベルの出所・終局までの条件はM4/M6で別に定義する。

## 代表構造・比較条件

729 token、幅256、6層、8 head、FFN幅1024のpre-norm Full Attentionを第一の代表構造とする。入力projectionと位置embedding、通常手のfrom/toの2組の射影・内積、駒打ちhead、Value headを含め5,021,064パラメータになった。seed314159・opset18・固定batch1のFP32変換をM3-1で実装し、5〜10Mの条件と6層の実行をテストする。正確な演算・ファイルhashと各比較値は生成manifestへ記録する。browserのために無記録で小さくしない。

全出力のshape・有限性を必須とし、空出力・NaN/Infを拒否する。各要素で `abs(actual-reference) <= atol+rtol*abs(reference)` を確認する。FP32はatol=1e-5／rtol=1e-4、FP16は1e-3／1e-2を事前の基準とする。以下の低精度変換条件も、各変換版の最初の実測前に固定する。

### M3-3で比較する変換方式

- FP16：同じFP32 ONNXからonnxconverter-commonで変換し、入出力はfloat32のまま保つ。非ゼロの最小値はIEEE FP16 subnormalの2^-24、最大は65504を指定する。converterの既定の非対応演算block listを記録し、その演算はfloat32を保つ。グラフ内の型とCastをmanifestへ記録し、すべての演算がFP16になったとは仮定しない。[ORT公式の変換設定](https://onnxruntime.ai/docs/performance/model-optimizations/float16.html)
- INT8（重み）：rankが2以上のfloat32 initializerをtensorごとに対称量子化する。`scale=float32(max(max(abs(w))/127, float32の最小正規値))`、すべて0ならscale=1、zero pointはint8の0。`q=int8(clip(roundTiesToEven(w/scale),-127,127))` とし、[ONNX DequantizeLinear](https://onnx.ai/onnx/operators/onnx__DequantizeLinear.html) の `(q-zero_point)*scale` でfloat32へ復元して既存の演算へ渡す。bias・normの1次元重み、activation・演算自体はfloat32。転送ファイルの重み圧縮であり、INT8演算による高速化・実行メモリ削減は保証しない。
- INT8版の同じ変換ファイルの基準実装対browserは、float32計算のatol=1e-5／rtol=1e-4で全出力を照合する。FP32からの変化は、FP16・INT8とも別の記述統計（最大絶対／相対誤差、平均絶対誤差・RMSE・Policyのargmax一致）として保存し、runtime合否の誤差に混ぜない。未学習のため、その差を棋力低下とは呼ばない。
- INT8のgraph optimizationは基準実装・browserとも **basic** に固定する。小行列の手計算テストで、ORT1.31.1のextended/allがDQ→MatMulを `MatMulNBits` へ変換し、期待 `[-126,4,257]` に対して `[-127,3.984253,256.99994]` を返すことを検出した。basic/disabledでは期待値と完全一致した。INT8の圧縮形式を保ち、近似が追加される最適化を使用しない。FP32／FP16はallを使い、設定差を測定記録に残す。
- 各形式の基準値はそのONNXを基準実装で実行して保存する。実行不能の場合は理由を記録し、FP32の別モデルで基準値を代用しない。browser未対応の形式×backendも理由を表示する。

変換前PyTorch対FP32 ONNX、各変換版の基準実装対browser、FP32対各低精度版を分ける。最大絶対／相対誤差・超過件数と全要素数を保存する。Top-1だけで成功扱いにしない。閾値変更は原因と根拠を先に記録し、該当比較を再実行する。

M3-0の小演算テスト `y=2*x+1` は依存・dynamo exporter・CPU ORTの動作確認に限る。これが通っただけでは代表モデルやWebGPUが動いたとは扱わない。
