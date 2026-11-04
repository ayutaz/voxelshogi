# P5-4の起動記録

## 目的

起動・依存の取得・検査・HF転送と、実際の学習時間を分ける。[同じ学習量の1／2／4GPU比較](P5_4_PLAN.md)は、全3構成の実更新と保存再開を測るまで未完了とする。[機械可読記録](experiments/p54-startup-2026-11-04.json)には、最初の起動試行と解放の証跡を残す。

## 最初の試行は学習前に解放

2026-11-04、Vast.aiのRTX5090×4、host49042を借用した。作成要求は11:46:53 UTC、削除要求は12:23:40 UTC、全ページからの消失とCloudRift所有資源なしを12:24:45 UTCに確認した。科学計測0件、checkpoint公開0件で、4GPUのCUDA検査にも達していない。GPUの故障や学習失敗を観測した試行ではない。

コンテナの起動が約16分かかり、専用公開鍵のinstance関連付けだけではSSH proxyの認証が通らなかった。アカウント側への登録が必要と分かり、現在のVMが本件の1台だけであることを確認して公開鍵を登録した。秘密鍵やprovider APIキーは転送していない。登録後のSSH接続で準備を一度だけ開始した。

uvの公式配布先でHTTP/2 PROTOCOL_ERRORが発生し、インストーラーの公式fallbackで取得が進んだ。fallbackの298秒時点で21,098,496 bytes、その後uvのインストール完了を観測した。別のRust配布元でも57秒で3,846,144 bytesだった。各観測ではおよそ70 KB/秒で、依存全体の取得速度を保証する値ではない。準備時間と残る固定実行枠から、動いていた処理を意図して解放し、別ホストを選んだ。観測timeoutを終了と見なして再作成したものではない。

単価は全4台・ディスク込みUS$2.262222/時。作成要求から削除要求までの単純な計算料金見積もりはUS$1.387で、転送料・確定請求は含まない。予約US$7は全額保持し、過去の予約を減らしていない。

## 置換時に固定した対策

旧VMのDELETE ACK、全ページからの消失、両providerの所有課金資源0を確認してから、host99796の別VMを作成した。登録済みの同じ専用鍵を作成前から用意した。次のbootstrapはcurlをHTTP/1.1、接続20秒・各要求180秒・再試行1回へ固定した。既存のcurl設定があれば上書きせず停止する。

科学計測のworker・rank worker・保存再開比較の3スクリプトは最初の試行とbyte一致する。source、固定HF入力、FP32、global batch16、seed63001、128更新・準備16更新・保存64更新、optimizerと再開許容誤差も保持した。起動経路の変更を、モデル・学習条件の変更へ混ぜない。

新しい予約も2時間・US$7で、全30予約126／承認総枠200。旧VM解放後に専用guardだけを閉じ、新VMには別の独立期限監視を用意した。Macはmetadataと静的確認に限り、データ・checkpointの中継は行っていない。置換先の実測結果・HF全hash・最後の資源解放は、[P5-4の記録](P5_4_PLAN.md)で別に確認する。

## 2番目の試行は1GPU主測定の後にNVMLアクセスを喪失

host99796は約4分で準備でき、物理4台それぞれのCUDA行列積・勾配検査と4rankのNCCL手計算検査に成功した。NCCLでは各rankの1・2・3・4を足した10を全要素で確認した。これは通信経路の起動検査であり、4GPU学習の完了ではない。driverは580.95.05、CPU quotaは92.16相当、メモリ上限は366,997,405,696 bytesだった。CPU／RAMの専有保証とは扱わない。

同じ開始重みと入力で、1GPUの連続128更新が完了した。準備16更新を除く112更新・1,792例のwall windowは14.142956秒、126.706182例／秒だった。同期した更新時間の合計13.538544秒、試行全128更新の17.188661秒を分けて保持する。rank0のTorch peak allocatedは3,688,706,560 bytes、reservedは4,133,486,592 bytesであり、device全体の使用量ではない。

続く64＋64更新の再開検証では、最初のprocessがmodel初期化前に失敗した。`nvidia-smi`もexit255・`Failed to initialize NVML: Unknown Error`となり、64更新の出力directoryは作られていなかった。所有コンテナを1回だけ再起動すると一時的に4台が再表示されたが、再開workerを起動する前に同じエラーが再発した。新たなGPU計算は開始していない。

[NVIDIAの公式説明](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/troubleshooting.html#containers-losing-access-to-gpus-with-error-failed-to-initialize-nvml-unknown-error)にはcgroup変更などでコンテナのGPUアクセスが失われる事例がある。ただし本ホストでの原因は特定しておらず、ホスト側systemdや共有設定の変更は行わない。別host・driver595以上を次の候補条件とする。次の比較では同じ新ホストで1／2／4GPUをすべて測り直し、今回の1GPUだけを別hostの2／4GPU値と組み合わせない。

## archiveの履歴互換性

退避用のCPU検証では、固定更新loopが出力する`global_step`・global sample index・準備期間flagなど10項目を、旧archiveの履歴allowlistが受け付けない問題を確認した。学習結果の不一致ではなく、実loopから保存形式へ渡す境界の欠落だった。[PR135](https://github.com/ayutaz/voxelshogi/pull/135)でdistributed profile専用の検査と保存を追加し、旧M6／自己対局の受入項目を維持する。

外部Linuxの実2rank AdamWで、2更新→typed archive→新model／optimizerへ復元→残り2更新を検証する。履歴はJSONの値と順序、model・optimizer・RNGは状態の一致を確認する。archiveは既存のJSON正規化を使うため、元JSONLの空白まで復元する要件は設けない。元の128行のJSONLは変更せず、partial測定datasetへそのまま保持する。

さらに故障環境のCPUで実128更新のcheckpointを約60.4 MBのtyped archiveへ変換し、新しいフォルダへ復元して128件の履歴値・順序を照合した。元checkpointとの直接比較でも、model・AdamW・全rank乱数・進捗・bindingの350 tensorと1,398 scalarが完全一致した。これはGPUでの後続更新の証拠ではない。実2／4GPU、各GPU保存再開、全比較の完了は引き続き未達である。

## 部分成果をHFへ退避して解放

archive publisherは`03fe80f8a59c0bf3b184776ffcad182f5ea062c7`、実学習sourceは元の`516da1a9ef8c07310f8bc987854df3ab67c35cf6`として分けて記録した。publisherの必須8チェック、Native全1,134テスト、全483変異・4shardを含む手動フルCIの成功後に送信し、PR135は`4746e1a0067d8ed6409935ffa3ac7ceda15b4d5a`へ通常squash mergeした。

| 部分成果 | 固定HF版 | 内容 |
|---|---|---|
| 128更新後のtyped state | [7a3528d](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1/tree/7a3528d5afc7751cc48a77efa00ad369b2508dbb) | 7ファイル・60,433,110 bytes、Apache-2.0。GPUでの後続更新は未達 |
| 主測定1件・全128履歴・失敗と実行source | [d191111](https://huggingface.co/datasets/voxelshogi/voxelshogi-distributed-benchmark-v1/tree/d19111106c97d5a65c87c4fd8390e87f31137a99) | 5ファイル・128,474 bytes、CC-BY-4.0。`pipeline_complete=false` |

両方とも外部Linuxから公開ハーネスを使い、public/manual・Community OFFと返された固定revisionの全bytes・SHA-256を照合した。Cardも内容・件数・未完了範囲と照合済み。Macへ移したのは小さいplan・receipt・manifest・Cardだけで、Parquet・checkpoint・state tensorは転送していない。

退避完了後の14:02:36 UTCにVM59103114をDELETEし、14:02:41 UTCに全ページからの消失とCloudRiftの所有課金資源0を確認した。その後に専用の独立期限監視を終了した。作成要求から削除要求までをquoteで掛けた計算・ディスク料金見積もりはUS$3.875で、転送料と確定請求は含まない。解放後のprovider報告料金はこのVMがUS$3.754、最初のVMがUS$0.811だった。日次APIの観測値であり、確定invoiceとは主張しない。[公式料金API](https://docs.vast.ai/api-reference/billing/show-charges)のGPU・disk・通信の内訳を保持する。両方のUS$7予約を含む全30予約126／200は減らさない。

共通state upload ledgerは既存8件を保持して9件・681,575,704／1,073,741,824 bytesとなった。次の6 archiveは各65,361,020 bytes以内なら同じ累積枠へ収まる。実bytesを検査してから送信し、量子化・optimizer省略・過去予約の削除で帳尻を合わせない。
