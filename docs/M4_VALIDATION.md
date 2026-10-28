# M4：Python連携・生成と実機検証

確認: 2026-10-28 JST。[M4実行計画](M4_PLAN.md)のうち、Python連携・少量生成・検証・停止再開が対象。[API・データ・実行上限の契約](M4_DATA_CONTRACT.md)・[固定した小規模確認のJSON](experiments/m4-small-validation.json)。以下のM4-0〜2は当時の固定記録。末尾に外部実機の結果を追記する。以下は当時の履歴。M4全体は[2026-10-29 JSTに本生成・公開・資源終了まで完了](M4_COMPLETION.md)。

## 実装とローカル検証

| 対象 | 確認したこと |
|---|---|
| Python3.14の依存 | 3.14.9でPyO30.30.1／maturin1.15.0の拡張をビルド・import。Gymnasium1.4.0、PyArrow26.0.0、psutil7.2.2をuv.lockで固定。3.13への切り替えなし |
| Rustとの共有 | 既存Session・探索を呼ぶ薄い境界。初期hash `043b66e12f6b84fd`、372枚・424合法手、手計算の角の王の7手と深さ1の8ノード、捕獲後の持ち駒・成り・評価を照合 |
| 履歴・終局 | 履歴付き再生、4回反復、履歴を捨てたVSFENとの違い、放棄・規定手数終了、終局での手なしを確認。Native／WASMの固定12 fixtureとも探索結果を照合 |
| 特徴量・行動 | M3の全4局面の43ch出力を既存の独立したPythonエンコーダーと全要素照合。白の座標反転・所有者・持ち駒、打ち・成りのID、合法マスクを確認 |
| Gymnasium | 合法手だけを適用し、手番交代・着手側の報酬・自然終局優先・手数によるtruncation・reset後の再利用を確認 |
| Parquetと検証 | random／rules／searchを区別。小規模3対局・各2手は9行。独立した履歴再生・合法手・探索教師再計算、checksum・schema・行数・終端・分割・重複除外を確認。hashを更新した不正な行も拒否 |
| 教師の資格 | 固定深さ・ノードを記録。深さ1未完了の代替手は保存しても最善手教師にはしない。scoreは駒得／終局の尺度で、勝率ではない |
| 再現と再開 | 連続生成2回のParquet／manifestバイト一致。1対局確定後の再開、shard書き込みとmanifest確定の間のクラッシュ、実プロセスの中断後の再開が連続生成と一致 |
| 資源監視 | 注入時計・観測値で時間とRSSの境界、メモリ不足の代理指標、swap増加、セッション合計10分、同時実行拒否、観測不能時の停止を確認。実Rust探索のCPU進行後に親から停止し、子と子孫が残らないことを確認 |
| 回帰 | Rust core153＋WASM5＋Python境界2のworkspaceテスト、Rust1.85の全targets、clippy・fmtが成功。既存Pythonモデル48件と最終追加・修正後の新規40件がローカルで成功。Node67件、依存監査、actionlint、ruff、文書リンクも確認。全Python88件をまとめた最終headの実行はPRのCIで確認する |
| 変異 | Rustの既知38件（新規Python境界5件を含む）を実行された失敗で検出。Pythonモデル16件と境界／データ／資源監視15件はCIでも実行する。収集エラー・timeoutは検出成功に数えない |

実装コミット`b8c7655`のcleanなソースから通常CLIで標準初期局面の3対局・各2手、計9行を生成し、別のvalidateコマンドでも全件照合した。生成＋検証は約0.45秒、単独検証は約0.32秒、子プロセス群の観測RSS最大はそれぞれ約70.8／66.2 MiB。共有初期局面の重複2行を除外し、有効なtrain4／val3を確認した。この小規模集合ではtestは0行であり、本規模の評価用データが整ったという意味ではない。セッションledgerの累積約0.77秒と、ファイル・manifestのhashをJSONへ記録した。生成データ本体は公開していない。

TDDのREDは、Python境界・データ生成・資源監視が未実装の各テストで確認した。時間上限後の完了を成功にしてしまうケースとCLIの生成／検証コマンドについても、失敗を確認してから修正した。変異で同値だった「完了深さの条件だけを緩め、scoreなしの拒否は残す」変更は検出の証拠にせず、実際に未完了教師を採用してしまう変異へ置き換えた。

## 環境と制約

Mac Apple M1・8 GiB、既存Python3.14.9・Rust1.97.1を使用。開始時のディスク空きは約9.2 GiB、依存・ビルド追加後に約8.8 GiBを確認した。既存のデータ・モデル・無関係なファイルは削除せず、新たなモデル設計・公開、GPU利用、外部サービスの契約は行っていない。既存モデルの回帰テストでは一時ディレクトリに検証用モデルを再生成する。

macOS27でrelease拡張のimport時に`mis-aligned LINKEDIT string pool`を観測した。Python専用の`profile.python`でdebug情報を残しstripを無効にして再ビルドし、importと実行テストを通した。既存のWASM／Web用release profileは変更していない。参考: [Rust側の既知の共有ライブラリ問題](https://github.com/rust-lang/rust/issues/157750)、[PyO3のビルド方法](https://pyo3.rs/main/building-and-distribution)、[maturinの設定](https://www.maturin.rs/config)。

サンドボックス内ではプロセス／システムメモリの読み取りが拒否され、監視が`observation_error`で停止することも確認した。正常経路の監視テストは読み取りを許可した実環境で行った。制限を無視して生成を続けるfallbackは設けていない。

親の中断とグループ先頭プロセスの終了が競合すると、子孫を回収し損ねるケースもREDで再現した。親の終了有無に依存せず所有グループを停止し、生存メンバーがないことまで確認するよう修正した。この回帰も既知変異へ追加した。

最初のmanifestを書いている間の停止もREDで再現した。空の所有マーカーを原子的に作ってから初期化し、初期manifest未確定の状態でも再開できるようにした。無関係な非空ディレクトリを取り込む条件は緩めていない。

依存監査で新しいpath依存のversion未指定と、PyO3のビルド依存target-lexicon0.13.5の`Apache-2.0 WITH LLVM-exception`が検出された。pathにversionを明記し、同クレートの固定版だけを`deny.toml`で明示的に許可した。ライセンス検査自体や一般の許可一覧を無効化していない。参考: [crateごとの許可設定](https://embarkstudios.github.io/cargo-deny/checks/licenses/cfg.html#exceptions)。

小規模テストの経過時間を、10万局面の生成速度や外部CPU費用へ換算しない。CLIのRSSは所有する子プロセス群の観測値で、監視する親やChromeの常駐分を含めない。利用可能メモリは負荷の代理指標、RSSは監視による停止基準であり、瞬間的なハード上限やGPUメモリではない。電源断耐性と異なるOS間のParquetバイト再現は未検証。外部並列生成は後述の代表試行で1／2／4ワーカーを比較済みだが、10万局面規模の効率は未実測。

## 再実行する検証

リポジトリルートのLinux CIまたは承認済み外部Linuxで実行する。以後、Macでは探索・生成・重い回帰検証を行わない。

```bash
uv sync --locked
uv run --locked pytest -q
uv run --locked python scripts/ci/mutation-python.py
uv run --locked python scripts/ci/mutation-training.py
cargo fmt --all --check
CARGO_BUILD_JOBS=1 cargo clippy --locked --workspace --all-targets -- -D warnings
CARGO_BUILD_JOBS=1 cargo test --locked --workspace
node scripts/ci/mutation-smoke.mjs
```

Pythonジョブは実拡張をビルドし、全Pythonテストと両変異スクリプトをCI Gateの必須依存として実行する。既知Rust変異は必須のKnown mutation regressionsでも実行する。生成したParquetや未公開のデータ内容をartifactへ添付しない。PRの必須8チェック・通常merge・統合後CIを確認するまでは取り込み完了とは扱わない。

## 取り込みと次の作業

ローカル検証の後、作業ブランチ`feat/python-engine`からPRを作成し、最終headの必須CI・レビュー・通常取り込みと、mainの自動公開後の配信SHA・公開検証を確認する。これらの結果は該当PRと対応するmain CIを正とし、実行前に成功とは記載しない。

当時の次作業はM4-3。後続のユーザー指定によりMacで計測せず、承認済みCloudRiftのCPUで代表局面の速度・RSS・保存サイズを測り、本生成・全件検証・全再生成・退避／終了の時間と総額を見積もる。利用前の見積もり承認、データ公開前のライセンス／公開方法の決定は別途必要。

## 外部実行の準備と初回計測（2026-10-28）

PR #34〜#36を必須8チェック成功後に通常統合。PR #36は全Python121テスト・既知training32変異が成功し、統合`a6e31aed1c2cad3614b718276d848c35e83aa461`の[main CI](https://github.com/ayutaz/voxelshogi/actions/runs/40635704166)・[Security](https://github.com/ayutaz/voxelshogi/actions/runs/40635704170)も成功。自動公開の配信SHA、公開21 E2E・C0追加3件・モデル6件、配信55ファイルの照合を確認した。

初回のCloudRift利用はユーザーが最大60分・消費上限US$2で承認し、単価$1/時の米国RTX5090を1台起動した。実機のPython境界11テスト、固定30探索、102行の生成・全件検証・全再生成バイト一致が成功。[固定集計](experiments/m4-cloudrift-pilot-2026-10-28.json)・[構成と測定値の解釈](M4_REMOTE_PLAN.md#初回実機の結果2026-10-28)。探索深さ2は初期局面約0.194秒。短い試料の有効81局面を、10万件完了へ読み替えない。データ本体はMacへ保存していない。

64手・1／2／4ワーカーと12対局の代表試行も全件検証・全再生成が成功した。[固定JSON](experiments/m4-cloudrift-representative-2026-10-28.json)。6対局ではワーカー数間も全ファイル一致。12対局は有効769局面・探索教師252件、教師は全て深さ2。共通ledgerの累積508.750秒、外側監視のRSS最大約531.4 MiBで初回試行の上限内だった。[本生成の見積もり](M4_PRODUCTION_QUOTE.md)は承認済み総枠US$100内で管理する。10万局面規模の実データは未生成であり、これを本生成の完了としない。

初回実機の[終了・資源解放](experiments/m4-initial-teardown-2026-10-28.json)と、PR #37の通常統合・main CI/Security・公開後の[固定記録](experiments/m4-pilot-publication-baseline.json)も確認済み。試料Parquetは退避できなかったため、[試料公開](M4_HF_PILOT_RELEASE.md)では承認済みCC-BY-4.0で再生成し、歴史的hashとの一致を条件にする。

## 本規模の完了確認（2026-10-29 JST）

[完了記録](M4_COMPLETION.md)・[job、全件report、HF plan／receiptと終了記録](experiments/m4-production-release-2026-10-29.json)。1,800局・有効113,321局面・探索教師36,894件を全検証し、固定環境で全再生成がバイト一致した。Card付きHF公開・public/manual・Community OFF・固定Hub commitの全1,831対象ファイル照合、実機終了・資源解放・volume 0まで確認。実装の通常CIと、小規模の停止再開／変異の履歴は上記の固定記録を保持する。
