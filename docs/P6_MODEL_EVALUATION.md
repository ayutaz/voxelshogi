# M規模モデルを固定条件の評価対局へ接続する

**2026-11-12・一時停止**：既存Sの公開デモと、Mの少量2 run・48局評価を現段階の成果とする。
本比較12 run・MのWeb配布・観戦表示2案／実端末各60分は未完了のまま停止する。
追加GPU・生成・学習を自動再開しない。[停止時点の結果と固定HF版](RESEARCH_CHECKPOINT_20261112.md)を現在の確認元とし、
以下の旧「現在」「次」「予算」は対象時点の記録、実行コマンドは再開後の手順として読む。

2026-11-05。4構造の学習結果を、既存のRust評価対局・合法手argmax／PUCT32で比較するための実装契約。実データ採用・GPU学習・比較対局の実行完了や棋力改善の記録ではない。

`training.research_weights`はFull／Axial／Geometry／3D-CNNの固定M構造だけを扱う。safetensorsのヘッダーへ、構造寸法、seed、学習source、学習bindingのhash、選んだbest／latestと更新数を埋め込む。既存の対局protocolが持つファイルSHA-256で、この来歴と実際の重みをまとめて固定する。metadataの読み取りは上限付きのヘッダーだけを読み、Torchやモデルを初期化しない。

実ファイルの作成・ロード・推論は外部Linux専用。writerは有限のFP32 tensor、構造に対応するparameter数、未使用の出力先を要求する。loaderはファイル形式・SHA・metadata、実tensorのdtype・有限性、全state keyとshape、ロード終了後の再hashを確認する。CUDAを指定したときは実CUDAと事前の決定的workspace設定を要求する。CPUへの暗黙の切替や半精度重みの自動採用はしない。

呼び出し側は、検証済みの学習checkpointから選択したstateとprogressを読み、metadataの`source_commit`・`architecture`・`seed`・`training_binding_sha256`をそのrun bindingから作る。`step`と`checkpoint_role`は実際に選んだ保存点から取る。このAPIのmetadata作成だけでは、教師品質や保存点の採用を証明しない。学習sourceと、後で評価するエンジンsourceは別々に記録する。

評価runnerは明示的なresearch tagがある重みをこのloaderへ渡す。tagのない従来Sモデルは既存経路を使い、不正なresearch tagをSとして読み替えない。どちらのモデルでも同じ開始局面・先後・M1上限・停止条件・Rust再生と入力監査を使う。argmaxは合法手の同点を最小action IDで選び、PUCT32は既存の32 simulations／深さ64／cpuct1・noiseなし・木の再利用なしを維持する。観測callbackを全NN参照へ渡し、探索枝の監査を省かない。

軽量テストは手書きの4構造metadata、壊れた来歴やtoy寸法、旧S経路との区別、Mac境界、fake playerによるpolicy／停止／観測の受け渡しを確認する。Linux結合試験では実M4構造の重みを保存し、constructorとは異なる値を含むstateの復元、実Rust特徴量での合法手選択、PUCT evaluatorへの接続を検証する。実GPUでの学習・保存再開・対局とHF公開は、[全体の実行計画](P6_EXECUTION_PLAN.md)の後続実行で証拠をそろえる。

## 完了したvisit学習から評価用bestを取り出す

2026-11-12 JST。`training.research_selection`を追加した。
少量試行と本比較の学習後に使う実行経路であり、実M学習・棋力評価・Web配布の完了報告ではない。

`review_selection`は、固定M構造のvisit binding、latest／bestの検証済みreceipt、全train／val履歴を照合する。
latestが固定した全更新数へ到達し、予定されたvalがそろっていることを要求する。
履歴全体の最小val損失を選び、同点なら先の更新を採用する。これはfitterの厳密な`<`による選択と同じである。
選択step・最小損失・receiptのprogress・実学習例数が一致しなければ拒否する。
開発対局や最終holdoutの結果で保存点を選び直さない。

外部Linuxで、事前に照合したrun bindingをJSONファイルへ固定して次を実行する。
`expected-binding.json`の内容は`run.json`の`binding`オブジェクトそのもので、run全体のJSONではない。
入力runは凍結済みの学習成果を使い、実行中の学習先へ接続しない。

```bash
uv run --project infrastructure/cuda --locked --no-sync python -m training.research_selection \
  runs/p6/research-pilot/full/continuous \
  runs/p6/research-pilot/full/selected \
  --binding runs/p6/research-pilot/full/expected-binding.json
```

実行時はcleanな実装source、run binding、checkpoint pointer／receipt／stateの実hashを確認する。
`weights_only=True`・CPUへの明示ロードでbest payloadを読み、全state keyとshapeを固定Mモデルへstrict loadする。
FP32・有限性・parameter数はresearch weights writerが確認する。
読み取り中のstate・history・run binding・実装sourceの変更と、既存の出力先を拒否する。
出力は`model.safetensors`と`selection.json`で、後者に学習／export sourceの来歴、latest／best receipt、
履歴hash、実重みのhashを記録する。元checkpointやoptimizerを推論配布へ混ぜない。
この選択記録は推論公開の承認ではなく、対局評価と3形式変換・形式別評価へ渡す入力である。

軽量テストは手書きの損失列とopaque portで33件、関連範囲を含め46件を確認し、22種類の意図的な不具合を検出した。
実固定Mのcheckpointからconstructor／latestと異なるbest値を取り出す結合試験も追加し、Linux CIで検証する。
Macでは実Tensor・checkpoint・コーパスを処理していない。
M専用推論manifest・公開role・Webの容量制限対応、実3形式の変換と評価は後続作業として残る。
