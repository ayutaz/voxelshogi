# M6の初回本学習と変換失敗の記録

2026-10-29 UTC。実RTX5090で3 epochの本学習、初期／選択済みTorchモデルの固定評価、HFへの再開状態保存を実施した。**推論用3形式の公開と実モデルのブラウザ計測は未完了。** [集計と元reportのhash](experiments/m6-initial-main-results.json)を固定し、以下の結果を再試行の成功で上書きしない。

## 学習・評価

計算元は必須CI成功済みcommit `d98cc4923625910bba68b28f1071742bbb06a2eb`。Python3.14.9、torch2.14.1+cu130、CUDA13.0、RTX5090。固定HFデータrevision・教師train29,884／val3,421／test3,589、FP32 AdamW、batch4、seed314159、lr0.0003、weight decay0.01、threads3、TF32無効・決定的計算を維持した。

1,000更新で意図的に中断し、新しいmodel／optimizerへcheckpointを読み込んで、合計22,413更新・89,652例・3 epochまで継続した。更新区間は合計約461秒。valだけでepoch3を選び、学習中のtest使用はない。同じ2,048件のtrain probeの損失は6.28969から0.78980へ下がり、選択時valとの差は0.08459だった。

| 固定集合の指標 | 初期モデル | val選択済みモデル |
|---|---:|---:|
| val損失 | 6.19951 | 0.87439 |
| val Policy Top-1 | 1.345% | 77.609% |
| test損失（3,589例） | 6.25522 | 0.89650 |
| test Policy Top-1 | 1.950% | 75.592% |
| test Policy Top-5 | 9.947% | 96.573% |

選択済み重みSHA-256は `dcdf28431a7eab40d98f98a1f2ef7b80fbea1b7d9e66f98b6428cfaa67336c85`。testのValue MAEは0.11377、MSEは0.03374、合法手マスク適用後の選択率は100%、適用前は0.167%だった。

| 固定対局・最大256手 | 初期モデル | val選択済みモデル |
|---|---|---|
| Random40局 | 0勝0敗0引分・40打切り | 0勝0敗0引分・40打切り |
| M1探索20局 | 0勝0敗18引分・2打切り | 0勝3敗9引分・8打切り |

同じ8手の序盤・先後入替・固定seedと探索予算を使用した。[事前評価契約](M6_EVALUATION.md)の打切りは引分や敗北へ変換しない。教師精度の改善は棋力の改善を証明しない。観測された勝率は0だが、打切りを含む限定した指標のbootstrap区間を、無制限対局の真の勝率へ一般化しない。生成データは64手までで、長期戦・終盤の分布は制約として残る。データ追加の判断にはtrain／valと分布を使い、testで再学習を調整しない。

## 保存と終了

[HF再開状態の固定revision](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-training-state/tree/bd8b39ecf8fcc476a389f49d25c8eb1ad120deec)をpublic/manual・Community OFF・Apache-2.0で保存し、全ファイルhashとlatest／bestの新run復旧でmodel・optimizer・RNGの完全一致を確認した。推論用パッケージの公開ではない。新規送信累計188,347,035 bytes／1 GiB、データやcheckpointはMacへ中継していない。

変換失敗と診断後、実機 `210e9e82-d38e-11f1-9fba-a33c9cea97e5` はInactive・resources_released=trueを確認。起動要求11:44:40〜解放確認12:37:25 UTC、約52.75分、US$1/時を掛けた参考額は約US$0.88。実請求は未回収。予約上限は試行US$4＋本学習US$8でM6累計US$12、プロジェクト累計US$53。参考額・予約額・実請求は区別する。

## FP32変換の失敗と次の基準

最初のFP32 ONNX変換は、固定初期局面のPolicy全1,067,985要素中7要素が旧 `atol=1e-5, rtol=1e-4` を超えて停止した。FP16／INT8の生成・評価や学習済み推論のHF公開には進んでいない。4入力の診断では旧基準超過は7／35／29／18要素、最大絶対差は4.19617e-5以下だった。

[数値診断の固定集計](experiments/m6-initial-numeric-diagnosis.json)は同じ重みをFP64へcastした参照と比較し、Torch FP32自体にもゼロ付近で旧基準を超える丸め差があることを確認した。ORTの最適化をdisabled／basicへ変えても解決しなかった。4入力で合法手のargmaxはTorch32／Torch64／各ORT設定で一致したが、これだけで全出力照合を成功扱いにはしない。[PyTorchの数値精度の説明](https://docs.pytorch.org/docs/2.14/notes/numerical_accuracy.html)も演算順による差を説明するが、以下の閾値そのものを保証する資料ではない。

次の独立した変換runより前に、学習済み専用の `numericContract=voxelshogi-trained-numeric-v1` を固定する。

| 比較対象 | atol | rtol |
|---|---:|---:|
| 学習済みFP32／INT8のPolicy | 1e-4 | 1e-4 |
| 学習済みFP32／INT8のValue | 1e-5 | 1e-4 |
| FP16のPolicy／Value | 1e-3 | 1e-2 |

Policyの絶対誤差上限は観測されたFP32／FP64との差に余裕を置いた実装上の判断であり、全局面・全端末の誤差保証ではない。各有限要素の `abs(actual-reference) <= atol+rtol*abs(reference)` を全件検査し、平均差やargmaxだけで通さない。M3未学習モデルの既存基準は変更しない。未知・欠落した学習済みnumericContractはPython・Webとも拒否する。各形式同士の精度低下は別の記述統計と固定評価で報告する。

次はこの基準を含むCI成功済みのclean sourceでcacheを作り直し、同じ学習条件と固定評価を再実行する。旧sourceのcheckpointや評価を新commitへ付け替えない。次のGPU枠は暫定3時間・最大4時間／US$4、M6累積予約US$16／基本枠US$24以内。構築・再学習30分、固定5モデル評価90分、変換・転送・ブラウザ60分を見込む。後半は未実測であり、完了前でも上限の15分前に保存・終了を優先する。開発／CI待ちでGPUを保持せず、追加US$100はまだ有効化しない。
