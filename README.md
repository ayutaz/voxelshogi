# VoxelShogi

9×9×9（729マス・372枚）の三次元将棋を題材にした、再現可能な三次元将棋AI研究プラットフォームです（開発中）。

- Rust製ルールエンジン（WebAssembly / Python から共通利用）
- ブラウザで遊べる VoxelShogi Arena（Cloudflare 公開予定）
- エンジンによる合成データセット / Transformer Policy-Value モデル（Hugging Face 公開予定）

ルールは [将棋ったー「三次元将棋」](https://shogitter.com/rule/三次元将棋) に準拠します。詳細は [docs/RULESET.md](docs/RULESET.md) を参照してください。

## ライセンス

Apache License 2.0 — Copyright 2026 ayutaz. 詳細は [LICENSE](LICENSE) と [NOTICE](NOTICE) を参照。
