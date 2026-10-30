# M6の学習済み重みからの変換

val選択・固定評価済みの重みからの3形式変換とHF公開は完了（[M6完了記録](M6_COMPLETION.md)）。公開版はFP32・FP16重み／FP32計算・INT8重み／FP32計算。初回FP32変換と混合精度FP16の失敗は[履歴](M6_PORTABLE.md)に保持する。以下は現行の変換・来歴契約と初期実装時の検証記録。M3未学習モデルの承認とは別に、M6対象のApache-2.0を確認済み。

## 評価した重みを使う

```bash
# 外部Linux。固定評価が完了したフォルダーと、新しい出力先を指定する形。
uv run --project infrastructure/cuda --locked python -m export.generate runs/m6/export \
  --selected-evaluation runs/m6/eval-trained \
  --training-source-commit 874aed9ac28c9e50e178c2dda706941b2d3294da \
  --fp16-weights-only --license Apache-2.0
```

入力はval最良epochの重みを固定し、test全件・Random40局・M1探索20局の評価を完了したフォルダー。学習元と変換元を明示したコードcommit・seed・教師契約・入力cache・split件数・選択元のreceiptと、評価したsafetensorsのサイズ／SHA-256を照合する。未完了の対局、重複したゲーム一覧、testや元ファイルの変更、途中epoch、宣言と異なるコードや別seedを拒否する。明示的な学習元・変換元の分離は後述の`export_provenance`で結び付け、旧reportのsourceを書き換えない。

変換の直前にも60局の全手と終局をRustで再生し、同じ序盤・先後・上限・生カウント・paired区間に一致することを確認する。対局を再探索する処理ではない。評価したFP32 safetensorsをモデルへstrictに読み込み、保存し直した重みのSHA-256も元と完全一致させる。初期seedの重みへの置換を、学習済みというラベルで通さない。

その一つのcheckpointからFP32・FP16・INT8重み版を作る。学習アーキテクチャや入力43ch／出力1,067,985行動を無記録で小さくしない。INT8はM3と同じ重みのみの対称per-tensor変換で、演算とactivationはFP32、ORTの参照はbasic最適化。公開FP16重み版は重みをFP16で保存し、活性・演算と入出力はFP32を保つ。旧混合FP16は別の失敗履歴として区別する。testを校正・変換方法の調整には使わない。

4つの固定入力で、FP32はTorchと照合し、各低精度版は同形式のORT CPU参照とFP32との差を別々に残す。変換により下がった精度や異なるpolicyを隠さず、各実ファイルを[固定testと対局](M6_EVALUATION.md)にも渡す。サイズ・数値差・教師精度・棋力と、ブラウザ実機の性能を混同しない。

## 来歴と公開の境界

manifestの`trained=true`には、元のtraining binding／receipt、評価した重みとtest／対局reportのhash、教師のsplit件数、正式評価60局の情報を付ける。package検査は、この来歴を失ったり別の重みhashへ差し替わったりしたmanifestを拒否する。元のoptimizer／RNGを含む`.pt`は配布モデルへコピーしない。

公開ライセンスが未確定の間は`license=null`の私的な変換で、公開承認に置き換えない。HFへ送る前にライセンス・Model Card・公開ファイル一覧を確定し、[HFハーネス](HF_PUBLICATION.md)でpublic/manual・Community OFFと全hashを確認する。既存のM3公開経路は引き続き未学習だけを受け付け、M6の重みをCloudflareへ複製して取得ゲートを迂回しない。

WebはHFから取得したモデルフォルダーを選び、実ONNXと同形式の照合入力／出力をWorkerへ渡す方式を準備する。公開catalogに固定したmodel ID・形式・manifest／ファイルhashへ照合する。HFの資格情報をブラウザへ埋め込まず、選択したファイルは端末内だけで使う。各変換版・backendの読み込み、全出力の数値照合、観戦への接続はM6-5の後続作業。

## CIで確認すること

Macは小さいopaque metadataの正例・拒否条件と静的検査だけ。fixtureの30,000／3,000／3,894件は検査用の架空の分割で、実データのsplit別件数として報告しない。

Linux CIではValue headの最終行列を0・biasを0.5にしたfixture重みを変換し、全3形式でValueが手計算の`tanh(0.5)`になることを確認する。これは重みの読み込み・変換の試験であり、学習の成果ではない。safetensorsの完全一致、同形式参照の全出力比較、来歴の改変検出、別schemaの小さいRust棋譜の再生・集計も確認する。実データでの学習済みモデルの成績・実機対応は、後続の実測がそろうまで未確認として残す。

## FP16重み版と学習・変換sourceの分離

実学習済みの混合FP16版はLinux実機のWASMで同形式参照の数値基準を超え、NVIDIA VulkanのF16を検証用フラグで有効にしても基準未達だった。旧版・初回HF revision・失敗した48条件の記録は[固定した診断結果](experiments/m6-fp16-portability-diagnosis.json)に保持する。誤差基準を変更せず、`--fp16-weights-only`でrank>=2の重みをFP16へ丸め、明示的なCastでFP32へ戻して演算する版を追加する。bias・活性・演算・公開I/OはFP32。無限大・NaN・65504超の重みはclipせず拒否する。これは混合FP16演算と別の変換方式であり、配布時は「FP16（重み）」と表示し、新しい実ファイルを同じ固定test・対局で評価する。

学習し直して既存の結果を別commitへ付け替える代わりに、変換だけを改善できるようsourceの役割を明示する。`--training-source-commit`を独立した期待値として指定した場合に限り、`training.export_provenance`の`voxelshogi-export-lineage-v1`へtraining／export両commitを記録する。元の学習binding・checkpoint receipt・test・60局とそのhashは変更しない。指定なしの旧契約ではsource不一致を引き続き拒否する。変換済み評価とブラウザも同じ両sourceを検証する。

```bash
# 外部Linuxで実行。2つのsourceはそれぞれ実際の固定commitを指定する。
uv run --project infrastructure/cuda --locked python -m export.generate runs/m6/portable-export --selected-evaluation runs/m6/eval-torch --training-source-commit "$training_commit" --fp16-weights-only --license Apache-2.0
```

専用Workerは検証済みmanifestからFP32演算モードを導き、main側も同じmanifestから期待値を導く。FP16重み版と宣言された場合だけ`shader-f16`を不要とし、FP32演算の証拠、全固定入力・全出力の同形式照合、実providerを要求する。混合FP16のfeature確認、数値基準、M3未学習モデルの形式は維持する。

私的な実機試作では同一4入力のPolicy全1,067,985要素とValueがWASM／通常設定WebGPUで基準内だった。これは実行経路を選ぶ診断であり、正式な変換版の固定評価・HF公開・全48条件計測・公開catalogの完了とは区別する。正式な実行はsourceを固定して再検証する。
