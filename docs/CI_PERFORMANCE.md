# CIの実行時間と変更範囲

2026-11-02 UTC。目的は、開発中の待ち時間を減らし、必要な検証を実行すること。CI結果の取得は従来どおり最短10分間隔とし、runner上の処理時間とは区別する。

## 変更前の実測

PR #99の[CI run](https://github.com/ayutaz/voxelshogi/actions/runs/41430347070)。最初のjob開始からGate終了まで約11分20秒。Python jobは11分8秒で、次の処理を直列に実行していた。

| 処理 | 実時間 |
|---|---:|
| Python単体・実モデルテスト | 1分12秒 |
| モデル系変異 | 1分26秒 |
| 学習系319変異 | 7分50秒 |
| Python依存環境の同期 | 17秒 |
| Web build／E2E | 5分14秒（別job） |
| Web完了後のE2E runtime確認 | 17秒 |

依存取得よりも、Python検証の直列実行が主な待ち時間だった。初期目標はコード変更時の全体5〜7分程度で、変更後の実runから再計測する。runnerの待ち行列・ネットワーク・cacheの状態で変わるため、保証値にはしない。

## 何を実行するか

PRはeventのbaseからcheckoutされたHEADまで、main pushはeventのbeforeからHEADまでを比較する。renameの検出を無効にし、削除側・追加側の両方を分類する。

| 変更 | 重い検証 |
|---|---|
| README、進捗・計画等のMarkdownのみ | 省略。変更判定／Gateの軽量検査とCodeQLは継続 |
| `training/` | Python通常テスト・両変異群・実ブラウザモデル検証 |
| `apps/web/` | Web build／E2E・coverage／Web変異・実ブラウザモデル検証 |
| `export/` | Python・モデル・Web |
| `crates/` | Rust・Python・WASM／Web・モデル |
| CI・共通設定・lock・infrastructure・分類できないファイル | 全検証 |
| 手動・週次、比較元が不明／取得不能・空diff | 全検証 |

`scripts/ci/ci-scope.mjs`が分類し、共通workflowがbool文字列6件を返す。各jobは判定の成功と出力型を確認する。省略した内容はjob summaryに記録する。省略対象のRust/Web等の必須jobは軽量な判定検証を実行して成功する。依存audit／review・追加2種類の変異jobのskipだけは、対応するscope=falseの場合にGateが受理する。失敗・中断・欠落はscope=falseでも成功へ変換しない。CodeQLとmain保護は維持する。

## 並列化と再検証

Python通常テスト、モデル系変異、学習系変異を別jobにする。学習系は4シャードで並列実行し、各変異をちょうど1回実行する。追加した分割・判定回帰を含むcatalog全体を対象にし、不正な分割や重複名を拒否する。各シャードの隔離baselineは担当テストファイルの和集合を先に実行する。通常テストjobは全テストを継続する。JUnitのskip・collection error・timeoutを変異検出と数えない。

共通設定変更時および週次・手動実行では全対象を実行し、普段の影響範囲判定だけに依存しない。新しいパッケージや実行入力を追加した場合は、分類と独立した期待値のテストを同じPRで更新する。未知の入力は自動的に全検証となる。

文書だけのmain更新ではWeb成果物を作り直さず、デプロイもしない。公開`build-info.json`は最後に検証・配信したアプリcommitを示し、文書のみ更新されたmain HEADと異なる場合がある。アプリ影響時は同じrunの検証済み成果物で公開・公開E2Eを行う。[配信手順](DEPLOYMENT.md)。

実装根拠：[GitHub matrix](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations)、[共通workflow](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)。変更後の実測と文書のみPRでの省略確認は後続で記録する。
