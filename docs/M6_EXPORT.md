# M6の学習済み重みからの変換

M6-4の変換処理を学習前に準備する。**本データの学習・変換・HF公開は未実施。** 基準は[学習・評価契約](M6_TRAINING_CONTRACT.md)と[固定評価ハーネス](M6_EVALUATION.md)。M3の未学習モデルの変換・公開許可は、そのまま学習済み重みの公開許可にしない。

## 評価した重みを使う

```bash
# 外部Linux。固定評価が完了したフォルダーと、新しい出力先を指定する形。
uv run --project infrastructure/cuda --locked python -m export.generate runs/m6/export --selected-evaluation runs/m6/eval-trained
```

入力はval最良epochの重みを固定し、test全件・Random40局・M1探索20局の評価を完了したフォルダー。コードcommit・seed・教師契約・入力cache・split件数・選択元のreceiptと、評価したsafetensorsのサイズ／SHA-256を照合する。未完了の対局、重複したゲーム一覧、testや元ファイルの変更、途中epoch、別コードや別seedを拒否する。

変換の直前にも60局の全手と終局をRustで再生し、同じ序盤・先後・上限・生カウント・paired区間に一致することを確認する。対局を再探索する処理ではない。評価したFP32 safetensorsをモデルへstrictに読み込み、保存し直した重みのSHA-256も元と完全一致させる。初期seedの重みへの置換を、学習済みというラベルで通さない。

その一つのcheckpointからFP32・FP16・INT8重み版を作る。学習アーキテクチャや入力43ch／出力1,067,985行動を無記録で小さくしない。INT8はM3と同じ重みのみの対称per-tensor変換で、演算とactivationはFP32、ORTの参照はbasic最適化。FP16は入出力FP32を維持する。testを校正・変換方法の調整には使わない。

4つの固定入力で、FP32はTorchと照合し、各低精度版は同形式のORT CPU参照とFP32との差を別々に残す。変換により下がった精度や異なるpolicyを隠さず、各実ファイルを[固定testと対局](M6_EVALUATION.md)にも渡す。サイズ・数値差・教師精度・棋力と、ブラウザ実機の性能を混同しない。

## 来歴と公開の境界

manifestの`trained=true`には、元のtraining binding／receipt、評価した重みとtest／対局reportのhash、教師のsplit件数、正式評価60局の情報を付ける。package検査は、この来歴を失ったり別の重みhashへ差し替わったりしたmanifestを拒否する。元のoptimizer／RNGを含む`.pt`は配布モデルへコピーしない。

公開ライセンスが未確定の間は`license=null`の私的な変換で、公開承認に置き換えない。HFへ送る前にライセンス・Model Card・公開ファイル一覧を確定し、[HFハーネス](HF_PUBLICATION.md)でpublic/manual・Community OFFと全hashを確認する。既存のM3公開経路は引き続き未学習だけを受け付け、M6の重みをCloudflareへ複製して取得ゲートを迂回しない。

WebはHFから取得したモデルフォルダーを選び、実ONNXと同形式の照合入力／出力をWorkerへ渡す方式を準備する。公開catalogに固定したmodel ID・形式・manifest／ファイルhashへ照合する。HFの資格情報をブラウザへ埋め込まず、選択したファイルは端末内だけで使う。各変換版・backendの読み込み、全出力の数値照合、観戦への接続はM6-5の後続作業。

## CIで確認すること

Macは小さいopaque metadataの正例・拒否条件と静的検査だけ。fixtureの30,000／3,000／3,894件は検査用の架空の分割で、実データのsplit別件数として報告しない。

Linux CIではValue headの最終行列を0・biasを0.5にしたfixture重みを変換し、全3形式でValueが手計算の`tanh(0.5)`になることを確認する。これは重みの読み込み・変換の試験であり、学習の成果ではない。safetensorsの完全一致、同形式参照の全出力比較、来歴の改変検出、別schemaの小さいRust棋譜の再生・集計も確認する。実データでの学習済みモデルの成績・実機対応は、後続の実測がそろうまで未確認として残す。
