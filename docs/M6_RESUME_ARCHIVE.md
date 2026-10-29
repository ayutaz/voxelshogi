# M6の再開状態を外部へ退避する形式

M6-2の起動前準備。実GPUでの実行・外部保存先への転送・復旧は未実施。[学習処理](M6_RUNTIME.md)の非公開checkpointを、実行可能なPythonオブジェクトを含まない形式へ変換する。Macへデータやcheckpointを中継しない。

## 目的と完了条件

GPU実機の終了後も、modelだけでなくoptimizer・乱数・次のbatch・latest/bestの選択を保ち、同じ学習を再開できるようにする。元のrunを使えない状態から復元し、連続実行と再開後のパラメータ・optimizer・progressが一致することをLinux CIで検証する。実機ではCUDAの事前一致基準と、外部保存先の固定revision全ファイルhash・再取得による復旧も必要。

## ファイルと読み込み境界

`training.resume_archive`は外部Linux専用。rootの`config.json`はrun binding、`history.json`は既知の学習イベントだけを収録する。`latest/`と必要な`best/`に、型を明記したJSON treeと`state.safetensors`を置く。manifestは全ファイルのbytes・SHA-256、元checkpointのhash、progress、入力cache・コード・設定・環境を結び、最後にatomicに確定する。

Tensorは有限のfloat32/64・整数・boolに限定し、Pythonのdict、OrderedDictのmetadata、list/tuple、基本スカラーの区別を保つ。未知の型・動的なPython型名・非有限値・過剰な深さ・未使用Tensor・重複参照を拒否する。元checkpointを読む時も`weights_only=True`を使う。archiveにpickle／`.pt`や生のstdout・stderr、資格情報、`.env`は収録しない。

復元時は期待するrun bindingと全ファイルhashを先に照合し、symlinkや外部パスを拒否する。TensorとJSONを検査してから新しいrunを作り、private checkpointへ戻す。`run.json`は全状態を書き終えてから確定する。元のシリアライズと復元後の`.pt`のバイト同一性は要求せず、元hashとarchive hashを記録し、状態の一致を検証する。

```bash
# 承認済み外部Linux上だけで実行。ネットワークへの送信は行わない。
uv run --locked python -m training.resume_archive pack runs/m6/train runs/m6/resume-archive
uv run --locked python -m training.resume_archive restore runs/m6/resume-archive runs/m6/restored --expected-run runs/m6/expected-run.json
```

`expected-run.json`は復旧前に保持した元の`run.json`。archiveのbindingを無条件に信頼して再開条件を変更しない。復元先は新規ディレクトリに限定する。

## 保存先と公開

この形式の実装は、optimizer状態の公開許可ではない。通常のHFモデル公開ハーネスはresume archiveを拒否する。[別承認を要求するstate専用profileと累積アップロード上限](M6_STATE_RELEASE.md)を準備する。保存先・保持期限・最大料金・取得権限・Model Cardとライセンスを具体化してから、別の保存方針を確定する。[M6計画](M6_PLAN.md)の通り、エフェメラルディスクだけに唯一の再開状態を残して実機を終了しない。実行前の費用・保存先が未確定の間はGPUを起動しない。

## 検証

CPUの小さいfixtureで3 epochの連続実行と、step 3で保存して元runを使えなくした後の復旧・継続を比較する。latestはstep 3、bestはstep 2という独立した途中状態を検証する。hash改変・異なるbinding・symlink・val未評価のbest・通常モデルへの混入を拒否する。Tensor値をゼロにする、hash確認を外す、bestの条件と公開境界を外す既知変異をLinux CIへ追加した。Macは小さい不透明なメタデータfixtureと静的検査だけを実行する。
