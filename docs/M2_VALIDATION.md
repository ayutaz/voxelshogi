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

M2-1のローカル検証終了時点では、Worker、観戦UI、Normal予算の実機決定、初回取得量の改善、公開版の検証は未完了だった。M2-1のみでライブ探索の公開完了とはしない。

M2-1は [PR #13](https://github.com/ayutaz/voxelshogi/pull/13) の必須7チェックが成功し、`012d4c987e14b3737a8bd608b48c6f02848162e0` として通常取り込み。統合後 [CI 40358486594](https://github.com/ayutaz/voxelshogi/actions/runs/40358486594) はブラウザ用のaptダウンロードで15分のjob上限に達してWebジョブがcancelledとなった。探索・単体・parity・buildの成功と、本番公開の未完了を区別する。

## M2-2〜4：Worker・観戦制御・表示分割

作業ブランチ `feat/m2-worker-client`。Workerエンジン／クライアント、revisionを含むGameStoreの採否、観戦スケジューラ、新規観戦E2Eはそれぞれ未実装によるREDを確認して実装した。

- 中断はWorkerのterminateで行う。古いメッセージだけでなく、古いWorkerのerror／messageerrorも新しい要求を壊さない。テストでこのエラーの失敗を確認後に修正。
- Easyも合法手と外部終局・絶対手数上限をRustで確かめる。上限を無視する失敗を確認して修正。NormalはM1の同期探索をWorkerで呼ぶ。
- 同じ盤面へundo／新規対局／読込で戻ってもrevisionを変える。応答は根とrequest IDを照合し、最後に表示側の検証付きplayで適用。
- 1手送り・一時停止・中断・再開・難易度／予算変更・履歴操作・非同期読込を一つの制御にまとめる。すでに停止中の1手送りの中断と、速度変更が予約済みの1手送りを消す失敗もREDから修正。
- 初期画面はNormal同士の観戦・停止・2D。3Dを遅延ロードし、描画済みフレームを待つ。最初の計測画像が未描画だったため、canvasの存在だけで完了にしないテストを追加してRED→GREENを確認。
- E2Eは既存9件を維持しつつ計21件。実Workerで全難易度の組合せ・1手送り・中断／回復、3D描画後の思考中カメラ操作、Normalでの人間先後、成り・打ち・棋譜の再検証、履歴・読込・同一盤面での中断、遅いFile.textの破棄を確認した。
- Worker・観戦制御・3D準備のWeb変異27件を追加する。timeout・import／compile失敗をcaughtに数えず、実行済みのassertion失敗で検出する。必須 `Web unit coverage` ジョブでも実行する。

`scripts/benchmark-browser.mjs` は実Chromeとproduction buildで、初期取得・3D後読込・描画済み画面、Worker初期化／履歴復元／探索／往復、同じ棋譜・カーソルのNative比較、全6棋譜と2manifestのSHAを保存する。開発途中の計測はdirtyと明記して最終証拠にせず、固定コミットと公開版で再取得する。Normalは深さ6・50,000ノード・1秒の予算を基本とする。

CIのWeb／deployは `ubuntu-24.04` に固定し、Playwrightに対応するChromium本体を導入する。実際に遅かったaptのフォント・既存ライブラリの更新を省く。[公式runnerのブラウザ・ライブラリ一覧](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md) を確認した上で、実際のChromium起動と全E2Eの成功を必須とする。依存が不足すれば成功扱いにしない。

必須CI、固定SHAの最終計測、通常取り込み・本番公開と公開E2Eは引き続き未完了。

### M2-2〜4のローカル結果

- Web単体111件、CI制御Node48件、Web変異27件がすべて成功。core/WASMの既知32件はM2-1で成功済みで、この段階ではその実装を変更していない。
- 実機ChromeのE2E全21件が成功。追加の2D/3D切替・カメラ、Worker再利用、Normalでの人間先後は最終差分でも対象3件を再実行して成功。
- Webの型検査・lint・production build、actionlint、Rust fmt・clippy、追加Native計測exampleを含むMSRV1.85のWASM全targetが成功。
- 3D描画済みの計測画像を確認し、rendererが `ANGLE Metal Renderer: Apple M1` であることを保存した。固定コミットでの最終計測・公開確認は後続の別記録とする。
