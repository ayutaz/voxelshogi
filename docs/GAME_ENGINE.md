# ゲームエンジン（`crates/voxelshogi-core`）

更新: 2026-10-28。ルールの正は [RULESET.md](RULESET.md)。標準1王と実験9王は、状態・棋譜・終局APIを分けて扱う。標準1王のM1探索を実装済み。全体検証・通常統合・公開後検証も完了した（[M1検証記録](M1_VALIDATION.md)）。M2の `Game.bestMove` と履歴付き専用Workerによるライブ探索も公開済み（[M2検証](M2_VALIDATION.md)）。M3の未学習モデル推論は別のブラウザWorkerで実装・公開済みで、Rustのルール／探索エンジンへNN依存は加えていない（[M3検証](M3_VALIDATION.md)）。PyO3／maturinのPython境界も実装済み。履歴・ルール・探索をcoreから共有し、Pythonへ再実装しない。[M4の契約](M4_DATA_CONTRACT.md)・[実機とCIの検証](M4_VALIDATION.md)。約10万有効局面の本生成と学習は [ROADMAPのM4／M6](ROADMAP.md#m4-python-バインディングとデータ生成phase-3-の本体)で進める。現在地は [STATUS](STATUS.md)。

## モジュール

| モジュール | 責務 |
|---|---|
| `coord` | `Square`（`z*81 + y*9 + x`）、表示座標（`5五V`）、ASCII座標（`555`） |
| `piece` | `Color`（= `Player`）、14種の `PieceKind`、`Piece`。コードは `1 + kind + 14*color`、0は空 |
| `board` | 729バイトの `Board`、標準初期配置 |
| `movegen` | 移動先 `targets`、利き `attacks`。飛角は動的計画法（ADR-004） |
| `state` | 標準の `GameState`、合法手・`apply_move`・王手・終局・履歴・`validate` |
| `moves` / `notation` | `Move::{Normal, Drop}`、指し手文字列、標準VSFENの入出力・検証 |
| `zobrist` | 固定シードの局面ハッシュ |
| `record` | 標準の `GameRecord`、ルールID・初期VSFEN・着手・結果・終局理由、再生検証 |
| `session` | 標準の棋譜カーソル、undo/redo/goto、投了、入出力 |
| `capture` | 9王試作の `CaptureGame` / `CaptureRule` / `Outcome`。立体移動は `movegen` を共用 |
| `experiment` | 幅制限探索、実験棋譜、検証済み `Replay`、標準1王の比較対照 |
| `search` | 標準1王の全幅αβ、駒得評価、反復深化・置換表・上限・計測 |

## 標準ルールのRust API

```rust
use voxelshogi_core::{Color, GameState, MoveError};
use voxelshogi_core::record::GameRecord;

fn main() -> Result<(), MoveError> {
    let game = GameState::new();
    let moves = game.legal_moves();
    let next = game.apply_move(&moves[0])?;
    assert_eq!(next.side_to_move(), Color::White);
    assert_eq!(next.ply(), 1);
    let record = GameRecord::from_moves(&game, &moves[..1]);
    assert_eq!(record.replay().unwrap().hash(), next.hash());
    Ok(())
}
```

`GameState::apply_move` は外部入力を検証する。`GameState::from_parts` 自体は検証済み局面を保証しないので、任意入力には `validate` が必要。VSFENインポートは検証を行う。標準の王は捕獲せず、王手回避・詰み・連続王手を処理する。

`targets` と `legal_moves` の列挙順はバージョン間の契約ではない。正しさは集合で比較し、探索の同点処理では順序を別途定義する。再現条件にはエンジンコミットも含める。

### VSFENと標準棋譜

`<盤> <手番 b|w> <持ち駒 or -> <手数>`

- 盤は9層（`z=0..8`）を `|`、各層の9段（`y=0..8`）を `/` でつなぐ。各段は9筋→1筋。
- 駒は `P L N S G B R K`。先手は大文字、後手は小文字、成駒は `+` を前置する。空マスの連続数は単独の1〜9。
- 持ち駒は先手→後手、それぞれ `R B G S N L P` 順（例 `R12P2g`）。手数は1始まり。
- VSFENは4,096 bytes以下、手数番号は1〜1,000,000。各1王、総駒数、行き所、二歩、手番でない側の王手を検証する。
- `GameRecord` は `ruleset_id = voxelshogi-standard-v1` と初期VSFENを持つ。JSONは4 MiB以下、20,000手以下。`from_json` は形式・サイズを読み、`replay` が全着手と結果を再検証する。UIの `Session` / WASMの `Game.fromRecordJson` は再生検証まで行う。
- ルール外の終局は `Termination::{Resignation, MaxPlies, Abandoned}`。標準の上限打ち切りと9王の規定手数採点を混同しない。

`GameRecord::replay()` が返す `GameState` 自体にはMaxPlies／Abandonedの外部打ち切りを保存しない。M2-1から `Session` は外部終局情報を保持し、`result()` は自然な終局を優先して規定手数の引き分けも返す。`is_finished()` は結果のないAbandonedも終了とする。終局情報は全棋譜の末尾でのみ有効で、undo先では未終了、redoで終了に戻る。分岐した手を指すと未来の終局情報を破棄する。`to_record_json()` はカーソルにかかわらず未来の手と終局情報も保存する。終了後の着手は拒否し、再投了で結果を上書きしない。

投了棋譜のインポートでは、`GameRecord::replay()` が検証して受け入れた末尾状態をそのまま復元する。既存の検証が受け入れる「詰みの盤面で投了を記録した棋譜」も、検証済みの投了理由と結果を保持して再保存する。インタラクティブな `resign()` の終了後ガードを再生処理へ流用して終局理由を変えない。

## M1：標準1王の探索API

```rust
use voxelshogi_core::GameState;
use voxelshogi_core::search::{search, SearchLimits, SearchOptions};

fn main() -> Result<(), &'static str> {
    let game = GameState::new();
    let limits = SearchLimits {
        max_depth: 3, max_nodes: Some(2_000),
        max_time: None, max_game_ply: None,
    };
    let result = search(&game, limits, SearchOptions::default())?;
    assert!(game.is_legal(&result.best_move.unwrap()));
    assert!(result.nodes <= 2_000);
    Ok(())
}
```

- `evaluate(&GameState)` は手番側の駒得（歩=100）、`piece_value(PieceKind)` は固定の駒価値。王の捕獲を評価せず、終局を先に処理する。勝ち／負けは±1,000,000、引き分け0。詰み距離の補正はない。
- `SearchLimits` は深さ0〜64、ノード数、時間、任意の絶対ゲーム手数上限。`SearchOptions` は反復深化・手の並べ替え・置換表とその容量（0〜1,000,000件）。不正な上限はエラー。
- `SearchResult` は `best_move`、`score`、`completed_depth`、`nodes`、`last_iteration_nodes`、`tt_hits`、`stop_reason`。停止理由は `Depth / Nodes / Time / Terminal`。
- 中断した反復の評価は採用しない。未探索なら合法な代替手を返して `score=None`、深さ0を完了した場合は静的評価。終局では手なしと終局評価を返す。代替手は `Move` 全順序の最初。
- ノード数は根・葉・置換表ヒットを含む訪問局面数。反復全体で予算を共有し、根の事前の終局確認・合法手取得は数えない。時間上限は各ノード直前に確認し、合法手生成など1処理分は超過し得る。
- `search_with_clock` は単調な経過時間の関数を受け取る。Nativeの `search` は必要なときだけ `Instant` を使い、M2のWASMアダプタにはブラウザの時計を渡す。
- 全合法手を保持する。置換表は呼び出しごとに新規作成し、同じ深さ・上限までの残り手数を区別する。履歴の最大同一ハッシュ出現数＋残り探索深さが4未満のノードだけ履歴を省略して再利用し、それ以外では再利用を止める。EXACT/LOWER/UPPERを区別し、中断ノードは保存しない。
- 同じ局面・履歴・設定・深さ／ノード上限で再現可能。時間だけの上限では完了深さが変わり得る。仕様・戦術・同値性と計測は [M1計画](M1_PLAN.md)・[検証記録](M1_VALIDATION.md) を参照。
- 標準の `GameState::after_generated` はcrate内部限定。R0の `experiment::choose_move` は別実装のまま。WASMの `bestMove` は下記、専用Web Workerから呼ぶ（[M2計画](M2_PLAN.md)）。

### WASM探索API

`Game.bestMove(configJson: string): string` は同期CPU探索で、表示中カーソルまでの `Session` の履歴を使う。局面・カーソル・redo先・棋譜を変更しない。ブラウザでは `performance.now()` の経過時間を `search_with_clock` に渡す。インタラクティブな画面からは専用Worker内で呼ぶ（Worker契約は[M2計画](M2_PLAN.md#wasmとworkerの契約)）。

設定はcamelCaseのJSONで、必須 `maxDepth` は0〜64。任意の `maxNodes` は0〜9,007,199,254,740,991の整数、`maxTimeMs` は同上限以下の有限・非負のミリ秒（小数可）、`maxGamePly` はu32範囲の絶対ply上限。省略・nullは上限なし。初期VSFENが42手目なら絶対plyは41で、表示カーソル0とは区別する。設定JSONは4,096 bytes以下。未知フィールド・不正型・範囲外を終了局面でも拒否する。

`options` は省略可。`iterativeDeepening`、`moveOrdering`、`transpositionTable` はbool、`tableCapacity` は0〜1,000,000。省略した各値はcoreの既定（true・true・true・65,536）。設定例は `{"maxDepth":4,"maxNodes":50000,"maxTimeMs":1000}`。これはAPI例。公開Normalの既定はM2の実機計測に基づく最大深さ6・50,000ノード・約1秒で、画面から0.1／1／3秒を選べる（[計測](M2_VALIDATION.md)）。

返り値はJSON文字列。`schema: 1`、`bestMove: string | null`、`score: number | null`、`completedDepth: number`、`nodes`・`lastIterationNodes`・`ttHits` は**10進文字列**、`stopReason` は `depth | nodes | time | terminal`。u64統計をJSのnumberへ暗黙変換しない。`score` の視点・尺度・未完了時の合法代替手は上記Rust探索と同じ。外部終了のMaxPliesは手なし・評価0、Abandonedは手なし・評価nullを返す。`maxGamePly` は探索の打ち切り条件であり、このAPI自体で対局を終了・保存しない。

`Game.isFinished(): boolean` はAbandonedも含めた終了判定。`Game.result()` はMaxPliesの引き分けも返すが、Abandonedはundefined。UIの `Snapshot.finished` と `legal` はこの終了判定に従う。

## 9王試作と探索のRust API

```rust
use voxelshogi_core::capture::{CaptureGame, CaptureRule};
use voxelshogi_core::experiment::{SearchConfig, choose_move};

fn main() -> Result<(), String> {
    let game = CaptureGame::new(CaptureRule::FirstFive, 400)?;
    assert_eq!(game.board().count(), 360);
    assert_eq!(game.legal_moves().len(), 554);
    let (mv, nodes) = choose_move(&game, SearchConfig { depth: 2, width: 8 }, 42)?;
    let next = game.after_move(&mv)?;
    assert_eq!(next.ply(), 1);
    assert!(nodes > 0);
    Ok(())
}
```

| API | 契約 |
|---|---|
| `CaptureGame::new(rule, max_plies)` | 各9王・計360枚、先手番。上限は2〜2,000の偶数ply |
| `CaptureRule::{FirstFive, AllKings, ScoreLimit}` | `id()` が各 `voxelshogi-nine-kings-…-v0` を返す |
| `board` / `hands` / `side` / `ply` / `hash` | 盤・両者の持ち駒・手番・着手数・局面ハッシュ |
| `captured()` | `[先手が取った王数, 後手が取った王数]`。王は持ち駒にしない |
| `legal_moves()` / `after_move(&mv)` | 王手回避なしの合法手、検証付き適用。終局後の着手は拒否 |
| `outcome()` | `None` または `Outcome { winner: Option<Color>, reason }`。理由は `Target / ScoreLimit / MoveLimit / Repetition / NoMoves` |
| `from_parts` | テストなどの任意局面。駒総数・二歩・行き所を検証し、欠けた相手王を捕獲済みとして数える。履歴はply 0から |
| `choose_move` | 同じ局面・履歴・設定・seedで再現。深さ1〜3、候補幅1〜64。`(Move, ノード数)` またはエラー |

探索用の `after_generated` は同じ局面の生成済み合法手だけを渡すcrate内部の経路。外部には検証付きAPIを使う。R0探索は候補幅を切るため、全合法手のminimax値を保存する保証はない。このR0実装には反復深化・置換表・ノード／時間上限を追加していない。標準1王のM1探索は上記の別APIを使う。

### 実験棋譜と比較対照

- `ExperimentRecord::play(rule, max_plies, seed, swapped, search, engine)` が固定初期配置から終局まで対局する。schemaは `voxelshogi-capture-experiment-v1`。
- フィールドは `schema`、`ruleset_id`、`max_plies`、`seed`、`swapped`、`search {depth,width}`、`engine`、`moves`、`outcome`、`final_hash`、`nodes`。`engine` は生成に使った実装コミットを呼び出し側で記録する。
- `Replay::from_json` は4 MiB以下、既知schema／ID、有効な設定・上限、全着手、終局結果と最終ハッシュを検証する。未終局の棋譜は受け付けない。`state(ply)` は0〜`len()`の局面を読み出す。
- 標準の `GameRecord` と実験棋譜は交換できない。9王を標準VSFENとしてインポートしない。
- `play_baseline` が返す `BaselineRecord` は、既存の標準 `GameRecord` を `record` フィールドに入れ、探索・seed・上限・実装・ハッシュ・ノードを付けた比較用の包み。標準インポートには内側の `record` を使う。
- [比較CLI](../crates/voxelshogi-core/examples/compare_rules.rs) と [集計器](../scripts/experiment-pack.mjs) の再現手順・1,052局の結果は [R0報告](NINE_KINGS_EXPERIMENT.md) を参照。集計器は配信seedがJSの安全な整数範囲であることも要求する。

## WASM API（`crates/voxelshogi-wasm`）

`scripts/build-wasm.sh` が `apps/web/src/wasm/pkg/` にJS・`.wasm`・型定義を生成する。`wasm-bindgen` とCLIは0.2.129で一致させる。

| 公開API | 用途・返却値 |
|---|---|
| `rulesetId()` | 標準のID。実験IDの取得APIではない |
| `new Game()` / `Game.fromVsfen(text)` / `Game.fromRecordJson(text)` | 標準セッションの生成・検証付きインポート |
| `Game.board()` / `hands()` | 駒コード729要素の `Uint8Array`、先手7種→後手7種の持ち駒14要素 |
| `sideToMove()` / `ply()` / `moveCount()` / `hash()` | `b/w`、表示カーソル、棋譜長、16桁hexの局面ハッシュ |
| `legalMoves()` / `play(text)` / `isInCheck(black)` / `result()` | 合法手・着手・王手・結果JSON文字列（未終局は `undefined`） |
| `undo()` / `redo()` / `goto(ply)` / `resign()` | 標準の局面移動・投了 |
| `bestMove(configJson)` / `isFinished()` | 同期探索の結果JSON文字列、外部中断を含む終了判定。上記WASM探索API参照 |
| `moveList()` / `lastMove()` / `vsfen()` / `recordJson()` | 棋譜、直前手、局面と棋譜の保存 |
| `new ExperimentReplay(json)` / `snapshot(ply)` | 検証済み9王棋譜の読取専用再生。`snapshot` はJSON文字列 |
| `free()` | 各WASMオブジェクトを使い終わったら解放する |

`ExperimentReplay.snapshot` のJSONは `board`（729要素）、`hands`（2×7）、`side`、`ply`、`hash`、`captured`、`lastMove`、`kingCapture`（この手で王を取ったか）、`outcome`。標準の `Game.hands()` のフラット配列とは形が違う。9王再生には `Game` の王手表示を流用しない。UIの [比較室](../apps/web/src/experiment/ExperimentViewer.tsx) が表示だけを行う。

`Game.recordJson()` はundo先のカーソルだけでなくredo先を含む全着手列を保存する。探索へ渡す場合は `ply()` のカーソルを併せて扱い、表示中の局面までの履歴を復元する。単独VSFENやhashでは千日手・連続王手の履歴を復元できない（[M2の契約案](M2_PLAN.md#wasmとworkerの契約)）。

## ハッシュ・ファイル照合・再現性

- Zobristの鍵は固定SplitMix64（シード `voxelshg`）。標準初期ハッシュ `043b66e12f6b84fd` は不変。
- 局面ハッシュは盤面・持ち駒・手番を表し、ルールID・上限・履歴・探索設定までは含まない。これだけで置換表の再利用可否を決めない。
- 配信棋譜のSHA-256はファイルの照合値で、Zobristとは別物。公開manifestに記録し、ブラウザで照合後にRust/WASMの再生検証を行う。
- 再現条件にはルール、実装、seed、探索設定、上限と必要な履歴を含める。R0の生成時間や再生速度は着手列に影響しない。

## 性能とサイズ

| 測定対象・時点 | 値・位置付け |
|---|---|
| 標準、Apple M1 CPU、2026-10-25 release | 初期合法手424、`legal_moves()` 1.18 ms、ランダム対局の生成＋適用0.66 ms/手（約1,500手/秒） |
| R0、2026-10-26 | 主試験600局で6,307,152ノード、経過289.473秒。並行処理を含むためM1の単独探索速度ではない |
| M1 Native、2026-10-26 | 初期局面・反復込み深さ2は1,697ノード・約0.33秒。[全条件](M1_VALIDATION.md) |
| 現在のWASM・Web配信サイズ | [技術構成の実測表](TECH_STACK_RESEARCH.md#採用済みの構成と初回調査の区別)。今回の確認元は2405e86、WASM284,605 bytes・入口JS1,196,200 bytes。過去のサイズと区別 |

標準の計測コマンドは `cargo run --locked --release -p voxelshogi-core --example bench`。Nativeの合法手生成、R0の幅制限探索、M1のNormal、GPU学習、ブラウザ描画の速度をそれぞれ区別する。
