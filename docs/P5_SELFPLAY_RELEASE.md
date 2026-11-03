# P5-2：世代ごとのHF公開トランザクション

2026-11-03 UTC。`training/selfplay_release.py`で、確定世代のDatasetと再開状態を既存HF公開ハーネスへ接続する。実HF公開・別GPU実機復旧の完了記録ではない。

## 実行順と成功条件

`run_generations(..., max_new_generations=1)`が戻ってrun lockを解放した後にstageする。`on_generation`からstageを呼ばない。Parquet packingもrun lockを取得するためである。公開済み世代数より確定世代数がちょうど1多い状態に限り、公開候補を作る。

```bash
# 承認済み外部Linux、CUDA環境の準備後に実行する。
uv run --project infrastructure/cuda --locked --no-sync python -m training.selfplay_release \
  stage runs/p5/selfplay/output runs/p5/release-000 \
  --protocol runs/p5/selfplay/protocol.json --dataset-license runs/p5/CC-BY-4.0.txt

# HF_TOKENは環境／メモリのみ。既存M6と共通の累積upload ledgerを使う。
uv run --project infrastructure/cuda --locked --no-sync python -m training.selfplay_release \
  publish runs/p5/selfplay/output runs/p5/release-000 \
  --upload-budget runs/m6/state-upload-budget.json
```

`bundle.json`は凍結したrunと両planを保持する。Datasetは`voxelshogi/voxelshogi-selfplay-v1`のCC-BY-4.0、stateは`voxelshogi/voxelshogi-transformer-s-selfplay-training-state-v1`のApache-2.0に固定する。stateのsource・世代・親モデル・実学習入力hash・進捗をDatasetの世代記録と突き合わせる。stateは自己対局専用JSON＋safetensors profileのみを使い、pickleや生ログを送らない。各Cardはstage時に作成し、実件数・hash・用途と限界を公開前に確認する。

public/manual・Community OFFを確認してからアップロードする。各receiptを先に保存し、固定Hub commitで全対象ファイルのbytesとSHA-256を照合する。両receiptの検証後にだけ、run lock下で公開cursorを進める。実行中に元runが変わっていたらcursorを書き換えない。stagingも同時公開を拒否するlockを持つ。

## 中断時の扱い

- receiptがある場合は同じ固定revisionの全hash照合から再開し、アップロードを繰り返さない。検証済みreceiptでも再確認する。
- 送信前のattempt記録だけがあり、receiptがない場合は送信結果不明として停止する。API失敗前に送信された可能性があるため、自動再送やstate upload予約の取消しをしない。固定宛先のHub履歴・plan・upload ledgerを監査してから復旧する。
- 両receiptを得てcursorを書いた直後に中断した場合も、同じrunとpairなら再照合できる。
- Datasetは現在の公開pair自身を含めないsnapshotであり、それ以前の公開pairは保持する。別VMへ移る際は最新Datasetのplan／receipt、今回のpairと全世代stateのplan／receipt、共通upload ledgerを小さい制御記録として別途保持する。

別VM復旧では、全世代のstateを固定revisionで取得・照合し、対応する子モデルを復元してhashを確認したうえで`restore_dataset`へ渡す。base model・保護入力・protocolも元と一致させる。今回の公開接続だけで、実VM間の復旧や後続世代の成功を主張しない。

## 検証と現在の外部条件

メタデータのみの12テストと関連13テストはMacで成功した。遠隔hash確認の省略、送信結果不明時の再送、学習入力bindingの省略、並行更新の無視の4変異をそれぞれ検出した。実Sモデル2世代テストには、run lock解放後のDataset／実state stage、fake Hubへの公開・全hash照合、pairのcursor反映を追加した。実tensor・Parquet・Rustの結合確認はLinux CIで行い、その結果は未確認である。fake Hubの成功は実HF公開の証拠に数えない。

2026-11-03 00:51 UTCの公式API読み取りではVast.aiの認証成功、所有VoxelShogi実機0、条件内RTX5090×1候補1件、残高US$0だった。候補の単価はdisk80GB込み約US$0.75556/時・転送無料であり、予約ではない。利用直前に再確認する。新たな有料実行・予算予約・HF公開は行っていない。

GitHubの`gpu-control`環境にはCloudRiftキーだけが登録されていた。Vastキーの同環境への保存は、自動承認レビューが宛先への明示承認を要求して拒否したため未実行で、ユーザーへ確認中。残高追加と独立停止の準備が完了してから、既定の最大1時間／予約US$1の試行へ進む。
