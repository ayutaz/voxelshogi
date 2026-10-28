# Hugging Faceの公開・保存ルール

2026-10-28ユーザー指定。作成したデータセット・モデルの公開先は[voxelshogi組織](https://huggingface.co/voxelshogi)。Macには必要な検証用モデルだけを残し、データセット・学習checkpointを保存しない。小さいmanifest・hash・集計は実行記録として保持する。

## 作成と公開の契約

- データは`voxelshogi/voxelshogi-synthetic-v1`・`voxelshogi/voxelshogi-search-v1`、最初の学習モデルは`voxelshogi/voxelshogi-transformer-s`を候補名とする。実際の分割・名前は公開planで固定する。
- リポジトリはpublic、取得申請の承認方式はmanual（`private=false`・`gated="manual"`）。公開アップロード前の人による承認を指す用語とは区別する。2026-10-28にユーザーが「ダウンロード申請の手動承認」の意味であると確認した。実repo作成・公開はまだ行っていない。
- 対象成果物のライセンスは公開前にユーザーと確定する。コードのApache-2.0、M3未学習モデルの公開許可をM4データ・M6学習モデルへ拡大しない。公開先と保存方針の指定は確認済みだが、ライセンスは未確定。
- 外部Linuxから直接送信し、Macへ中継しない。公開するファイルだけを別stagingへ用意する。READMEのカード、LICENSE、生成元コミット、生成／変換設定、検証記録、データ／重みのSHA-256を保持する。ログ・秘密・optimizerのcheckpointをstagingへ入れない。
- HFに書ける資格情報と`voxelshogi`への権限を実際の送信元で確かめる。2026-10-28に接続済みHFツールとローカル認証の両方で`ayousanz`の組織所属を確認したが、外部Linuxでも同アカウントの認証と候補dataset repoが未作成であることを確認した。ただしAPIで組織roleは返らず、所属だけでは作成・設定変更権限の証明とはしない。

## スキルとハーネス

作成・公開時は[hf-publicationスキル](../.agents/skills/hf-publication/SKILL.md)を使う。実装は[training/hub_release.py](../training/hub_release.py)。新規作成にも同じ送信先・公開設定・ライセンスの検査を適用する。既存private repoはpublicへ変更しない。manual設定を読み取り確認できない場合は、データ・重みを送信しない。

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
# 新規repo作成・manual設定の確認だけ。重みはまだ送らない
uv run --locked python -m training.hub_release runs/release/model runs/release-plan.json --create-repo --execute
# アップロードと、固定Hub revisionでの全ファイルhash照合
uv run --locked python -m training.hub_release runs/release/model runs/release-plan.json --execute --receipt runs/release-receipt.json
```

実行に必要な`HF_TOKEN`は送信元プロセスの環境へ渡し、値をコマンド引数やログへ書かない。`HfApi`へ直接渡すトークンは永続ログインしない。検証用ダウンロードのHF cacheも外部ホストに置く。receiptの`verified=true`と不変のHub commit、各SHA-256を確認するまで、転送完了を理由に元データを削除しない。検証失敗時のreceiptは`verified=false`のまま保持し、公開済みファイルを自動削除したり再アップロードを無制限に繰り返したりしない。

## 検証と限界

純粋テストは、送信先違い、private/auto、未承認ライセンス、変更されたファイル、Macでの公開、秘密ファイル・symlink・optimizer、未確認のHub gateを拒否し、API変更前に止まることを検証する。記録用fakeで新規repoのpublic設定、manual設定確認後の送信、親commit固定と転送後のhash不一致も確認する。これらを通常Linux CIと既知変異の回帰へ含める。実repoの作成・公開・実権限・実転送の確認は別の実行記録を必要とする。

一次資料：[Hubへのアップロード](https://huggingface.co/docs/huggingface_hub/guides/upload)、[APIのrepo設定](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api#huggingface_hub.HfApi.update_repo_settings)、[モデルのmanual gate](https://huggingface.co/docs/hub/models-gated)、[データのmanual gate](https://huggingface.co/docs/hub/datasets-gated)。
