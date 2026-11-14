---
license: apache-2.0
datasets:
- voxelshogi/voxelshogi-synthetic-v1
tags:
- voxelshogi
- shogi
- board-games
- transformer
- onnx
- supervised-learning
---

# VoxelShogi Transformer-S

**9×9×9の三次元将棋で、指し手と局面の評価値を予測する小型Transformerモデルです。**
探索AIを教師とした教師あり学習で作成し、ブラウザでのAI対局やモデルの比較研究に利用できます。

[ブラウザで試す](https://voxelshogi.yousan-apps.workers.dev) · [ソースコード](https://github.com/ayutaz/voxelshogi) · [評価の詳細](https://github.com/ayutaz/voxelshogi/blob/main/docs/M6_PORTABLE.md)

## モデル概要

| 項目 | 内容 |
|---|---|
| 開発 | VoxelShogi |
| 構造 | Transformer・6層・約502万パラメータ |
| 入力 | 三次元将棋の局面（729マス × 43特徴量） |
| 出力 | 指し手のスコア（policy）と手番側から見た局面評価（value） |
| 配布形式 | ONNX：FP32・FP16重み版・INT8重み版 |

## 使い方

Web版の「AIと対戦」→「学習済みS」から形式を選んで対戦できます。申請・ログインは不要です。
モデルは自動で取得し、端末内のWeb Workerで推論します。AI同士の観戦では「対局設定」で選択できます。

独自に組み込む場合は[入力・出力仕様](https://huggingface.co/voxelshogi/voxelshogi-transformer-s/blob/main/manifest.json)を参照してください。
指し手の出力は固定長の行動空間であり、**ルールエンジンが生成する合法手マスク**を適用して選択する必要があります。

## 配布形式と評価

同じ学習済みモデルから変換した3形式です。「教師一致率」は、テスト3,589局面で教師と同じ指し手を選んだ割合で、勝率ではありません。

| ファイル | 容量 | 教師一致率（Top-1） |
|---|---:|---:|
| `fp32.onnx` | 20.46 MB | 75.592% |
| `fp16.onnx` | 10.46 MB | 75.592% |
| `int8.onnx` | 5.47 MB | 75.536% |

FP16・INT8版は重みを圧縮し、演算はFP32で行います。INT8版の一致率はFP32版より0.056ポイント低下しています。容量の削減が推論の高速化を保証するものではありません。

## 学習データと方法

[VoxelShogi Synthetic v1](https://huggingface.co/datasets/voxelshogi/voxelshogi-synthetic-v1/tree/6e7fb29d2469b56a895042fbb089d86e7b4d074f)の探索教師を使用しました。
重複を除いた学習29,884・検証3,421・テスト3,589局面を使い、指し手と探索評価値を学習しています。
AdamWで3 epoch学習し、検証損失でモデルを選択しました。テスト局面は学習・モデル選択に使用していません。

## 制約

各形式の対局評価では、ランダムAIとの40局はすべて256手で打ち切り、探索AIとの20局で勝利はありませんでした。**教師の指し手を再現できることと、対局で強いことは別で、棋力の向上は確認できていません。**
局面評価は探索値の近似であり、勝つ確率を表しません。

## ライセンス・再現情報

モデルは[Apache-2.0](https://huggingface.co/voxelshogi/voxelshogi-transformer-s/blob/main/LICENSE)。学習データはayutaz / VoxelShogi contributorsによるCC-BY-4.0です。
学習・変換条件、生成元コードのcommit、各ファイルのSHA-256は[manifest.json](https://huggingface.co/voxelshogi/voxelshogi-transformer-s/blob/main/manifest.json)に記録しています。
