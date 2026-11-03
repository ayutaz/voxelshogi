# P5-2：合法手の確率和による停止と修正

2026-11-03 UTC。本条件の最初の実行は1世代16対局を公開した後、2世代目の開始直後に停止した。48対局・別VMでの後続世代は未完了。修正後はM6基点から新しいprotocolで3世代48対局を実行し、この部分成果を混ぜない。

## 停止と再現

実行sourceは`018ee6b3f2dc06bd48c170bee834170381beb583`、protocol IDは`a647e4d660a7f550dcf1cb16ef6390aa1ee6a08fa0485672a7e2b97386fa534b`。所有RTX5090のVM `58965624`で、第2世代の最初の対局を同じseed・モデルで再現した。

- 合法手2,026件、履歴126手。キー・型・有限性・各確率の範囲は正常。
- FP32 softmaxの確率をPython floatとして合計すると`1.000001103069236`。探索の確率和許容差`1e-6`を超えるため、既存の厳密な検査が拒否した。
- Valueは`-0.6737136840820312`で範囲内。再現まで3,559評価・約31.5秒。
- 子モデルSHA-256は`fec4445c2542e6a707f4658149efa1434985c28f2dbfb094c9c75738e7a5dcd4`。

## 修正と検証

`TorchPolicyValue`の合法手logitsに対するsoftmaxだけをFP64で計算する。モデル重み・logits・学習はFP32、探索検査の許容差も`1e-6`のまま維持する。同じ実GPU・同じ停止局面で確率和は`1.0000000000000002`となり、元の探索検査が成功した。独立したscalar `math.exp`／`math.fsum`参照との最大絶対誤差は`2.220446049250313e-16`。

Linux上のTDDでは、等確率3手、共通offset4,096、合法手2,026件を使う3ケースが修正前に失敗し、修正後は関連17テストが成功した。非合法手に極端に大きいlogitを置き、合法手だけで正規化されることも検証する。FP32へ戻す変異は3ケース、全行動で正規化する変異は既存の独立期待値で検出した。フル回帰検証と取り込みは対応するPRの必須CI成功を条件とする。これらは速度・棋力改善の証明ではない。

## 保持した部分成果と資源

第1世代16対局・3,746 sample・937更新、116,008件の保護入力との学習重複0、自然勝敗0・自然引分4・cutoff12。全16履歴と学習入力hashを独立監査し、次の固定revisionで全ファイルhash・public/manual・Community OFFを照合済み。

- [Dataset](https://huggingface.co/datasets/voxelshogi/voxelshogi-selfplay-v1/tree/32de8493dea0ec861e42144816b19f28e091d835)：CC-BY-4.0。
- [State](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-selfplay-training-state-v1/tree/6805b08f3bf2e70b082ffe7a929c4b821ac3d618)：Apache-2.0。
- [停止時の集計report](https://huggingface.co/datasets/voxelshogi/voxelshogi-selfplay-run-reports-v1/tree/c3fdb29d361a5275c7c59f15353a0b87f5a8e2f1)：CC-BY-4.0。全体の成功を示すreportではない。

workerの停止を実PIDで確認し、記録・数値修正の検証を回収後、14:02 UTCにVMの削除応答と全件一覧からの不在を確認した。元の最大US$2予約は取り消さず、全体予約US$80／100・Phase5 US$19／24を保持する。実請求は未回収。

## 次の実行

[本条件](P5_SELFPLAY_MAIN.md)の3×16対局・32 simulations・追加256手・同じ開始局面・M6基点・保護集合・学習設定を維持する。修正のCI成功後、clean sourceと新しいprotocol IDを事前固定し、最初のVMを最大2時間／US$2、異なる復旧VMを最大3時間／US$3として再開する。予約後は全体最大US$85／100、Phase5 US$24／24であり、条件付き追加US$100は使わない。旧runを修正後のrunとして改名・継ぎ足ししない。P5-2完了後の全ドキュメント点検・資源解放・報告・停止を維持する。
