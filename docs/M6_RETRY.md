# M6の数値契約修正後の再実行

2026-10-29 UTC。[初回のFP32変換失敗](M6_MAIN.md)を保持し、学習済み専用の数値契約を含むCI成功済みsourceから学習をやり直した。**3 epochの学習とHF再開状態の復旧、[全5モデルの固定評価・3形式変換・初回HF推論公開](M6_MODELS.md)は完了。実モデルのブラウザ検証・公開catalogは未完了で、M6全体は未完了。** [固定した進捗・学習曲線・元記録hash](experiments/m6-numeric-retry-progress.json)。

## 学習と選択

sourceは `874aed9ac28c9e50e178c2dda706941b2d3294da`。旧sourceのcheckpointや評価のcommitを書き換えて流用せず、固定HFデータを再取得・全件監査し、cacheから再作成した。データrevisionは `6e7fb29d2469b56a895042fbb089d86e7b4d074f`、`production-64`、train29,884／val3,421／test3,589の教師36,894件。新cache manifestのSHA-256は `a5964be6625d6dd8fe69abffab83f33a25dda3d029a57fdbda00b3007419361e`。

CloudRift米国のRTX5090×1、driver580.159.03、Python3.14.9／torch2.14.1+cu130／CUDA13.0を使用した。FP32 AdamW、batch4、seed314159、lr0.0003、weight decay0.01、threads3、TF32無効・決定的計算の条件を維持し、1,000更新で保存、新しいmodel／optimizerへ再開して22,413更新・89,652例・3 epochを完了した。fitの更新区間は20.06＋440.87＝約460.92秒。データ取得・cache・前後の評価・転送は含まない。

| valの指標 | 初期 | epoch1 | epoch2 | epoch3・選択済み |
|---|---:|---:|---:|---:|
| 損失 | 6.19951 | 1.44245 | 1.07299 | 0.87439 |
| Policy Top-1 | 1.345% | 68.167% | 73.926% | 77.609% |

同じ2,048件のtrain probe損失は6.28969→0.78980。選択時valとの差は0.08459。probeのID順序hash、全epochのval値、保存・再開位置を固定記録へ残した。初回本学習とこれらの指標が同じ結果になったが、別runの実測として扱い、未確認の全環境再現性へ一般化しない。

testを開く前にtrain／valのみで判断し、今回の教師模倣baselineの固定評価へ進む根拠を `validation_review` に記録した。追加データはこのrunでは生成していない。64手までの合成データによる長期戦・終盤の被覆制限は残る。教師精度を棋力と読み替えず、固定test・対局の結果は別に記録する。

## HF再開状態

[voxelshogi-transformer-s-training-stateの固定revision](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-training-state/tree/02228242fc6b7fa39f6c051584b35d755d3b7ce5)へApache-2.0で保存した。public/manual・Community OFFと全ファイルのbytes／SHA-256を照合し、外部Linuxの新runへ復元したlatest／bestのmodel・optimizer・RNGは最大絶対差0だった。新しいsourceとcacheのbindingを維持し、過去のHF revisionも保持している。推論用モデル公開の完了とは区別する。

データ・checkpointをMacへ中継せず、ここには小さい集計とhashだけを保存する。再開状態の共通アップロードledgerも外部実行後の値へ同期した。

## 残りの実行

1. 初期／選択済みTorchの固定test3,589件と各60局を評価する。
2. 評価済みの同じ重みからFP32／FP16／INT8重み版を生成し、同条件のtest・対局で比較する。初回失敗は成功結果で上書きしない。
3. Model Cardを実測で埋め、HFのpublic/manual・Community OFFで公開し、固定revisionの全ファイルを照合する。
4. Linux実機で48条件・各backend20切替と実モデルの観戦操作を検証する。CIや未学習M3の結果を学習済み物理GPUの証拠に使わない。
5. 検証済みcatalogをPRで登録し、必須・関連CIと公開E2E、配信SHA／hashを確認する。実機終了・resources_releasedと費用を記録してM6の完了条件を監査する。

実機 `55607c82-d3ac-11f1-8a85-1383f5decdec` はこの記録時点で稼働中。単価US$1/時、最大4時間／US$4、終了上限の15分前にcleanupを開始するguardianを起動済み。M6累計予約US$16／基本枠US$24、プロジェクト累計予約US$57／US$100で、追加GPU予算は未使用。予約額は実請求ではなく、このrunの最終費用・終了確認は未完了。
