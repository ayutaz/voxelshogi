# M0 検証記録

対象: main `e3f7f7a` からの作業ブランチ `chore/finish-m0-validation`。検証開始: 2026-10-25、公開確認完了: 2026-10-26（JST）。

M0-1〜5は完了した。[PR #3](https://github.com/ayutaz/voxelshogi/pull/3) の最終文書コミットも必須7チェックが成功し、保護を迂回せず通常の squash merge を行った。統合後の main の CI・CodeQL・本番公開・配信 SHA・公開 E2E の成功も確認済み。M0完了時のソース・テスト・CI設定は全体変異調査時点の `5a14c0d` と同じ。

本書は**M0時点の履歴**を保持する。R0追加直後はRust116件・Web36件・既知変異14件・E2E9件だった。その後M1・M2も完了した。現在の件数・公開版は [STATUS](STATUS.md) と [M2記録](M2_VALIDATION.md) を正とし、次の作業は [M3計画](M3_PLAN.md)。[M1記録](M1_VALIDATION.md)・[現在のCI状況](CI_CD_PLAN.md#現在の状態) と [R0報告](NINE_KINGS_EXPERIMENT.md) を参照し、以下の旧件数・カバレッジ・全758変異を現在の実測値と混同しない。

## M0 完了時の取り込みと公開

| 記録 | 確認結果 |
|---|---|
| PR 最終コミット | `ee7b1026e64a0825fdbe2283db7c11ee5b8d2298`。必須7チェック成功（[CI](https://github.com/ayutaz/voxelshogi/actions/runs/40194273936)・[Security](https://github.com/ayutaz/voxelshogi/actions/runs/40194273973)・[Quality](https://github.com/ayutaz/voxelshogi/actions/runs/40194273928)） |
| 統合 | 2026-10-25 23:14 JST、PR #3 を squash merge。`1ff4e2fe76b60c470ed57c75c984620dcc8fc7c2` |
| 統合後の検証 | [main CI 40201319748](https://github.com/ayutaz/voxelshogi/actions/runs/40201319748) と [main Security 40201319737](https://github.com/ayutaz/voxelshogi/actions/runs/40201319737) が成功 |
| 公開後の検証 | 2026-10-26 00:53 JST、公開 E2E 6件成功（33.4秒）。deploy・配信 SHA 確認も省略なしで成功 |
| Cloudflare version ID | `ce499132-9c06-4a0c-aea6-8491a10fbfa7` |
| 公開記録 artifact | `production-1ff4e2fe76b60c470ed57c75c984620dcc8fc7c2`。commit・version・run ID を取得して照合 |
| 独立した配信確認 | 公開 URL の `build-info.json` が HTTP 200 を返し、上記の完全長 commit SHA と一致 |

この表は M0 完了時のスナップショット。以後の文書更新でも自動デプロイされるため、現在の公開版は配信中の `build-info.json` と対応する main の CI で確認する。当時はM1未着手だった。その後の実装・検証は [M1の記録](M1_VALIDATION.md)、今後の順序は [ROADMAP](ROADMAP.md) を参照。

## PR と取り込み制御

[PR #2](https://github.com/ayutaz/voxelshogi/pull/2) は必須7チェックの成功後、保護を迂回せず squash merge した。当時の統合コミットは `e3f7f7a392d58ebc167d3f058eaa2f35b2f0f6cc`。未完了時の merge 拒否と、成功時の通常取り込みの両方を確認済み。

- 通常 CI: [40181542610](https://github.com/ayutaz/voxelshogi/actions/runs/40181542610)
- CodeQL: [40181542576](https://github.com/ayutaz/voxelshogi/actions/runs/40181542576)
- 品質計測: [40181542587](https://github.com/ayutaz/voxelshogi/actions/runs/40181542587)
- 統合後の本番公開: [40183599117](https://github.com/ayutaz/voxelshogi/actions/runs/40183599117) でdeploy・配信SHA・公開E2Eがすべて成功。公開URLも `e3f7f7a392d58ebc167d3f058eaa2f35b2f0f6cc` と一致、Cloudflare version IDは `0f356b50-806b-4621-aecf-c554ccdf7a71`。

PR #3の機能・テスト更新 `5a14c0d` も、[通常CI 40187911594](https://github.com/ayutaz/voxelshogi/actions/runs/40187911594)・[CodeQL 40187911528](https://github.com/ayutaz/voxelshogi/actions/runs/40187911528)・[品質計測40187911530](https://github.com/ayutaz/voxelshogi/actions/runs/40187911530) が成功し、必須7チェックすべてのpassをAPIで確認した。通常CIではRust 101テスト、MSRV、Web単体33件、ブラウザE2E 6件と依存監査が成功し、PRの本番deployは省略された。

fork PR の実検証は未実施で、外部からの開発参加を受け入れる際の追加確認とする。現在の一人開発では M0 の完了条件に含めない。検証用 fork・組織リポジトリは作成していない。通常PR・Dependabot・本番環境の制限の検証とは区別する。

APIの再確認では repository Secrets は空、Cloudflare の2件は production environment にのみ存在し、そのデプロイ許可は `main` の1件のみ。CI の deploy は main の push と成功した Gate を要求し、PRでは省略する。実行した通常PR・Dependabot PRの動作と、設定で保証する範囲を区別して記録する。

## 本番を変更しない復旧訓練 — 完了

公開検証が成功した旧 run の成果物を選び、再ビルドせずローカルの loopback で配信した。

| 記録 | 値 |
|---|---|
| 成果物を取得した run | [40170836102](https://github.com/ayutaz/voxelshogi/actions/runs/40170836102) |
| commit | `0e29eb42229ef111494d8d5b73f254729e4df38f` |
| Cloudflare version ID | `afe83bf7-97c2-4f4f-94b5-7f3ab04d0337` |
| metadata artifact | `production-0e29eb42229ef111494d8d5b73f254729e4df38f` |
| 配信 artifact | `web-dist` |
| ローカル配信先 | `http://127.0.0.1:4181` |
| 実ブラウザの検証 | Chrome E2E 6件成功（9.8秒）。配信 SHA、初期表示、人間先手・後手のAI対局、undo、AI観戦、棋譜入出力 |

`deployment-info.json` の commit と `web-dist/build-info.json` が一致した。対象SHAを `E2E_COMMIT` に指定して、訓練当時のリポジトリの6件を実行した。本番 Worker・デプロイ履歴は変更していない。これは計画どおり旧成果物を隔離配信する訓練であり、Cloudflare の本番 rollback コマンド自体を実行した記録ではない。

当時の再現手順（配信artifactは7日・metadataは30日で期限切れになる。取得不能なら別の検証済み成功runを選び、[現行の復旧手順](DEPLOYMENT.md#復旧手順) に従う）:

```bash
gh run download 40170836102 -R ayutaz/voxelshogi -n web-dist -D /tmp/voxelshogi-recovery/web-dist
gh run download 40170836102 -R ayutaz/voxelshogi -n production-0e29eb42229ef111494d8d5b73f254729e4df38f -D /tmp/voxelshogi-recovery/production
# commit / version / run と build-info.json を照合した後、別ターミナルで配信
pnpm --dir apps/web exec vite preview --outDir /tmp/voxelshogi-recovery/web-dist --host 127.0.0.1 --port 4181 --strictPort
E2E_BASE_URL=http://127.0.0.1:4181 E2E_COMMIT=0e29eb42229ef111494d8d5b73f254729e4df38f pnpm --dir apps/web exec playwright test e2e/game.spec.ts e2e/build-info.spec.ts
```

## 変異テストの生き残り分類

### M0 完了時のカバレッジ

`5a14c0d` の[Quality 40187911530](https://github.com/ayutaz/voxelshogi/actions/runs/40187911530) でRust/Webのカバレッジと既知変異9件の検査がすべて成功した。保存したLCOV・HTML・JSONの存在と計測行数、変異のbaseline成功と9件すべてのcaughtを再確認した。

| 対象 | 行カバレッジ | 範囲 |
|---|---|---|
| Rust core | 95.92%（1457 / 1519） | 独立参照実装・統合テスト・examplesを除く。WASMラッパーは対象外 |
| Web単体 | 35.37%（127 / 359） | 未importのUI/3Dも含む。生成WASM glueとブラウザE2Eの計測値は含まない |

割合の一律基準は設けない。Webの未計測領域は残しており、実ブラウザE2Eの成功とは別の証拠として扱う。

### 生き残りの再現とテスト補強

以前の調査は core の全ファイルではなく、`piece.rs`・`state.rs`・`zobrist.rs` の232変異が対象だった。元の結果は199 caught、18 missed、15 unviable、timeout 0。ビルド不能は検出成功に数えない。

同じ18件を main `e3f7f7a` の86テストで再実行した結果は9 caught、9 missed。以前追加した6テストの効果を確認した。さらに `tests/state_contracts.rs` の6テストを追加し、残る振る舞いの変化7件が実際にテスト失敗になることをコピー上で確認した。製品コードの変更はない。正常コードの Rust 92テスト、Clippy が成功。

| 以前の missed | 件数 | 分類・検証 |
|---|---:|---|
| 駒index（0/1）、成り状態、駒名（空/xyzzy）、エラー表示、持ち駒数（0/1）、全種類を持つ場合の駒打ち | 9 | 前回追加したテストで caught と再確認 |
| `check_move` の強制成り条件から `!` を削除 | 1 | 両色の歩・香・桂の行き所のない段への移動を、成りあり・なしで検証して caught |
| `is_legal` を常に true / false にする | 2 | 合法・不合法・終局済みの各入力を公開APIで検証して caught |
| 後手の連続王手の判定分岐を削除 | 1 | 両色の連続王手と繰り返し前の1手を含む局面で、王手側の敗北を確認して caught |
| `play` を状態を更新しない `Ok(())` にする | 1 | 手書きの捕獲・成り・持ち駒・手番・手数と、不合法時の非更新を検証して caught |
| 持ち駒ハッシュの XOR を OR / AND にする | 2 | 全7持ち駒・両所有者・両手番について、Zobrist の XOR 合成則で caught |
| 千日手区間の開始を `first + 1` から `first * 1` にする | 1 | 同値変異。first自身と現在の局面は同じ盤面・手番・王手状態。末尾に既に含まれる値を再度含めても `all` / `any` は変わらない。ハッシュ衝突の扱いは元実装と同じ |
| 千日手判定の存在確認 `.any` の手番比較を `==` から `!=` にする | 1 | 同値変異。履歴は合法着手ごとに手番を交代し、4回目の同一手番の出現区間には両方の手番が必ずある。どちらを検索しても `any` は true。王手を判定する `.filter` は変更されない |

同値2件を caught として数えない。同じ232件の再調査は完了し、215 caught・15 unviable・2 equivalent・timeout 0・未分類の生き残り0と確認した。以前の18 missedのうち、16件がテストで検出され、2件は根拠付きで同値と分類された。

| 再調査 | 証拠 |
|---|---|
| 対象 | `piece.rs`・`state.rs`・`zobrist.rs` の232件。製品ソースは main `e3f7f7a` と同一、テストは作業コミット `d9f5509` の追加6件を含む |
| 実行 | cargo-mutants 27.1.0、Rust 1.97.1、`--timeout 90 --jobs 2 --cargo-arg=--locked` |
| 時間 | 2026-10-25 10:20 UTC開始、約18分。baselineのbuildとtestも成功 |
| raw出力 | git管理外 `coverage/m0-mutants-after/mutants.out/` の全inventory・outcomes・diff・log |
| 照合結果 | `node scripts/ci/mutation-report.mjs coverage/m0-mutants-after/mutants.out` が成功。`review.json` は `{"caught":215,"unviable":15,"equivalent":2,"total":232}` |

core全体の758件は別範囲として、[8分割の手動実行40184455263](https://github.com/ayutaz/voxelshogi/actions/runs/40184455263) で初回調査を完了した。`d9f5509` 時点の結果は666 caught・58 unviable・34 missed・timeout 0。各分割のbaselineは成功した。このrunには同値変異の新集計と、以下の追加テストはまだ含まれず、rawの生き残りがあるため失敗した。後述の修正後の全体CI成功とは区別する。232件だけの結果をcore全体の結果とは扱わない。

### core全体の追加調査

ローカルでも、既存の232件と重複しない526件を完了した。結果は451 caught・43 unviable・32 missed・timeout 0。先の232件との合計は全758件で666 caught・58 unviable・34 missedとなり、GitHubの初回調査と一致した。全inventoryの名前集合が232件と526件の和集合と一致し、交差が空であることも照合した。この実行は追加の座標・入力境界テストより前のスナップショットで、見つかった34件は下記の再検証ですべて対応している。

追加範囲で `Board::Debug` の空出力、`Square::from_index` の上限729を許してしまう変異、`Square::offset` のz方向の符号反転、`Square` のDebug/Displayを空にする計5変異を発見した。`geometry_contracts.rs` に盤面・座標表示、明示的な座標インデックス、各軸の加算と全6境界の3テストを追加し、全5変異をコピー上で検出した。特にz方向の対称性がある利き生成では符号反転が集合比較から漏れるため、座標演算そのものに手計算の期待値を置いた。正常コードのRustは95テスト成功。

さらに `NotationError::Display` の空出力を発見し、棋譜インポートの理由・不正な指し手のindex/text・Sessionへの伝播を確認する1テストを追加した。同じテストが `RecordError::Display` の空出力も拒否することをコピー上で確認した。正常コードのRustは96テスト成功。

全8分割の結果から、さらに入力とセッションの境界の検証不足を確認した。手書きの期待値による5テストを追加し、正常コードのRust計101テストとfmt・Clippyが成功した。

- VSFENの空マス数は単独の1〜9のみ。`09`・`45`を拒否し、持ち駒の先頭0も拒否する。162歩を持つ局面は受理する。
- VSFENは4096 bytes以下、手数番号は1,000,000以下を受理し、それぞれ境界の前後を検証する。サイズ超過は構文解析に進まず拒否する。
- 棋譜JSONは4 MiB以下、指し手は20,000手以下を受理する。正しいJSONに空白を付けてサイズ上限を検証する。再生時の手数上限は、範囲内では先頭の不正な指し手まで検証し、上限超過時は先に`TooLong`で拒否することを確認する。
- `Session::is_empty`はundoで保持した履歴も含めて判定する。`goto`は0と履歴末尾を受理し、末尾の次を拒否する。

初回の34 missedを同じ名前で再選択し、追加テストで26件を検出し、根拠付きの同値8件だけが残ることを再確認した。baselineのbuild/testも成功し、ビルド不能・timeoutは0件。rawの終了コードは2で、新集計が全34件を照合して `{"caught":26,"unviable":0,"equivalent":8,"total":34}` を出力した。証拠はgit管理外の `coverage/m0-all-survivors-after/mutants.out/`。製品コードの変更や、新たな同値の承認追加はない。

### 全758件のCI再検証 — 完了

更新後の `5a14c0d30cc748ff22cd843146f95e496dc9252d` を対象とした[全体再検証40187925728](https://github.com/ayutaz/voxelshogi/actions/runs/40187925728) は8分割すべて成功した。cargo-mutants 27.1.0・Rust 1.97.1、各分割は `--shard N/8 --timeout 90 --jobs 2 --cargo-arg=--locked` で実行した。

| 分割 | caught | unviable | equivalent | 合計 |
|---|---:|---:|---:|---:|
| 0 | 87 | 8 | 0 | 95 |
| 1 | 67 | 28 | 0 | 95 |
| 2 | 91 | 1 | 3 | 95 |
| 3 | 91 | 1 | 3 | 95 |
| 4 | 90 | 5 | 0 | 95 |
| 5 | 89 | 6 | 0 | 95 |
| 6 | 94 | 1 | 0 | 95 |
| 7 | 83 | 8 | 2 | 93 |
| **全体** | **692** | **58** | **8** | **758** |

全8件のartifact `full-mutations-0`〜`full-mutations-7` を新しい一時ディレクトリへ取得して監査した。各baselineのbuild/test成功、空でないinventoryと全outcomesの1対1対応、実行されたテスト失敗によるcaught、ソース指紋を含む同値の根拠を照合した。CI保存の `review.json` と再集計は全分割で一致し、当時の `cargo mutants --list --json` の全758件と各分割の和集合も一致した。欠落・重複・timeout・未分類の生き残りは0件。ビルド不能58件と同値8件をcaughtには含めない。rawレポート・diff・log・reviewは同runで7日保存する。

### 同値変異の根拠（移動生成）

初回runの分割2の95件は91 caught・1 unviable・3 missed。missedは次の同値変異と確認し、raw成果物を新集計で照合して91 caught・1 unviable・3 equivalentになった。変異名と `movegen.rs` 全体のソースハッシュを承認リストへ記録した。この分類を更新後の全体CIでも再確認した。

| 変異 | 同値の根拠 |
|---|---|
| `room` の `sign > 0` → `sign >= 0` | 呼び出し側が渡す値は `[-1, 1]` のみで、0は渡らない |
| 飛車の `umax == 0 || vmax == 0` → `&&` | 片方が0なら出力用の二重ループは空。追加で初期化するDPの片辺も盤内読み取りと局所変数の更新だけで、移動先の集合を変えない |
| 角の方向bit生成の `sign > 0` → `sign >= 0` | 3軸の符号もそれぞれ `[-1, 1]` だけで、方向bitは変わらない |

初回runの分割3も95件中91 caught・1 unviable・3 missedで完了した。次の3件を契約上の同値として分類し、新集計で91 caught・1 unviable・3 equivalentと照合した。

| 変異 | 同値の範囲・根拠 |
|---|---|
| 角の平面対角の片側選択 `sc > 0` → `sc < 0` | **列挙順は変わり得る**。`b=0` の平面対角を正負どちらの走査で追加するかだけが変わり、座標・`g[0]` / `pe[0]` の遮り条件は同じ。`b>0` の処理は不変。同じ移動先を1回ずつ返す集合の契約上の同値で、順序まで同一とは主張しない |
| 同じ箇所の `sc > 0` → `sc >= 0` | `sc` は±1だけなので条件が一致する |
| 香の利きの `dy < 0` → `dy <= 0` | x/zの差が0という条件下で追加されるdy=0は始点=終点。関数先頭で既にfalseを返すため結果は変わらない |

片側選択の変異は、コピー上の空盤中央の角で調べ、Vecの順序は異なるが、重複のない移動先集合が一致することを確認した。既存の独立参照実装との集合比較もこの変異を通過している。`targets` / `legal_moves` のバージョン間の順序互換性は元の仕様に含まれず、再現性の記録はエンジンコミットを含む。[API契約](GAME_ENGINE.md#標準ルールのrust-api) に明記した。M1の順序が必要な処理では明示的に定義する。

### 継続実行での同値変異の扱い

`scripts/ci/mutation-report.mjs` が全体調査の出力を照合する。変異を生成対象から除外せず、完了した baseline、空でない inventory と全結果の1対1対応、各変異の build/test 結果を確認する。未知の生き残り、timeout、途中終了、欠落したテスト結果、ツール版の変更は失敗とする。ビルド不能は unviable のままで、caught に含めない。

確認した同値変異は `scripts/ci/equivalent-mutations.json` に理由と対象ソース全体の SHA-256 を保存し、完全一致したものだけ equivalent に分類する。M1等で対象ソースが変わった場合は同値の根拠を再確認する。集計を `review.json` として raw report と一緒に保存する。cargo-mutants の終了コード2（生き残りあり）はこの照合を通った場合だけ成功とする。

集計処理は RED を確認後、6テストが成功した。ソースハッシュ照合を無効にする変異もテストが拒否した。CI制御用テストは計26件。
