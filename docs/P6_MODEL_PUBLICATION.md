# 学習済みM推論パッケージのHF公開契約

[3形式変換](P6_MODEL_CONVERSION.md)と[Web読込](P6_MODEL_DISTRIBUTION.md)の間で、
選択した重み・各実ONNX・最終評価を同じ配布ファイルへ結び付ける。
この変更は公開role・メタデータ／hash検証・catalog生成の実装であり、実Mの学習・最終評価・公開の完了記録ではない。
Linuxでの最終評価実行、実NN参照監査、下記組立関数を使う42ファイルのstagingと実配布の登録は後続作業として残る。

## 公開先と上限

- roleは`research-inference-package`。`model` repoとして`voxelshogi/voxelshogi-research-m-{architecture}-v1`を使う。
  architectureは`full`／`axial`／`geometry`／`cnn`のみ。
- 承認済みApache-2.0、public/manual、Community OFFを既存のHF公開ハーネスで要求する。
  manualは取得申請の設定であり、ユーザーへの追加アップロード承認待ちではない。
- ONNX／元重みは各512MiB以下、パッケージ全体は1,536MiB以下。
  小型S推論の各64MiB／全体512MiB、研究checkpointの容量契約は変更しない。
- plan、送信前の再検証、Linuxからの送信、固定Hub revision全ファイルhash照合の順で進める。
  データ、元重み、checkpoint、全モデル世代をMacへ中継しない。

## 必須ファイルと来歴

基本42ファイル（任意の`NOTICE`があれば43）を明示的に列挙する。

| 内容 | ファイル |
|---|---|
| 人が読める説明 | `README.md`、`LICENSE`、`manifest.json` |
| 同じ元重みと選択履歴 | `model.safetensors`、`selection.json`、`training-history.jsonl` |
| 固定した最終評価と全入力監査 | `final-protocol.json`、`input-audit.json` |
| 固定4局面の入力 | `inputs/{name}.f32`の4件 |
| 実配布モデル | `fp32.onnx`、`fp16.onnx`、`int8.onnx` |
| 形式ごとの全出力参照 | 3形式×4局面×Policy／Valueの24件 |
| 形式ごとの最終評価 | `evaluation/fp32.json`、`evaluation/fp16.json`、`evaluation/int8.json` |

研究manifestは既存Web契約に、`research.history`・`research.finalProtocol`・`research.inputAudit`の
path／bytes／SHA-256を追加する。元の`research.selection`と各形式の`evaluation.report`も同様に固定する。
選択履歴は元のraw bytesを保持し、全更新・train／val履歴と最初のval最小値を再確認する。
CUDAで実学習した固定M profileと、学習source・選択書出source・ONNX書出sourceを区別する。
未学習、CI fixture、部分run、小型Sへの差し替え、元重みとの不一致は拒否する。

`final-protocol.json`は事前固定した`protocol`と`roots`を持つ。
`protocol`は保護済み最終12局面・先後24局の元条件、`roots`は各idの`purpose="holdout"`・物理position hash・
手番正規化input hashである。元protocol／rootsのcanonical fingerprintをmanifestへ保存する。
形式別protocolで差し替えるのは評価sourceとmodel／M1の実行identityだけで、
case、seed、探索上限、評価上限、bootstrap、感度条件は維持する。
最終評価を学習条件やbest選択の調整に使わない。

## 実形式別評価との照合

### 変換からmanifestを組み立てる

`training.research_manifest_assembly.assemble_manifest`は、元の`conversion.json`と
7 metadataファイルのraw bytesから最終manifestを返す純粋関数である。
変換receiptのSHAと、学習前に固定した`final-protocol.json`のSHAを明示する。
後者は[元の保護済み12 rootからの固定slice](experiments/p6-final-protocol-freeze.md)を使い、
最終評価結果に応じてopeningやseedを差し替えない。

必要なbytesは`selection.json`、`training-history.jsonl`、`final-protocol.json`、
`input-audit.json`、`evaluation/{fp32,fp16,int8}.json`。
変換側が固定した選択・履歴・M weights metadataとの一致を確認し、各形式の報告を
それぞれのONNX／元重みへ結び付けた後、既存の完全な`review_manifest`を通す。
重複JSON key・非有限値・欠落／余計なファイルを拒否する。
元bytesのhashと量子化によるargmax不一致を保持し、不完全な評価を完了へ変更しない。

この関数はモデルや棋譜を実行せず、ファイルのコピー・HF公開も行わない。
Linux実行側は実変換・Rust再生・全NN監査後の同じ7ファイルを保持してmanifestを書き、
公開ハーネスの42ファイル全bytes／hash検証と固定HF版照合へ進む。

`evaluation/{precision}.json`は`schema="voxelshogi-research-format-evaluation-v1"`とし、
`complete`、`precision`、`evaluation_source_commit`、`model_sha256`、`weights_sha256`、
`protocol`、全24件の`games`、元`run.json`の`run_sha256`、実callback回数`actual_neural_queries`を持つ。
各実ONNXを`ort-cpu`・合法argmaxで評価する。元safetensorsで3形式の評価を代用しない。

公開検証は全24件の条件・先後・重複・棋譜prefix・終局結果・打切りを確認する。
元run／protocolのhashと全NN参照数を、3形式すべての`input-audit.json`へ照合する。
合法性のRust再生、元コーパス・全自己対局・開発入力・実NN参照の全件監査そのものは、
このメタデータ検証だけで代用できない。外部Linuxの実行側で終えてから組み立てる。
FP32との差分、argmax不一致、打切り、負の結果を保持し、bootstrap教師再現を一般棋力と呼ばない。

## 公開ハーネスとcatalog

Linuxで検証済みのfolderから`training.hub_release.plan_release`へroleと承認済み条件を渡す。
通常の`artifacts`／Sの`inference-package`では研究M manifestを受け付けない。
Cardには`Training and provenance`、`Evaluation`、`Inference`、`Access and license`の4節を埋める。
余計なoptimizer、非列挙ファイル、symlink、変更されたmetadataや参照値は送らない。

`publish_release`後、`verify_release`で固定revisionの全ファイルと設定を確認してから、
`training.research_inference_release.catalog_release`でcatalog entryを作る。
entryは`profile="research-m-v1"`と実architectureを明示し、元manifest・noticeのbytes／hash、
固定Hub commitを含む。送信成功だけのreceiptや、確認後に変わったfolderから登録しない。
HFの取得ゲートを別経路で迂回せず、Webは同じ実ファイルを読ませる。

Macの検証には手書きの履歴・評価メタデータ・不透明な小さいファイルとfake portだけを使う。
実Mや実ゲームを実行せず、軽量テストの成功を本学習・棋力・Web公開の証拠にはしない。
