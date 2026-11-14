---
license: apache-2.0
language:
- ja
tags:
- voxelshogi
- three-dimensional-shogi
- onnx
- supervised-learning
---
# VoxelShogi Transformer-S

9×9×9の三次元将棋を指す、約502万パラメータの学習済みAIです。
**[ブラウザで対戦・観戦する](https://voxelshogi.yousan-apps.workers.dev)** →「AIと対戦」→「学習済みS」。申請・ログインは不要です。
強さを追求する途中の研究モデルです。

## Training and provenance

6層のTransformerを、浅い探索AIの指し手と評価値で教師あり学習しました。seedは314159。
[VoxelShogi Synthetic v1](https://huggingface.co/datasets/voxelshogi/voxelshogi-synthetic-v1/tree/6e7fb29d2469b56a895042fbb089d86e7b4d074f)（ayutaz / VoxelShogi contributors、CC-BY-4.0）を使用し、重複を除いた教師を学習29,884・検証3,421・テスト3,589局面に分けています。
学習元コードは`874aed9ac28c9e50e178c2dda706941b2d3294da`、変換元は`5415899c445b95c5ce19d3a79c1ebb55f48bf642`。
構造・学習条件・ファイルごとのSHA-256は[manifest.json](manifest.json)、詳細な初回記録は[旧カード](https://huggingface.co/voxelshogi/voxelshogi-transformer-s/blob/f196c75236f0f0cfd028b91661b39a2c64ee448f/README.md)を参照してください。

## Evaluation

テスト3,589局面で、教師の指し手と一致した割合です。**勝率ではありません。**

| 配布形式 | ONNX容量 | 指し手の一致率 |
|---|---:|---:|
| FP32 | 20.46 MB | 75.592% |
| FP16（重み） | 10.46 MB | 75.592% |
| INT8（重み） | 5.47 MB | 75.536% |

各形式の固定60対局では、ランダム相手40局はすべて256手で打ち切り、探索AI相手20局で勝利はありませんでした。棋力の向上は未確認です。
長い対局・終盤の学習は不足しています。評価値は探索値を模倣したもので、勝つ確率を表しません。数値・対局条件の詳細は[検証記録](https://github.com/ayutaz/voxelshogi/blob/main/docs/M6_PORTABLE.md)にあります。

## Inference

Web版で3形式を選べます。モデルは必要なときに取得し、端末内のWorkerで動きます。初回はランタイムと数値検査用データも読み込みます。
FP16とINT8は**重みの圧縮**で、演算はFP32です。INT8には上表の精度差があり、圧縮しても高速化は保証しません。
独自実装では、729マス×43チャンネルの入力、1,067,985手の出力契約と**合法手マスク**が必要です。Web版はhashと同形式の参照出力を検査してから着手します。

## Access and license

このS推論用リポジトリはpublic・取得ゲートなし、CommunityはOFFです。Apache-2.0（[LICENSE](LICENSE)）。モデルの利用・ダウンロードに申請は不要です。
データセットと学習再開用の別リポジトリには、それぞれの取得条件が適用されます。今回、モデルの重みは変更していません。
