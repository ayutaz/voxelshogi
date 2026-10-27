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

全出力のshape・有限性を必須とし、空出力・NaN/Infを拒否する。各要素で `abs(actual-reference) <= atol+rtol*abs(reference)` を確認する。FP32はatol=1e-5／rtol=1e-4、FP16は1e-3／1e-2を事前の基準とする。量子化版のscale・zero point・丸めと誤差の基準は、対象の量子化方式を決めて実測比較する前に追記する。

変換前PyTorch対FP32 ONNX、各変換版の基準実装対browser、FP32対各低精度版を分ける。最大絶対／相対誤差・超過件数と全要素数を保存する。Top-1だけで成功扱いにしない。閾値変更は原因と根拠を先に記録し、該当比較を再実行する。

M3-0の小演算テスト `y=2*x+1` は依存・dynamo exporter・CPU ORTの動作確認に限る。これが通っただけでは代表モデルやWebGPUが動いたとは扱わない。
