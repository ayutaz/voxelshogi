# M2 段階別の検証

2026-10-27 JST。**M2-1〜5の実装・公開確認は完了。** 実装順と完了条件は [計画](M2_PLAN.md)。各節は段階ごとの固定記録。PR取り込み・公開後確認と最終判定は後半にまとめる。

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
- Worker・観戦制御・3D準備と専用Worker入口のWeb変異29件を追加する。timeout・import／compile失敗をcaughtに数えず、実行済みのassertion失敗で検出する。必須 `Web unit coverage` ジョブでも実行する。

`scripts/benchmark-browser.mjs` は実Chromeとproduction buildで、初期取得・3D後読込・描画済み画面、Worker初期化／履歴復元／探索／往復、同じ棋譜・カーソルのNative比較、全6棋譜と2manifestのSHAを保存する。開発途中の計測はdirtyと明記して最終証拠にせず、固定コミットと公開版で再取得する。Normalは深さ6・50,000ノード・1秒の予算を基本とする。

CIのWeb／deployは `ubuntu-24.04` に固定し、Playwrightに対応するChromium本体を導入する。実際に遅かったaptのフォント・既存ライブラリの更新を省く。[公式runnerのブラウザ・ライブラリ一覧](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md) を確認した上で、実際のChromium起動と全E2Eの成功を必須とする。依存が不足すれば成功扱いにしない。

この段階では、必須CI、固定SHAの最終計測、通常取り込み・本番公開と公開E2Eは未完了だった。

### M2-2〜4のローカル結果

- Web単体115件、CI制御Node48件、Web変異29件、core/WASM変異33件が成功。Rustはcore153件＋WASM境界5件。終局理由の追加修正を含む。
- 実機ChromeのE2E全21件が成功。追加の2D/3D切替・カメラ、Worker再利用、Normalでの人間先後は最終差分でも対象3件を再実行して成功。
- Webの型検査・lint・production build、actionlint、Rust fmt・clippy、追加Native計測exampleを含むMSRV1.85のWASM全targetが成功。
- 3D描画済みの計測画像を確認し、rendererが `ANGLE Metal Renderer: Apple M1` であることを保存した。固定コミットでの最終計測・公開確認は後続の別記録とする。

追加の終局境界では、既存の `GameRecord::replay()` が受け入れる「詰みの盤面で投了を記録した棋譜」の終局理由が、Session読込後に変わることをRustと実WASMで再現した。検証済み末尾状態をそのまま復元する修正でGREENにし、元の処理へ戻す変異も検出した。これによりRust core153件、Web112件、core/WASMの既知33変異になった。

[PR #14の初回修正版CI](https://github.com/ayutaz/voxelshogi/actions/runs/40365706331) はChromiumの導入と起動・20 E2Eまで成功し、3D操作テスト1件が失敗した。SHA照合したtrace（ZIP SHA-256 `8eae9bea9b2f95b5bd3ffd7682778a584ef1b60cbf64016977ca7fd5a873788f`）をデータとして読み、software GLで画像取得だけに数秒かかることを確認。画像の取得を探索前後へ分け、断面・カメラ・2D/3Dの各操作は別々の**実探索中・応答前**に確認する形へ修正した。探索予算は3秒のまま。ローカルSwiftShaderとMac実機の全21件で成功し、失敗したCIを成功扱いにはしていない。

[次のCI 40371773950](https://github.com/ayutaz/voxelshogi/actions/runs/40371773950) でも同じ操作テストが失敗した。traceのZIP SHA-256 `c711a1ea392a66c18cce1e15c2beda42b826b4f49cb7ba81c9d393e029fcff9a` を照合して解析し、静止中も毎フレーム描画する負荷で操作・観測が3秒を超えることを確認した。実WebGLの描画回数が静止中も増えるREDを確認後、静止中はdemand描画、軌跡アニメーション時は連続描画へ変更。初期描画までの次フレーム要求もRED→GREENと変異検出で確認した。SwiftShaderの対象E2EとMac実機の全21件が成功した。

CodeQLの専用Worker入口に対するorigin警告も調べ、HTMLのMessagePort契約に従って空のoriginを受け付け、Window形式のoriginは探索前に拒否する境界テストをRED→GREENで追加した。実WorkerのE2Eに加え、この検証を削る変異も検出。Web単体115件・既知Web29変異がすべて成功し、最終コミットの必須CIの確認は後半に記録する。

## 固定コミットの実機計測

対象は `63a47163301121bd5ca1335d8adf208ad0d033db`、クリーンな別作業ツリー（dirty=false）。[全入力・環境・source hash・アセットhash・Worker／Native結果](experiments/m2-search-browser-local.json)。Apple M1・8 GiB、Chrome155.0.8059.85、ANGLE MetalのApple M1で、**3D盤面を描画・表示した状態で**計測した。Native側はブラウザを閉じてから同じ棋譜・カーソル・上限を実行し、コンパイル時間は含めない。3Dは静止中に連続描画せず、操作・盤面変更で再描画する。

| 局面 | Workerの完了深さ | 探索時間 | Worker往復 | 停止理由 |
|---|---:|---:|---:|---|
| 初期局面・初回 | 2 | 1,001.6ms | 1,018.8ms | 時間 |
| 初期局面・再利用1 | 2 | 1,000.0ms | 1,000.3ms | 時間 |
| 初期局面・再利用2 | 2 | 1,000.2ms | 1,000.4ms | 時間 |
| 2手進行 | 2 | 1,000.1ms | 1,000.6ms | 時間 |
| 捕獲・成りの戦術局面 | 3 | 143.7ms | 144.0ms | 50,000ノード |
| 持ち駒あり | 2 | 344.9ms | 345.2ms | 50,000ノード |
| 履歴あり・redo先を含む棋譜 | 6 | 42.9ms | 43.3ms | 深さ |

上限は全て深さ6・50,000ノード・1秒。初期局面の探索速度は約13.1〜13.2千ノード/秒で、Worker・Nativeとも3回全て深さ2。初回のWorker初期化3.2ms、棋譜復元2.6msも別記録している。時間はsoft deadlineで、全端末の1秒応答を保証する値ではない。Normalはこの予算を既定とし、0.1／1／3秒を選べる。

7件すべてのsource hash・要求と応答の根を照合した。同じ完了深さではNativeと評価・指し手が一致し、時間ではなくノード／深さで止まったケースは全結果フィールドも一致した。2manifest・全6棋譜のSHAも既存の固定記録と一致。

### 初回の実取得量

公開旧版 `2f517ca03cef33d8290be8f38bcde410e954db15` を新しいChromeコンテキストで測り、ResourceTimingの非圧縮バイト数と実際の配信ファイルの長さ・SHAを照合した。[変更前のNetwork記録](experiments/m2-initial-load-before.json)。旧版は初期3D+2Dで、2Dへ切り替えても3Dを含む入口JSは取得済み。M2は初期2Dと3Dの後読込を区別した。

| 対象（非圧縮） | 変更前の公開版 | M2の固定コミット |
|---|---:|---:|
| 初回に実取得した全JS | 1,196,200 bytes | 255,096 bytes |
| 3D選択後の全JS累計 | 1,196,200 bytes | 1,207,163 bytes |
| WASM | 284,605 bytes | 361,171 bytes |
| 探索開始時のWorker JS | なし | 11,784 bytes |

2D初回のJSは約78.7%減。3D選択後のJS総量は約0.9%増えており、3D利用時の全コードが小さくなったとはしない。探索API追加でWASMは増えたが、初回JS＋WASMは1,480,805から616,267 bytesへ約58.4%減った。変更前はCloudflare、ローカル計測はVite previewなので、この表で圧縮転送量やネットワーク速度は比較しない。公開版の実取得は次節に記録する。

再計測は、クリーンな対象コミットをcheckoutしてWASMとWebをbuildし、`node scripts/benchmark-browser.mjs runs/m2/browser.json`。公開URLには `M2_BENCH_BASE_URL` と `M2_BENCH_COMMIT` で対象を指定する。初回取得だけなら `node scripts/measure-initial-load.mjs BASE_URL OUTPUT.json`。CIは固定予算の正しさを検証し、この実時間を速度の合否閾値にはしない。

## M2-5：公開されたM2実装の実機検証

[PR #14](https://github.com/ayutaz/voxelshogi/pull/14) の最新 `63a4716` は、[CI](https://github.com/ayutaz/voxelshogi/actions/runs/40374200903)・[品質](https://github.com/ayutaz/voxelshogi/actions/runs/40374200783)・[CodeQL](https://github.com/ayutaz/voxelshogi/actions/runs/40374201185) の必須7チェックがすべて成功し、未解決CodeQL警告0件を確認して通常取り込みした。統合main `5b5b3c5941de67a10c9112eadbb2aae08283bff0` と計測版のソース差分は0である。

[main CI 40376138505](https://github.com/ayutaz/voxelshogi/actions/runs/40376138505) の通常検証・公開・配信SHA照合は成功し、Cloudflare version IDは `81181179-dc5d-4339-97d2-9070cb4c784b`。公開後E2Eは、Nodeで棋譜を再検証する生成WASMがdeployジョブにないためテスト収集時点で失敗した。このCIを成功とはしない。[PR #15](https://github.com/ayutaz/voxelshogi/pull/15) で同じrunの生成pkg受け渡しと、PRでも新しいcheckoutで全21テストを実収集する必須ジョブを追加する。ローカルのクリーンな消費側で欠落のRED・復元後のGREENを確認し、Gateから外す変異も検出した。CI制御は49テストとなる。

PR #15も [CI](https://github.com/ayutaz/voxelshogi/actions/runs/40378365779)・[品質](https://github.com/ayutaz/voxelshogi/actions/runs/40378365620)・[CodeQL](https://github.com/ayutaz/voxelshogi/actions/runs/40378365718) の必須7チェック成功・警告0件を確認して通常取り込みした。修正後main `3a500cdcdd020cbc3e632a4cb56229d3a305edd7` の [CI 40380474249](https://github.com/ayutaz/voxelshogi/actions/runs/40380474249) は、通常検証・実際の生成pkg受け渡し・公開前の21テスト収集・自動公開・配信SHA・公開E2Eが成功。Cloudflare version IDは `39f45df6-420e-4473-a83c-997645f5d4aa`。

このrunの公開E2Eは20 passed＋1 flaky（カメラ操作の1件が再試行で成功）だった。ログ精査でPlaywrightのクリック待機がカメラ慣性のフレームを待ち、思考中の確認とクリックの間に探索が終わる競合を確認した。実マウスのドラッグと実Workerの3秒予算を保ち、カメラ後の思考状態の観測と中断クリックだけを同じブラウザ処理内で実行する形へ修正。公開Workerの生成イベントも非同期に待つ。公開URL＋SwiftShaderで再試行なしの2回連続成功を確認し、他の中断操作は引き続きPlaywrightの実クリックで検証する。

修正後mainの公開SHAに対し、Mac実機Chromeで**公開E2E全21件が再試行・skipなしで成功（24.7秒）**した。[機械可読レポート](experiments/m2-public-e2e.json)。固定7入力の [公開版計測JSON](experiments/m2-search-browser-public.json) は、sourceCommitとpublishedCommitが修正後main SHAで一致し、dirty=false。3D表示・renderer、Worker再利用・根の全識別子・ソースhashを保存し、同じ完了深さのNativeの評価値と指し手がすべて一致した。ノード／深さ上限で止まった3件は全結果フィールドも一致した。

| 公開版の局面 | 完了深さ | 探索時間 | Worker往復 | 停止理由 |
|---|---:|---:|---:|---|
| 初期局面・初回 | 2 | 1,001.2ms | 1,052.9ms | 時間 |
| 初期局面・再利用1 | 2 | 1,000.1ms | 1,000.5ms | 時間 |
| 初期局面・再利用2 | 2 | 1,000.4ms | 1,000.7ms | 時間 |
| 2手進行 | 2 | 1,001.0ms | 1,001.5ms | 時間 |
| 捕獲・成り | 3 | 148.5ms | 148.9ms | 50,000ノード |
| 持ち駒あり | 2 | 346.0ms | 346.2ms | 50,000ノード |
| 履歴あり・redo先あり | 6 | 43.5ms | 43.9ms | 深さ |

初回の初期化1.8ms・棋譜復元1.8msと、Workerスクリプトのネットワーク取得を含む往復を区別する。初期局面は約12.1〜13.2千ノード/秒、3回とも深さ2。Normalの既定は深さ6・50,000ノード・約1秒を維持し、全実機の速度保証やGPU学習速度には換算しない。

### 公開ファイルと初回取得

[変更前](experiments/m2-initial-load-before.json) と [変更後](experiments/m2-initial-load-after.json) は同じCloudflare公開ホストを、新しいChromeコンテキストから測った。初回JSの非圧縮量は1,196,200→255,096 bytes、ResourceTimingのtransferSizeは325,697→83,198 bytes。後者はHTTPヘッダーを含む実取得値で、ネットワーク速度や全端末の値を保証しない。旧版の初期3D+2DからM2の初期2Dへの導線変更を含む。

公開版WASMは361,183 bytes、3D JSは952,067 bytes、Worker JSは11,784 bytes。3D選択後のJS累計は1,207,163 bytes。初回JS＋WASMは616,279 bytesで、旧版の1,480,805 bytesから約58.4%減る。3D選択後の全JS量は約0.9%増であり、3Dを使う場合のコード総量の削減とはしない。MacのローカルbuildとLinux CIのWASMは12 bytes異なるため、それぞれのファイルの実長・SHAを記録し、同一バイナリとは扱わない。

同じmain runの `web-dist`（artifact12679012024）をZIPとして読み、CIのdigest `24d787399b564e3d5cfb14becda0d6a0ac58fe9f14c5fc91c2da81aaa6a6ddbf` と照合した。コードを実行せず、build-infoのSHA、公開中のJS/WASM/Worker/3Dと2manifest・全6棋譜の計12ファイルが、長さとSHA-256で一致した。[照合記録](experiments/m2-public-artifact-match.json)。

## 最終PRの取り込みと公開（e212ec7）

完了記録とカメラ中断テストの修正を含む [PR #16](https://github.com/ayutaz/voxelshogi/pull/16) は、[CI](https://github.com/ayutaz/voxelshogi/actions/runs/40383894485)・[品質](https://github.com/ayutaz/voxelshogi/actions/runs/40383894486)・[CodeQL](https://github.com/ayutaz/voxelshogi/actions/runs/40383894474) の必須7チェック成功後、通常squash mergeした。PRのE2E21件も再試行なしで成功した。

最終main `e212ec739aeb23b3dedac83f60b861903d96fbc2` の [CI 40385647318](https://github.com/ayutaz/voxelshogi/actions/runs/40385647318) は自動公開・配信SHA・公開E2E21件（37.2秒）が再試行なしで成功。Cloudflare version IDは `f8ad9d72-2aab-4d36-afe6-881d6df4ca04`。Mac実機Chromeでも同じ公開SHAの全21件が22.7秒で成功し、skip・失敗・再試行は0件だった。[最終公開の固定記録](experiments/m2-final-publication.json)。

最終版は性能計測対象の `3a500cd` とRust／Webの実行ソースに差分がなく、公開HTMLが参照する入口JSと、JS/WASM/Worker/3D・2manifest・6棋譜の計12ファイルもバイト数とSHA-256が一致した。したがって前節の計測JSONは元のSHAを維持し、最終公開の確認と混同しない。2026-10-27の文書更新開始時にもmain CI成功と配信SHAを再確認した。後続の文書PRで公開SHAが変わる場合は、そのmain CIと `build-info.json` を確認する。

## 完了条件の照合

| 条件 | 達成の証拠 | 判定 |
|---|---|---|
| G1：同じ履歴・設定のWASM探索 | 手計算12fixtureとNative/WASM parity、両色・終局・境界・絶対ply・履歴、core/WASM33変異、必須CI | ✅ |
| G2：両AIのEasy/Normal | 実Workerの全4組合せ、保存棋譜の全着手をRustで再検証、公開E2E | ✅ |
| G3：非ブロッキング・古い応答の破棄 | 描画済み3Dの思考中操作、局面変更・履歴・読込・設定・投了、ID/revision照合、古いエラー／File.textの変異、公開E2E | ✅ |
| G4：停止・1手送り・速度 | Worker再利用、1クリック1着手、待ち時間・探索予算の分離、実機の中断とWorker数、公開E2E | ✅ |
| G5：エラー回復と後始末 | 実Worker読込失敗と再試行、通信不正・実行エラー・解放・StrictMode、Web29変異、必須CI・公開E2E | ✅ |
| G6：予算・初回ロードの実測 | 固定SHA・dirty=falseの7局面、Metal実GPU・Network、初期化／復元／探索／往復、同一CIの12アセット照合 | ✅ |
| G7：人間対AIとR0 | Normalの人間先後・投了、成り／打ち・棋譜／履歴、比較室・2manifest・6棋譜、公開E2E | ✅ |

M2-1〜5のAPI・Worker・観戦UI・バンドル分割・予算決定・通常統合・公開検証を上記で照合した。APIは [GAME_ENGINE](GAME_ENGINE.md)、開発・公開手順と件数は [CLAUDE](../CLAUDE.md)・[CONTRIBUTING](../CONTRIBUTING.md)・[DEPLOYMENT](DEPLOYMENT.md)、現在地と次のM3は [STATUS](STATUS.md)・[ROADMAP](ROADMAP.md)・[M3実行計画](M3_PLAN.md) に反映した。完了記録自身の通常PR・必須CIとmain自動公開も上記の最終版で確認した。9王の正式採用・学習モデル・有料GPUはM2の成果に含めない。
