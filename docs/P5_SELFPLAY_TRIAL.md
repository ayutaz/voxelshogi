# P5-2：Vast運用試行の結果

## 小規模試行の成功と資源解放（2026-11-03 UTC）

[固定した成功記録](experiments/p52-vast-trial-success-2026-11-03.json)。所有RTX5090実機58961875、source `40ae236`で2対局・32sample・8学習更新を完了した。子モデルhashは`4033110176314d04544c5bfe4c3ac551ae271f0dcd0c6b63de37bec9d21b1cea`。自然終局0・cutoff2であり、棋力改善・P5-2本条件の証拠ではない。

- 固定入力の取得・全hash照合720.4秒、保護集合作成131.5秒、自己対局と学習3.9秒、世代の両HF公開・照合38.2秒、同じVMでのHF復旧1.3秒。cursor公開を含むworker全体は916.8秒。
- [Datasetのcursor snapshot](https://huggingface.co/datasets/voxelshogi/voxelshogi-selfplay-v1/tree/b3d81a45ce0e5d81fdb1559c1e77dd3667e1b922)、[再開状態](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-selfplay-training-state-v1/tree/ead8140accc264378699adc9e860b66204fd407a)、[集計report](https://huggingface.co/datasets/voxelshogi/voxelshogi-selfplay-run-reports-v1/tree/9e3e1ede7a60276e70f32602ba5a0412553ea888)を固定revisionで全hash照合済み。Dataset／reportはCC-BY-4.0、stateはApache-2.0。4節のCard、public/manual・Community OFFを確認した。
- [保護集合の固定版](https://huggingface.co/datasets/voxelshogi/voxelshogi-protected-inputs-v1/tree/ec3bfa0acfa6c5c9f59f98bf1750a3143c0007d8)をLinuxから公開・全hash照合した。116,008件と元の`protected.json`の全bytes／hashを保持し、次のVMで全コーパスを再取得する必要をなくした。除外範囲を減らしていない。
- 本条件用の開始局面16件をLinuxのRustで生成・再生した。seed42000〜42015、履歴16手×4・128手×6・256手×6、rootの保護集合との重複0・root間重複0。長い履歴を代表的な終盤と呼ばない。
- 12:55:21 UTCに実機の削除ack、12:55:23 UTCに全inventoryからの不在を確認した。外部停止期限より早い手動終了であり、この試行を実期限停止の再実証とは数えない。独立監視は資源解放後に取消を依頼した。実期限停止は下記の初回試行で確認済み。

共通state upload ledgerは累積376,685,551 bytes／1 GiB。GPU保守的予約は全体US$78／100、Phase5累積US$17。実請求は未回収、追加US$100は未適用。[本条件と配分変更](P5_SELFPLAY_MAIN.md)へ進み、別VMでの後続世代と48対局を確認する。

## 初回試行：内部締切による未完了

2026-11-03 UTC。[固定した実行・停止記録](experiments/p52-first-vast-trial-2026-11-03.json)。実行sourceは`40ae236`。**独立期限停止と入力保護を確認したが、自己対局学習・HF往復の試行は未完了**。P5-2本条件の48対局を実行したとは扱わない。

## 確認できたこと

- Vastの1GPU契約を再照合し、RTX5090・80GB・約US$0.72889/時で起動した。Python3.14.9、Torch2.14.1+cu130、driver610.43.02、実CUDAの手計算forward／backwardが一致した。
- HFは本人・組織とpublic/manual・Community OFFを確認した。外部Linuxで固定データ1,831、モデル37、P5-1候補12ファイルを取得・照合した。取得・照合に約656.8秒かかった。
- M4/M6の113,321入力、P5-0の1,601入力、P5-1 holdoutの1,090入力を照合し、一意な保護集合116,008件を作成した。約132.0秒。P5-1教師の採用は0。
- [独立監視](https://github.com/ayutaz/voxelshogi/actions/runs/41584787471)が06:15 UTCに所有ID58924518の削除を要求し、06:16 UTCに削除ackと全件inventoryからの不在を確認して正常終了した。現在の所有実機は0。外部削除receiptをローカル制御へ照合し、ローカル監視も終了した。

## 未達と次の変更

元workerは取得・監査後に計算用の内部締切へ達し、`reason=stopped`、確定世代0・Replay cursor0で停止した。同じprotocol・同じ実機・同じ外部期限で再開したworkerの最終記録は回収できなかった。HFには初期`.gitattributes`だけがあり、検証済み世代・学習更新・Dataset/state公開の成功には数えない。失われた実行結果を推測で埋めない。

内部上限の見積もりが入力取得・監査に対して短かった。次は最大2時間／保守的予約US$2、作業見積もり30分として同じ小規模条件を試す。初回の最大1時間／US$1はこの失敗記録として保持する。追加のGPU予算US$100はまだ適用しない。

次のworkerは、世代の両HF receiptと同じVMでの往復復旧を検証後、公開済みcursorをDatasetの新しい固定snapshotへ保存する。さらにtypedな集計・protocol・receiptだけのrun reportを、既存公開ハーネスで`voxelshogi/voxelshogi-selfplay-run-reports-v1`へCC-BY-4.0、public/manual・Community OFF・Card付きで保存する。成功・失敗と未検証を分け、資格情報・raw log・重みはreportへ入れない。実機終了後も小さい制御記録から結果を判定するためであり、reportの存在だけで学習成功としない。

台帳の保守的予約は全体US$76／基本枠100、Phase5 US$15／初期枠20。今回のUS$1も実請求未回収のため予約を保持する。次のUS$2を加える場合も既存の総枠・Phase5枠で管理する。料金・時間の見積もりを請求額と呼ばない。

小規模試行の目的は実学習・HF往復・速度／運用費の測定。本条件3世代×16対局、別GPU実機での後続世代、全ドキュメント点検・報告後の一時停止は引き続き未達である。
