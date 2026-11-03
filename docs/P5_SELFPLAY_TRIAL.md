# P5-2：Vast初回運用試行の結果

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
