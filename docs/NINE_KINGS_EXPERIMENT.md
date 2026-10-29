# 9王ルールと観戦表示の比較試作

2026-10-29のユーザー指示により、公開画面の「9王ルール比較室」とその導線を外す。旧`/?experiment=1`は通常の標準1王観戦を開く。以下は比較当時の研究記録であり、9王の正式採用を示すものではない。比較結果・棋譜・エンジンの回帰検証は保持する。

2026-10-26（JST）。目的はAI同士の対局を眺める用途に適した勝利条件と表示を探すこと。**ルールの実測と、同じ棋譜を見せる表示の検証を分けた。採用ルールや人の好みの結論はまだ出していない。**

本書はR0の生成版・条件・当時の件数を固定した記録。標準1王のM1探索とM2のWeb探索観戦はその後完了したが、9王への対応・全幅探索による再比較は未実施。[現在地](STATUS.md)・[M2検証](M2_VALIDATION.md) と次の [M3計画](M3_PLAN.md) を参照。

## 固定した条件

- [ルール仕様](RULESET.md#10-比較実験用の9王ルールv0)。同一の9層配置（各9王、合計360枚）、立体移動、持ち駒、王手回避なしを共通にし、5王先取・全9王捕獲・規定手数での王捕獲数比較だけを変える。
- CPU探索の実装版は `b899927`（完全SHAは各JSON）。学習モデルではなく、捕獲・成り・前進で並べた候補を幅で制限するnegamax＋αβ。駒得・前進・王捕獲を評価し、勝利条件は終端評価に反映する。深さ2、候補幅8。全合法手のminimaxやM1完成版ではない。
- seed 0〜99の100組。各組は同じ2つのseedストリームを先後交換して2局。各候補200局、計600局。各着手の乱択は固定seedと局面ハッシュによる同順位解決だけに使い、実時間で探索を打ち切らない。
- 主試験の上限は400 ply（先後各200着手）。5先取／全王では上限引き分け、得点比較では規定手数の採点による終局。勝敗確定と実験打ち切りを区別した。
- 現行1王は同じ探索量の別対照。初期配置372枚、王の安全・詰みという相違も含むため、勝利条件だけの因果比較には使わない。
- Mac Apple M1 / 8 GiB / macOS 27.0.1 / arm64、Rust 1.97.1、Node 24.22.1。GPU・有料サービスは使用していない。生成と棋譜照合はCPU。計測中は対照試験やビルドも並行したため、経過秒数を単独実行の探索速度やGPU費用の見積もりには使わない。

## ルールの結果

[全600局の集計・設定・SHA-256](experiments/nine-kings-main.json)。各棋譜の全手を生成後に再検証し、最終ハッシュと結果を照合した。原棋譜JSONLは `runs/nine-kings/`（git管理外）。

| 勝利条件 | 自然な目標到達 | 上限打ち切り | 得点比較で終了 | 先手勝／後手勝／引分 | 長さ 中央値／p90 | 王捕獲 合計平均 |
|---|---:|---:|---:|---|---|---:|
| 5王先取 | 30/200 | 170/200 | — | 17 / 13 / 170 | 400 / 400 | 4.555 |
| 全9王捕獲 | 0/200 | 200/200 | — | 0 / 0 / 200 | 400 / 400 | 4.690 |
| 得点比較 | — | — | 200/200 | 82 / 85 / 33 | 400 / 400 | 4.605 |

- 最初の王捕獲は、王が取られた198局に限ると3候補とも中央値60手・p90 212手。王が1枚も取られなかったのは各2局。層をまたぐ移動率は約57%。駒打ちはこの率の分母に含むが、層間移動には数えない。
- 王が取られない連続手数の最長区間は、各対局で測った値の中央値が166〜168手、p90が292手。得点が動かない時間も長い。通常駒の攻防まで止まっていたことを意味しない。
- 先後交換の組を保つクラスターブートストラップ（2,000回）では、5王先取の決着率15%は10.5〜20.5%、得点比較の勝敗が付く割合83.5%は78〜88.5%（95%区間）。これはこの固定AI・観測seed群を再標本化した幅で、他のAIや未観測事象の確率を保証しない。全件同じ結果の区間が0〜0や1〜1になる場合も、一般的な発生確率の確定ではない。

### 手数と探索量を変える確認

主試験の先頭20組（seed 0〜19、各40局）を共通にして、400→800手、候補幅8→16を別々に変える。規模を後から勝敗に合わせて選ばず、比較するseed組と先後交換をそろえる。

[400手・40局の対応部分](experiments/nine-kings-short40.json)、[800手・各40局](experiments/nine-kings-long.json)、[幅16・各40局](experiments/nine-kings-wide.json)。

| 条件 | 5王先取の目標到達 | 全9王捕獲の目標到達 | 得点比較の勝敗あり |
|---|---|---|---|
| 400手・幅8 | 10/40 | 0/40 | 34/40 |
| 800手・幅8 | 40/40 | 21/40 | 26/40 |
| 400手・幅16 | 4/40 | 0/40 | 34/40 |

800手では5王先取の長さは中央値501手・p90 583手、全王捕獲は787手・p90 800手。**「全王捕獲は決着しない」ではなく、この探索AIでは400手が短すぎる**。規定手数を800へ延ばした得点比較では、同点も6/40から14/40局に増えている。幅16では5先取の決着が10/40から4/40へ減ったため、探索量を増やせば短くなるとも言えない。上限・探索量を固定せずにルールを優劣順へ並べることはできない。

補助の捕獲優先AI（深さ1・幅1、seed 1000〜1001を先後交換した各4局）も生成・全手再生した。これは進行異常を探す小規模確認で、面白さやバランスの根拠には使わない。ランダムな合法手列と独立した移動参照実装との照合はRustテストでも行った。

### 現行1王の対照

同じ100組・200局、深さ2・幅8・400手では、詰み4局（先手3勝／後手1勝）、上限引き分け196局、連続王手負け・千日手0局。対局長の中央値・p90はともに400手、最短255手。勝敗が付いた割合2%のseed組ブートストラップ95%区間は0.5〜4%。初期配置・王の安全・終局条件の違いが重なるため、5先取の15%との差を王数だけの効果とは扱わない。通常の王は捕獲しないので、王捕獲指標の比較は行わない。

生成ログの経過時間は、9王主試験289.473秒（計6,307,152探索ノード）、現行対照593.020秒、800手試験124.352秒、幅16試験107.976秒、捕獲優先の補助試験0.630秒。計1,052局を生成し、全手・結果・最終ハッシュの再生照合を通した。並行実行を含むため、これを単独の探索ノード/秒やM1のNormal応答時間に換算しない。

## 同じ棋譜による観戦表示

公開版は通常画面から「9王ルール比較室」へ入る。直接URLは [公開比較室](https://voxelshogi.yousan-apps.workers.dev/?experiment=1)。400手主試験と800手試験を切り替え、各ルールを選べる。ブラウザ内の対局・推論ではなく、実際に生成した探索AI対探索AIの棋譜再生であることを画面に明記する。

| 表示 | 変える見せ方 | 共通に保つ情報 |
|---|---|---|
| A：全体を眺める | 9層を同時表示。断面の層は手動で選択 | 棋譜、現在手数、盤面・持ち駒、捕獲数、勝利条件、再生速度 |
| B：着手と捕獲を追う | 着手先の層を自動強調、他層を薄くする。移動経路と方向の光、王捕獲の告知 | Aと同じ。切り替えで着手を進めたり初期化したりしない |

- 初期／最終局面、前後1手、次の王捕獲、シーク、一時停止、再生間隔を操作できる。再生時間とAI生成時間を混同しない。
- 代表棋譜は、**打ち切りも含む全局から対局長の中央値に最も近いもの**。同順位はseed昇順・先後交換なしを優先し、面白い局だけ選ばない。400手の代表は打ち切り／同点の例になり、800手では全9王捕獲による実際の決着も見られる。
- 配信ファイルのSHA-256をmanifestと照合してから、Rust/WASMで全手・結果・最終局面ハッシュを検証する。A/B切り替えの前後で棋譜SHA・手数・局面ハッシュが等しいことを実ブラウザで検査する。照合情報と棋譜ダウンロードも画面に用意する。
- UIはルールを再実装しない。標準の `GameState` と `Game`、実験の `CaptureGame` と `ExperimentReplay` を分ける。標準ルールのZobrist固定値や既存棋譜は変えていない。

### 表示の評価手順

機能テストと実機での目視は実施するが、観戦者による好み・理解度の測定はまだ実施していない。次の条件で判断を分ける。

1. ルールを比べるときは表示Aに固定し、勝利条件・捕獲進捗・決着までの長さ・停滞を確認する。全局の集計を先に見て、代表棋譜だけで一般化しない。
2. 演出を比べるときはルール・棋譜・手数・再生速度を固定する。同じ捕獲局面をA→BとB→Aの両順序で試す。
3. 「どちらのAIが得点したか」「勝つまであと何王か」「どの層に動いたか」の正答と把握にかかった時間を、好み（眺め続けたいか）とは別に記録する。Bの捕獲告知に誘導されたルール評価を、ルール自体の優位性と扱わない。
4. 放置して眺める場合と、停止・1手送りで攻防を追う場合を分ける。人間同士の対局は行わない。モデル比較はM3/M6で実機推論と統合してから、別途行う。

## 再現

Node/Rustはリポジトリの固定版。Pythonは使用しない。新しいgit管理外ディレクトリへ出力し、保存済みの集計・配信棋譜を上書きしない。エンジンの完全SHAは次のとおり。squash mergeによりmainの祖先とは限らないため、ローカルにオブジェクトがなければ最初に `git fetch origin b8999270bf2583ad589096aa5838388dcda8db88` で取得する。

```sh
set -eu
experiment_engine=b8999270bf2583ad589096aa5838388dcda8db88
# M1後のcoreを過去の生成版として記録しない。固定コミットを別ディレクトリでビルドする。
experiment_source=$(mktemp -d "${TMPDIR:-/tmp}/voxelshogi-r0-source.XXXXXX")
git archive "$experiment_engine" | tar -x -C "$experiment_source"
CARGO_TARGET_DIR="$experiment_source/target" cargo build --locked --release \
  --manifest-path "$experiment_source/Cargo.toml" -p voxelshogi-core --example compare_rules
experiment_binary="$experiment_source/target/release/examples/compare_rules"
mkdir -p runs
experiment_output=$(mktemp -d "$PWD/runs/nine-kings-reproduce.XXXXXX")
# バイナリの実装版を確認した上で、その版を棋譜に記録する。
"$experiment_binary" 100 400 8 2 0 "$experiment_engine" > "$experiment_output/main.jsonl"
"$experiment_binary" 100 400 8 2 0 "$experiment_engine" baseline > "$experiment_output/baseline.jsonl"
"$experiment_binary" 20 800 8 2 0 "$experiment_engine" > "$experiment_output/long.jsonl"
"$experiment_binary" 20 400 16 2 0 "$experiment_engine" > "$experiment_output/wide.jsonl"
"$experiment_binary" 2 400 1 1 1000 "$experiment_engine" > "$experiment_output/greedy.jsonl"
node --input-type=module - "$experiment_output" <<'JS'
import { readFileSync, writeFileSync } from 'node:fs';
const dir = process.argv[2];
const lines = readFileSync(`${dir}/main.jsonl`, 'utf8').trimEnd().split('\n');
const paired = lines.filter(line => JSON.parse(line).seed < 20);
if (paired.length !== 120) throw Error('expected 3 rules × 20 seed pairs');
writeFileSync(`${dir}/short40.jsonl`, paired.join('\n') + '\n');
JS
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web wasm
node scripts/experiment-pack.mjs "$experiment_output/main.jsonl" "$experiment_output/public" "$experiment_output/nine-kings-main.json" "$experiment_output/baseline.jsonl"
node scripts/experiment-pack.mjs "$experiment_output/long.jsonl" "$experiment_output/public/long" "$experiment_output/nine-kings-long.json"
node scripts/experiment-pack.mjs "$experiment_output/wide.jsonl" "$experiment_output/wide-samples" "$experiment_output/nine-kings-wide.json"
node scripts/experiment-pack.mjs "$experiment_output/short40.jsonl" "$experiment_output/short40-samples" "$experiment_output/nine-kings-short40.json"
node scripts/experiment-pack.mjs "$experiment_output/greedy.jsonl" "$experiment_output/greedy-samples" "$experiment_output/nine-kings-greedy.json"
for variant in main long wide short40 greedy; do
  cmp "docs/experiments/nine-kings-$variant.json" "$experiment_output/nine-kings-$variant.json"
done
diff -r apps/web/public/experiments "$experiment_output/public"
```

差分確認が失敗した場合は版を付け替えて続行しない。生成器は固定した測定コミット、集計器・Web側は本報告を含む現在の版を使う。集計器は生成時のコミットにまだ存在しない。今回の文書更新では上記の隔離ビルドと2 plyの少数対局による起動確認を行い、1,052局全体は再生成していない。`short40` は主試験からの対応部分であり追加の120局ではない。

生JSONLのSHA-256、各サンプルのSHA-256、深さ・幅・上限・seed集合は各集計に保存する。棋譜再生成では経過時間をJSONへ入れないため、同じ実装・条件でバイト列を比較できる。

## 検証と次の判断

- TDDのRED：未実装のRustモジュール／対照関数、Web照合関数、観戦画面・800手選択が失敗することを確認して実装した。
- 手計算の捕獲数・成駒の持ち駒化・勝敗境界・同点・先後・上限優先、二歩・行き所・千日手、独立した移動参照実装、素朴なminimaxと同じ候補木でのαβ一致、合法手・再現性・不正棋譜拒否を検査した。
- 局所変異で、目標判定の境界、得点比較の勝者、千日手回数、最終ハッシュ照合、王評価、SHA照合、代表選択の順位、A/B時の局面リセットを検出した。注入した変異は復元済み。
- ローカル：Rust 116件、Web単体36件（実WASM、公開用6棋譜とSHA・捕獲イベント）、CI制御Node 42件、既知変異14件、fmt／clippy／actionlint／ShellCheck／Web lint／型検査／buildを実行した。実機Chromeの全9件E2E（配信SHA、A/B保持、再生・停止、全王捕獲の決着、破損拒否を含む）が成功した。
- Mac実機Chrome 155.0.8059.85で、400手・seed0・先後交換なしの56手目をA/Bで目視確認した。局面ハッシュは両方 `d1f6004f594e20f0`。1440px幅と390px幅で横方向のはみ出しはない。全層を初期カメラ内に収める調整を行った。人の好みの実験を実施したとは扱わない。
- [実装PR #7](https://github.com/ayutaz/voxelshogi/pull/7) は、必須7チェックすべての成功とCodeQL警告なしを確認し、通常のsquash mergeで統合した。[PR CI](https://github.com/ayutaz/voxelshogi/actions/runs/40248077708)・[Security](https://github.com/ayutaz/voxelshogi/actions/runs/40248077596)・[Quality](https://github.com/ayutaz/voxelshogi/actions/runs/40248077726)。統合コミットは `92c57fdfeed8bf19669692a67edf5bac10d0b5f3`。
- **初回公開確認完了（2026-10-26 JST）**：[main CI](https://github.com/ayutaz/voxelshogi/actions/runs/40249850975) で通常CI・本番デプロイ・配信SHA照合・公開E2Eが成功し、[main Security](https://github.com/ayutaz/voxelshogi/actions/runs/40249850944) も成功した。Mac実機Chromeから公開URLへの全9件E2Eも成功。配信SHAは `92c57fdfeed8bf19669692a67edf5bac10d0b5f3`、公開manifestと全6棋譜のSHA-256は測定・保存したファイルと一致した。
- 文書の取り込み後は公開SHA `73f4cdc63c44afca80d785bee8281689c0218933` でも [main CI 40254365292](https://github.com/ayutaz/voxelshogi/actions/runs/40254365292) の公開E2E 9件が成功。2026-10-26の独立取得で公開manifestと全6棋譜のSHAが保存版に一致した。以後の公開SHAは `build-info.json` で確認する。
- R0の実装・比較計測・観戦試作・公開検証は完了。正式採用と観戦者による理解度・好みの評価は別の判断として残す。

現段階では、長めの観戦を許すなら5王先取を中心に、一定時間で結果を見たい用途には得点比較を並べて試すのが妥当という**試作上の見通し**。全王捕獲は長期戦の候補として残す。弱い固定探索AIの成績だけで正式採用せず、観戦の理解度・好みと、M1の全幅探索を9王へ対応させた再評価を今後の判断材料にする。M1完成・M2ライブ探索・M3/M6実機モデル推論はこの試作では完了扱いにしない。
