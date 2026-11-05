# P5-4：1／2／4GPUの実測と保存再開

2026-11-05 00:13 UTC。[今回の1〜5](P5_3_PLAN.md)の5番目について、同じ所有4GPUホスト上の1／2／4GPU、各64更新→HF固定版→新model／AdamWへの復旧→残り64更新、6 state archive、結果datasetの全hashと最後の資源解放を確認した。目的は同じ学習量に対するGPU並列化の投資効果を測ることであり、棋力改善やPhase6の完了ではない。

## 固定条件と実行環境

source `0171a6b7113bc16ed2a0d8b72cebac2ccd96420f`。M6開始重み、自己対局由来の保護除外済み7,788入力、global batch16・seed63001・128更新・準備16更新・AdamW・FP32・TF32 OFFを固定した。全構成の同じglobal scheduleは`901ede2099be79b6a331c19ea9ab2eae3f3c4b51a35bf0d14bf19a8cd1ec5d7b`。各rankのbatchは16を等分し、GPU数ごとの追加・複製・間引きは行わない。7,788件には学習集合内の同一入力の再出現185件を含み、そのまま全構成で共有した。保護入力との重複除外は0件。元入力・設定・全revisionとhashは[機械可読記録](experiments/p54-completion-2026-11-05.json)とHF manifestに保持する。

Vast.aiのRTX5090×4、instance 59172937、host54141。Python3.14.9、Torch2.14.1+cu130／CUDA13.0、driver610.57.04。実コンテナのCPU quotaは30.71999相当、メモリ上限183,351,902,208 bytes。CPU／RAMの専有保証ではない。親のTorch処理と各rankを2threadへ制限した。物理UUID4台の個別CUDA行列積・勾配検査と、実4rank NCCLの手計算1+2+3+4=10に成功し、全3構成で同じUUID列の先頭1／2／4台を使った。実CPU affinity・cgroup・GPU接続図・lscpuはHF manifestに記録した。

全worldでv2 bindingの`gradient_reduction=rank-ordered-float32-v1`を固定した。勾配をall-gatherで転送し、rank順のFP32加算と平均を使う。前試行の[4GPU再開不一致](P5_4_PARITY_FAILURE.md)は負の結果として保持し、今回の速度と混ぜない。

## 連続128更新の主測定

測定窓は準備後の112更新・1,792例。保存再開の検証更新は主測定へ合算しない。

| 使用GPU | 測定窓 秒 | 例／秒 | 1GPU比 | rank最大 allocated / reserved GiB | 独立all-reduce平均 ms | 主測定の割当GPU時間 h |
|---|---|---|---|---|---|---|
| 1 | 10.916352 | 164.157 | 1.000 | 3.435 / 3.850 | 通信なし | 0.00379347 |
| 2 | 8.660872 | 206.908 | 1.260 | 1.816 / 2.004 | 4.574 | 0.00612847 |
| 4 | 8.044092 | 222.772 | 1.357 | 0.988 / 1.148 | 5.423 | 0.01143581 |

測定窓はCUDA同期後のrank最大wall時間で、中間保存とevent IOを含み、最終checkpointを除く。同期更新時間の合計と全128更新のattempt wallはJSONへ別々に残す。VRAMは各rankのTorch peakの最大で、device全体の総使用量ではない。通信probeはモデルFP32勾配相当byte、準備5回＋測定20回の単独all-reduceであり、DDP学習中の通信割合ではない。割当GPU時間は使用GPU数×全128更新のattempt wall／3600で、実GPU稼働率ではない。

同じ小型モデル・global batch16・各1試行の実測であり、他のモデル規模・batch・hostへ速度比を外挿しない。[先行ホストの1GPU部分値](P5_4_STARTUP.md)は今回の表へ合算していない。

4GPUの速度比1.357を台数4で割った台数当たりの効率は約33.9%。現条件では4台に増やす効果は限定的だった。全4台を借りる料金と実使用GPU時間を区別し、次のモデル・batchの費用を理想的な4倍高速化から見積もらない。

## 各構成のHF保存と実GPU再開

1／2／4GPUそれぞれで独立した64＋64更新を実施し、連続128更新と比較した。modelはatol1e-6／rtol1e-5、optimizerはatol1e-7／rtol1e-5という実行前の許容差内で一致。全rankの乱数とcursorは完全一致を要求し、全3構成が合格した。実際のmodel・optimizer・全rankのRNGは全3構成ともbit単位で完全一致し、最大絶対差は0だった。modelやoptimizerを省略せず、typed JSON＋safetensorsへ保存した。GPU数間の重みbit一致や棋力改善の証拠とはしない。

| GPU | 保存点 | HF固定revision | bytes |
|---|---|---|---|
| 1 | mid | [5c6250f](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1/tree/5c6250fe7b9abca35d5bcb7ef0af5ab9778e0837) | 60,412,242 |
| 1 | final | [8e6a722](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1/tree/8e6a722e69d261bb9b730b2942f69f6c3afef045) | 60,433,321 |
| 2 | mid | [cbd7f7d](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1/tree/cbd7f7dc42ac822508e92d4663e4bfdd4ce84933) | 60,460,090 |
| 2 | final | [3e06459](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1/tree/3e06459b6b8c2ee078024fed53d99e2db9ec2b4d) | 60,481,147 |
| 4 | mid | [73f3eb9](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1/tree/73f3eb972a9ef94808634e0010cd4ca2c5333d9c) | 60,555,818 |
| 4 | final | [669866c](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1/tree/669866cd055601178440ac13a646f2af72d1b0af) | 60,576,877 |

stateはApache-2.0。3行の測定・通信・再開結果と実行sourceをまとめた[結果datasetの固定版](https://huggingface.co/datasets/voxelshogi/voxelshogi-distributed-benchmark-v1/tree/05759b1de6dbb4f15a2b9f017902cdb7bf10d55e)はCC-BY-4.0。すべてpublic/manual・Community OFF・Card付きで、外部Linuxから公開ハーネスを使い、返された固定revisionの全bytes／SHA-256を照合した。Macへデータ・checkpoint・state tensorを中継していない。共通upload ledgerは既存15件を含む21件・1,407,414,632／2,147,483,648 bytesを保持する。累積2GiBはユーザー承認に基づくプロジェクトの自主上限であり、HFの契約容量の変更や有料storage購入ではない。

## 準備・工程別時間と費用

worker全体は676.038秒。取得・復旧、各構成の主測定、再開検証、HF保存はJSONの工程別時間へ分けた。主測定processの起動・cache全hash検査・初期化・通信probeを含む外側と、固定更新loopのattempt wallも分ける。

| GPU | 主測定process全体 秒 | 全128更新のattempt wall 秒 |
|---|---|---|
| 1 | 30.035 | 13.656 |
| 2 | 30.029 | 11.031 |
| 4 | 30.027 | 10.292 |

この差には複数の準備処理が含まれ、CPU検証・転送・初期化ごとの比率は測っていない。旧試行では`ReplayBuffer.episodes`の排他lock内の全検証を全rankが繰り返し、準備が直列化していた。今回は外部Linuxで全Rust再生・保護検証を1回行った後、特徴量を量子化せずFP32のままhost cacheへ保存・復元し、producerと全consumerで元と同じSamples SHAを検証した。cacheの生成・検査も工程別時間に含める。更新部分の速度比だけで全工程の短縮を見積もらない。

作成要求から削除要求まで5104.804秒で、全4台・diskのquoteはUS$3.222222／時。この区間を単純に掛けた計算・disk見積もりはUS$4.569115、全4台の割当時間は5.672005 GPU時である。転送料・確定invoiceは別で、予約US$11.50も実請求とは区別する。未使用のGPU、準備・検証・転送中も同じ4GPUホストを借りている。

過去の予約を減らさず、全33予約US$152.5／承認総枠200を保持した。低速起動・NVML故障の部分成果は[起動記録](P5_4_STARTUP.md)、旧4GPUの再開不一致と1rank開始前検査の失敗は[不一致の記録](P5_4_PARITY_FAILURE.md)に保持する。今回の所有VMは1rankの開始前失敗後、修正のPR／統合main CI待ちも含めて保持し、学習更新0を確認して新source・新出力へ移った。この時間も全4台の借用時間・quote見積もりに含めた。

## 資源解放と今回の終了範囲

HFの全照合とCard review後にVMをDELETEし、全ページからの消失とCloudRiftの所有課金資源0を確認してから専用独立guardを終了した。[機械可読記録](experiments/p54-completion-2026-11-05.json)にACK・確認時刻・receiptを結び付ける。これはMacやCIで得たGPU性能ではない。

評価準備→8局試行→150局の全入力監査→12局の1要因診断→今回の実1／2／4GPUと保存再開が、「5まで」の実行範囲である。150局の保護入力重複4件、一般棋力改善の未確認、戦術family3件の小標本という制約は保持する。Phase6の構造比較・新しいモデルのWeb採用・観戦の端末検証は今回開始していない。
