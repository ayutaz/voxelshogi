# 開発時の必須手順

- 仕様・進捗は [CLAUDE.md](CLAUDE.md)、実行計画は [docs/ROADMAP.md](docs/ROADMAP.md) を読む。
- **変更前に必ず作業ブランチを作成する。main へ直接 commit / push しない。** 既存の作業ブランチでは、その作業の範囲内で続行してよい。
- [CONTRIBUTING.md](CONTRIBUTING.md) に従い、TDD、独立した期待値、変異による検出確認、変更に適したローカル検証を行う。
- push 後は PR を作成し、必須 CI の成功を確認する。失敗・中断・未完了のチェックを無視して取り込まない。保護の無効化や bypass は使わない。
- CI確認時は [.agents/skills/ci-checks/SKILL.md](.agents/skills/ci-checks/SKILL.md) を使う。取得は最短10分間隔とし、CI待ちだけの短いwait/sleepの反復も行わない。
- 人間同士の対局・マルチプレイは実装しない。Python は3.14を基本とし、依存が未対応の場合は3.13を使う。
- Pythonは `uv run` から実行し、ライブラリは `uv add` で管理する。`pyproject.toml` と `uv.lock` を更新し、CIでは `--locked` で検証する。
