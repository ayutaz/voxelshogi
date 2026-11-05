# P6の無料public保存枠と累積stateの自主上限

**2026-11-05・実台帳へ適用済み**：[固定した移行証跡](experiments/p6-state-capacity-transition-2026-11-05.json)のとおり、PR #148の全27チェック成功と通常merge、同一source tree、両provider所有資源0、排他lockと前後bytesを確認した。全21予約1,407,414,632 bytesと過去承認を保持し、自主上限を2GiBから32GiBへ移した。新予約・実upload・有料storage購入は0、GPU総枠200も変更していない。以下の未適用の記述は実装準備時点の履歴。

2026-11-05。ユーザーのHF公開・state保存・無料public容量の継続承認と、[1〜6の研究計画](P6_EXECUTION_PLAN.md)を対象とする。
これは版付き移行のコードと見積もりであり、実台帳の移行や実uploadを完了した記録ではない。
追加の有料storageを購入せず、GPU予算US$200も変更しない。

## 必要量と数え方

HFの無料public枠と、ハーネスが累積uploadへ付けている自主的な2GiB上限は別である。
実M候補のparameter数はFull／Axialが25,783,688、Geometryが26,098,120、CNNが28,606,344。
1個のFP32 modelとAdamWの二つのmomentで12 bytes/parameterを使う。
latestとval選択bestは両方にoptimizerを保存するため、1 archiveのtensorを**24 bytes/parameter**で見積もる。
bestを重みだけとして数える16 bytesの見積もりにはしない。

- 最大tensor量と乱数・step counter・履歴・metadata等の余裕64MiB：1 archive **753,661,120 bytes**。
- 少量2 run＋本比較12 run＝14 run。各runに中間・最終・失敗退避用1回の計3 archiveを確保：計42個。
- 現台帳の過去21予約1,407,414,632 bytesを保持した合計見積もり：**33,061,181,672 bytes**（約30.79GiB）。
- 新しい自主上限案：**32GiB＝34,359,738,368 bytes**。これはHFの保存プラン購入や32GiBの即時uploadではない。

上記は実byteの保証ではなく事前上限見積もりであり、各送信は実ファイルの検証済みbytesを予約する。
想定を超えたarchiveや追加試行を、履歴の削除・予約の取消しで押し込まない。
4構造の条件や保存点数を変える場合は、この版の見積もりが引き続き十分か再確認する。
データセット、ONNX配布、無料public全体の利用量と、このtraining-state ledgerの対象も区別する。

## 移行の契約

`training.state_upload_budget.extend_research_upload_budget`は純粋関数で、ファイル・Hub・課金を変更しない。
既存のv2からv3へ一度だけ移し、旧v1→v2の承認記録、全予約、その順序と実額を保持する。
移行前ledger全体のcanonical hash、予約prefix件数、immutable source、既存公開scopeへの参照、実parameter数と保存点数の見積もりを記録する。
新しい予約後も、旧prefixと旧承認記録を含む移行前ledgerの完全一致を要求する。
上限だけを直接書き換えた値、不完全・改変済みの証拠、再移行、重複送信、容量超過は拒否する。

実適用は関連CIの成功後、共通ledgerへの排他lock・移行直前bytes照合・fsync・前後receiptを使って行う。
予約を増やす通常の公開も同じ共通ledgerへ行い、M6／自己対局／分散学習の履歴を分割して消さない。
Macには小さい台帳・receiptだけを保存し、実checkpointは外部Linux→`voxelshogi/`のpublic/manual・Community OFFへ直接送る。
固定revisionで全bytes・hashを照合してから資源を解放する。
