# CIの速度と実行する検証

目的はPRの短いフィードバックと、main／定期実行での深い検証を両立すること。PRは1〜2分を目標とし、実runで判断する。runner待ち・cache・ネットワークによる変動と、結果取得の最短10分間隔は別に扱う。

## 実測した変更前の状態

| 段階 | CIの最初のjob開始〜Gate終了 | 確認元 |
|---|---:|---|
| Pythonを直列実行 | 11分20秒 | [PR #99](https://github.com/ayutaz/voxelshogi/actions/runs/41430347070) |
| 4シャード＋変更範囲判定 | 6分14秒（約45%短縮） | [PR #101](https://github.com/ayutaz/voxelshogi/actions/runs/41456192962) |
| PRの短い検証とmainの深い検証を分離 | 2分2秒（変更前比約82%短縮） | [PR #102](https://github.com/ayutaz/voxelshogi/actions/runs/41474974297) |

PR #101でもWebが5分13秒、学習系変異の最長jobが5分45秒だった。Web内ではモデルE2E69秒、通常E2E35秒、カメラ反復61秒、モデル生成36秒を実行していた。これらを通常PRから移したPR #102では、Webが1分7秒、Python通常検査が1分37秒、Rust通常検査が49秒だった。scope開始15:47:03 UTCからGate終了15:49:05 UTCまでが2分2秒。変更前と同じ開始・終了定義で比較している。workflow起動前のキュー待ちと、独立したCodeQLの終了時間はこの値に含めない。必須8チェックと関連検査の成功を確認して通常mergeした。1〜2分は目標であり、全PRの保証値ではない。

同じPRの[Security run](https://github.com/ayutaz/voxelshogi/actions/runs/41474974403)ではRust CodeQLが182秒で、15:50:06 UTCに最後に完了した。最初の必須検査開始15:47:03 UTCから必須8チェック全体の完了までは**3分3秒**。Gateの2分2秒とは区別する。保護とCodeQL4言語は維持しており、全体1〜2分の目標はまだ未達である。

文書だけの[PR #103の初回run](https://github.com/ayutaz/voxelshogi/actions/runs/41477557229)はscope開始からGate終了まで**1分6秒**。Rust／Web／Python／モデルはscopeの検証のみで、重い処理、依存監査、変異job、artifact配布、デプロイを省いた。CodeQLと必須8チェックの成功を確認した。

統合後のmain `fb1134a`の[CI](https://github.com/ayutaz/voxelshogi/actions/runs/41477320560)では、深い検証を実際に実行した。Python Native結合試験、モデル変異、学習系変異4シャード、3形式のモデル生成・実ブラウザ推論、通常E2E・カメラ反復、Rust／Web coverage・既知変異が成功。Qualityを含むGateは6分11秒で、その後のCloudflare公開・配信SHA・公開E2E・公開実ファイル照合も成功した。PRでの延期を検証削除へ置き換えていない。

## PRと深い検証を分ける

| 検証 | PR | main取り込み後・手動・週次 |
|---|---|---|
| 変更範囲／Gateの契約・静的検査 | 影響する分を実行 | 影響する分を実行 |
| Rust fmt/clippy/core通常テスト、WASM／Web単体・型・build | 影響する分を実行 | 影響する分を実行 |
| Python通常テスト | 実モデル自己対局等の`training/tests/*_native.py`を除いて実行 | Native結合試験を含め全件 |
| MSRV・coverage・既知変異 | 深い検証へ延期 | 実行。Python学習系は4シャード並列 |
| モデル3形式の生成・実ブラウザ推論・全E2E・カメラ反復 | 深い検証へ延期 | 実行 |
| CodeQL 4言語 | コード影響時に継続。文書だけならscope検証 | mainもコード影響時に実行。週次・手動は全解析 |
| core全変異の調査 | 延期 | 独立Qualityの週次、または手動指定 |
| デプロイ・公開E2E | 実行しない | mainのアプリ影響時、深い検証成功後 |

PRで省く検証は削除しない。mainではCIからQualityを共通workflowとして呼び、coverage／既知変異の成功もGateへ結び付ける。独立したQuality週次とCI週次が同じcore全変異を二重起動しないようにする。PRのモデルなしbuildを公開用artifactとして送らず、mainの同一runで生成・検証した成果物だけをデプロイする。

## 影響範囲と結果の扱い

`ci-scope.mjs`はPRのbase〜HEAD、pushのbefore〜HEADを比較する。renameの削除・追加を両方扱い、Markdownだけなら重い処理を省く。training→Python／モデル、Web→Web／モデル、export→Python／モデル／Web、crates→Rust／Python／Web／モデル、共通設定・依存・CI・未知の入力→全分野を対象にする。比較不能・空diffも全分野へ倒す。

6分野のflagに`deep`を加える。PRはdeep=false、それ以外はtrue。未知の入力でもPRでは全分野の短い検証を行い、深い検証はmain以降へ回す。手動・週次は全分野・deepで実行する。

各jobはscope成功と7つのbool文字列を検証し、省略理由をsummaryへ残す。必須8チェック名とmain保護を維持する。PRのcoverage／既知変異checkは実行tierの判定を検証し、計測や変異実行そのものの成功とは報告しない。実結果はmain／定期runで確認する。Gateは対応する省略だけを許可し、失敗・中断・欠落はPRでも許容しない。mainでdeep=falseになった場合も拒否する。

Securityも同じ変更判定を使う。PR／mainで6分野すべての影響がないと確認できた場合だけ、CodeQLの初期化・抽出・解析を省略する。4つの必須CodeQL jobはscopeの成功と7つのbool文字列を検証して省略理由を記録する。コード・共通設定・未知の入力・比較不能は従来どおり全4言語、週次・手動も全解析を行う。文書PRのsuccessは新しいコード解析を行った意味ではない。

PR #105の実装時点ではローカルのNode111テスト・制御63変異・actionlintを確認し、変更後の実CI所要時間は未計測だった。文書だけの[PR #106](https://github.com/ayutaz/voxelshogi/pull/106)を実経路の確認対象とする。[GitHubのcode scanning保護](https://docs.github.com/en/code-security/concepts/code-scanning/merge-protection)は必須status checkとは別に働くため、導入の判定条件は、文書のみのPRとmainでinit／analyze各0回、必須8チェック成功、保護を維持した通常mergeである。保護が解析結果を要求して取り込みを阻止する場合、保護を解除せず従来の解析を維持する。架空のSARIFや過去の解析を新解析として送信しない。

学習系変異は全catalogをちょうど1シャードへ割り当て、担当テスト集合の隔離baselineを先に通す。通常の全pytestは深い検証で継続する。JUnitのskip・collection error・timeoutを変異検出と数えない。

文書だけのmain更新は再ビルド・再デプロイを省く。公開SHAは最後に配信したアプリcommitで、文書更新後のmain HEADと異なる場合がある。[配信手順](DEPLOYMENT.md)。
