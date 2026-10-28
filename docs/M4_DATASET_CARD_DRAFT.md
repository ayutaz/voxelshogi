---
license: cc-by-4.0
pretty_name: VoxelShogi Synthetic Pilots v1
size_categories:
- n<1K
tags:
- voxelshogi
- synthetic
- shogi
- game-ai
configs:
- config_name: pilot-16
  default: true
  data_files:
  - split: train
    path:
    - pilot-16/game-000001.parquet
    - pilot-16/game-000002.parquet
    - pilot-16/game-000003.parquet
    - pilot-16/game-000004.parquet
    - pilot-16/game-000005.parquet
  - split: validation
    path:
    - pilot-16/game-000000.parquet
- config_name: representative-64
  data_files:
  - split: train
    path:
    - representative-64/game-000001.parquet
    - representative-64/game-000002.parquet
    - representative-64/game-000003.parquet
    - representative-64/game-000004.parquet
    - representative-64/game-000005.parquet
    - representative-64/game-000006.parquet
    - representative-64/game-000007.parquet
    - representative-64/game-000008.parquet
    - representative-64/game-000009.parquet
    - representative-64/game-000010.parquet
    - representative-64/game-000011.parquet
  - split: validation
    path:
    - representative-64/game-000000.parquet
---
# VoxelShogi Synthetic Pilots v1

Small, reproducible synthetic datasets for research on standard single-king 9x9x9 shogi. These are CPU-search pilot samples, not the planned 100,000-position training release or a trained model. Generated independently by the VoxelShogi Rust engine; no third-party game records are included.

| Configuration | Games / maximum plies | Rows | Nonduplicate positions | Nonduplicate search teachers |
|---|---|---:|---:|---:|
| pilot-16 | 6 / 16 | 102 | 81 | 15 |
| representative-64 | 12 / 64 | 780 | 769 | 252 |

Counts are per configuration. Configurations overlap, and their eligible counts must not be summed as independent positions. The first six representative games also reproduce the 1/2/4-worker comparison, not additional independent samples.

## Generation and provenance

Source commit: a6e31aed1c2cad3614b718276d848c35e83aa461 of https://github.com/ayutaz/voxelshogi . Python 3.14.9 and the source uv.lock were used on CloudRift Linux. Ruleset: voxelshogi-standard-v1; schema: voxelshogi-dataset-v1; seed: 17. Sources random/rules/search have equal game counts. Search limits are depth 2, 10,000 nodes, and table capacity 4,096. Search games use 0 seeded opening plies in pilot-16 and 16 in representative-64; the played opening move may differ from the search recommendation. Generation settings are in each configuration's generation.json and manifest.json.

Every game stays in one split. HF validation corresponds to the row value val. These samples have no test games and are not a full evaluation set. duplicate_of marks positions excluded from training and evaluation; keep the duplicate rows for history replay and filter them for model fitting. random/rules moves are not best-move teachers. teacher_valid and duplicate_of jointly define usable search teachers. Scores are material/terminal search scores, not win probabilities, and limited-depth search is not proof of optimal play. The final position in each truncated game has no teacher.

## Usage and schema

After manual access approval, use datasets.load_dataset('voxelshogi/voxelshogi-synthetic-v1', 'pilot-16', token=True) or select representative-64. Pin the release Hub revision for reproducible use. Rows store VSFEN positions, game/split provenance, move labels and search scores; consult https://github.com/ayutaz/voxelshogi/blob/a6e31aed1c2cad3614b718276d848c35e83aa461/docs/M4_DATA_CONTRACT.md for the exact field types and semantics. Filter duplicate_of and teacher_valid as described above before using search supervision.

## Verification

All histories, legal actions and search teachers were validated through the same Rust rules implementation. Both configurations were fully regenerated and byte-compared, then matched to the historical pilot manifests and every file hash recorded in the GitHub documentation. Each configuration contains the original generation manifest, generation settings and validation report. Root manifest.json indexes these separate configurations; it is not a single generation manifest. The original empty local ownership marker is excluded from public artifacts. validation.json contains the combined release evidence. Process logs, credentials, raw input fixtures and the second generation copies are excluded.

To reproduce, use the pinned source and lockfile on external Linux, construct GenerationConfig from generation.json, call generate_dataset into a new directory and validate_dataset on it. Compare all Parquet and manifest SHA-256 values to the included manifest and validation.json. The generator creates its own empty ownership marker. The marker should not be confused with training data.

## Access and license

Community discussions and pull requests are disabled. This is a public repository with manually approved download requests. Request access on Hugging Face; download after approval. Access requests are not automatically accepted. These synthetic data are licensed under CC-BY-4.0; see LICENSE (https://creativecommons.org/licenses/by/4.0/). Attribution: ayutaz and VoxelShogi contributors, VoxelShogi Synthetic Pilots v1, with the source commit above. Code remains separately licensed Apache-2.0. Future trained models have separate licensing decisions.
