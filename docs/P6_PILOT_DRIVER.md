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
