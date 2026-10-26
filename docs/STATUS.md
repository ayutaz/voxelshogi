# 現在の状態と文書の案内

確認: **2026-10-26（JST）**。公開アセットの取得時刻は下記JSONに記録。本更新を始めたmainと公開版は `2405e86a0313d4b454119bd472937f2e10622bf5`。以下はこの版を照合した記録であり、以後の文書PRによる配信SHAとは区別する。現在配信される版は公開 `build-info.json` と対応するmain CIを確認する。

## 完了したものと次の作業

| 対象 | 状態・根拠 |
|---|---|
| Phase 0〜2、M0 | 調査・標準ルール・Web Alpha・CI/CDを完了。[M0記録](M0_VALIDATION.md) |
| R0 | 9王3ルール＋標準対照など1,052局を比較し、400／800手の代表6棋譜を公開。正式な9王採用と観戦者の好みの評価は保留。[結果](NINE_KINGS_EXPERIMENT.md) |
| M1 | 標準1王の全幅αβ、評価、反復深化・手の並べ替え・履歴を区別する置換表、深さ／ノード／時間上限を完了。[PR #10](https://github.com/ayutaz/voxelshogi/pull/10)・[#11](https://github.com/ayutaz/voxelshogi/pull/11)、[検証・計測](M1_VALIDATION.md) |
| 現在の公開画面 | 通常画面はランダムAI対局・観戦。比較室はCPUで生成した固定棋譜を再生。M1のブラウザ内ライブ探索、Worker、学習モデルは未実装 |
| 次の実装 | **M2：探索AI同士のWeb観戦**。[具体的な実装順・TDD・完了条件](M2_PLAN.md) |
| M3〜M6 | 未着手。モデル推論の先行検証→Python／データ生成→小型モデルの学習・配信。M5の実棋譜互換性は独立して挿入できる。[フェーズごとの目的・ゴール](ROADMAP.md) |

主用途はAI同士を見て眺める観戦と、そのためのモデル研究。人間対AIは補助機能、人間同士の対局・マルチプレイは対象外。Pythonは3.14系を基本、依存が未対応の場合だけ3.13系とする。モデルをFP16化・量子化した場合も、公開する実行可能版を選択して試せることと、評価した配布ファイルとのSHA-256一致をM3・M6で検証する。

## 実装・公開・品質の確認元

| 項目 | 今回照合した値・一次資料 |
|---|---|
| 固定ツール | Rust1.97.1／MSRV1.85、Node24.22.1、pnpm10.32.1、Python3.14.9、wasm-bindgen/CLI0.2.129。設定ファイルとlockfileを正とする |
| テスト | Rust150件、Web36件、CI制御Node46件、既知変異21件、実ブラウザE2E9件。Rust/Web/Nodeは文書照合時にも再実行して成功 |
| M1全体変異 | 1,172＝1,075 caught＋89 unviable＋8 reviewed equivalent。欠落・重複・未知の生き残り・timeoutなし。[対象SHAと全分割](experiments/m1-mutations.json) |
| main CI・本番公開 | [CI 40318499296](https://github.com/ayutaz/voxelshogi/actions/runs/40318499296) の通常検証・deploy・配信SHA・公開E2Eが成功 |
| セキュリティ | [Security 40318499415](https://github.com/ayutaz/voxelshogi/actions/runs/40318499415) のCodeQL 3言語が成功。今回確認した未解決CodeQL警告は0件 |
| PR運用 | APIでruleset25816100がactive、必須7チェック（Actions app15368）・strict、CodeQL error/high以上を確認。他者承認0、bypassなし、force push・削除禁止。repoで許可するmerge方式はsquashだけ。設定は [.github/main-ruleset.json](../.github/main-ruleset.json)、運用は [CONTRIBUTING](../CONTRIBUTING.md) |
| 認証の配置・報告経路 | APIでproductionの許可元mainのみ、repository Secrets0件、production Secretsは既存の2名を確認。秘密値は取得していない。Secret scanning・push protection・Dependabot security updates・private vulnerability reportingが有効 |
| 未取り込み依存更新 | [Dependabot PR #1](https://github.com/ayutaz/voxelshogi/pull/1) はopen。mainに採用済みとは扱わず、本更新で依存を変更しない |
| 配信 | WorkerスクリプトなしのStatic Assets。COOP/COEP・R2・NN runtimeは未導入。公開SHA、JS/WASMのサイズ・hash、2 manifestと全6棋譜の照合は [取得記録](experiments/documentation-baseline-2026-10-26.json) |

M1のNative単独計測はApple M1・8 GiB、初期局面の深さ2が約0.33秒、1秒予算で3回とも深さ2を完了。R0の幅制限探索・ブラウザ・GPU学習の速度へ一律換算しない。M2で実機のWASM/Workerを測り、M4で生成対象のpilot、M6で学習速度を測る。

## 文書の役割と更新範囲

| 文書 | 用途・今回の扱い |
|---|---|
| [README](../README.md)、[CLAUDE](../CLAUDE.md) | 入口・開発時の現在地。M1完了、次のM2、固定ツールとコマンドへそろえる |
| [PROJECT_SPEC](PROJECT_SPEC.md)、[ROADMAP](ROADMAP.md) | プロジェクト要件、各Phase／Mの目的・ゴール・依存関係・ユーザー準備の正 |
| [M1_PLAN](M1_PLAN.md)、[M1_VALIDATION](M1_VALIDATION.md) | 完了したM1の実装契約と固定した検証記録。[M2_PLAN](M2_PLAN.md) が次の作業手順 |
| [GAME_ENGINE](GAME_ENGINE.md)、[RULESET](RULESET.md) | 実装済みAPIとルールの正。予定のAPIを現行APIとして記載しない。MaxPlies等のメタデータ再保存の制約も明記。M5互換性は未実施 |
| [CI_CD_PLAN](CI_CD_PLAN.md)、[DEPLOYMENT](DEPLOYMENT.md) | 現行のCI・main保護・認証の配置・配信・復旧手順。過去のrunは固定記録として保持 |
| [ARCHITECTURE_DECISIONS](ARCHITECTURE_DECISIONS.md) | ADR-001〜017は当時の判断。後続ADR・現在の仕様を優先し、過去の経緯を現在の未実装事項と混同しない |
| [M0_VALIDATION](M0_VALIDATION.md)、[NINE_KINGS_EXPERIMENT](NINE_KINGS_EXPERIMENT.md) | M0／R0完了時の歴史的記録。旧テスト数・生成コミット・実測値を保持し、現在地への案内を更新 |
| [RULE_VARIANTS_RESEARCH](RULE_VARIANTS_RESEARCH.md) | ルールの先行調査と未実施の継続評価。標準のM1完了と9王への未適用を区別 |
| [RESEARCH](RESEARCH.md)、[RELATED_WORK](RELATED_WORK.md) | 外部資料の調査記録と将来の研究候補。Gumbel・モデル構造・DDPを実装済み／確定採用と扱わない |
| [TECH_STACK_RESEARCH](TECH_STACK_RESEARCH.md)、[COST_ESTIMATE](COST_ESTIMATE.md) | 固定済み構成と公開実測を更新。初回の外部版・GPU相場・為替・ドメイン価格は取得日付き参考値で、採用／課金時に再取得する |
| [AGENTS](../AGENTS.md)、[CONTRIBUTING](../CONTRIBUTING.md)、[SECURITY](../SECURITY.md)、[PRテンプレート](../.github/pull_request_template.md)、[ci-checks](../.agents/skills/ci-checks/SKILL.md) | ブランチ・TDD・PR・秘密情報・最短10分間隔のCI確認という現行方針と整合を確認。追加の承認フローや人間同士の対局は導入しない |

外部資料は記載の取得日に対する記録であり、全リンク先の最新版や将来の採用版を保証しない。現在の実装・固定版と、M3以降で評価する候補を分けて読む。GPU費の初期予算例は支出の承認ではない。M2までの作業にユーザー側の追加準備はなく、モデル／データのライセンスや有料GPUはROADMAP記載の時点で確定する。

文書の更新時はコード・設定・実行結果を照合し、ローカルリンク／アンカー、掲載API例とコマンド、数値の出典を確認する。本更新も通常PRの必須7チェック成功後に取り込み、mainの自動公開を確認する。
