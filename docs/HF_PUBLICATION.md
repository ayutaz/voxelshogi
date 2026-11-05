# Hugging Faceの公開・保存ルール

**2026-11-03 16:56:12 UTC・P5-2の終了と停止**：[本条件3世代48対局・HF保存・別VM後続世代](P5_2_COMPLETION.md)の結果を記録した。使用した所有課金資源は0。棋力改善・P5-3・DDP・Phase6は未完了であり、結果共有後に停止する。

2026-10-28ユーザー指定。作成したデータセット・モデルの公開先は[voxelshogi組織](https://huggingface.co/voxelshogi)。Macには必要な検証用モデルだけを残し、データセット・学習checkpointを保存しない。小さいmanifest・hash・集計は実行記録として保持する。

## 作成と公開の契約

- データは`voxelshogi/voxelshogi-synthetic-v1`・`voxelshogi/voxelshogi-search-v1`、最初の学習モデルは`voxelshogi/voxelshogi-transformer-s`を候補名とする。実際の分割・名前は公開planで固定する。
- リポジトリはpublic、取得申請の承認方式はmanual（`private=false`・`gated="manual"`）。公開アップロード前の人による承認を指す用語とは区別する。2026-10-28にユーザーが「ダウンロード申請の手動承認」の意味であると確認した。実repo作成・公開の確認元は[試料の公開記録](M4_HF_PILOT_RELEASE.md)。
- Community（Discussions／Pull Requests）はOFF（`discussionsDisabled=true`）にする。送信前と全件照合後に確認し、通常の認証エラー403をOFFの証拠にしない。
- 対象成果物のライセンスは公開前にユーザーと確定する。コードのApache-2.0、M3未学習モデルの公開許可をM4データ・M6学習モデルへ拡大しない。M4自作合成データv1のCC-BY-4.0は2026-10-28にユーザー承認済み。M6の対象学習済みモデルと別repoの再開状態は2026-10-29にApache-2.0を個別承認済み（[承認記録](../export/m6-approval.json)）。
- 外部Linuxから直接送信し、Macへ中継しない。公開するファイルだけを別stagingへ用意する。READMEのカード、LICENSE、生成元コミット、生成／変換設定、検証記録、データ／重みのSHA-256を保持する。通常のmodel／datasetのstagingへログ・秘密・optimizerのcheckpointを入れない。再開状態は別承認・専用repo・JSON＋safetensorsのprofileに限定する。
- HFに書ける資格情報と`voxelshogi`への作成・設定変更権限を実際の送信元で確かめる。所属だけでは権限を証明しない。初期OAuthの403は、ユーザー指定の`hf auth login --force`と再ログイン後に解消した。[実行記録](M4_HF_PILOT_RELEASE.md)。
- HF CLIの現在の認証、または専用の`.env`の`HF_TOKEN`を公開時だけ外部Linuxの環境／メモリへ渡す。別の保存済み資格情報を無断で列挙・切り替えない。`.env`自体やproviderキーは送らない。
- **送信の継続承認（2026-10-28）**: ユーザーは、承認済みのVoxelShogiのHF公開に必要な認証情報の一時送信とHFへのアップロードを、都度確認せず進めるよう明示した。管理下のVast.ai／CloudRift実機へのHF CLI認証のSSH標準入力による引き渡し、同目的・承認済み予算内の所有実機の置き換え・再接続を含む。トークンは環境／メモリだけで使い、ファイル・引数・履歴・ログへ保存しない。取得申請のmanual gate、成果物ごとのライセンス、予算・宛先・公開設定の検証は継続する。

## Dataset Cardを必ず書く

データセットのroot `README.md`をDataset Cardとし、HFのYAMLにライセンス・config・実際のsplit／パスを記載する。本文は次の4節を空欄なしで用意する。ハーネスは4節の存在と空欄を検査するが、内容の正確さはmanifest・検証結果・データ契約に照らしてレビューする。

| 節 | 記載する内容 |
|---|---|
| `Generation and provenance` | 目的・来歴、ソースcommit、ruleset/schema、seed・探索条件、config別の対局数・行数・重複除外数・教師数、分割、用途と制約 |
| `Usage and schema` | 列の意味・型への参照、読み込み例、重複・無効教師の扱い、固定revisionでの取得 |
| `Verification` | 全件検証・再生成、hash、検証結果への参照、未検証事項 |
| `Access and license` | public/manualとCommunity OFF、取得申請、承認済みライセンス・帰属 |

[試料公開時のカード](M4_DATASET_CARD_DRAFT.md)は[HFの固定版](https://huggingface.co/datasets/voxelshogi/voxelshogi-synthetic-v1/blob/83dd4523817908770dcaf11319243a5405addf26/README.md)と同じ内容。試料を10万局面の本生成や学習済みモデルと呼ばず、config間の重複も明示する。

## スキルとハーネス

作成・公開時は[hf-publicationスキル](../.agents/skills/hf-publication/SKILL.md)を使う。実装は[training/hub_release.py](../training/hub_release.py)。新規作成にも同じ送信先・公開設定・ライセンスの検査を適用する。既存private repoはpublicへ変更しない。manual・Community OFF設定を確認できない場合は、データ・重みを送信しない。

検証済みのreleaseフォルダを**外部Linux上**に用意し、次のようにplanを作る。`license_approved=True`は実際に対象ライセンスの承認がある場合だけ指定する。下記の名前とライセンスはモデル用の例で、M4データの承認を表さない。

```python
import json
from pathlib import Path
from training.hub_release import plan_release

plan = plan_release(
    Path("runs/release/model"),
    repo_id="voxelshogi/voxelshogi-transformer-s",
    repo_type="model",
    license_id="apache-2.0",
    license_approved=True,
    source_commit=source_commit,  # 実際に生成・検証した40桁のcommit
)
Path("runs/release-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
```

planには全ファイルの相対パス・bytes・SHA-256と宛先・形式・ライセンス・生成元コミットを固定する。plan自体にトークンを入れない。ファイルが追加・変更されたら、再検証してplanを作り直す。

```bash
# 外部変更なし
uv run --locked python -m training.hub_release runs/release/model runs/release-plan.json
# 新規repo作成・manual／Community OFF設定の確認だけ。重みはまだ送らない
uv run --locked python -m training.hub_release runs/release/model runs/release-plan.json --create-repo --execute
# アップロードと、固定Hub revisionでの全ファイルhash照合
uv run --locked python -m training.hub_release runs/release/model runs/release-plan.json --execute --receipt runs/release-receipt.json
```

実行に必要な`HF_TOKEN`は送信元プロセスの環境へ渡し、値をコマンド引数やログへ書かない。`HfApi`へ直接渡すトークンは永続ログインしない。検証用ダウンロードのHF cacheも外部ホストに置く。receiptの`verified=true`と不変のHub commit、各SHA-256を確認するまで、転送完了を理由に元データを削除しない。検証失敗時のreceiptは`verified=false`のまま保持し、公開済みファイルを自動削除したり再アップロードを無制限に繰り返したりしない。

## 検証と限界

M6の学習済みモデルと全3形式の参照値は、[専用の推論パッケージprofile](M6_INFERENCE_RELEASE.md)を使う。`artifact_role="inference-package"`でmanifestが列挙した固定入力・全出力だけを追加対象とし、通常profileで任意の`.f32`を許可しない。実学習とライセンス確定・実モデル検証の後、既存の公開／全hash照合を行い、検証済みreceiptから固定revisionのWeb catalog項目を作る。

再開状態は[別承認・専用repoを要求するtraining-state profile](M6_STATE_RELEASE.md)で準備する。通常modelへの混入を許可せず、実送信時には共通ledgerをAPI操作前に予約する。移行前v1は累積1GiB、ユーザー承認後の現行v2は累積2GiBで、旧予約prefixを維持する。M6のoptimizer・乱数を含む承認済みarchiveは[公開・復旧まで完了](M6_COMPLETION.md)。自己対局は別の承認対象・専用repo・selfplay profileを使い、同じ累積ledgerを引き継ぐ。新たな未確定licenseへ許可を拡張しない。

純粋テストは、送信先違い、private/auto、未承認ライセンス、変更されたファイル、Macでの公開、秘密ファイル・symlink・optimizer、未確認のHub gateを拒否し、API変更前に止まることを検証する。記録用fakeで新規repoのpublic設定、manual設定確認後の送信、親commit固定と転送後のhash不一致も確認する。これらを通常Linux CIと既知変異の回帰へ含める。実repoの作成・公開・実権限・実転送の確認は別の実行記録を必要とする。

一次資料：[Hubへのアップロード](https://huggingface.co/docs/huggingface_hub/guides/upload)、[APIのrepo設定](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api#huggingface_hub.HfApi.update_repo_settings)、[モデルのmanual gate](https://huggingface.co/docs/hub/models-gated)、[データのmanual gate](https://huggingface.co/docs/hub/datasets-gated)。

Community設定はSDK未対応のため`PublicationApi`から公式HubのsettingsへPUTし、discussions APIの無効応答を確認する。参考：[HF公式SDKの設定例](https://github.com/huggingface/swift-huggingface/blob/main/README.md#repository-management)、[Community設定の仕様](https://huggingface.co/docs/hub/repositories-settings)。

## 本生成公開の完了（2026-10-29 JST）

[本生成のDataset Card](https://huggingface.co/datasets/voxelshogi/voxelshogi-synthetic-v1/blob/6e7fb29d2469b56a895042fbb089d86e7b4d074f/README.md)は実数・来歴・制約を記載済み。`production-64`を追加し、旧試料を保持した。固定Hub commitの全1,831対象ファイルとCardのhash、public/manual・Community OFF、実機終了・資源解放を[完了記録](M4_COMPLETION.md)へ残した。

## 自己対局の再開状態

[P5-2の専用archive・公開profile](P5_SELFPLAY_STATE.md)を使う。`profile="selfplay"`と`artifact_role="selfplay-training-state"`を明示し、旧M6の契約・repoへ混ぜない。public/manual・Community OFF・カード・固定revision全hash・共通upload ledgerは同じ境界を維持する。本条件3世代48対局の公開・別VMでの後続世代は[P5-2完了記録](P5_2_COMPLETION.md)を参照。コードとfake Hubの成功だけを実運用の証拠にしない。前述のM6公開前の記述は過去の計画で、M6の実公開・復旧は[M6完了記録](M6_COMPLETION.md)を確認する。

## P5-2の保存先と復旧情報

| 内容 | repo | license |
|---|---|---|
| 完成episode・全世代Replay・protocolと系譜 | `voxelshogi/voxelshogi-selfplay-v1`（dataset） | CC-BY-4.0 |
| 世代ごとのモデル・optimizer・乱数・進捗 | `voxelshogi/voxelshogi-transformer-s-selfplay-training-state-v1`（model） | Apache-2.0 |
| 元bytesを保持した全保護入力index | `voxelshogi/voxelshogi-protected-inputs-v1`（dataset） | CC-BY-4.0 |
| typedな集計・全release descriptor・復旧と入力監査 | `voxelshogi/voxelshogi-selfplay-run-reports-v1`（dataset） | CC-BY-4.0 |

各世代の両receipt・bundle/plan・全stateの固定revision・共通upload ledgerを保持してから旧VMを解放する。集計reportはデータや重み、raw log、資格情報を含めず、通常のdataset公開ハーネスで外部Linuxから送る。成功／失敗／不足する証拠を分け、reportの存在だけで本条件完了としない。元VM終了後の別VMでは[復旧手順](P5_SELFPLAY_RELEASE.md)で全ファイル・全Replay・モデルhashを照合し、後続世代を実行する。Datasetのpublished cursor snapshotは、すでに検証した両receiptを反映するための追加snapshotであり、新しい世代ではない。

本条件の実件数・全固定revision・実機IDと限界は[P5-2完了記録](P5_2_COMPLETION.md)。HFのmanual gateは一般利用の取得申請を人が承認する仕組みとして維持し、アップロードの都度承認と取り違えない。

## P5-4の分散学習state

[1／2／4GPU比較](P5_4_PLAN.md)の保存は`profile="distributed"`・`artifact_role="distributed-training-state"`を使う。候補repoは`voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1`（model、Apache-2.0）。public/manual・Community OFFとState Cardの4節を維持する。共有model／optimizerと全rankの乱数・共通進捗をtyped archiveへ入れ、source・入力・global schedule・world size・FP32設定を照合する。

通常modelへの混入を拒否し、M6／自己対局から引き継いだ同じ累積1GiB upload ledgerを使う。過去の予約を減らしたり初期化したりせず、実bytesを予約してから外部Linuxで公開・全hash照合する。このprofileの準備やCPUテストだけでは、実repo公開・GPU保存再開が完了したことにはならない。

**2026-11-05 00:13 UTCの実公開**：[P5-4の全3構成と各GPU保存再開](P5_4_RESULTS.md)で中間／最終の計6 stateと3行の測定datasetを公開し、固定revisionの全bytes・hash・Card・public/manual・Community OFFを照合した。共通ledgerの過去予約は保持し、実機解放も確認済み。先行する1GPU部分結果は別の固定revisionとして残す。

## P6の研究用学習state

[4構造の学習・再開契約](P6_TRAINING_STATE.md)の`profile="research"`／`artifact_role="research-training-state"`を使う。
専用先は`voxelshogi/voxelshogi-research-training-state-v1`（model、Apache-2.0）。全モデル寸法・seed・cache・source・環境を結び付け、latestとval選択bestをtyped archiveとして保存する。
通常モデル／旧Sのstate repoへ代替公開しない。M用artifact上限はこのroleだけに適用し、共通の累積upload ledgerは継承する。
現時点はコード準備であり、実MのGPU保存再開・実repoへの公開を完了した記録ではない。
