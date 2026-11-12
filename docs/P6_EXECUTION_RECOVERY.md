# P6ブラウザ実行の通信復旧と早期解放

**2026-11-12・一時停止**：既存Sの公開デモと、Mの少量2 run・48局評価を現段階の成果とする。
本比較12 run・MのWeb配布・観戦表示2案／実端末各60分は未完了のまま停止する。
追加GPU・生成・学習を自動再開しない。[停止時点の結果と固定HF版](RESEARCH_CHECKPOINT_20261112.md)を現在の確認元とし、
以下の旧「現在」「次」「予算」は対象時点の記録、実行コマンドは再開後の手順として読む。

2026-11-12 JST。[再開計画](P6_RESUMPTION_PLAN.md)のAに対応する実装。
コードとfake port検証の追加であり、実ブラウザ8ケース・実M学習・GPU解放の再実測は未完了。

## 実行ソースをGitで固定する

前回`runs/p6`にあったコードを、以下へ移して次の実行で使う。
`runs/`は入力の固定plan、receipt、owner、期限、ログと小さい成果記録の置き場として維持する。

| Git管理するsource | 制御フォルダ／外部Linuxでの配置 |
|---|---|
| `infrastructure/research/bootstrap.sh` | source SHAのplaceholderを置換して`bootstrap.sh`へ固定 |
| `infrastructure/research/browser_control.py` | controller本体。`control_operator_sha256`で同じsourceを照合 |
| `infrastructure/research/browser_worker.py` | 外部Linuxの`runs/p6/research-browser/worker.py` |
| `infrastructure/research/corpus_worker.py` | その配下の`corpus/worker.py` |
| `infrastructure/research/corpus_inspect.py` | `corpus/inspect-corpus.py` |

凍結時はこれらのGit管理ファイルからコピーし、古い`runs/p6/*-template`の実装を代わりに使わない。
各ファイルのSHA-256をworkloadへ含め、source commit、owner、見積もり、絶対期限も固定する。
固定17ファイルの実M入力、3つのデータ入力のplan／receiptとlicenseは、従来の公開ハーネスで照合する。
ホストは実装・関連CI・入力・費用と独立監視がそろってから作成し、旧制御フォルダや期限を再利用しない。

controllerは既存実機のAPI account、instance ID、完全な一覧、owner label、SSH先、clean sourceを確認する。
HF認証は承認済みのSSH標準入力で外部Linuxのメモリだけへ渡し、引数やログに含めない。
モデル・データ・checkpointをMacへ中継しない。

## HFの復旧範囲

`training.hub_recovery.RecoveryApi`をbrowser／corpus両workerの実際のHF接続へ接続した。
利用するHTTP例外は固定SDKの`httpx2.TransportError`と狭いtransport例外で、HTTP拒否やメタデータ不正を成功へ変えない。
`httpx2==2.16.0`は既存lock内の依存で、今回root／CUDAの直接依存へ明記した。モデル依存の版は変えない。

- `whoami`・repo存在／情報・Community状態の読取りだけを最大3回、待ち2秒／4秒で再試行する。
  固定の転送期限と停止要求を操作の前後で確認し、期限を超える待ちは行わない。
- repo作成、manual gate設定、Community OFF設定の応答が失われた場合は、適用済みか読み戻す。
  結果を確認できない書込みをそのまま再送しない。既存private repoの公開切替は既存ハーネスが拒否する。
- uploadのタイムアウトを自動再送しない。publication-attemptと固定receiptから照合する後続の復旧が必要。
- 各操作名と試行番号を記録する。例外本文、URL引数、headers、tokenやSDKのaccount payloadを診断記録へ含めない。
  アカウント`ayousanz`と`voxelshogi`所属を確認する前に、workerの公開APIを有効化しない。

deadlineは個々のSDK呼出しを途中で強制中断する仕組みではない。
SDK／HTTPのtimeout、所有プロセスの監視、独立ホスト停止期限を併用する。
公開の宛先・license・public/manual・Community OFF・全ファイルhashの検証は従来の`hub_release`を使う。

## 終了後の解放

controllerの`start-worker`は起動済みPIDと生成時刻を保存し、独立したcontrol側の`watch`も起動する。
適切な薄いcontrol環境からmodule経路を使う。

```bash
uv run --locked --no-sync python -m infrastructure.research.browser_control research-browser3-control start-worker
```

`research-browser3-control`は新しい凍結済み制御フォルダの例で、上記はレンタルを作成しない。
実際の番号は新しいowner tagに合わせる。`start-worker`を再送せず、起動済みmarkerと実PIDを照合する。

`training.research_retirement.watch_browser`が次を順に行う。

1. 約60秒間隔で実PID・生成時刻・sourceと状態を観測する。PID再利用を別workerの終了と誤認しない。
2. process終了と`worker-finished.json`を両方確認し、小さい記録をcontrollerへ回収する。
3. 成功時は同じsourceのcompleteと固定HF版の照合済みreceiptを保持する。
   失敗時は診断記録を保持し、成功とは扱わない。この解放経路は再現可能なoperator測定専用で、未退避の学習checkpointへ流用しない。
4. 保持できたことを記録してから、既存の所有確認付き`Phase6VastRental.terminate`を一度呼ぶ。
   providerの破棄承認と一覧からの消滅がそろって初めて資源解放済みにする。

稼働中・記録回収失敗・PID／source不一致を終了成功へ読み替えない。
削除結果が不明なら盲目的に再送せず、既存の独立停止監視とguardianを残して照合する。
watcherのログと状態は`completion-watcher*`に保存する。
GitHubのCI状態確認とは別の実機監視であり、CIは引き続き最短10分間隔で取得する。

## 検証と未完了

軽量検証はfake SDK、fake clock、手書きの3回／2秒／4秒の期待値、fake process portを使う。
実workerの前処理とSSHで送るPython断片もfake port上で実行し、公開のcomplete／partial／空結果・hash破損・二重送信拒否を確認する。
Macでは実モデル、実コーパス、PyArrow生成、ブラウザやGPUを実行しない。
13種類の意図的なバグを関連テストが検出し、CIの既知変異カタログにも追加した。

この実装が通っただけでは再開計画A全体やB〜Fを完了としない。
実行planを新しいsourceと価格で凍結し、必須／関連Linux CI成功後に、新しい独立期限付きの実ブラウザ試行で復旧と早期解放を確認する。
少量学習driverのGit管理、教師品質判断、実2 run、12 run比較、学習済みモデル配布と端末観戦も残る。
