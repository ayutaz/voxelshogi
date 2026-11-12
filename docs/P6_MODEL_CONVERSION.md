# 選択済みM重みの3形式変換と実ONNX評価

**2026-11-12・一時停止**：既存Sの公開デモと、Mの少量2 run・48局評価を現段階の成果とする。
本比較12 run・MのWeb配布・観戦表示2案／実端末各60分は未完了のまま停止する。
追加GPU・生成・学習を自動再開しない。[停止時点の結果と固定HF版](RESEARCH_CHECKPOINT_20261112.md)を現在の確認元とし、
以下の旧「現在」「次」「予算」は対象時点の記録、実行コマンドは再開後の手順として読む。

[実行計画の5](P6_EXECUTION_PLAN.md)・[Web読込契約](P6_MODEL_DISTRIBUTION.md)へつなぐLinux実行経路。
変換コード・形式別評価adapterを追加した段階であり、実M学習・変換・24局評価・HF公開の完了記録ではない。
新しい課金を始める前に、実行sourceのCI、所有実機・独立停止期限、生成・評価・転送を含む費用を固定する。

## 入力と同じ重みの維持

`training.research_selection`の出力folder（`selection.json`と`model.safetensors`）と、
その選択に使った元の完成runの`events.jsonl`を使う。
履歴をJSONから再出力してhashを変えたり、途中runや最終holdoutで選んだ重みへ差し替えたりしない。
全更新数・全train／val履歴・latest／best receiptから、最初のval最小値を再確認する。
CUDAで学習した固定M profile、元重みの実bytes／SHAと内部metadataも照合する。

学習source、bestを書き出したsource、今回のONNX書き出しsourceを別々に記録する。
書き出しはcleanな凍結sourceだけで行い、最後にもsourceと元重み・選択receipt・履歴の不変を確認する。
Mの実model constructorで全state key／shapeとFP32の有限性を検証してから、変換用のCPUへ配置する。
CPU変換・ONNX評価も外部Linuxで行い、Macへ元重み・checkpoint・データを中継しない。

## 変換の実行

`FROZEN_EXPORT_SOURCE`・`SELECTION_SHA256`・`CONVERSION_DEADLINE`は、
実行許可済みのsource、元receiptのSHA-256、所有ジョブの固定絶対期限（UTC epoch秒）である。
起動時に期限を延ばさず、新しい出力先を使う。

```bash
uv run --project infrastructure/cuda --locked --no-sync python -m export.research_generate \
  runs/p6/selected runs/p6/completed-run/events.jsonl runs/p6/conversion \
  --selection-sha256 "$SELECTION_SHA256" \
  --source "$FROZEN_EXPORT_SOURCE" \
  --deadline "$CONVERSION_DEADLINE"
```

1. 同じ元FP32重みと選択receipt・履歴をLinuxの出力folderへbyte一致で保存する。
2. 標準4 fixtureをRustで再生し、特徴量encoderとRustの特徴量が一致することを確認する。
3. 実M networkから固定batch1・opset18・external dataなしのFP32 ONNXを書き出す。
   全Policy／ValueをTorch CPUと比較し、同形式のORT CPU参照値を保存する。
4. 同じFP32 graphからFP16重み版とINT8重み版を別々に生成する。
   計算とactivationはFP32のまま、実際の変換tensor数・要素数を保存する。
   各形式・全fixtureの参照値とFP32との差分も保存する。精度低下やargmax不一致を隠さない。
5. graphの形式・来歴・固定shapeと全出力ファイルのbytes／SHAを検査し、元入力の不変と期限を再確認する。

`request.json`は小さい実行条件、失敗時の`failure.json`は段階とerror classだけを記録する。
既存の出力を上書きして再送せず、失敗した部分結果を完成品として扱わない。
期限は各工程前後で協調停止する。処理中の強制停止と実機終了は、所有ジョブのsupervisorと独立監視で行う。

## 変換完了と公開を分ける

変換成功時の出力は`schema="voxelshogi-research-conversion-v1"`の`conversion.json`である。
`conversion_complete=true`でも`inference_publication_approved=false`とし、`manifest.json`は作らない。
このfalseは形式別評価と公開検証が未完了という状態であり、ユーザーへの追加承認待ちではない。

後続で固定した最終12 root×先後の24局を**各実ONNXで**評価し、全手のRust再生と全NN参照の監査を行う。
完成した形式別report、共通protocol・最終root集合のSHA、Model Card・license・実配布物のhashを結び付けてから、
[M専用公開role](P6_MODEL_PUBLICATION.md)に渡す最終manifestを組み立てる。
M専用roleと検証済みreceiptからのcatalog生成APIは実装済み。Linux最終評価・全入力監査・最終組立・固定HF全hash・実catalog登録は後続作業である。
public/manual・Community OFFを維持し、送信と全ファイル再確認はLinuxから行う。

## 実ONNXを使う対局評価

既存の`evaluation_v2_runner`で、model participantを
`policy="legal-argmax-v1"`・`backend="ort-cpu"`、`artifact_sha256`を**評価するONNXのSHA**にする。
`artifacts["model"]`にも、その同じONNXファイルを渡す。
元のsafetensorsを渡して3形式を評価したことにはしない。ONNXでPUCTやCUDAを暗黙に選ばない。

各graphには次のmetadataを保存し、読込時に検証する。

- `voxelshogi.research`：固定Mの構造・学習source・binding・bestの更新位置。
- `voxelshogi.precision`：`fp32`／`fp16`／`int8`。
- `voxelshogi.weights_sha256`：同じ元FP32重みのSHA。
- `voxelshogi.export_source`：凍結したONNX書き出しsource。
- `voxelshogi.conversion`：FP32ならnull、変換版はFP32計算と実変換件数の設定。

重複key、不明なVoxelShogi tag、未選択／未学習のprofile、不正な変換件数は拒否する。
外部tensorはnested graph内も含め拒否し、別の`.onnx.data`を暗黙に読むことはしない。
固定FP32 input／output、実ファイルSHA、CPUExecutionProviderだけでの実行を検査する。
初期化後もSHAと停止要求を再確認し、着手前の実NN入力observerを既存の全入力監査へ接続する。
結果には実ORT versionを記録し、CPUの結果をCUDA性能と呼ばない。

## 固定した最終24局を3形式で実行する

`training.research_final_evaluation.run_final_formats`は、実Linuxの変換結果から
FP32／FP16重み／INT8重みの各ONNXを読み、同じ最終12 root×先後＝24局、計72局を実行する。
変換結果と学習前に固定した最終protocolのraw SHA、clean source、全3形式のpath／bytes／SHAを要求する。
最終rootの盤面とcanonical入力はモデルを割り当てる前にRustで再生・照合する。

```bash
uv run --project infrastructure/cuda --locked --no-sync python -m training.research_final_evaluation \
  runs/p6/conversion runs/p6/final-protocol.json runs/p6/final-evaluation \
  --conversion-sha256 "$CONVERSION_SHA256" --frozen-sha256 "$FINAL_PROTOCOL_SHA256" \
  --source "$FROZEN_EXPORT_SOURCE" --deadline "$FINAL_EVALUATION_DEADLINE" \
  --development-sources runs/p6/references/plan.json \
  --development-sources-sha256 "$DEVELOPMENT_SOURCES_SHA256" \
  --corpus runs/m4/production --selfplay runs/p6/input-selfplay \
  --selfplay-protocol runs/p6/selfplay-protocol.json --protection runs/p6/input-protection/config.json
```

各形式の全手を既存のnative verifierで再検証し、全24件から指標を再計算する。
実NN呼出しの全履歴を`queries.jsonl`へ保存し、実呼出し数とuniqueな物理局面／canonical入力数を区別する。
基底の全入力監査はM4全split・供給した自己対局の全公開raw sample・既存保護と、全対局・全queryを照合する。
[開発用全入力の再構成](P6_DEVELOPMENT_REFERENCES.md)で、元G2の48局と全NN参照、少量学習後の対局、条件選定へ使った全runを一覧に固定する。
実行前後のRust再生・全ファイルhash・全query列挙を要求し、元の監査集合へ追加する。
実行workflowは全対象のHF sourceを取得・照合して一覧へ含める。未列挙sourceの非使用を自動証明するものではない。
採用した全学習sourceの由来binding・追加監査と、実Mの72局実行はまだ完了していない。

各形式のreportと共通auditを[manifest組立](P6_MODEL_PUBLICATION.md#変換からmanifestを組み立てる)へ渡し、元重み・選択履歴・凍結条件・各runのhashを閉じる。
最後に元の変換物・source・選択／履歴・凍結protocolを再確認し、期限内だけ`complete.json`を作る。
途中失敗・期限切れ・query0・再生不一致・漏洩・変更された入力は失敗記録に残す。

`assembled-manifest.json`はmetadataであり、配布用`manifest.json`や42ファイルのstagingではない。
`inference_publication_approved=false`を維持し、HF送信・公開登録は行わない。
所有GPU／独立停止監視・固定費用・転送余裕は外側のworkflowで先に用意する。
Macの検証は不透明な小さいfakeファイルと手書きcohortのみで、実72局やモデル推論の証拠にはしない。

## 検証範囲

Macでは手書きの履歴と不透明な小さいファイル、fakeのgraph／ORT portだけを使う。
新規37変異を、import失敗やtimeoutではなく、実際に失敗したassertionで検出する。
CPUを拒否するテストでは、CPU以外のbinding・receipt・metadataは整合した入力を用意し、
他の不整合だけで拒否されてしまうテストを避ける。

Linuxの`test_research_conversion_native.py`は小さい実graphで3形式の保存dtype、metadata、
全参照値、ORT実行とRustの合法手選択、nested external tensorの拒否を確認する。
これは実M規模の変換・棋力・速度・GPU・実ブラウザの証拠ではなく、Macでは実行しない。
通常PRでは既存方針どおりnative結合試験を省き、main／定期の深いLinux検証で実行する。
