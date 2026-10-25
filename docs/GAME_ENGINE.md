# ゲームエンジン（`crates/voxelshogi-core`）

ルールの正は `docs/RULESET.md` である。本書は、エンジンの API と内部表現を説明する。

## モジュール

| モジュール | 責務 |
|---|---|
| `coord` | `Square`（`z*81 + y*9 + x`）、表示座標（`5五V`）、ASCII座標（`555`） |
| `piece` | `Color`（= `Player`）、`PieceKind`（14種）、`Piece`（コードは `1 + kind + 14*color`、0は空） |
| `board` | `Board`（729バイト）、初期配置 |
| `movegen` | 擬似合法な移動先 `targets`、利きの判定 `attacks`（飛角は動的計画法、ADR-004） |
| `moves` | `Move::{Normal, Drop}`、文字列表記 |
| `state` | `GameState`: 合法手、`apply_move`（純粋関数）、王手、終局、千日手の履歴、`validate` |
| `zobrist` | 固定シードの Zobrist ハッシュ |
| `notation` | `parse_move`、VSFEN の入出力（入力長の上限あり、局面を検証する） |
| `record` | `GameRecord`（`ruleset_id`、初期 VSFEN、指し手、結果、終局理由）。JSON 入出力、再生による検証 |
| `session` | UI 向け: 指し手リストとカーソル、undo/redo/goto、投了、棋譜の入出力 |

## 主な API

```rust
let g = GameState::new();
let moves: Vec<Move> = g.legal_moves();
let next = g.apply_move(&moves[0])?;          // Result<GameState, MoveError>
next.is_in_check(Color::Black);
next.result();                                 // Option<GameResult>
voxelshogi_core::notation::to_vsfen(&next);
GameRecord::from_moves(&g, &moves[..1]).to_json();
```

`targets()` と `legal_moves()` は移動先・指し手の集合を返すAPIで、列挙順序のバージョン間互換性は保証しない。乱数で要素を選ぶ処理や探索の同点処理を再現する際は、シード・設定に加えてエンジンのコミットを固定する。ルールの正しさを調べる比較は集合として行い、順序が要件になる処理はその処理側で順序を定義する。

## VSFEN

`<盤> <手番 b|w> <持ち駒 or -> <手数>`

- 盤: 9つの層（`z = 0..8`）を `|` でつなぐ。各層は9つの段（`y = 0..8`）を `/` でつなぐ。各段は、9筋から1筋の順に駒を並べる。
- 駒の文字: `P L N S G B R K`。先手は大文字、後手は小文字。成り駒には `+` を付ける。数字は連続する空きマスの数。
- 持ち駒: 先手の分、後手の分の順に、それぞれ `R B G S N L P` の順で書く（例: `R12P2g`）。
- 読み込み時に `GameState::validate` で検証する内容: 玉が各1枚、駒の総数が372枚の構成以内、行き所のない駒がない、二歩がない、手番でない側が王手されていない。

## ハッシュと再現性

- Zobrist の鍵は SplitMix64（シード `voxelshg`）から生成する。初期局面のハッシュ `043b66e12f6b84fd` をテストで固定している。
- 千日手は、局面の履歴（ハッシュ、手番、王手かどうか）から判定する。

## 性能（2026-10-25 実測、Apple M1 CPU、release）

| 項目 | 値 |
|---|---|
| 初期局面の合法手数 | 424（参照実装と一致） |
| `legal_moves()`（初期局面） | 1.18 ms |
| ランダム自己対局（生成と適用） | 0.66 ms/手、約1,500手/秒 |
| WASM サイズ（release） | 227 KB |

計測: `cargo run --release -p voxelshogi-core --example bench`
