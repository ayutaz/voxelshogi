# 最終12 rootの固定metadata slice

元の[Linux検証済みHF固定版](https://huggingface.co/datasets/voxelshogi/voxelshogi-research-screen-v1/tree/fa3728cc6d362ce6b278ec974bfb2dee13b1c363)のconfigから、`holdout_protocol`と`roots`のうち`purpose=holdout`の12件だけを取り出す。
`{"protocol": config["holdout_protocol"], "roots": holdout_roots}`をPythonの`json.dumps(..., indent=2) + "\n"`で保存したbytesのSHAを固定する。

元configのSHAと12入力の保護集合との一致、metadata契約だけを照合した。新しい局面の生成・探索・推論・最終評価は行っていない。
実モデルを選定した後の実Linux評価でも、元の開示済み条件とRustでのroot照合を必要とする。
以下のモデルSHAを指定しない固定sliceを、[manifest組立](../P6_MODEL_PUBLICATION.md#変換からmanifestを組み立てる)へ渡す。

```json
{
  "frozen_at": 1794439842.230377,
  "original_config_sha256": "a35eab4708e2227fe5a4c20d9fca1d6ae78f7f3cc504adee693f8dd1e86068e2",
  "original_source_repo": "voxelshogi/voxelshogi-research-screen-v1",
  "original_hub_commit": "fa3728cc6d362ce6b278ec974bfb2dee13b1c363",
  "original_conditions_sha256": "771407a1e8a7ecf468840448d81fb9dc136ad2a09ed93e75f5e6d1ee85413446",
  "final_protocol_file_sha256": "273ad83a41b191422e1cda4cafdc2a817fb48357d40b78dd35ae4756e482f00b",
  "protocol_sha256": "ef4b2e6b3a9b126b47b241977ab9c39dabb4cd8fdf58c7c4d7d16f05c055a7c6",
  "roots_sha256": "9074c9371aad436bd0e7c921220c5af9ff7ee233754e1552be954c0ffce3f95a",
  "root_count": 12,
  "metadata_only": true,
  "generated_or_evaluated_positions": 0,
  "scope": "Exact slice of original Linux-validated preregistered final12; no positions regenerated, evaluated or selected. Source of expected frozen bytes for later format assembly."
}
```
