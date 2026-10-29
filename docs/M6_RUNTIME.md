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

テストは2択の`log(2)`、勾配`[-0.5,+0.5,0]`、SGD更新量、勾配制限、2件＋1件の評価平均など、手計算の期待値を使う。違法な最大logit・非有限勾配・別split・同点・途中cache・hash改変・履歴不一致も対象にする。損失・勾配・Rust再生・特徴量・バッチの実行と既知変異はLinux CIで確認する。Macは純粋なメタデータ45テストと静的検査に限る。

この実装だけではM6-1全体の完了にならない。学習loop／CLI、model・optimizer・RNG・samplerを含む保存再開、誤再開の拒否と継続実行との一致確認を続けて実装する。本学習の設定・速度・精度は未測定。
