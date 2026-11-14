# 対局の自動保存：schema 2

2026-11-14。承認済み[U4](design/ARENA_IMPLEMENTATION_PLAN.md)のAPI先行変更。
このPR時点では旧画面の任意送信を維持し、常時自動送信clientは後続PRで接続する。
schema 1の同意・送信ID・保存済み行を自動保存へ読み替えない。

## 契約と更新

`POST /api/games`は従来のschema 1に加え、schema 2／policy `automatic-game-v2`を受け付ける。
`gameId`は1対局、`requestId`は固定snapshot、`version`は対局内の単調な整数を表す。
`conditionsScope: game-start`と開始時のAI条件、アプリcommit、初期局面、全着手、進行／終局／中断を保存する。
0手・import・履歴閲覧はclientで除外し、APIも0手は受け付けない。未知のfieldを拒否する。

専用`automatic_games`は1対局1行。新versionだけをSQL UPSERTで更新する。
既存の着手列の延長、初期局面・AI条件・モード・アプリcommitの不変を同一transactionのtriggerで確認する。
終局／中断の行は以降更新しない。分岐・AI条件変更は新しいgameIdを使う。
同version・同hashは200、同version・別hashは409、古いversionは保存済みversionを付けた200で無視する。
古い応答や再送は、件数・更新数・容量を増やさない。
正規化した検査済みJSONだけを保持し、SHA-256はそのbytesから計算する。
受信は`received_unverified`。全手合法・勝敗一致の確認や学習・HF公開は別途行う。

## 上限と保持

- 256KiB／2,048着手。streamの実bytesも検査する。
- v1と共通のUTC日次新規1,000対局、保持本文100MiB。更新の容量差分も同一transactionで計上する。
- 1対局で途中snapshotを最大128回保存し、その後の終局／中断を1回許す。
- v2の新規・途中・終局を合わせてUTC日次10,000保存。再送・古いversionを含めない。
- 30日を超える行を旧tableとともに毎時削除する。更新しても保持開始日は延長しない。
- 上限429／障害503。対局は継続し、SQLや棋譜を例外ログへ出さない。

生IP・User-Agent・名前・メール・token・モデル本体・ファイルpathをDBへ追加しない。
利用者向けprivacyはclient移行と同時に更新する。

## 配備と実データの確認

専用D1 `voxelshogi-games`のIDを`apps/web/wrangler.jsonc`と照合してから、
rootの`scripts/cf.sh`で**このPRのconfigを指定して**migrationを先に適用する。
0002は追加tableとtriggerのみ。旧APIと旧clientを変更せず利用できる。

```bash
scripts/cf.sh d1 migrations apply voxelshogi-games --remote --config /absolute/worktree/apps/web/wrangler.jsonc
```

既存の通常PR・必須8件・関連CIを通し、保護を維持して通常mergeする。
新API配信後、自分の合成棋譜だけで新規・延長・同一再送・競合・古い更新・終局固定を実HTTPで確認する。
保存された本文・bytes・hashと台帳の差分を照合し、検証gameIdだけを削除する。
全ユーザー棋譜をMacへ取得しない。証拠には合成テストのID・hash・応答・対象commitだけを残す。
本番確認未実施の段階を完了と記載しない。

管理者の停止は`GAME_COLLECTION_ENABLED=false`。期限削除は継続する。
削除依頼は対局JSONのgameId（旧版はrequestId）を使い、UUIDを検査して該当行だけを削除する。
本文や個人情報を公開Issueへ投稿させない。詳しい旧方式の記録は[保存仕様](GAME_DATA_COLLECTION.md)。
