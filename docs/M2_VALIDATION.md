# M2 段階別の検証

2026-10-27 JST。**M2全体は進行中。** 実装順と完了条件は [計画](M2_PLAN.md)。この記録のM2-1は作業ブランチ `feat/m2-worker-spectator` での検証であり、PR取り込み・公開後確認は別途追記する。

## M2-1：WASM探索境界

- Sessionの終局保持テストを先に追加し、未実装APIによるREDを確認。MaxPlies／Abandonedの保持、undo/redo・分岐・終了後の拒否と再投了を実装してGREEN。
- WASMアダプタのRustテストも未実装によるREDを確認後、実装。実WASMは既存生成物に対して新規13件すべてが `bestMove`／`isFinished` 未実装で失敗することを確認し、再ビルド後に成功。固定ノードの2件を追加して探索は計15件。
- Rustと実WASMで共通の手計算fixture 12件：両色の隅の王（深さ2、合計29ノード）、9ノードでの反復中断、詰み、千日手、連続王手、非対称な持ち駒評価。fixtureの期待値は規則から用意し、別のCI照合ではNativeと実WASMの全結果フィールドも比較する。
- 絶対ply41とカーソル0の区別、redo先の保存、予算0、未完了の評価null、ブラウザ時計、JSON上限と安全整数・設定範囲・未知フィールドを検証。
- GameStoreも先にAbandonedの終了表示用状態・合法手のテストを追加し、`finished` 欠落のREDを確認後に実装。

### ローカル結果

- Rust core152件＋WASM境界5件、Web52件、CI制御Node46件が成功。
- `cargo fmt --all --check`、workspace全targetのclippy、Webの型検査・lint・production build、actionlintが成功。
- `node scripts/ci/search-parity.mjs` の12局面で全フィールドが一致。
- `node scripts/ci/mutation-smoke.mjs` の32件すべてが実際に実行されたテストの失敗で検出。追加分は終局情報の読込・カーソル・分岐・終了後の着手／再投了、WASMの安全整数・時間換算・ノード上限・絶対ply・評価null・Abandoned。
- Mac実機Chromeでproduction previewのE2E全9件が成功（既存の人間先後・ランダム観戦・比較室・棋譜入出力）。Workerでのライブ探索・非ブロッキングの証明はM2-2以降に別途行う。

後続のWorker、観戦UI、Normal予算の実機決定、初回取得量の改善、公開版の検証は未完了。M2-1のみでライブ探索の公開完了とはしない。
