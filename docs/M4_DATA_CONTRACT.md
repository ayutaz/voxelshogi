# M4 小規模データ生成の契約 v1

2026-10-28 JST。[実行計画](M4_PLAN.md)のM4-0〜2を対象とする。本生成・外部CPUの選定・データ公開は後続の作業。

**実行方針の更新**: この文書のMac確認はM4-0〜2時点の履歴。以後のエージェント作業ではMacで生成・探索・計測・学習を行わず、CIと承認済みVast.ai／CloudRiftを使う。[Linux専用pilotと初回利用案](M4_REMOTE_PLAN.md)。既存generate／validateの上限は保持するが、Macでの実行を再開する手順とはしない。

## Python境界と環境

`crates/voxelshogi-python`はPyO3／maturinのuv workspace member。`uv sync --locked`でRust拡張をビルドする。Python3.14.9、PyO30.30.1、maturin1.15.0、Gymnasium1.4.0、PyArrow26.0.0、psutil7.2.2を使用。Rustは既存の1.97.1、MSRVは1.85を維持する。

`voxelshogi.Game`はRustの`Session`を保持する。`Game(initial=None)`は標準初期局面、VSFEN指定はそこで履歴を開始する。`Game.from_record(dict)`はRustで全手・終局を検証し、繰り返し判定に必要な履歴も復元する。

| API | 戻り値・契約 |
|---|---|
| `snapshot()` | ruleset、VSFEN、hash、729駒コード、持ち駒14個、手番、絶対ply、合法手、王手、終局、手番視点の駒得評価 |
| `play(text)` | Rustで合法性を検証して適用。不正なら例外を出し、局面を変更しない |
| `record()` | 初期局面・全指し手・終局注記を持つ棋譜dict |
| `search(**limits)` | 推奨手、score、完了深さ、総／最終反復ノード、TT hit、停止理由。`max_depth`、`max_nodes`、絶対手数上限、最適化設定を受け取る |
| `legal_actions()` | 手番側の正規座標によるPolicy ID→Rustの合法手文字列のdict |
| `action_masks()` | bool配列`[1067985]`。終局・放棄・規定手数終了は全false |
| `features()` | float32配列`[729,43]`。[M3の入出力契約](MODEL_CONTRACT.md)と同じ座標・所有者・持ち駒の正規化 |

探索のscoreは駒得（歩=100）／終局の尺度で、勝率ではない。深さ0の評価や完了反復のない代替手は返せるが、最善手教師へ採用しない。Pythonへルール・終局・探索を再実装しない。ラベル／特徴量の薄い変換は、M3契約の独立したPython実装とも照合する。

`voxelshogi.env.VoxelShogiEnv`はGymnasiumの交互手番環境。各stepの入力は現在の手番側、次の観測は次の手番側。報酬は直前に着手した側の勝ち=+1、負け=-1、その他=0。`reset()`は観測とinfo、`step()`は観測・報酬・terminated・truncated・infoを返す。infoの`action_mask`を使って合法手を選ぶ。自然終局を手数上限より優先し、終了後のstepはresetまで拒否する。自動で相手の手を進めない。

## ファイルと各行の意味

schema IDは`voxelshogi-dataset-v1`。1対局を1 Parquetファイルへ保存する。現在のローカルCLIは最大16対局・各64手、探索深さ4／10,000ノードまでに制限する。既定の確認は3対局・各2手・深さ1／1,000ノード。本生成向けの大規模実行は今回のCLIへ追加していない。

`manifest.json`は設定（seed、ソースコミット、初期局面、生成元、対局数、手数、教師条件）、そのSHA-256、writer設定、確定済みファイル名・hash・行数、completeを持つ。writerはParquet2.6、zstd level3、辞書・統計なし、row group128で固定する。生成時刻・実測時間・RSSは含めない。

| 行の項目 | 意味 |
|---|---|
| `game_id`, `ply`, `source`, `split`, `ruleset_id` | 対局ID、開始地点からの手数、生成元、対局単位の分割、標準1王のルールID |
| `initial`, `history`, `vsfen`, `hash`, `side` | 履歴を保持した再生と局面同一性の確認に使う |
| `legal_moves`, `legal_actions`, `in_check`, `finished`, `result` | Rustで確定するルール上の事実。resultはJSON文字列またはnull |
| `evaluation`, `teacher`, `teacher_valid` | 静的駒得、固定条件の探索結果JSON、最善手教師への採用可否。teacherの完了深さ・score・ノード・停止理由を保持 |
| `played_move`, `termination` | 次の行へ進む手。最後の行は手なし、自然終局または生成の手数上限を区別 |
| `duplicate_of` | 同じ盤・持ち駒・手番が先に現れた行のID。null以外は学習・評価サンプルから除外し、履歴再生のためだけに残す |

`random`はランダム方策で選んだ手と軌跡、`rules`は同じ生成方式による合法手・王手・終局等のルール教師、`search`は探索で進めた軌跡と探索教師。前二者を探索の最善手教師とは表示しない。生成元は対局IDの昇順で設定リストから順に割り当てる。

本生成向けの追加設定`search_opening_plies`は既定0。0より大きい場合、search対局の指定序盤手数だけ固定seedで着手を選び、それ以降は探索推奨手を使う。探索教師自体は序盤も同じ固定条件で計算するため、序盤の`played_move`とteacherの`best_move`が異なる場合がある。検証器はその区間の着手をseedから独立に照合する。設定・ソースコミットをmanifestへ記録し、過去のデータはその記録済みコミットで検証する。[本生成の契約](M4_PRODUCTION.md)。

各対局には開始局面から最後の局面までを保存するため、2手なら3行。終局が早ければそこで終了する。探索が深さ1以上を完了しscoreを持つ場合だけ`teacher_valid=true`。上限で深さ0の代替手を使った対局も区別して記録する。生成の最終局面には探索教師を付けない。

## 分割・重複・再現

- `SHA256("split:{seed}:{game_id}")`の先頭8桁を整数化し、mod10の0〜7=train、8=val、9=test。同じ対局の全行は同じsplit。少量確認で全splitが埋まることは保証せず、有効件数を報告する。
- ランダムな手は、ソートした合法手を`SHA256("move:{seed}:{game_id}:{ply}")`全体の整数mod合法手数で選ぶ。ワーカー数や完了順に依存しない。
- 重複はVSFENの盤・手番・持ち駒（手数を除く）で保守的に判定する。対局ID・手数順の最初の行だけを候補に残す。異なる反復履歴のラベルを流用せず、全履歴とルール結果は各行で検証する。
- 全件検証器は生成器の行生成関数を呼ばず、初期局面から一手ずつ再生して保存した事実・履歴・合法行動・評価・生成方策・終端・重複除外を照合する。探索教師も固定条件で再探索する。ファイルhashを書き直した不正データも拒否する。
- 一致対象はデータファイルとmanifest。固定したソース・環境・依存・設定・writerで、連続生成と対局単位の中断再開がバイト一致する。異なるOS／CPU環境をまたぐバイト再現はまだ未検証。

## 確定と中断再開

manifestが確定点。最初に空の所有マーカー`.voxelshogi-dataset-v1`を排他的に作り、最初のmanifest書き込み中に停止しても、無関係なディレクトリと区別して再開できるようにする。生成中は`.tmp`へ書き、完成した対局ファイルをrenameした後にmanifestも一時ファイルからrenameする。未登録の対局・途中の行をサンプルとして読まない。再開時には確定済みファイルのhashと全内容を検証し、設定が同じ場合だけ残りを生成する。中断した対局は最初から再実行し、探索条件は変更しない。

空でない無関係なディレクトリへの生成は拒否する。manifestのパス・順序・schema・設定・writer・行数・完了フラグ・hashを照合する。書き込みは通常のプロセス中断に対して原子的な確定を使うが、突然の電源断に対するファイルシステム全体の永続性は保証しない。

## 実行と制限

以下はリポジトリルートで実行する。来歴を固定するためCLIはcleanなコミットを要求する。`validate`はデータに記録したソースコミットのcheckoutで実行する。再開は同じgenerateコマンドを使う。

```bash
uv sync --locked
uv run --locked python -m training generate runs/m4/small --games 3 --max-plies 2 --seconds 60
uv run --locked python -m training validate runs/m4/small --seconds 60
```

生成と検証は専用の子プロセス群で行い、内部スレッドは1。親は0.1秒間隔で実時間・子と子孫のRSS合計を観測し、5分／RSS1 GiBを上限として停止する。システムの利用可能メモリが512 MiBまたは全体の10%を下回る場合と、swap使用量が開始時より64 MiB以上増えた状態が3観測続く場合も停止する。利用可能メモリは負荷の代理指標で、macOSのGUIが示すメモリプレッシャーそのものではない。RSSも監視値であり瞬間超過を防ぐハード上限やGPUメモリではない。親・既存ブラウザ等のメモリはRSS上限の対象に含めない。

監視不能・期限内完了を確認できない場合は成功にしない。所有するプロセス群だけにTERM、必要なKILLとwaitを行う。SIGINT等でも終了処理を行う。監視停止から子の回収までには短い猶予があり、停止指示と全プロセス消滅の時刻は同一ではない。

`runs/m4/session-budget.json`の排他lockで同じセッションの同時実行を拒否し、実時間を合計10分まで記録する。起動前に利用時間を予約し、親の強制終了時は予約を消費したままにする。コマンドごとにledgerを作り直さず、上限到達後に同じ作業の続きを自動起動しない。新しい作業セッションに移る場合も、実行中プロセスがないことと前回の記録を確認してから、ledgerを別名へ退避する。

`*.worker.log`と`*.validation.json`はデータディレクトリの隣に置き、モデル学習用データのhashから分離する。`runs/`とParquetはgit管理外で、CIでも生成したデータを公開artifactへ添付しない。本生成・公開は [M4-3以降](M4_PLAN.md)で見積もりと必要な承認を経て進める。
