# 最終評価前の開発用入力の再構成

[全1〜6の実行計画](P6_EXECUTION_PLAN.md)と[実ONNX3形式の最終評価](P6_MODEL_CONVERSION.md)に用いる。
コードの検証経路であり、実Mの最終72局や実データの追加監査が完了した記録ではない。

## 目的と監査対象

本比較の条件・モデル選定に使った開発対局を、最終holdoutの参照入力と照合する。
指された手の経路だけでなく、PUCTが枝でNNへ問い合わせた全履歴を含める。
元のG2の48局・24,579 NN参照、今回の少量2モデルの48局・全参照、
以後に条件選定へ使った全runを、最終評価を始める前に一覧へ固定する。
旧150局・診断・時間試行等を判断へ使う場合も、対象sourceとして明示する。

`training.research_development_references.collect_references`は外部Linux専用である。
公開ハーネスでHFの固定revision・全hash・取得条件を確認した元ファイルを入力とする。
同関数はHF取得の代行や、一覧にないsourceを使っていないことの自動証明をしない。
実行workflowが全対象を列挙し、元のHF revision・plan／receiptと照合する責任を持つ。

## 凍結するsource plan

schemaは`voxelshogi-development-reference-plan-v1`。
`screens`、`runs`、`traces`はそれぞれ空でない配列とし、source IDは全体で一意にする。
plan自体のraw SHA-256を最終評価CLIへ渡す。relative pathは同planの親folderから解決し、
絶対path・親への移動・symlink・同じファイルの二重登録を拒否する。

| 配列 | 記載するもの | 再検証 |
|---|---|---|
| `screens` | `id`、全`games`／`queries`件数、`files`の4 descriptor。各pathは`<id>/config.json`・`manifest.json`・`matches.parquet`・`queries.parquet` | 条件hash、全cohort・先後、全手Rust再生、queryのcase／role／連番・盤面・手番・物理／canonical ID、件数 |
| `runs` | `id`、全`games`件数、`run` descriptor（`<id>/run.json`）、`query_coverage` | 既存`verify_run`の全receipt／ファイルhash／Rust再生、全cohort・先後、開始後から終端までの入力 |
| `traces` | `file` descriptor、`cohort_field`（`architecture`／`arm`／`cohort`／`precision`）、`cohorts`（記録中のlabel→run ID）、`queries`（label別の実件数） | JSONL全行、割当cohort、NN participant、開始履歴との対応、Rust再生と物理／canonical ID、label別の全件数 |

descriptorは`path`・`bytes`・`sha256`の3項目。
Parquetは小さいbatch、JSONLは1行4MiB以内で順に読み、source全体をMacやメモリへ中継しない。
最終holdoutのprotocolを開発用sourceへ転用しない。

`query_coverage="trace"`では、そのrunの全NN参照traceを要求する。
過去のlegal argmaxのrunで個別query traceが残っていない場合だけ、
`query_coverage="scored-superset"`を明示し、全scored経路・終端の集合を保守的な包含集合として用いる。
この場合の記録trace数0を、実NN呼出し0回とは表記せず、`query_count_is_exact=false`を残す。
PUCT participantが一つでもあるrunでは、この代替を拒否する。
PUCTの未保存の枝を、指された経路から復元できたことにはしない。

## 最終監査への接続

各sourceは`development/<id>`という独立した物理局面／モデル入力集合になる。
元のM4全split・自己対局全raw sample・既存保護集合を置き換えず、和集合へ追加する。
receiptは全sourceの対局数・query記録数、unique件数と集合hash、元ファイルdescriptor、planのcanonical hashを持つ。

`training.research_final_evaluation`は次の引数を必須にする。

```bash
--development-sources runs/p6/references/plan.json \
--development-sources-sha256 "$DEVELOPMENT_SOURCES_SHA256"
```

最終モデルの割当前に全sourceを再構成し、各形式の全query・scored経路を追加済みの集合と照合する。
全形式の評価後にも開発sourceを再構成・比較し、plan bytesの不変と同じreceiptを要求する。
抜けたtrace、不正なID、変更されたsource、期限切れ、重複検出を成功へ読み替えない。
`input-audit.json`へreceiptを含めるため、公開42必須ファイルの構成は増やさない。

追加の学習コーパスを使う場合は、その全sourceの採用・由来bindingと全入力も別途監査へ接続する。
開発用sourceだけの照合を、未供給の学習源を含めた漏洩0の証拠にはしない。

## 検証範囲

Macは小さい手書き履歴とfake replay portだけを使い、枝だけに現れる重複・改変・欠落を検証する。
Linux CIには実Rust・実Parquet／JSONLの結合と、終局済みqueryの拒否を追加する。
結合テストのNN chooserはfakeで、実M推論・棋力や性能の証拠ではない。
実際の対象source一覧・HF照合・全件再構成と最終72局は、外部実行で別に確認する。
