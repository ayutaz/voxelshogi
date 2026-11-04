# P5-4：1／2／4GPUの学習比較

2026-11-04 JST。[今回の実行範囲](P5_3_PLAN.md)の5番目。P5-3の実測を待つ間に共通スケジュールと保存境界を準備する。ここに記したGPU測定はまだ実行結果ではない。

## 目的と数量ゴール

小型モデルの学習を複数GPUに分ける価値を、同じ学習量・入力・精度で判断する。1／2／4GPUの全3構成について、実時間、VRAM、通信、GPU時間、費用と保存再開を記録する。4GPU未測定のまま5番目を完了にしない。速度が改善しない結果も残す。

比較候補は同じ所有4GPUホスト上の1／2／4台の使用である。GPUの種類・個体とホスト構成を固定し、CPU割当・接続・driverも記録する。この方法では使っていないGPUにも料金がかかる。実際の4GPU全体の借用時間・単価を費用へ計上し、使用GPU数×学習時間から求める計算量と分ける。在庫・価格とP5-3の実測から見積もりを固定し、controller・ledger・独立期限監視が対応するまで借りない。

## 4GPUの借用条件

[専用controller](../training/vast_distributed_control.py)はRTX5090×4・80GBディスク・verified・信頼性0.99以上・CUDA13対応・driver580以上を扱う。GPUごとに約32GB VRAM、ホスト合計でCPU RAM 98,304 MB以上（API値）と24以上のeffective CPU coreを要求する。旧1GPUの上限US$1/時・転送無料の契約は維持する。

[読み取り在庫記録](experiments/p54-four-gpu-quotes-2026-11-04.json)では、verifiedなRTX5090×4がディスク込み約US$2.26222/時、転送は各方向US$0.00390625/GBだった。これは2026-11-04 01:41 UTC時点の候補であり、起動予約や在庫保証ではない。[公式API仕様](https://docs.vast.ai/api-reference/search/search-offers)の転送料単位を確認した。

専用planの計算・ディスク単価上限は全4GPUでUS$3/時、各方向の転送単価上限はUS$0.01/GB。依存導入も含むdown 40GB・up 10GBの保守的な見積もりを別に記録し、転送用にUS$1を追加予約する。したがって1時間なら予約上限4、2時間なら7である。共有ディスクをGPUごとに4重計上せず、クレジットと共通／Phase別ledgerには転送枠も含める。これは固定workloadの費用見積もり・予約であり、providerが強制する転送量や請求の上限ではない。

既存の用途配分や基本総枠をこの実装だけで増やさない。8局の時間試行と最新quoteから時間・費用を固定し、コードとledgerの一致・同じprofileの予備guard・protected mainの独立監視を確認してから実機を作る。観測失敗後の作成再送や、未知の既存実機がある状態での追加起動を拒否する。

## 同じ条件で比較する

- 同じTransformer-Sの開始重み、検証済み自己対局入力、保護集合を使う。source・HF固定revision・全hashと実学習sampleのhashを固定する。評価holdoutを学習へ混ぜない。
- global batch 16、128更新、最初の16更新を準備期間とする案を[設定](../training/distributed_training.py)へ明示する。測定対象は残り112更新。同じ学習率・AdamW設定・FP32で、TF32や量子化を使わない。実機起動前に最終条件をprotocolへ固定する。
- [共通スケジュール](../training/distributed_benchmark.py)で先に全更新のindexを固定する。各更新をrankへ等分し、GPU数によってsampleを追加・複製・間引きしない。Value由来はbatch内で統一し、全体で除外した端数を記録する。
- 各構成の主測定は連続128更新。別の再開検証では同じ開始状態から64更新で保存し、新しいmodel／optimizerへ読み込んで残り64更新を行う。後者の128更新を主測定のthroughputへ足さない。
- CUDA同期を含む更新時間と準備・保存・復旧を分ける。rankごとのTorch peak allocated／reserved bytesと、device全体の観測値を混同しない。
- 通信の単独probeと学習全体の時間を別に保存する。単独all-reduceの所要時間を、そのままDDP学習中の通信割合とは呼ばない。

## 正しさと保存

[固定更新ループ](../training/distributed_loop.py)の`fit_schedule`は同じglobal scheduleを再構築し、更新cursor・入力・初期重み・構成・runtimeをbindingへ固定する。全rankで停止flagを共有し、0・中間・最終状態を既存のDDP保存境界へ渡す。再開では新しいmodel／optimizerへ読み込み、残りの更新だけを実行する。実行前の不一致とrank0の保存失敗を全rankへ伝え、同じ出力には排他leaseを取る。

更新ごとのCUDA同期・rank最大時間の合計と、準備後から最終更新までの壁時計時間を別々に残す。後者には中間checkpoint・event IOを含み、最終checkpointは除く。先頭から全更新を連続実行した試行だけをprimary throughputの対象とし、中断・再開確認は件数を保持して速度を未設定にする。Torchのrank別peak allocated／reservedはdevice全体のVRAMではない。

同moduleの`communication_probe`は、モデルのFP32勾配byte数に合わせた独立all-reduceを行い、各rankの1の和がworld sizeになることを全要素で確かめる。既定は準備5回＋測定20回。fill・検査・barrier・時間集計は測定区間から分け、1rankは通信なしと明記する。このprobeから学習中の通信割合を算出しない。

ループの手計算テストは4更新・batch4・準備1更新で、時間2・4・6・8秒を与える。測定は3更新・12例・18秒、中間2と最終4で保存となる。実2rankのAdamWで連続4更新と新しいmodel／optimizerへの2＋2再開、rank1だけの停止要求と実all-reduceの和をLinux Nativeテストで確認する。これらは実GPU測定に先行する正しさの検証であり、1／2／4GPUの実績とはしない。

[DDPの更新・checkpoint境界](../training/distributed_training.py)は等しいlocal batchの平均勾配を使う。モデルとoptimizerの一致・共通binding・進捗を全rankで検査してから、共有する重み／optimizerを1組と各rankのPython・NumPy・Torch・使用中CUDAの乱数を保存する。GPU0の乱数だけを全rankへ複製せず、未使用GPUのcontextも作らない。

Linuxの2プロセスGlooテストでは、手計算のMSE・勾配・SGD momentum更新を期待値にする。4sampleの最初の重みは0.03、再開後2更新目は0.07455となる条件で、各rankの担当indexと別々の乱数復旧も確かめる。別のAdamW経路でJSON＋safetensors archiveを作り、新しいrunへ復旧して連続更新との重み・optimizerの一致を確認する。CPUテストの成功をGPU性能の証拠にはしない。

公開する再開状態には`profile="distributed"`・`artifact_role="distributed-training-state"`を使う。保存先は`voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1`、Apache-2.0、public/manual・Community OFF。旧M6／自己対局のstateへ混ぜず、[既存の公開ハーネス](HF_PUBLICATION.md)を通す。world size・global schedule・入力・optimizer設定が違えば復旧を拒否する。各構成の中間／最終状態を計6回保存する案は、実ファイル量と既存の累積1GiB upload ledgerを照合してから確定する。

Macではmetadata・fake portsと静的確認だけを行う。数値・分散プロセス・保存復旧はLinux CI、1／2／4GPUの学習は承認済み外部Linuxで実行する。全3構成の実測・HF固定revision全hash・各構成の再開と最後の資源解放がそろうまで未完了である。
