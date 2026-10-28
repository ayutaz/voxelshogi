# Hugging Faceの公開・保存ルール

2026-10-28ユーザー指定。作成したデータセット・モデルの公開先は[voxelshogi組織](https://huggingface.co/voxelshogi)。Macには必要な検証用モデルだけを残し、データセット・学習checkpointを保存しない。小さいmanifest・hash・集計は実行記録として保持する。

## 作成と公開の契約

- データは`voxelshogi/voxelshogi-synthetic-v1`・`voxelshogi/voxelshogi-search-v1`、最初の学習モデルは`voxelshogi/voxelshogi-transformer-s`を候補名とする。実際の分割・名前は公開planで固定する。
- リポジトリはpublic、取得申請の承認方式はmanual（`private=false`・`gated="manual"`）。公開アップロード前の人による承認を指す用語とは区別する。2026-10-28にユーザーが「ダウンロード申請の手動承認」の意味であると確認した。実repo作成・公開の確認元は[試料の公開記録](M4_HF_PILOT_RELEASE.md)。
- Community（Discussions／Pull Requests）はOFF（`discussionsDisabled=true`）にする。送信前と全件照合後に確認し、通常の認証エラー403をOFFの証拠にしない。
- 対象成果物のライセンスは公開前にユーザーと確定する。コードのApache-2.0、M3未学習モデルの公開許可をM4データ・M6学習モデルへ拡大しない。M4自作合成データv1のCC-BY-4.0は2026-10-28にユーザー承認済み。M6学習モデルは別途確認する。
- 外部Linuxから直接送信し、Macへ中継しない。公開するファイルだけを別stagingへ用意する。READMEのカード、LICENSE、生成元コミット、生成／変換設定、検証記録、データ／重みのSHA-256を保持する。ログ・秘密・optimizerのcheckpointをstagingへ入れない。
- HFに書ける資格情報と`voxelshogi`への作成・設定変更権限を実際の送信元で確かめる。所属だけでは権限を証明しない。初期OAuthの403は、ユーザー指定の`hf auth login --force`と再ログイン後に解消した。[実行記録](M4_HF_PILOT_RELEASE.md)。
- HF CLIの現在の認証、または専用の`.env`の`HF_TOKEN`を公開時だけ外部Linuxの環境／メモリへ渡す。別の保存済み資格情報を無断で列挙・切り替えない。`.env`自体やproviderキーは送らない。

## Dataset Cardを必ず書く

データセットのroot `README.md`をDataset Cardとし、HFのYAMLにライセンス・config・実際のsplit／パスを記載する。本文は次の4節を空欄なしで用意する。ハーネスは4節の存在と空欄を検査するが、内容の正確さはmanifest・検証結果・データ契約に照らしてレビューする。

| 節 | 記載する内容 |
|---|---|
| `Generation and provenance` | 目的・来歴、ソースcommit、ruleset/schema、seed・探索条件、config別の対局数・行数・重複除外数・教師数、分割、用途と制約 |
| `Usage and schema` | 列の意味・型への参照、読み込み例、重複・無効教師の扱い、固定revisionでの取得 |
| `Verification` | 全件検証・再生成、hash、検証結果への参照、未検証事項 |
| `Access and license` | public/manualとCommunity OFF、取得申請、承認済みライセンス・帰属 |

[今回の公開カード](M4_DATASET_CARD_DRAFT.md)は[HFの固定版](https://huggingface.co/datasets/voxelshogi/voxelshogi-synthetic-v1/blob/83dd4523817908770dcaf11319243a5405addf26/README.md)と同じ内容。試料を10万局面の本生成や学習済みモデルと呼ばず、config間の重複も明示する。

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

純粋テストは、送信先違い、private/auto、未承認ライセンス、変更されたファイル、Macでの公開、秘密ファイル・symlink・optimizer、未確認のHub gateを拒否し、API変更前に止まることを検証する。記録用fakeで新規repoのpublic設定、manual設定確認後の送信、親commit固定と転送後のhash不一致も確認する。これらを通常Linux CIと既知変異の回帰へ含める。実repoの作成・公開・実権限・実転送の確認は別の実行記録を必要とする。

一次資料：[Hubへのアップロード](https://huggingface.co/docs/huggingface_hub/guides/upload)、[APIのrepo設定](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api#huggingface_hub.HfApi.update_repo_settings)、[モデルのmanual gate](https://huggingface.co/docs/hub/models-gated)、[データのmanual gate](https://huggingface.co/docs/hub/datasets-gated)。

Community設定はSDK未対応のため`PublicationApi`から公式HubのsettingsへPUTし、discussions APIの無効応答を確認する。参考：[HF公式SDKの設定例](https://github.com/huggingface/swift-huggingface/blob/main/README.md#repository-management)、[Community設定の仕様](https://huggingface.co/docs/hub/repositories-settings)。
