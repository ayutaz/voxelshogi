# M6のブラウザ向け変換と検証済みHF配布

2026-10-29 UTC。混合精度FP16のブラウザ数値検証が失敗したため、FP16重み・FP32計算の形式を追加し、全3形式を新しい実ファイルで固定評価した。本記録は候補計測時点の履歴。公開catalog差し替えなしの実機検証・資源終了を含む最終状態は[M6完了記録](M6_COMPLETION.md)を参照。 [固定集計](experiments/m6-portable-release.json)。

## 目的とゴール

ユーザーが評価済みの同じ変換ファイルを取得し、公開Arenaで形式を選んで観戦できるようにする。完了には固定評価、HF全件hash照合、公開catalog一致、実モデルの全48条件・40実切替と合法な着手、停止・中断・人間対AI、資源終了の証拠をそろえる。精度や速さの改善は実測結果として扱う。

## 形式と来歴

FP16重み版はrank2以上の重みをFP16で保存し、明示的なCastでFP32計算へ渡す。bias・活性はFP32。画面は「FP16（重み）」と表示し、native FP16演算とは呼ばない。INT8も重み量子化・FP32計算。容量低下をそのまま速度・メモリ低下とは呼ばない。

学習元は`874aed9ac28c9e50e178c2dda706941b2d3294da`、変換・新ONNX評価元は`5415899c445b95c5ce19d3a79c1ebb55f48bf642`。明示的な`export_provenance`で結び付け、元のcheckpoint・Torch評価を別sourceへ書き換えていない。再生成でONNXのhashが変わったため、FP32・INT8も旧評価を流用せず、全3形式を各test3,589件・Random40局・M1探索20局で再評価した。元の5モデル評価と失敗は[初回変換記録](M6_MODELS.md)・[FP16診断](experiments/m6-fp16-portability-diagnosis.json)へ保持する。

| モデル | test Policy Top-1 | Value MSE | M1探索20局：勝／敗／引分／打切り |
|---|---:|---:|---|
| 初期Torch | 1.950% | 0.2309179 | 0／0／18／2 |
| 学習済みTorch | 75.592% | 0.03374008 | 0／3／9／8 |
| FP32 ONNX | 75.592% | 0.0337401 | 0／3／9／8 |
| FP16重み版ONNX | 75.592% | 0.0337383 | 0／3／9／8 |
| INT8重み版ONNX | 75.536% | 0.03367491 | 0／4／9／7 |

Random40局は各モデルすべて打切り。最大256手、同じ序盤・先後入替・探索上限とpaired bootstrapを使用する。打切りを引分・敗北へ変えない。教師再現精度の向上は確認できたが、探索AIに対する棋力向上は確認できていない。INT8のTop-1は3,589件中2件分低下。testによる学習・checkpoint選択はしていない。

| 形式 | Bytes | SHA-256 |
|---|---:|---|
| fp32 | 20,461,391 | `8bd7bd91e38d7319f72b87495f63f0a86a85f3759d22913f787d963834b92e63` |
| fp16 | 10,463,104 | `b22a7fd9a5e31a15cc6fb15cca76b945bed3cac6ce199b62294c885840f4dd0a` |
| int8 | 5,467,835 | `12b225402ce32d483e44ba766d7c695e08698408d310e8f88197a8a2ef92deb9` |

## HFとブラウザ候補検証

[固定HF revision](https://huggingface.co/voxelshogi/voxelshogi-transformer-s/tree/f196c75236f0f0cfd028b91661b39a2c64ee448f)をpublic/manual・Community OFF・Apache-2.0で公開し、全37ファイルをLinuxから再取得・bytes／SHA-256照合した。Model Cardには各形式の評価・差・容量・実機候補性能、学習元と変換元、取得条件・制約を記載した。モデル・データ・checkpointはMacへ中継していない。

HFの取得申請が承認されたら、HF CLIでログインしてフォルダー全体を取得できる。リポジトリのuv環境を使う場合は次のとおり。

```bash
uv run --locked hf auth login
uv run --locked hf download voxelshogi/voxelshogi-transformer-s \
  --revision f196c75236f0f0cfd028b91661b39a2c64ee448f \
  --local-dir ./voxelshogi-model
```

公開Arenaで「学習済みモデルを読み込む」を開き、`voxelshogi-model`フォルダーを選ぶ。先後を「学習済みモデル」にして精度形式・実行先を選ぶ。HF CLIの資格情報はブラウザへ渡さない。

公開アプリ`47d27b32dbf5bf21a3ea5eb99d59529e7b5955c1`上で、候補catalogだけを私的に差し替え、実際の学習済み全3形式×WASM／WebGPU×4入力×2D／3Dの48条件、各準備10回＋測定30回、backendごと20実切替を完了した。[元の実機記録](experiments/m6-portable-browser-candidate.json)のSHA-256は`7199ff1d6a699dca26e6a8ffc4c8a550d07ce4bc50fd132ccb21100f069d2a2d`。全条件の同形式全出力照合、実provider、Rust合法手、3D描画とtrusted camera入力、Worker終了、5秒以内の資源観測を検査した。

初期局面・3D表示ありの同一条件での推論時間（ms、CPUへの出力readback込み、準備10回後の30回）：

| 実行先 | 形式 | 中央値 | P95 |
|---|---|---:|---:|
| WASM | FP32 | 254.2 | 255.8 |
| WASM | FP16重み | 253.9 | 256.8 |
| WASM | INT8重み | 260.5 | 268.3 |
| WebGPU | FP32 | 8.6 | 16.6 |
| WebGPU | FP16重み | 9.4 | 13.6 |
| WebGPU | INT8重み | 9.3 | 11.5 |

この条件では容量の小さい重み版が一律に速いという結果にはなっていない。ほかの入力・2D条件、初回、往復時間、資源観測は元記録とModel Cardに保持する。

物理RTX5090／Linux／Chromiumの結果であり、未測定の端末へ一般化しない。NVIDIAの実験的shader-f16有効化フラグは使わない。[学習済み数値契約](M6_MAIN.md#fp32変換の失敗と次の基準)は維持した。main heapはWorker／GPUを含まず、Chrome RSSは共有ページを重複計上し得る。GPU全割当量は取得できない。観測値はピーク保証ではない。

同じモデルの前回計測は数値48条件・40切替に成功したが、WASMの準備中に操作を使い切り、測定中のtrusted入力が0のため全量検査が失敗した。[失敗した元記録](experiments/m6-portable-browser-interaction-failed.json)は保持する。操作開始を測定リクエストのpending後へ移したhelper `f279649cc95ab76ae88ab86371a5f53c3552b991`で再計測し、必須8チェック・関連CIの成功後に受理した。閾値や成功条件の緩和はしていない。

この記録は`candidate=true`で、最終の公開catalogの証拠とは区別する。次はPRの必須CI・通常取り込み・自動公開後に、差し替えなしの全48条件・40実切替、実Arenaの3GPU形式と7 E2Eを検証する。HF取得ゲートを迂回する重みのCloudflare複製は行わない。

同じ最終HF配布を使う[候補Arenaの実ONNX E2E](experiments/m6-portable-arena-candidate.json)も7件・58.6秒で成功した（retry／skip／flakyなし）。3形式の合法手・条件付き棋譜、速度・自動再生、3D準備中の操作と中断、破損拒否、GPUなし時の明示エラーと人間対AI、実計測driverのsmokeを確認した。公開URL上でcatalogだけを差し替えた候補検証であり、差し替えなしの最終公開検証とは区別する。
