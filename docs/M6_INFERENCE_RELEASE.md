# 学習済み推論パッケージのHF公開

[HF公開ハーネス](HF_PUBLICATION.md)に`artifact_role="inference-package"`を追加する。対象はM6のval選択・固定評価済みの重みから作った3形式と同形式の照合データ。通常のmodel／datasetの許可範囲は広げず、任意の`.f32`やoptimizerを追加可能にはしない。**実データ監査と少量CUDA試行は[M6-2で確認済み](M6_TRIAL.md)。本学習・最終評価・学習済み推論パッケージ公開は未実施。** [費用・ライセンス・再開状態公開の方針](M6_RUN_PROPOSAL.md)は2026-10-29に個別承認済み。

## 目的と範囲

HFのmanual取得承認を受けた利用者が、公開デモで同じONNXと参照値を読み込めるようにする。単独の重みだけを公開し、数値照合に必要な入力／出力が欠ける状態を防ぐ。モデル本体、形式、評価記録とcatalogのhashをつなぐ。

ハーネスは純粋なmetadataとファイルhashの検査を行う。実モデルの実行可能性、tensorのshape・数値一致、各変換版の精度・棋力・実機速度は、[生成・評価](M6_EXPORT.md)と[Web検証](M6_ARENA.md)で別に確認する。小さいopaque fileの単体テストを、学習や推論の証拠にしない。

## 送信できるもの

manifestの生成元commit・clean source・承認済みライセンスと、選択済み学習のreceipt・36,894件の教師母数・固定60局評価の来歴を検査する。`ciFixture`を持つ合成CI用manifestは拒否する。Model Cardには`Training and provenance`、`Evaluation`、`Inference`、`Access and license`の4節が必要。記載内容は実測と照合してレビューする。

| ファイル | 検査 |
|---|---|
| `README.md`、`LICENSE`、任意の`NOTICE` | 各1 MiB以下。カードのYAML licenseと承認したlicenseが一致 |
| `manifest.json` | 1 MiB以下。固定した学習・評価来歴と承認したsource／licenseが一致 |
| `model.safetensors` | val選択後に評価したcheckpointと同じbytes／SHA-256 |
| `fp32.onnx`、`fp16.onnx`、`int8.onnx` | 全3形式が必要。manifestのbytes／SHA-256が一致 |
| `inputs/<fixture>.f32` | 固定4局面の全入力。manifestのbytes／SHA-256が一致 |
| `reference/<precision>/<fixture>-{policy,value}.f32` | 全3形式×4局面×2出力が必要。同形式のdescriptorと一致 |
| `evaluation.json`、`test.json` | 変換manifestのtrainingに固定された評価reportのSHA-256と一致 |

NOTICEなしで37ファイル。固定の相対パス以外、隠しファイル、symlink、余分なJSONやoptimizerは拒否する。最大1ファイル64 MiB（evaluation.jsonは16 MiB）、全体512 MiBとし、既知のsize違いはhashを読む前に止める。通常の公開profileによる再開archiveの拒否も維持する。再開状態用の別の公開方針・実装とは区別する。

## 外部Linuxでの実行

生成・変換の検証済みフォルダーへ元の`evaluation.json`・`test.json`と完成したCard／LICENSEをコピーする。Macへモデルや評価データを中継しない。以下の`license_approved=True`は、2026-10-29に個別承認されたM6対象モデルのApache-2.0に基づく（[承認記録](../export/m6-approval.json)）。既存のM3許可の流用ではない。

```python
from training.hub_release import plan_release

plan = plan_release(
    folder,
    repo_id="voxelshogi/voxelshogi-transformer-s",
    repo_type="model",
    artifact_role="inference-package",
    license_id=approved_license,
    license_approved=True,
    source_commit=source_commit,
)
```

planを保存した後のdry-run、repo作成・public/manual・Community OFF設定、アップロード、固定Hub commitでの全hash照合は、既存の`python -m training.hub_release`の手順をそのまま使う。再検査でも同じroleを適用し、変更されたファイルはAPI操作前に止める。CI内で実repoを作成・公開しない。

全件照合後の`verified=true`、`community_disabled=true`、`dry_run=false`のreceiptから、次の関数でcatalogの1項目を作れる。未検証のアップロードreceipt、浮動revision、宛先・planのhash違い、照合後のローカル変更は拒否する。

```python
from training.inference_release import catalog_release

entry = catalog_release(folder, plan, verified_receipt)
```

返されたentryはmodel ID・manifest hash・Card／LICENSEのhashと、照合した40桁のHF revisionを持つ。公開catalogへの登録はレビュー付きPRで行い、実際の配布物を使ったE2Eと配信hash照合を通す。entryの生成だけでは公開デモの完了にしない。

## 検証

Macではモデルを実行せず、opaque fileによる公開profileと従来の公開／再開archive拒否を含む42テストが成功。追加8変異は実行済みassertionで検出した。全Python検証と既存の学習111＋追加8＝119変異はLinux CIで確認する。実HF公開・外部Linuxでのhash照合は実モデルの準備後に別途行う。
