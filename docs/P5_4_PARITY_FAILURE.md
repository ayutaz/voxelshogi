# P5-4：4GPU保存再開の不一致

2026-11-04 15:51 UTC。**実1／2／4GPUの連続128更新と各64＋64更新は実行したが、4GPUの再開後のmodel・optimizerが許容差を超えた。P5-4は未完了。** 原因を修正し、同じ条件の全3構成を改めて検証する。[実行計画](P5_4_PLAN.md)の完了条件は維持する。

## 実測と判定

sourceは`4746e1a0067d8ed6409935ffa3ac7ceda15b4d5a`。同一ホストのRTX5090×4、driver615.71.09、Python3.14.9、Torch2.14.1+cu130、CUDA13.0を使用した。全4GPUの独立CUDA計算・勾配とNCCLの和の検証を通してから測定した。

同じM6初期重み、検証済み7,788 sample、global batch16、seed63001、AdamW、FP32・TF32無効、128更新を固定した。先頭16更新を準備とし、残り112更新・1,792例を主測定とする。別の再開検証は64更新で保存し、固定HF revisionから新しいmodel／optimizerへ復旧して64更新した。再開検証の更新をthroughputへ足していない。

| GPU数 | 主測定 examples/s | 主測定window秒 | 1GPU比 | 128更新と64＋64更新の比較 |
|---|---:|---:|---:|---|
| 1 | 209.460574 | 8.555309 | 1.000 | model・optimizer・RNG完全一致 |
| 2 | 313.171316 | 5.722108 | 1.495 | model・optimizer・RNG完全一致 |
| 4 | 415.082849 | 4.317210 | 1.982 | model・optimizer不一致、全4rankのRNG一致 |

単一ホスト・各1回の測定であり、他ホストや大きなモデルの速度へ外挿しない。全4GPUの借用料金には未使用GPUも含まれる。通信probe、rank別VRAM、使用GPU時間と準備時間を含む詳細は、下記の固定HF評価データに保存した。これは4GPUの再現性を満たした性能比較ではない。

4GPUの最終modelの最大絶対差は`0.0005349568091332912`、optimizerは`0.00001802295446395874`。modelの`atol=1e-6, rtol=1e-5`、optimizerの`atol=1e-7, rtol=1e-5`を超えた。step128・2,048例のcursorと全rankのRNGは一致した。許容差は変更していない。

中間checkpointから固定HF版への転送・新runへのCPU復元は356 tensor・5,163 scalarで完全一致した。したがって確認できたのは「archiveの復元は一致するが、その後の4GPU更新が連続実行と一致しない」という境界である。GPUの子学習processは正常に128更新を完走し、後続の比較processが不一致で終了した。前試行のNVML故障とは区別する。

## 修正と検証方針

4rankの浮動小数点加算順がprocess再作成で変わる可能性を調べる。これは仮説であり、実機での再検証前に原因を確定しない。

DDPの勾配bucketをFP32のままall-gatherで運び、rank0→1→2→3の順で加算してrank数で割るhookを追加する。順序を固定するための追加通信・メモリを含め、速度を再測定する。量子化や許容差の緩和は行わない。新しいbindingは`voxelshogi-distributed-training-v2`と`gradient_reduction=rank-ordered-float32-v1`を記録する。旧v1 archiveは旧契約として読み取れるが、v2の更新へ同一契約と見なして再開しない。

手計算のFP32丸めと入力不変性、実4rank Glooでのhook登録・勾配、実2／4rankのAdamWとarchive経由の継続を検証する。CPU CIの一致だけでGPU実測の再開一致を達成したとはしない。[PyTorchのhook仕様](https://docs.pytorch.org/docs/2.14/ddp_comm_hooks.html)に従い、hookは一度だけ登録し、rank平均後のbucketと同形状のTensorをFutureで返す。

## 保存・解放・残る上限

全6 checkpointをstate専用repo、4GPUの連続／再開の最終modelだけを診断repo、全3構成と失敗判定を評価datasetへ外部Linuxから直接保存した。public/manual・Community OFF・Card・license・固定revision全hashの照合を確認した。Macには小さいmetadataだけを回収した。

- [全3構成と不一致を含む評価dataset](https://huggingface.co/datasets/voxelshogi/voxelshogi-distributed-benchmark-v1/tree/f147d5e5a4cb33864d0be402ab080dbd513bde1f)：CC-BY-4.0。`pipeline_complete=false`。
- [4GPU最終model対](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-diagnostics-v1/tree/3599c585e096177881fa87ee0bc8074cf01b01b4)：Apache-2.0、FP32 safetensors。optimizer・RNGは含めない。

| state | 固定HF revision |
|---|---|
| 1GPU中間 | [c3aa3e9](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1/tree/c3aa3e926a6e1418d86843b06ec2fc2f5aa220b0) |
| 1GPU最終 | [c155f2e](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1/tree/c155f2e2ecdd0708ff080db9f703ef96826dd42e) |
| 2GPU中間 | [401ad03](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1/tree/401ad03d6cbde59ceee918774f25250ed29eaaad) |
| 2GPU最終 | [108464b](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1/tree/108464b9b88370e9939bbac6a27e10531098c027) |
| 4GPU中間 | [c428b91](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1/tree/c428b919187b946dc3d0c071f40bfa1e60707bd5) |
| 4GPU再開後最終・不一致 | [f42f8cf](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1/tree/f42f8cfee5b76a359ffe224012b501668c7d0769) |

保存・照合後、15:51:09 UTCに所有VMの削除とVast／CloudRiftのプロジェクト課金資源0を確認した。独立期限guardは解放後に取り消した。保守的な予約は31件・US$133／200で保持し、実請求と区別する。

共通state upload ledgerは15予約・1,044,495,137／1,073,741,824 bytesで、残り29,246,687 bytes。約60MBのarchiveをもう1件送る余地がない。[累積1GiBの保存上限](M6_STATE_RELEASE.md)と過去予約を維持し、上限の再承認なしに増量・履歴削除・ledgerの初期化をしない。次の有料試行は修正の必須CIと保存容量の条件をそろえてから起動する。
