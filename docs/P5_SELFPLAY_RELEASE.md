# P5-2：世代ごとのHF公開トランザクション

**2026-11-12・一時停止**：既存Sの公開デモと、Mの少量2 run・48局評価を現段階の成果とする。
本比較12 run・MのWeb配布・観戦表示2案／実端末各60分は未完了のまま停止する。
追加GPU・生成・学習を自動再開しない。[停止時点の結果と固定HF版](RESEARCH_CHECKPOINT_20261112.md)を現在の確認元とし、
以下の旧「現在」「次」「予算」は対象時点の記録、実行コマンドは再開後の手順として読む。

**2026-11-03 16:56:12 UTC・P5-2の終了と停止**：[本条件3世代48対局・HF保存・別VM後続世代](P5_2_COMPLETION.md)の結果を記録した。使用した所有課金資源は0。棋力改善・P5-3・DDP・Phase6は未完了であり、結果共有後に停止する。

2026-11-03 UTC。`training/selfplay_release.py`で、確定世代のDatasetと再開状態を既存HF公開ハーネスへ接続する。本書はAPIと運用の契約を説明する。本条件の実HF公開・別GPU実機での後続世代は[P5-2完了記録](P5_2_COMPLETION.md)へ分けて保持する。

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

## 別実機への復旧接続

`training/selfplay_recovery.py`は全確定世代のrelease descriptorを受け取り、HFからの全hash照合、各stateの実decode／復旧、子モデルの再exportとhash照合、全ReplayのRust再生を行う。世代順・全モデルの系譜・過去の公開pairを検査し、base model・保護入力・protocolも元と一致させる。完成したrunに今回のpairを反映してから新規outputへ確定する。

`releases.json`は世代0から順に`{"bundle": <bundle.jsonの内容>, "pair": <pair.jsonの内容>}`を並べたJSON配列とする。planとreceiptだけを含む小さい制御記録で、データやcheckpoint、認証値は含めない。実データのダウンロードと復元は外部Linuxで行う。

```bash
uv run --project infrastructure/cuda --locked --no-sync python -m training.selfplay_recovery \
  runs/p5/releases.json runs/p5/selfplay/protocol.json \
  runs/p5/inputs/base.safetensors runs/p5/inputs/protected.json \
  runs/p5/recovered/output runs/p5/recovered/workspace
```

`recovery.json`は復旧したモデル・公開pairと検証範囲を残す。同じVMの別フォルダでも動くため、このファイルだけを別実機復旧の証拠にしない。所有VM IDと旧VMの終了、新VMでの実後続世代を別途記録する。共通upload ledgerも制御側の最新値を引き継ぎ、新しい空のledgerで累積上限を回避しない。

## 実装時の検証と外部条件の履歴

メタデータの公開／復旧テストと関連テストをMacで実行した。遠隔hash確認の省略、送信結果不明時の再送、学習入力bindingの省略、並行更新の無視、凍結protocolの省略、復旧パスの検査省略の6変異をそれぞれ検出した。実Sモデル2世代テストには、run lock解放後のDataset／実state stage、fake Hubへの公開・全hash照合、pairのcursor反映、元run除去後のstate／Replay復旧と後続世代の一致確認を追加した。独立した変異用checkoutにも、stageが必要とするLICENSEを保持する。実tensor・Parquet・Rustの結合確認は、数値修正後のmain `7e44310`の[CI](https://github.com/ayutaz/voxelshogi/actions/runs/41652351549)で820テスト・skip0と学習系変異4シャードの実行成功を確認した。FP32へ戻す精度変異と非合法手を分母へ含める変異も検出した。CPU CIの時間をGPUの性能値へ流用しない。fake Hubの成功は実HF公開の証拠に数えない。

2026-11-03 00:51 UTCの公式API読み取りではVast.aiの認証成功、所有VoxelShogi実機0、条件内RTX5090×1候補1件だった。`balance=0`を利用クレジットと取り違えていたが、02:01 UTCに`credit`を確認して訂正した。[訂正記録](experiments/vast-credit-preflight-correction-2026-11-03.json)。追加入金は不要。候補の単価はdisk80GB込み約US$0.75556/時・転送無料であり、予約ではない。利用直前に再確認する。新たな有料実行・予算予約・HF公開は行っていない。

VastキーのGitHub `gpu-control`環境への保存は、当初は自動承認レビューが宛先への明示承認を要求して拒否した。その後ユーザーが明示承認し、登録を完了した。providerキーをGPUへは送らない。credit判定の修正と関連CI・独立停止の準備を完了してから、既定の最大1時間／予約US$1の試行へ進む。
