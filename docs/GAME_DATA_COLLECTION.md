# 同意した棋譜のCloudflare保存

**2026-11-14追加指定**：今後は常時自動保存・送信表示なしへ変更する。[実装計画U4](design/ARENA_IMPLEMENTATION_PLAN.md#u4自動保存と移行)で新APIとclientを接続する。以下は現行schema 1の実装・運用記録であり、今回そのコード・DB・配信を変更していない。

2026-11-14 JST。[公開準備L4](PUBLIC_LAUNCH_PLAN.md)の実装。**実装・D1作成と、公開URLの動作確認は別である。**
[現在地](PUBLIC_LAUNCH_PROGRESS.md)で配信と検証の状態を確認する。利用者向けの説明は[privacy.html](../apps/web/public/privacy.html)。

## 利用者の動作

送信は**対局ごとにOFFから開始**する。OFFでも全ゲーム機能と端末へのJSON保存を使える。
ONにした対局が終局した時、または「ここまでを中断棋譜として送信」を押した時に、その対局を1回だけ送る。
終局後にONにしても遡って送らない。読み込んだ棋譜は送らない。

通信失敗でも観戦・着手・端末保存を継続できる。再送は利用者が選び、最初に固定した本文とIDを使う。
途中で設定や対局が変わっても再送本文を差し替えない。OFFにすると進行中のリクエストを中断し、未送信本文・再送待ちを破棄する。
既にサーバーへ届いた分は自動削除されない。ページ離脱時のbeacon、自動再送、手ごとの送信は行わない。

## 構成とデータ契約

- `src/collection/worker.ts`：`/api/games`のPOST受信、`/api/collection`の公開設定、期限削除。静的アセットはasset-firstで配信する。
- `wrangler.jsonc`：Workerの`GAMES`へ専用D1 `voxelshogi-games`をbindし、`/api/*`だけWorkerを先行させる。KV・R2・公開棋譜一覧・アカウント機能は追加しない。
- `migrations/0001_games.sql`：棋譜、受信時刻、本文SHA-256、本文bytes、検証状態を保存する。生IP・User-Agent・アクセスログのカラムはない。
- `contract.ts`：version 1、同意版`game-research-v1`、標準1王ルール、対局モード、初期局面・着手・結果／中断理由、アプリcommit、送信ID、先後の選択AI条件を検査する。未知のfieldを拒否する。
- AI条件のscopeは`selected-at-submission`。**送信時の選択条件であり、途中の設定変更を含む全着手の実行条件を保証しない。** モデルはID・HF版・source・license・形式・backend・package hashのみで、bytes・ローカルpath・tokenを含めない。
- パース済みの検査対象を正規化して保存・hash計算する。raw JSONの重複キーに隠れた、検査されていない本文を残さない。

`received_unverified`は構造を検査して受信した状態で、全手合法・勝敗一致の証明ではない。
研究へ使う場合は外部LinuxのRust全手再生を別に行う。自動学習・HF公開・研究GPUの再開は含めない。

## 上限・保持・障害

- リクエスト本文は実際のstreamを数えて**256KiB**まで。最大**2,048着手**。Content-Lengthの申告だけに依存しない。
- DB triggerで**UTC日次1,000件、保持本文合計100MiB**を同じinsertのトランザクション内で検査する。新しい日には日次件数だけを切り替える。
- 同一ID・同一本文は200で再読取確認。異なる本文の同一IDは409。新規保存は201。重複で件数・容量を増やさない。
- 超過は429、機能OFF・DB障害は503を返す。ゲームを止めず、受信例外・SQL・本文をログや応答へ出さない。
- 受信後30日を目安に保持し、毎時17分のscheduled handlerで30日を超えた行を削除する。受信OFF時も期限削除は動く。削除失敗はhandlerを失敗として記録する。
- 管理者による期限／個別削除は容量の台帳も減らす。日次受入件数は削除で減らさない。

本文の上限はDB全体の上限ではない。index・migration管理・DB管理領域を含む実使用量と、アカウント全体のリクエスト・D1使用量を監視する。
公開前の読取では既存DB合計は5GB未満だったが、他サービスと共有する残枠・日次実績をこのサービス専用とは扱わない。
subscription APIは権限不足で403だったため、**完全無料や追加請求0を検証済みとは説明しない**。プランの変更・R2購入・GPU予算の転用はしていない。
[Workersの制限](https://developers.cloudflare.com/workers/platform/limits/)・[D1の制限](https://developers.cloudflare.com/d1/platform/limits/)・[D1料金](https://developers.cloudflare.com/d1/platform/pricing/)も参照する。

## 配備と管理

専用D1は2026-11-14にAPACで作成し、初回migrationを適用した。既存サービスのDBへ変更しない。
公開は作業ブランチ→PR→必須／関連CI成功→mainの深い検証→GitHub Actionsの通常deployを使う。
初回schemaは所有者のプロジェクト専用ログインで適用済み。今後のschema変更も公開前に対象DBとmigrationを照合して適用する。

```bash
scripts/cf.sh d1 migrations apply voxelshogi-games --remote
scripts/cf.sh d1 execute voxelshogi-games --remote --command 'SELECT count(*) AS records, coalesce(sum(payload_bytes),0) AS payload_bytes FROM games;'
scripts/cf.sh d1 execute voxelshogi-games --remote --command 'SELECT day,daily_count,retained_bytes FROM collection_usage;'
```

複数worktreeでは`--config /absolute/path/to/apps/web/wrangler.jsonc`で対象を明示し、認証はrootの`scripts/cf.sh`を使う。
ローカルCLIのグローバルな別アカウントを使わない。DB名・IDはwrangler設定と照合する。

削除依頼は利用者向け案内どおりGitHub Issueで送信IDを受け取り、本文・個人情報を公開投稿させない。
管理者がIDを検査して対象だけを削除する。例えば下記のplaceholderを**UUID形式を確認した実ID**へ置き換える。入力を無検査でSQLへ連結しない。

```bash
scripts/cf.sh d1 execute voxelshogi-games --remote --command "DELETE FROM games WHERE request_id='REPLACE_WITH_VALIDATED_UUID';"
```

全件のexport・研究用解析が必要になった場合は外部Linuxで扱う。Macへデータセットとして退避せず、取得・二次利用・公開の範囲を先に決める。

## 停止・復旧

新規収集の停止は`GAME_COLLECTION_ENABLED`を`false`にした通常の変更で行う。利用者のON表示が残っても受信側は503となり、ゲームは使える。
同じWorkerを維持すれば、受信OFFでも保持期限の削除は継続する。DBを消すことを通常の停止手順にしない。
静的配信しかない過去versionへrollbackする場合は、期限削除のhandlerもなくなるため、管理者が別途期限削除を実行・記録する。
公開前の失敗では既存サイトの版を確認し、保護を迂回して失敗した候補を配信しない。[配信と復旧](DEPLOYMENT.md)

## 検証の範囲

SQLiteを使った軽量テストでは、保存・再送・競合、同意・Origin・schema・実bytes上限、不正field、日次／容量上限と同時要求、日付切替、期限削除を検証する。
クライアントとUIではOFF時POST 0件、終局1回・明示中断1回、失敗後の固定本文再送、OFF時の中断・破棄、import除外を検証する。
9種類の変異を実際の失敗で検出し復元済み。深いCIの既知変異に追加し、migrationも隔離コピーへ含める。

実D1の初回確認は、**ローカルの受信処理からAPI経由で接続した検証**であり、公開されたCloudflare WorkerのHTTP確認ではない。
合成1件で201、新規と同内容の再送200、同一IDで別内容409、保存後の全本文とSHA一致を確認した。テスト行は削除済み。
[実D1の確認記録](experiments/launch-game-storage-2026-11-14.json)に、対象DB・検査コード／migrationのSHA・確認範囲・削除後0件を保存した。
LinuxのブラウザE2Eは公開設定／POSTの応答を制御してUIを検証する。実WASMによる棋譜の再生も行う。
公開版の実POST・binding・公開commit一致はL6で別に確認し、これらのテストで代用しない。

送信済みの対局の同意欄は固定し、異なる本文を再送しない。終局後のOFFからONへの変更はできず、理由を画面に表示する。送信を始めた後も未完了分はOFFで中止できるが、その対局では再びONにしない。再開は新しい対局で選ぶ。
