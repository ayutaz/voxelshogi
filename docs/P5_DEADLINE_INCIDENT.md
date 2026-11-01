# P5-1の終了遅延と再開前の対策

2026-10-30 UTCの[取得記録](experiments/p5-deadline-incident-2026-10-30.json)。P5-1は未完了であり、新しい有料実機は独立監視の統合・稼働確認まで起動しない。

## 確認した事実

CloudRift実機`e6de287a-d425-11f1-af00-3b87432bf57c`を05:51:06 UTCに要求した。ローカルガードは09:36:06 UTCに終了要求を始め、09:51:06 UTCまでに終了確認する設計だったが、保存された終了要求は17:29:20 UTCだった。17:30:34 UTCにInactive・resources_released=trueを確認し、その後の利用情報取得でも同じ状態を確認した。

公式APIの計上済み利用は41,893.426068秒、取得単価は65セント/時。単価との積は約US$7.56409で、当初の4時間／US$4という試行上限を超えた。これはAPI利用情報からの計算であり、請求書の確定額ではない。料金単位と利用秒数の意味は[公式OpenAPI](https://api.cloudrift.ai/api-docs/openapi.json)のInstanceResourceInfo／InstanceUsageInfoを参照する。

台帳の今回予約をUS$4からUS$8へ増やし、保守的な全体予約額をUS$73／基本枠100、未予約分をUS$27へ修正した。Phase5はUS$12／初期枠20。追加US$100は未使用。過去の試行予約も残しており、予約額を累積実請求やサービス残高とは扱わない。既存のUS$65／69という文書・起動記録は当時の値として保持する。

プロセスの起動時の生存確認だけでは、Macの停止・通信断・実行中断にまたがる期限停止を保証できなかった。今回どの要因で遅れたかは確定していない。OSの電源OFFだけで課金が止まるとも判断しない。

## データと学習コードの現在地

HFの`voxelshogi/voxelshogi-search-v1`、固定revision `1b86f7e83b70a69cdfa3cc0bd4e9b0886623c472`には8対局・35採取局面を退避した。浅い教師35件、深い教師3件。カードとvalidationはcomplete=falseで、教師再計算・正規化入力監査・再生成一致は未完了。学習へ投入しない。Macにはカード・検証metadataだけを取得した。

Replay BufferはPR #90で統合済み。学習・世代更新コードは別ブランチで実装中で、Linuxの数値確認と小さいSモデル2世代の停止再開試験まで行った。この試験は別VM・HF復旧・本条件の学習ではなく、Phase5の完了条件を満たしていない。

## 独立監視

新しい`.github/workflows/gpu-deadline.yml`は手動実行・main限定・専用`gpu-control` environmentに限定する。APIキーはそのenvironmentのSecretと監視stepの環境変数だけで使い、GPUへ送らず、artifactを作らない。environmentのdeployment branch policyもmainだけに設定する。PR、fork、Dependabotから呼ばない。

1. レンタル前に、新しい正確なtagと絶対期限を指定して監視workflowをmainから起動する。過去に使ったtagや4時間を超える期限は拒否する。
2. Arm stepでCloudRiftへの接続と当該tagの未使用を確認する。runner待ち・setup中のrunは準備完了としない。
3. レンタルCLIに`--guard-run RUN_ID`を渡す。GitHub APIで実際のmain workflow・実行中job・Arm成功・監視step実行中・同じtagと期限を確認する。ローカルに保存したready記録だけでは許可しない。
4. ローカル期限は独立監視の期限より60秒以上早くし、独立監視は絶対期限の20分前から終了APIを呼ぶ。通常は60秒ごとに所有実機を確認し、通信失敗や資源未解放を成功にしない。観測済み実機が一覧から欠けた場合も終了確認としない。
5. ローカルガードも残す。独立監視が早期終了・失敗・中断した場合は直ちに所有実機を調べ、必要なら終了する。稼働中監視の取消や上書きdispatchをしない。

この方式はMacへの依存を減らす二重監視であり、provider自身が強制するリース期限ではない。GitHub／providerの障害、取消、認証失効による遅延の可能性は残る。新しいコードのCI成功だけを実機での費用上限達成とは呼ばない。通常CIの状態再取得は最短10分間隔を維持する。レンタル前の稼働確認はその確認とまとめ、同じrunを短時間で再取得しない。

## 再開の順番

- この修正のPR・必須8チェックと関連CIを確認して通常mergeする。
- main限定environmentとSecretを設定し、無料の空tag監視で公式API接続・独立runner・終了を確認する。
- 単価・在庫・台帳・残り時間をそろえた少量実機試行で、Macからの監視を使わず、独立runnerの終了API・利用時間・資源解放を確認する。成功前に長い生成を再開しない。
- P5-1のHF退避を外部Linuxで取得し、全ファイル照合・監査・再計算・再生成を完了する。教師不足なら結果を保持し、新configの採否基準を実行前に固定する。
- P5-2の複数世代・HF退避・別実機復旧、P5-3の世代比較、P5-4の実1→2→4GPU、Phase6の複数構造・複数seed・変換・ブラウザ公開を順に進める。

## 操作例

下記は統合・environment設定後の例。`gpu-control`をmainだけに制限してから、専用environment SecretへCLOUDRIFT_API_KEYを登録する。キーをCLI引数・workflow input・ログへ入れない。

```bash
# Pythonはリポジトリ指定版。30分〜4時間先の絶対期限を作る。
guard_end_at=$(uv run --locked --no-sync python -c 'import time; print(int(time.time()) + 14400)')
rental_tag='voxelshogi-phase5-REPLACE_WITH_FRESH_LOWERCASE_TAG'
gh workflow run gpu-deadline.yml --ref main -f tag="$rental_tag" -f maximum_end_at="$guard_end_at"
# 次の状態取得はci-checksの最短10分間隔を守る。
# Arm成功・Guard CloudRift deadline実行中を確認した実run IDをrentへ渡す。
```

現在の実装はCloudRift単一GPUの研究用レンタルを対象にする。Vast.aiや複数GPUへ切り替える際は同じ独立停止要件を満たす拡張と試行を先に行い、旧M4／M6コントローラで回避しない。

## この修正の検証

新規7件とレンタル連携3件の失敗を実装前に確認し、その後は関連77テストが成功した。GitHub実run／job取得とHTTP秘匿の追加回帰も含む。独立監視15変異は実際のテスト失敗で検出し、通常CIの既知変異へ追加した。Ruff・actionlint・差分の空白確認も成功。これはfake providerと制御metadataの検証であり、独立runnerによる実API接続・有料実機の終了試験はまだ未実施。

## 2026-10-31 UTCの追記

[所有12実機の再確認](experiments/p5-resource-recheck-2026-10-31.json)ではすべてInactive・resources_released=true。計上済み利用秒数と取得単価の計算合計は約US$21.03で、請求書の確定額ではない。今回以外の既知レンタルに元の予約上限を超える計算額はなく、保守的予約US$73を維持する。

ユーザーがGitHubへのCloudRift APIキー保存を明示承認した。[専用environmentの設定記録](experiments/p5-gpu-control-environment-2026-10-31.json)のとおり、custom branch policyをmainのbranch 1件に限定してから環境Secretを保存した。キー値は記録しない。main統合後の無料接続試験と有料実機の独立終了試験は未実施。

PR #91の最初のLinux CIでは全713テストは成功したが、research-time-cap変異が生存した。独立ガードの残り時間検査が既存の計画上限検査の欠落を隠していたため、計画の4時間制約をread_planで直接検査するように直し、当該変異の検出を確認した。終了APIを呼んだ時刻と所有IDを、資格情報を含まないJSONとして監視ログへ残す検査も追加した。最新mainとの統合後、既知変異は全297件。

## 終了監視の優先順と作成直前の再検査

初期の独立監視は期限15分前、Mac側はそれより1分早い終了要求になっていた。有料試験でGitHub側の独立動作を確認できるよう、GitHub側を期限20分前、Mac側を予備の15分前へ変更する。ローカルの絶対上限はGitHubの絶対期限より60秒以上早いまま維持する。先に動くGitHub側に合わせ、実行予定時間に20分＋60秒の余裕を要求する。

また、providerの在庫・所有確認を待った時間だけ絶対期限が後ろへ動く問題と、待機・休止から復帰した制御プロセスが古い監視確認でレンタルを作る問題を、時刻を進める4つのテストで再現した。在庫確認後に時刻を取り直してquoteを更新し、費用予約前と有料作成APIの直前に残り時間を再検査する。後者で失敗した場合の予約は監査のため残し、同じ識別子で盲目的に再作成しない。

[無料接続試験](experiments/p5-independent-guard-connection-2026-11-01.json)では、mainの専用workflowでArm成功・監視step実行中を確認し、対象tagに実機がないことを確認した。これは接続の実証であり、有料実機をMacに依存せず期限終了した証拠ではない。初期runは実機を作らず、古い15分設定のまま正常終了した。修正版は新しいtag・監視runで試行する。

今回の5件は実装前に失敗し、関連するCloudRift／Vast・M6・研究用の129テストが成功した。新規4変異と影響する既存3変異の検出を確認し、archive統合後は全311既知変異をCIへ含める。実機の強制終了やprovider障害を含む厳密な課金上限は引き続き主張しない。

独立監視の絶対期限がジョブの予算時間を超える組み合わせも、実機作成前に拒否する。たとえば1時間の予約に残り4時間の監視を渡す設定を許可しない。新しい試験も最大1時間／予約US$1とし、その時間内に監視の絶対期限を結び付ける。

自己対局archive統合後の関連168テストも成功した。
