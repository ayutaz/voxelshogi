# M6の読み込みと学習処理

M6-1の実装記録。教師・損失・評価の条件は[M6教師契約](M6_TRAINING_CONTRACT.md)、全体の完了条件は[M6計画](M6_PLAN.md)を参照する。実データの監査・GPU学習・学習済みモデルの公開はまだ行っていない。

## データを読む

外部Linuxで、固定Hub revisionの`production-64`を取得してから実行する。Macでは実行しない。

```bash
uv run --locked python -m training.feature_cache runs/m6/input/production-64 runs/m6/cache
```

このコマンドは、M4公開receiptに記録された全ファイルのサイズ・SHA-256と教師契約を検査してから、Parquetを対局単位で読む。探索対局の履歴をRustエンジンで順に再生し、VSFEN・局面hash・全履歴を照合する。有効な探索教師だけを特徴量と組み合わせて保存する。教師の合計とsplit別件数が監査結果に一致した時だけ、最後にmanifestを確定する。途中停止したディレクトリを完成済みとして再利用・上書きしない。

特徴量は`float32 [N,729,43]`のNumPy memory map、合法手は可変長の整数列とoffsetで保持する。全3splitの36,894件なら特徴量本体は約4.63 GB（10進）で、**外部Linuxのディスクだけ**に置く。読み込み時は全ファイルのhashを確認し、各バッチ分をRAMへコピーする。各splitの教師件数は実監査で確定する。

manifestには入力の契約・監査結果・生成コードのcommit・全cacheファイルのhashを残す。読み込んだmanifestのSHA-256は、次のcheckpoint実装で入力を識別するために使う。cacheは派生成果物で、学習データを別repoへ複製公開するものではない。

## 更新と評価

`training.learning.train_step`はtrainだけを受け付け、合法手集合へlogitを絞って交差エントロピーを計算する。Valueは手番側の`tanh(score/1000)`に対するMSEで、両損失の平均を等重みで加える。勾配が有限であることを更新前に検査し、全パラメータの勾配ノルムを1に制限する。

`evaluate_model`はval／明示したtestに対して`eval()`と`inference_mode()`で動く。重複ID・空集合・別splitを拒否し、最後の小さいバッチも例数で重み付けする。Policy Top-1／Top-5、Value MSE／MAE、マスク前の合法手率を返す。マスク後は合法手に限定し、同点は小さい行動IDを選ぶ。評価終了後は元のtrain/eval状態へ戻す。

trainの順序はseed・epochだけから作る独立した乱数生成器で決まり、環境の乱数状態には依存しない。最後の端数を落とさず、`start_batch`以降だけを再開できる。val／testは固定順序で全件を評価する。

## 検証の範囲

テストは2択の`log(2)`、勾配`[-0.5,+0.5,0]`、SGD更新量、勾配制限、2件＋1件の評価平均など、手計算の期待値を使う。違法な最大logit・非有限勾配・別split・同点・途中cache・hash改変・履歴不一致も対象にする。損失・勾配・Rust再生・特徴量・バッチの実行と既知変異はLinux CIで確認する。読み込み・損失のPR #48はPython3.14.9のLinux CIで全234テストと74既知変異に成功した。Macは純粋なメタデータと静的検査に限る。学習CLI・保存再開のPR #49もPython3.14.9のLinux CIで全255テストと85既知変異に成功し、mainへ取り込み済み。実データとCUDAの試行は未実施。

## 学習loopと保存再開

`training.fit`は外部Linux専用のCLIで、固定configと実行時間上限を必須にする。以下はコマンドの形であり、GPU起動・本学習の承認や実行結果ではない。

```bash
uv run --locked python -m training.fit runs/m6/cache runs/m6/train --config runs/m6/config.json --max-seconds 600 --max-new-steps 10
uv run --locked python -m training.fit runs/m6/cache runs/m6/train --config runs/m6/config.json --max-seconds 600 --resume
```

configの項目はseed、epochs、batch_size、learning_rate、weight_decay、save_every、threads、device。初期値は1 epoch・batch 1・FP32・AdamW（lr=0.0003、weight_decay=0.01、betas=0.9/0.999、eps=1e-8、foreach/fused無効）で、実VRAMを確認するための出発点にすぎない。CUDAが使えなければ停止し、CPUへ自動切替しない。CPU指定はLinux CIの小さいfixture向けで、Mac MPSは受け付けない。

valを毎epochで全件評価し、損失が最小だった世代をbestに選ぶ。同点は先に選んだ世代を保持する。testは学習loopから一切読まない。SIGINT／SIGTERMと時間上限はstep間・valのbatch間で確認し、完成したstepまでを保存する。valの途中停止ではepochを完了扱いにせず、再開後にそのvalをやり直す。上限は各CLI実行に対するもので、GPUの課金上限は別の外部guardianで管理する。

checkpointはmodel、optimizer、Python／NumPy／Torch CPU／CUDAのRNG、epoch・次のbatch・step・学習例数・val最良損失を含む。NumPyのRNG配列も整数列にし、`torch.load(weights_only=True)`だけで読み込む。入力cacheのmanifest hash・教師契約・学習config・コードcommit・依存lock hash・実行環境が異なれば、状態の読み込み前に拒否する。保存されたsampler位置・step・例数の整合も検査する。

stateとreceiptをfsyncしてから、latest／best両方の参照を一つのJSONでatomicに確定する。通常はlatestとbestの最大2世代を残す。削除は、同じrunのbinding・固定命名・ファイル一覧・全hashを確認できた旧世代だけに限定する。未完了・改変・無関係なファイルを一括削除しない。run全体は外部Linuxの非公開作業領域に置き、optimizer付きcheckpointをそのまま公開モデルへ混ぜない。

`events.jsonl`には試行ID、step、学習例ID、損失、val結果を残す。保存前の異常終了で既存stepを再実行した場合も、過去のイベントを消さず試行IDで区別する。完了判定はイベントの行数でなく、検証済みcheckpointのprogressを使う。

## 再開の事前一致基準

- 同じLinux CPU環境・依存・thread数では、継続と再開のパラメータ、optimizerの全Tensor、次のPython／NumPy／Torch乱数を`atol=0, rtol=0`で比較する。端数batchを含む3 epochの連続実行と、epoch途中での中断再開をLinux CIで検証する。
- CUDAはM6-2で同じGPU・driver・依存・FP32・TF32無効・決定的演算を使って別に検証する。学習例IDとstep・optimizer整数counterは完全一致、パラメータ・optimizer浮動小数点状態・次stepの損失と出力は`atol=1e-6, rtol=1e-5`を事前基準とする。最大誤差も記録し、超過したら本学習へ進まない。CPU CIの成功でCUDAの一致を主張しない。

[PyTorchの再現性の説明](https://docs.pytorch.org/docs/2.14/notes/randomness.html)に従って決定的演算を有効にし、非対応の演算はエラーにする。[state_dictとweights_onlyの公式仕様](https://docs.pytorch.org/docs/2.14/notes/serialization.html#torch-load-with-weights-only-true)を使い、読み込み権限を広げるallowlistや`weights_only=False`で失敗を回避しない。

実データ・CUDAでの実行、GPU終了後の外部保持先と復旧試験、本学習の設定・速度・精度は未確認。保存先は課金を始める前に具体的な対応・料金・保持期限まで確定する。
