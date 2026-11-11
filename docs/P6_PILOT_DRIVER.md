# 実M少量学習の実行ドライバー

[再開計画](P6_RESUMPTION_PLAN.md)のA・Cに使う実行経路を
`infrastructure/research/pilot/`へ移し、一時ファイルだけに依存しないようにする。
本書は実行契約であり、実2 run・CUDA再開・HF公開の成功報告ではない。
GPUの起動・学習条件の採用・最終評価は、この変更では実行しない。

## 入力と実行環境

- `attempt.validate_inputs`はsource、採用前監査、全開発入力の保護、教師診断のhashと、
  その診断に基づく明示的な教師判断を要求する。少量試行だけを許可し、本比較への採用は許可しない。
- 固定した実M構造・CUDA・全更新数を使う。小さいCI用モデルやCPUへの置換を拒否する。
  Pythonは外部Linuxの固定したuv／CUDA lockに従う。
- `attempt.run`はcleanな実sourceを確認し、入力を再監査してtrain／val特徴量を作る。
  元の固定入力と開発保護・教師判断を、保存再開のbindingへ含める。
  test特徴量、最終holdout、対局評価はこのドライバーでは生成・実行しない。
- `child.run_attempt`は別process groupで実行し、認証情報を渡さない。
  固定deadlineと停止要求で所有processへTERM、20秒後に必要ならKILLを送る。
  既存の起動logを上書きして再起動せず、観測結果を照合する。

## 1試行と同一軌跡の再開検証

`infrastructure.research.pilot.job`が2構造の実行をまとめる。
元のselfplay・protection・開発評価screenと採用前diagnosisの4つの固定HF releaseを、
外部Linuxで各revision・全bytes／SHA-256・public/manual・Community OFFまで再確認してから学習へ進む。
最初の構造はFull対照、2つ目は別の実M構造とし、データ・教師判断・seed・batch・全更新数は共通にする。
以前のdiagnosisは検証済みreceiptだけがcontrollerへ回収され、全ファイルplanが残っていない。
その場合だけ、元の7ファイルを固定revisionで外部Linuxへ取得してplanを再構成し、
元のreceiptのrelease SHAと完全一致してから再検証する。Macへmanifestの全IDやParquetを中継しない。
単なる再計算hashを正解とせず、元の保存済みrelease hashとの不一致や欠けたファイルは拒否する。
同じ更新数が同じFLOPsになるとは主張せず、本比較の計算量は実測後に固定する。

凍結済みjob JSONと、元のhashに一致する累積state ledgerを所定のowned directoryへ配置し、
controllerのsource／owner／独立期限／実機確認後に次を実行する。

```bash
uv run --project infrastructure/cuda --locked --no-sync python -m infrastructure.research.pilot.job runs/p6/research-pilot/job.json
```

CLIはHF認証を環境からメモリへ取り込み、providerキーを拒否する。
clean source・HFのアカウントと組織・実CUDA環境を確認し、起動済みmarkerがあるjobを再送しない。
childを含む所有RSS・CPUとdevice全体のGPU利用を観測する。RSS超過は学習停止を要求し、
観測値を実測区間外のpeakやGPU専有量へ拡張しない。
成功・失敗の両方で、追記されたstate ledgerの過去履歴・容量上限を検証して小さい記録を保存する。
このjobの`learning_complete`は2 runの学習部分だけを示し、開発用対局・HF結果dataset・棋力判断・Phase6完了とは区別する。

`cycle.run_cycle`へ凍結済みinputs、途中停止step、別々の固定compute_deadlineとdeadline（転送終了）、公開API、
固定revisionの取得port、累積state upload ledgerを渡す。順序は次のとおり。

1. 連続実行で全更新数を学習する。
2. 同じ条件を途中stepで止め、型付きJSONとsafetensorsのresearch archiveを作る。
3. 外部LinuxからHFへ公開し、固定版の全ファイルhashを照合して別directoryへ復元する。
4. 復元したmodel／optimizer／乱数／進捗から残りを学習する。
5. 連続・復元後のlatest／best両方と全train／val履歴を完全一致で照合する。
6. 連続実行の最終stateもHFへ退避し、全ファイル検証と復元を確認する。

これは**科学的な1 run＋同一軌跡の再実行**で、独立seedを2本得たことにはならない。
時間・更新数・費用の見積もりには両軌跡、特徴量準備、archive、転送・復元・終了を含める。
テンソルの値・型・shape、optimizer、Python／NumPy／Torch／CUDA RNG、進捗、bindingを比較する。
checkpointの直列化byteが同じことだけで数値一致を代用しない。

## HF保存と復旧

保存先は`voxelshogi/voxelshogi-research-training-state-v1`、roleは`research-training-state`。
[HF公開ハーネス](HF_PUBLICATION.md)を通し、public/manual・Community OFF・Apache-2.0・
State Card・全ファイルhashを要求する。これは推論用モデル配布先ではない。
実checkpointやデータをMacへ中継しない。

一度でも公開を試みたcontrol directoryは再使用しない。
uploadの応答不明を理由に盲目的に再送せず、publication-attempt・receipt・固定HF版を照合する。
更新されたupload ledgerと必要成果を回収する前に、学習ホストを終了しない。
失敗時も、停止したchildのcontinuous／interrupted／restoredにあるcheckpointを検証して
残りの転送時間内に型付きarchiveの公開・全hash照合・復元を試みる。
不正なcheckpoint、空のdirectory、期限超過を退避成功には数えない。
以前のuploadや今回の救出の応答が不明な場合は追加の送信を止め、既存markerとreceiptの照合へ戻す。
救出できても元の試行は失敗のままで、controllerのledger回収と所有確認がそろうまで終了を許可しない。
このmodule群はレンタル、独立停止監視やhostの解放を行わない。
ブラウザoperator専用の自動解放を、未退避checkpointのある学習へ流用しない。

## 検証範囲と次の作業

手書きのfake tensor・SDK・process・archive portを使う軽量テストで、実行順序、
入力binding、全更新数と途中停止の区別、資格情報を含まないchild環境、
全履歴とlatest／bestの検証、公開未検証時の拒否、二重送信拒否を確認する。
意図的な38種類のバグを関連テストで検出し、既知変異カタログへ登録する。
Macで実Torch、GPU、コーパス生成、HF uploadは実行しない。
このfake検証は実CUDA再開の証拠ではなく、Linuxの関連CI成功も実2 runの成功とは扱わない。

実行前には、教師判断・2構造・更新数・batch・共通計算予算を固定し、
全工程見積もりと所有資源・独立期限、state救出・ledger回収を含む外部supervisorを接続する。
実行後の開発用対局と全NN参照監査・費用・HF結果退避も別に必要。
最終holdoutを調整に使わず、12 run本比較とWeb配布の完了条件を維持する。

## 学習後の出所別検証と開発48局

`infrastructure.research.pilot.validation`を後続の検証APIとして追加した。
`origin_metrics`は固定valだけを受け取り、同じ選択済み重みでterminal／bootstrapのPolicy CE・Value MSE・合計損失を別々に計算する。
集計は実行数で重み付けし、存在しない由来は`available=false`として残す。
bootstrapへの一致を、実際の勝敗予測精度と呼ばない。検証batchの前後にも停止要求を確認する。

`development_protocol`へ渡す凍結スライスは、検証済みscreenの
`protocols["legal-argmax-v1"]`を`protocol`、`families`を同名のキーに持つオブジェクトである。
そのcanonical fingerprintを学習前の実行条件へ固定する。
12開始局面のid／seed／層／追加手数、6 family、M1深さ3／20,000 nodes／TT4,096を維持し、
実装source・実M重みSHA・CUDA合法argmaxと、そのsourceに対応するM1の識別子だけを差し替える。
最終holdoutを渡したり、結果を見て開始局面を差し替えたりしない。

`run_development_pair`はFull／Geometryの2つの選択済みフォルダと各`selection.json`の固定SHAを受け取る。
実重みのSHA・research header、best／latestの更新数、来歴、同じseed・共通学習bindingを確認する。
学習・重みexport・対局評価のsourceを別々に記録し、後続の評価修正だけを理由に既存の学習重みを作り直さない。
各12局面×先後の24局を実行し、Rustで全棋譜を再検証する。
実際のmodel callbackから全NN参照履歴を保存し、その場でRust再生と物理／手番正規化入力を確認する。
最後にM4全split・公開自己対局全sample・保護集合・対局経路・実NN参照を監査する。
24局の部分成功、NN参照の欠落、重複、実行中に変わった重み、期限超過は`complete.json`を作らず、失敗と部分結果を残す。
6 familyの等重み得点上下限と、開始局面ごとの既存bootstrap集計を併記し、相関と打切りの制約を維持する。

この全入力監査には**学習用4 releaseに加えてM4 production-64の実ファイル**も必要である。
元の固定HF releaseから外部Linuxへ直接取得し、起動見積もりに取得・全件検証の時間と転送を含める。
MacへM4コーパスやNN参照履歴を回収しない。

これらは実行APIであり、現在の`pilot.job`の`learning_complete`を48局完了へ拡張するものではない。
実行前に、固定valの再構成・同じbestモデルのロード、全検証のdeadlineと資源監視、
結果dataset公開、更新ledger回収、所有ホスト解放を外部supervisorへ接続する必要がある。
純粋／fake portの検証を、実CUDA・実48局・全入力監査の実行証拠へ読み替えない。

## 固定valの再構成と選択モデルの診断実行

`attempt.prepare_corpus`を学習と診断で共有する。cleanな凍結source、元の全入力hash、
採用前監査・全開発入力の保護・教師判断を再検証し、同じtrain／valとprovenanceを作る。
教師判断と保護のhashを加えた後に、特徴量全体のdigestを再計算する。
診断側だけ異なる分割や保護条件を使って、その差を無視する経路は作らない。

`pilot.post`はこの再構成結果を実run binding・全設定・CUDA環境と照合し、
完了したrunのbestを[選択・書き出し](P6_MODEL_EVALUATION.md#完了したvisit学習から評価用bestを取り出す)して、
`research_weights.load_research_network`からロードする。
このnetwork loaderを合法argmax／PUCT32とも共有し、全重みのhash・metadata・FP32・有限性・
全state key／shapeのstrict loadとCPU／CUDAの明示的な配置を維持する。

外部Linuxで、学習を終えた同じsource・CUDA環境から次を実行する。
`pilot_compute_deadline`には凍結した`job.json`の`compute_deadline`を渡し、実行時に延長しない。

```bash
uv run --project infrastructure/cuda --locked --no-sync python -m infrastructure.research.pilot.post \
  runs/p6/research-pilot/full/inputs.json \
  runs/p6/research-pilot/full/continuous \
  runs/p6/research-pilot/full/diagnostics \
  --compute-deadline "$pilot_compute_deadline"
```

Geometryも同じ条件で実行する。`CUBLAS_WORKSPACE_CONFIG=:4096:8`をTorchの初期化前に設定し、
CPUへの暗黙の切替を行わない。選んだ同じ重みで出所別の固定valを評価し、
その後も重み・特徴量・run bindingが変わっていないことを確認する。
`complete.json`へ入力／binding／特徴量／選択重みのhash、選択step、由来別指標と経過時間を保存する。
この経過時間は再構成・hash・保存・ロードも含み、純粋なGPU性能とは扱わない。
中断・不一致・test指標の混入は失敗として保存し、既存の出力先を再使用しない。

この段階もGPUの起動・HF結果公開・台帳回収・解放は行わない。
次のworkflowが学習・両診断・開発48局・結果の固定HF版照合をつなぐ。
小さい台帳の回収・所有確認・実機解放は、引き続き外部supervisorで接続する。
データ・checkpoint・NN参照履歴はLinuxとHFに保持し、Macへ移すのは小さい進捗・hash・集計だけとする。

## 全工程のworkerと結果データセット

`infrastructure.research.pilot.workflow`が、Full／Geometryの学習、同じbest重みの診断、
開発48局と全NN参照監査、結果datasetの公開・固定版照合を順番に実行する。
これも外部Linux専用で、provider APIや課金要求・実機削除は含まない。

凍結するworkflow JSONはschema `voxelshogi-research-pilot-workflow-v1`と、既存の`job`、
`m4_bundle`、`development`、`development_sha256`の5項目である。
M4 bundleは元のproduction公開証跡のplan／receiptと完全一致させる。
4学習入力に加えM4をLinuxへ直接取得し、実際のscreen releaseの開発条件が学習前の凍結値と一致するまでfitへ進まない。
途中で条件や更新数を小さくして成功させる経路は設けない。

controllerが新しいowner／絶対期限・検証済みsource・独立停止監視と初期ledgerを用意した後、次を実行する。

```bash
uv run --project infrastructure/cuda --locked --no-sync python -m infrastructure.research.pilot.workflow \
  runs/p6/research-pilot/workflow.json
```

全computeは既存jobの`compute_deadline`、HF転送・検証は`transfer_deadline`を使い、実行中に延長しない。
CLIはHF認証をメモリへ取り込み、providerキーを拒否する。
childを含む所有RSS／CPUとdevice全体のGPU使用観測を、学習・診断・開発評価・公開の間も続ける。
公開直前のsnapshotと、最後のworker終了観測を区別し、観測していないpeakを主張しない。
初期state ledgerの設定・過去予約prefixを維持して、最終ledgerと小さいworker終了markerを保存する。

結果公開先は`voxelshogi/voxelshogi-research-pilot-results-v1`のdataset、CC-BY-4.0、public/manual、Community OFF。
既存公開ハーネスでplanを作り、一度だけ送信し、返された固定Hub revisionの全ファイルをLinuxで照合する。
uploadの応答不明、期限超過、既存control directoryは再送・再起動せず、元のmarkerとreceiptから照合する。
LICENSEは検証済みM4 releaseの元のCC-BY-4.0全bytesとhashを確認して使う。
入力取得がそのLICENSEの取得前に失敗した場合など、結果公開も失敗し得る。公開できたものとして終了せず、controllerへ残存記録と未達を渡す。

公開する`records.parquet`の列は`path`、`line`、`content`、`sha256`。
JSON文書はline=-1、JSONLは0からの行番号と改行を含む元のUTF-8内容を保存する。
manifestのファイルbytes／hashから復元でき、Linuxの実PyArrowでschemaを含む往復一致を確認する。
対象は明示した学習・診断・保存再開・対局・監査の記録だけで、raw corpus、checkpoint、推論重み、環境ファイルや任意logは含めない。
rootのDataset Cardに実件数、固定入力・source、列と読込方法、由来別指標・小標本・打切りの制約、検証・再構成、取得条件と帰属を記載する。

成功時は、2 cycleのCUDA再開proofと各中間／最終HF roundtrip、両best診断、48局のcohortを再照合する。
NN参照traceと入力監査のhash、固定protocol、24局ずつの全棋譜とsummary、選択重みを公開直前にも確認し、
変更・欠落・重複・部分成功を完了へ読み替えない。失敗結果も公開可能な証拠を保ち、`pipeline_complete=false`のまま残す。
公開後の停止要求や期限超過もworkerの成功markerを作らない。

軽量／fake検証と既知変異は、実CUDA・実48局・実HF公開の完了証拠ではない。
次は関連Linux CIと統合sourceの全検証、外部supervisorの所有プロセス確認・台帳回収・退避証跡確認・実機解放を接続する。
`workflow-complete.json`でも`host_retirement_authorized=false`を維持し、controllerの回収・所有確認を省かない。

## 所有ホストの起動・回収・終了

`pilot.control`と`pilot.remote`が所有確認済みのVastホストへ接続する。
これらはレンタルや費用予約を行わない。実行前に、統合mainの全検証・教師条件・全工程の見積もり・
新しいowner tag・絶対期限・独立停止監視を既存のPhase6レンタルハーネスで確定する。
旧ブラウザ用sourceの実行許可をM学習に流用しない。

control directoryは`runs/p6/research-pilot<N>-control`。
凍結した`workflow.json`、`workload.json`、`plan.json`、`deadline.json`、専用SSH鍵、providerのaccount／instance記録、
実際の所有先と一致する`owner.json`、共通台帳から元bytesのままコピーした`state-upload-budget-initial.json`を用意する。
`workload.json`のstageは`research-pilot`、sourceはworkflowと同じ、`workflow_sha256`はcanonical fingerprint、
run labelは`voxelshogi-phase6-<control名>`とする。実行可能なbootstrapはGit管理の
`infrastructure/research/pilot/bootstrap.sh`からsource placeholderだけを置換し、そのhashをworkloadへ固定する。

```bash
# Mac側の既存control環境を使い、rootの数値計算依存を同期しない例。
pilot_control() {
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$PWD/.venv/lib/python3.14/site-packages" \
  UV_CACHE_DIR="${TMPDIR:-/tmp}/voxelshogi-control-uv-cache" \
  uv run --no-project --python 3.14.0 python -m infrastructure.research.pilot.control "$@"
}
pilot_control research-pilot1-control start-bootstrap
pilot_control research-pilot1-control bootstrap-status
pilot_control research-pilot1-control start-worker
pilot_control research-pilot1-control observe
pilot_control research-pilot1-control retirement-status
```

Macではこのcontrol側の軽い通信・metadata処理だけを行い、CUDA環境の構築・データ検証・checkpoint検査はLinux上で行う。
上の番号は新規control directoryの例であり、既存directoryを使い直さない。
bootstrapはPython3.14.9・固定uv／Rust・CUDA lockを使い、研究学習に不要なNode／ブラウザの導入は行わない。
HF認証はログイン済みCLIからメモリへ読み、SSHの標準入力からLinux launcherへ渡す。
tokenをコマンド引数・ファイル・起動markerへ記録せず、workerの環境も明示したruntime項目とHF認証だけにする。

起動前に両出力repoをpublic/manual・Community OFFで準備する。
学習前の認証／権限失敗も、classだけの失敗記録・最終ledger・worker終了markerを保存し、既存の実行記録を上書きしない。
起動要求後にSSH応答が不明になった場合は、local／remoteの起動markerと同じPID・生成時刻・sourceを照合する。
再送して別workerを作らない。正常に起動を確認した後は、独立したcontrol側watcherが60秒間隔で終了を確認する。
これはGPU jobの終了監視であり、GitHub CIの取得間隔は引き続き最短10分とする。

`pilot.collection`は外部Linuxで最新／best checkpointの実receiptと全bytesのhash、予定train／val履歴、
型付きarchiveの全inventoryを既存validatorで検査する。Macへ返すのは4MiB以下のsource・進捗・hash・receipt・集計だけ。
重み、checkpoint、元corpus、ParquetやNN参照履歴そのものを返さない。
所有workerだけでなく同じ出力先を使う残存computeも確認し、PID再利用・不明なrun・未解決のstate転送は早期終了を拒否する。

`pilot.retirement`は、現在残るcontinuous／interrupted／restoredのlatest／bestを、
検証済みHF archiveの元checkpoint hashとprogressへ照合する。
restoredを連続実行の保存点で代用できるのは、両者のbinding・model／optimizer／RNG・全履歴・両receiptの
完全一致proofが現在の保存点に対応する場合だけ。古いarchiveがあることだけで、新しい未保存状態を破棄しない。
NN参照traceが存在する場合は、その現在のbytes／hashを含む検証済み結果datasetも必要とする。
学習開始前の失敗でcheckpointもtraceもなければ、保持した失敗metadataと変更のないledgerを確認して早期終了できる。

回収後は、Macの`runs/m6/state-upload-budget.json`を同じfileの排他lockで更新し、過去予約prefix・設定・上限を保持する。
無関係な追記を上書きせず、fileのfsync・読戻しと回収receiptの永続化を終えてから、所有確認付きの削除portへ一度だけ進む。
既に同じ最終台帳を回収済みなら照合で再開できるが、削除要求markerがある場合は削除を再送しない。
providerの破棄応答と所有一覧からの消失の両方がそろうまで、資源解放成功とはしない。
確認できない状態は記録して既存の独立期限へ戻し、期限を延長したり未保存状態を成功扱いしたりしない。

この実装・fake検証は、実GPUでの2 run、開発48局、HFへの実公開、実機解放の完了証拠ではない。
次は現在の実装を統合mainでLinux全検証し、ブラウザ8ケースの結果、最新offer／価格／account／guardを照合して実行する。
