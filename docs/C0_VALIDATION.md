# C0：3D操作中の探索テストの観測競合

2026-10-27（JST）。対象の旧公開版は `c9d046c329a54f07ea7c94c3199519b7b6815910`。発端はmain `b6cfc93` の [公開CI 40432366163](https://github.com/ayutaz/voxelshogi/actions/runs/40432366163) の1件の再試行。アプリ・Rust・探索上限は変更せず、E2Eの観測とCIの回帰手順を修正した。固定したローカル検証は [計測JSON](experiments/c0-interaction.json)。通常PRの必須CI・mainの公開・配信SHA・公開後検証も成功してからC0完了と判定する。

## 原因の切り分け

旧テストは実マウスのドラッグ後にNodeへ戻り、次の `page.evaluate` の時点で「まだ思考中か」を確認して中断した。操作と確認は別時刻であり、その間に正しい探索応答が届くと失敗する。最大3秒は最低3秒の保証ではなく、深さ・50,000ノードの上限でも先に終了する。

固定公開版の実機Metal・SwiftShader、同じ実行ソースのlocal/Metalで各3回、計9回の通常操作は成功した。その後、観測だけを3.3秒遅らせた1回では、入力は要求から約16〜51ms、描画も思考中、実Worker応答は約2,376ms、確認時は「一時停止中」になった。応答内の探索時間は約2,367msで、50,000ノード上限だった。

診断付きE2Eでも、カメラ操作から確認まで3.3秒待つテストを先に追加し、期待「思考中」／実際「一時停止中」のREDを確認した。この実行でも入力・描画は思考中に行われ、応答は要求後約2,400msだった。修正後、同じ観測遅延でGREENになった。

したがって、**操作後の観測時刻を操作中の状態として判定する競合**は再現・対処できた。元のCIの失敗時には詳細な時刻の記録がないため、その一回の遅延が描画・driver通信・runner競合のどれによるものだったかは断定しない。今回の測定では製品側の画面停止は観測されず、画面停止を注入すると修正後のテストが失敗することも確認した。すべての端末の応答時間を保証する計測ではない。

## 修正と維持した条件

- `e2e/interaction-probe.ts` がブラウザの同じ `performance.now()` で、要求送信・本物のWorker応答・terminate、trustedなpointer入力、実際の非ゼロinstanced drawを記録する。Workerのメッセージを保留・置換・遅延しない。drawは描画命令の提出であり、GPU完了時間とは扱わない。
- カメラはウォームアップ済みの同じ実Workerで探索する。pointerupのイベント内で状態を記録し、思考中かつ応答未到着のときに中断ボタンを押す。Nodeの次のRPC時点に判定を持ち越さない。
- 実マウス入力、要求→ドラッグ→描画→pointerup→terminateの順序、思考中のphase、カメラ画像の変化を要求する。Node側を3.3秒遅らせても盤面が進まないことを確認する。速度・断面・2D/3D切替の操作、Playwrightでの中断クリック、5個のWorkerと中断後の再探索も維持する。
- 固定待機で「必ず計算中」とは判定しない。ウォームアップ後100ms待つが、合格には入力・描画・pointerup時点の応答未到着とphaseの両方が必要。初期化中の要求だけで成功扱いにしないため、同じWorkerの先行する実探索応答も要求する。
- 全時系列・renderer・user agentをJSON attachmentとCIログへ保存する。計測器はテスト内にだけ注入し、配布アプリへ追加しない。

## 変異による検出確認

依存・WASMを用意した隔離コピーの製品ソースへ各変異を入れ、production build後に同じ対象E2Eを再試行なしで実行した。コンパイル失敗・テスト未収集・全体timeoutを検出として数えていない。

| 変異 | 期待する検出 | 実測 |
|---|---|---|
| `Board3D.tsx` の `OrbitControls` に `enabled={false}` | 入力後の思考中の描画がない | drawの存在を求めるassertionで失敗 |
| `SearchClient` の `worker.postMessage(request)` 直後、3秒予算時だけmain threadを3.5秒busy wait | 操作前に実応答が届き、同時操作ではなくなる | camera-endの `pending: true` を求めるassertionで失敗 |

変異は隔離コピーごと除去済み。実装・テストを成功に合わせて弱めたり、探索上限を増やしたりしていない。

## 反復条件とCI

反復は各条件3回、1 worker、retries=0と先に固定した。ローカルChrome/Metalと公開Chrome/SwiftShaderを分け、rendererの実値を確認した。全スイートは21件を別途実行する。成功まで試行数を増やす運用にはしない。各結果・失敗・skip・再試行数は計測JSONに残す。

```bash
# WASM・Webを固定ツールでbuildした後、ローカル版
E2E_COMMIT="$(git rev-parse HEAD)" pnpm --dir apps/web e2e ai.spec.ts \
  --grep '2D/3D and camera' --repeat-each=3 --workers=1 --retries=0
# 公開SHAはローカルHEADと区別して指定する
E2E_BASE_URL=https://voxelshogi.yousan-apps.workers.dev \
E2E_COMMIT=REPLACE_WITH_PUBLISHED_COMMIT_SHA \
pnpm --dir apps/web e2e --retries=0
```

SwiftShader比較ではPlaywrightの `launchOptions.args` に `--use-angle=swiftshader` と `--enable-unsafe-swiftshader` を指定し、実rendererがSwiftShaderであることを記録する。実GPUの証拠には使わない。旧REDの再現は、診断の記録を残したままpointerup内の中断を外し、3.3秒後の `page.evaluate` で状態を取得して「思考中」を要求する。

通常のWeb CIとmainの公開後ジョブに、対象E2Eの3回連続・retries=0を追加した。Webジョブは必須 `CI Gate` の依存で、公開側も1回の失敗でjobが失敗する。通常21件の成功やretryだけで反復の失敗を上書きしない。CI状態の取得は [ci-checks](../.agents/skills/ci-checks/SKILL.md) の最短10分間隔を維持する。

C0完了時点ではモデル・推論runtime・Python依存は未導入だった。その後 [M3-0〜5](M3_PLAN.md#実装順とtdd) を進め、公開・実機検証まで完了した（[M3記録](M3_VALIDATION.md)）。次は [ROADMAP](ROADMAP.md) のM4。
