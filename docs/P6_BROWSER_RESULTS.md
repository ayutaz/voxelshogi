# 実M構造のブラウザ測定結果（2026-11-12 JST）

測定source `8b4289ff0b3354633d271627580480de8170bfcd`、Vast RTX5090／AMD EPYC7B12上の
実Chromium 156.0.8078.4、ORT Web 1.31.1、WASM 1 thread。
対象は未学習のFull／Axial／Geometry／3D-CNNであり、学習済みMの棋力・端末対応を示す結果ではない。

4構造×WASM／WebGPUの全8ケースを終了したが、WASM成功は3構造で、全4構造成功の完了条件は未達。
全ケースでfixture 0／3、各8 warmup＋32測定を予定した。
下表の時間は成功ケースの各fixtureの平均推論msで、初期化時間を含まない。

| 構造 | backend | 結果 | fixture 0／3の平均ms |
|---|---|---|---|
| full | wasm | 成功 | 1822.9／1827.4 |
| full | webgpu | 180秒上限で終了 | 取得できず |
| axial | wasm | 180秒上限で終了 | 取得できず |
| axial | webgpu | 180秒上限で終了 | 取得できず |
| geometry | wasm | 成功 | 1859.9／1859.0 |
| geometry | webgpu | 180秒上限で終了 | 取得できず |
| cnn | wasm | 成功 | 1586.4／1590.9 |
| cnn | webgpu | 180秒上限で終了 | 取得できず |

成功した3ケースは全Policy／Value出力の数値基準と合法手argmax一致を確認した。
Geometryの初期biasは0であり、Fullとの数値一致を学習後の構造効果とは扱わない。
時間上限の5ケースは読込・session作成・初回推論・反復推論のどこで止まったか未確定。
WebGPU一般の非対応や数値不一致と断定しない。次は段階別進行記録を加え、同じ測定数・数値基準で再検証する。

## 保存・監査・資源

全8ケースの生データと失敗、実機情報を[HF固定版](https://huggingface.co/datasets/voxelshogi/voxelshogi-research-browser-v1/tree/82597bb0a16c6e8d5cacaecdc58d29bc27816d09)に保存した。
public/manual、Community OFF、Dataset Card、CC-BY-4.0、外部Linuxでの全ファイルhash照合を確認。
release hashは`53c43d684630617991042da8e4af8ed60d3eb93595a9cd0a4063c095df47f8ca`。

同じホストで11,534件から280重複を除いた11,254件と、開発48局・全24,579 NN参照の監査を再実行した。
[監査HF固定版](https://huggingface.co/datasets/voxelshogi/voxelshogi-research-pilot-admission-v1/tree/0e6edc0984b07dd2bd9f380add7b35f27799a715)も外部Linuxの全hash照合済み。
少量学習の凍結済み入力revisionは元の版を維持し、この再監査結果へ暗黙に差し替えない。

旧実機`60266373`はワーカー終了後約66秒で削除応答を受け、不在を確認した。
集計worker全体はWASM全4成功に届かず失敗として終了し、保存・資源解放の成功と区別する。
旧実機用の独立期限workflowも停止要求後の`completed/cancelled`を確認した。
この解放確認は少量学習用の別実機`60271691`が存在しないことを意味しない。

[調査証跡](experiments/p6-resumption-2026-11-12.md)・[ここからの計画](P6_RESUMPTION_PLAN.md)。
