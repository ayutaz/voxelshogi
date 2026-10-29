# M6完了：学習済み3形式でAI対局を観戦する

2026-10-29 UTC（2026-10-30 JST）。M6-0〜M6-5／Phase4の目的だった、学習から評価・中断再開・変換・HF公開・実機ブラウザの観戦までの流れを完了した。対象の公開アプリは`564715ab7bedd549bed5038e417b8cbedc32e134`。**教師再現精度は向上したが、探索AIに対する棋力向上は今回の評価では確認できていない。** [固定した完了記録](experiments/m6-completion.json)。

## 目的と達成したゴール

| 段階 | 目的 | 確認したゴール |
|---|---|---|
| M6-0〜1 | 同じ教師と条件で学習・再開できる基盤を作る | 固定データ・teacher契約・対局単位split、独立期待値・変異検出・Linux CI、model／optimizer／RNG保存再開 |
| M6-2 | GPUの実行条件と費用を実測する | RTX5090・Python3.14.9・固定CUDA lockの実学習、batch4約185局面/秒の試行、HFからの新run復旧 |
| M6-3 | 教師の再現度と棋力を分けて評価する | 3 epoch／22,413更新、val選択、test3,589件、初期／Torch／3変換版で各60局の固定比較 |
| M6-4 | 評価した実ファイルを取得・比較できるようにする | FP32・FP16重み・INT8重み、数値・棋力・容量・速度比較、Model Card、public/manual・Community OFF・全37ファイルhash照合 |
| M6-5 | 公開Arenaで同じモデルを選んで観戦する | catalog差し替えなしの全48条件・40実切替、3形式それぞれのGPU着手、7実モデルE2E、公開配信SHA／hash、資源終了 |

## 学習・評価・公開物

教師train29,884／val3,421／test3,589。FP32 AdamW、batch4、seed314159、3 epoch。1,000更新で中断し、新model／optimizerへ読み込んで22,413更新まで継続した。学習の更新区間は計460.9秒、89,652例で約194.5局面/秒。初期val損失6.19951→選択epoch3の0.87439、val Policy Top-1は77.609%。testを学習やcheckpoint選択に使っていない。[再学習・復旧](M6_RETRY.md)・[全形式の固定比較](M6_PORTABLE.md)。

test Policy Top-1はTorch／FP32／FP16重み版75.592%、INT8重み版75.536%（3,589件中2件分低下）。マスク後の合法手選択率は100%。Random40局は全て打切り。学習済みTorch／FP32／FP16重み版のM1探索20局は0勝3敗9引分8打切り、INT8重み版は0勝4敗9引分7打切り。最大256手・同じ序盤・先後交換・固定探索上限を使い、打切りを引分へ変換していない。小標本・打切りを含む勝率やbootstrap区間を無制限対局の真の勝率へ一般化しない。

- [推論モデル・最終revision](https://huggingface.co/voxelshogi/voxelshogi-transformer-s/tree/f196c75236f0f0cfd028b91661b39a2c64ee448f)：Apache-2.0、public/manual、Community OFF。元の実機と新しい最終検証実機の両方で全37ファイルを再取得・bytes／SHA-256照合した。
- [再開状態の固定revision](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-training-state/tree/02228242fc6b7fa39f6c051584b35d755d3b7ce5)：同じ取得設定・Apache-2.0。latest／bestのmodel・optimizer・RNGを新runへ復旧し、最大絶対差0を確認済み。
- [元データとDataset Card](https://huggingface.co/datasets/voxelshogi/voxelshogi-synthetic-v1/tree/6e7fb29d2469b56a895042fbb089d86e7b4d074f)：CC-BY-4.0、production-64。有効113,321局面・探索教師36,894件。追加生成は今回行っていない。

FP16とINT8は重みの低精度化で、計算・活性はFP32。画面の「FP16（重み）」「INT8（重み）」で選ぶ実ファイルが評価・配布hashと一致する。混合精度FP16の数値不一致、初回FP32の旧数値基準不一致、カメラ操作が準備中に終わった計測失敗は[履歴](M6_PORTABLE.md)へ保持し、成功で上書きしていない。

## 公開URLでの実機検証

[差し替えなしの全量原本](experiments/m6-public-browser-full.json)：FP32／FP16重み／INT8重み×WASM／WebGPU×4固定局面×2D／3Dの48条件が成功、未対応0。各準備10回＋測定30回、WASM／WebGPU各20実切替、全4参照・全出力・実provider・Rust合法手・Worker終了を検証した。3Dでは実測リクエスト中のtrusted camera入力と実描画、5秒以内の資源観測を確認した。計測の開始から後続UI検証終了まで、公開アプリ／catalogは同じ実バイト列だった。

[実GPU Arena原本](experiments/m6-public-arena-gpu.json)：公開されたcatalogをそのまま取得し、全3形式を先後へ選択、各2手の着手・棋譜のRust再生・実WebGPU provider・条件保存を確認した。FP16重み版のFP32計算も記録に含む。

[実モデルUI・driver E2E](experiments/m6-public-arena-wasm.json)：7件・63.1秒、retry／skip／flakyなし。3形式の合法手・自動再生／停止・速度・条件付き棋譜、3D準備中の中断、破損拒否、GPUなし時の明示エラー・人間対AI、計測driverを確認した。この7件のsuiteは同じ検証済みcatalogのfixtureを使う。実際の公開catalogの取得・一致は前述の全量計測とGPU Arenaが差し替えなしで別に確認している。

初期局面・3D表示ありの推論時間（ms、CPU出力readback込み、準備後30回）：

| 実行先 | 形式 | 中央値 | P95 |
|---|---|---:|---:|
| wasm | fp32 | 254.3 | 257.9 |
| wasm | fp16 | 254.2 | 260.6 |
| wasm | int8 | 263.0 | 268.6 |
| webgpu | fp32 | 8.1 | 11.9 |
| webgpu | fp16 | 8.7 | 12.3 |
| webgpu | int8 | 8.8 | 11.8 |

物理Linux RTX5090／Chromiumの結果で、ほかの端末への対応は未検証。新context／Workerを初回とし、OS／driver cacheまでは初期化しない。main JS heapはWorker／GPUを含まず、Chrome RSSは共有ページを重複計上し得る観測値。GPU全割当量は取得不能であり、ピーク保証や全端末の速度保証はしない。

## PR・公開・同一性

PR #73〜#74は必須8チェック・関連CI成功後に保護を迂回せず通常merge。統合`564715ab7bedd549bed5038e417b8cbedc32e134`の[main CI](https://github.com/ayutaz/voxelshogi/actions/runs/40935461524)・[Security](https://github.com/ayutaz/voxelshogi/actions/runs/40935461571)、自動公開と配信SHA、公開21 E2E・追加カメラ3件・未学習ラボ6件・57応答のhash監査が成功した。CIの未学習fixtureを実学習の証拠へ読み替えていない。

本記録の追加は文書・計測記録だけの変更としてPRとCIを通す。物理計測対象SHAは上記に固定したまま保持し、文書公開後は実行ファイル・ORT runtime・M6 catalogのhash同一性を再確認する。計測していない後続SHAへ実測値を付け替えない。

## 費用と資源終了

直近2実機はどちらも所有IDだけを終了し、provider APIでInactive・resources_released=trueを確認した。Macへ中継したのはmetadataと小さい原本計測記録だけで、dataset・checkpointは置いていない。最終検証実機には推論パッケージだけを取得した。

| 所有ID | 解放確認 | 起動要求〜解放確認×単価の参考額 | 状態／資源解放 |
|---|---|---:|---|
| `55607c82-d3ac-11f1-8a85-1383f5decdec` | 18:50:26 UTC | 約US$3.49 | Inactive / true |
| `b7e48156-d3c9-11f1-af7f-7febb26930d6` | 19:31:03 UTC | 約US$0.66 | Inactive / true |

これは請求額ではなく、単価US$1/時からの参考値。実請求は未回収。累積の予約**上限**はM6がUS$20／基本枠24、プロジェクトがUS$61／基本枠100で、実際の支払額とは区別する。条件付き追加US$100は未使用。終了ガードは解放確認まで維持した。

## 次の段階

Phase5〜7は未着手。[目的とゴール](ROADMAP.md)を保ち、M6の約185〜194局面/秒・棋力・実機性能から次の実行単位と費用を見積もる。今回の合成対局は64手までで、長期戦・終盤の分布は限られる。次の研究では教師・局面分布と自己対局の評価設計を先に決め、固定val／testを守る。人間同士の対局・マルチプレイは対象にしない。
