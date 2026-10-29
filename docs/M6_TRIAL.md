# M6-2：RTX 5090でのCUDA試行

2026-10-29にCloudRiftのRTX 5090×1・RAM48 GiBで実行し、少量学習、再開、HF退避と復旧、ブラウザの物理GPU利用を確認した。実機は終了・資源解放済み。[固定した実測記録](experiments/m6-cuda-trial-2026-10-29.json)。本学習、固定test／対局評価、学習済みモデルの推論公開とArenaの実機検証はこれから行う。

## 目的と結果

M6-3へ進む前に、固定データ、CUDA対応、実学習の速度・メモリ、終了後に再開できる保存先を実測で確定する。

| 確認 | 結果 |
|---|---|
| ソースと依存 | PR #62の必須CI成功済み `d98cc4923625910bba68b28f1071742bbb06a2eb`、Python3.14.9、torch2.14.1+cu130、driver580.159.03 |
| 実GPU | RTX5090・VRAM32,607 MiB、CUDA13.0・sm_120。手計算した2×2積と勾配が一致 |
| 実データ | 固定HF revisionのproduction-64を全ファイルhash照合・監査。教師36,894件：train29,884／val3,421／test3,589。深さ1が1件、深さ2が36,893件 |
| 前処理 | 取得129.16秒、監査66.49秒、特徴量cache83.62秒。cache manifest SHA-256は固定記録に保存 |
| batch 1 | 64更新、約54.60局面/秒。Torch peak allocated約336.62 MiB |
| batch 4 | 64更新、約184.98局面/秒。Torch peak allocated約980.87 MiB |
| CUDA再開 | 各batchで64連続と32＋32再開を比較。入力順・RNG・重み・optimizer・固定val出力が完全一致。事前基準はatol=1e-6、rtol=1e-5 |
| HF保存と復旧 | JSON＋safetensorsの64更新状態を別repoへ公開し、固定revisionの全7ファイルを照合。新しいrunへ復旧して追加64更新し、元runの継続と完全一致 |
| Linuxブラウザ | Chromium156.0.8078.4、WebGPUのNVIDIA Blackwellで整数計算42、WebGLもRTX5090で青pixelをreadback。モデル推論・Arenaの3D同時動作の証拠とは分ける |
| 費用と終了 | 初回上限4時間／US$4。起動から資源解放確認まで約18.9分、時間×単価の参考額約US$0.31。実請求未回収。追加US$100は未使用 |

64更新は短い試行で、1 epochの完了ではない。速度はログ・保存を含む更新区間から求めた短時間の値であり、継続学習や全工程の速度保証ではない。GPU使用率／RSSの2秒サンプルも少数で、長時間のピークや平均利用率へ一般化しない。

最初の操作スクリプトはデータ取得前にPython検索パス不足で失敗し、記録を保持して修正・再開した。ブラウザも最初のadapter取得はnullだった。Vulkanの物理GPU検出を確認し、ChromiumのSystemInfo初期化を待った診断実行で同じflagsが通った。原因を断定せず、最初の失敗も固定記録へ残した。NVIDIA driverは変更していない。

## 保存先

[再開状態repo](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-training-state/tree/cc0f29219ea426587548451cfca850721ef704ac)はpublic/manual・Community OFF、Apache-2.0。Cardは学習途中の試行であることとoptimizer／乱数状態の公開範囲を明記した。新規アップロードの累積予約は60,417,110 bytes／1 GiB。Macへモデルやcheckpointを中継せず、小さいmanifest・hash・集計だけを回収した。

推論用repoもpublic/manual・Community OFFで準備済みだが、学習済み推論パッケージはまだ送っていない。ブラウザのcatalogも未登録のまま。

## 次の実行単位：M6-3〜5

目的は、固定データでの本学習から、評価した同じ3形式を公開デモで観戦するまでを完了すること。次の1台は同じ既知SKU・US$1/時以下、**最大8時間／US$8**とする。初回のUS$4予約を含め、M6累積予約はUS$12で基本枠US$24内。追加GPU枠はまだ有効化しない。

| 作業 | 条件と見積もり |
|---|---|
| 環境・データ | 同じclean source／lock、固定revisionを再取得・全監査し、cache hashを照合。構築・監査・転送に30分を確保 |
| 本学習 | seed314159、FP32 AdamW、batch4、3 epoch、lr0.0003、weight decay0.01、threads3。train29,884件×3÷184.98で更新区間は約8.1分。val全件評価と保存を含め30分を確保 |
| 損失とデータ量 | 初期重みとval選択済み重みを同じ固定valで比べ、学習曲線を保存。追加データはtrain／val・分布から必要性を判断し、固定testは調整に使わない |
| 固定評価・変換 | 初期モデル、学習済みTorch、実ONNXのFP32／FP16／INT8重み版を、事前の同じtestと各60対局で評価。対局時間は未実測のため暫定3時間、変換・数値照合30分を確保 |
| HF・ブラウザ・終了 | Model Card、固定Hub revision全hash、実3形式・Worker・3D・公開E2E・配信hashと再開状態保存。1.5時間を確保 |

合計の暫定見積もりは6時間、起動上限8時間には約2時間の余裕を取る。終了guardianは上限の15分前から終了処理する。未測定の対局・ブラウザ時間を試行の局面/秒から算出した実績とは扱わない。時間内に収まらない見込みになったら、外部保存・hash照合と終了を優先し、実測で次の実行枠を更新する。
