# 調査サマリ（初回2026-10-25、実装状況更新2026-10-28）

現在の確認元は [STATUS](STATUS.md)、次は [実行計画のM4](ROADMAP.md#m4-python-バインディングとデータ生成phase-3-の本体)。完了したM3の契約と証拠は [M3計画](M3_PLAN.md)・[M3検証](M3_VALIDATION.md)。詳細は各文書を参照。

本書の外部技術・価格情報は初回調査時点の記録。採用済みの構成と現在の進捗は [ROADMAP.md](ROADMAP.md)、CI/CD の実装・検証は [CI_CD_PLAN.md](CI_CD_PLAN.md) を優先する。WASM は wasm-bindgen-cli を直接使用し、Python は3.14系を基本、依存が未対応の場合は3.13系とする。

- ルール: `docs/RULESET.md`
- 関連研究: `docs/RELATED_WORK.md`
- 技術: `docs/TECH_STACK_RESEARCH.md`
- 費用: `docs/COST_ESTIMATE.md`

## 実装と調査の現在地

- 標準1王の独立実装・Web AlphaとM0のCI/CDは完了。R0では9王3ルールを別IDで実装し、現行1王の対照・上限／幅の感度を含む1,052局を生成・再生照合した。
- [公開比較室](https://voxelshogi.yousan-apps.workers.dev/?experiment=1)は生成済み6棋譜のA/B観戦再生。通常画面は両AIのEasy/Normalを選ぶWorker探索観戦。標準1王のM1全幅探索とM2のライブ探索・中断・実機公開確認は完了した（[M1](M1_VALIDATION.md)・[M2](M2_VALIDATION.md)）。
- M3も完了。[公開推論ラボ](https://voxelshogi.yousan-apps.workers.dev/?models=1)で未学習の約502万パラメータTransformerを3形式から選んで実行できる。M1／ChromeではFP32とINT8重みのWebGPU、全3形式のWASMを数値検証済み。FP16×WebGPUの基準未達は明示し、自動fallbackしない。公開55ファイル照合、48組の実機計測と各backendでの20回実切替を [固定記録](M3_VALIDATION.md) に保存した。
- 9王の正式採用、観戦者による理解度・好みの測定、M4のPythonバインディング／学習データ生成、M5の実棋譜互換性、M6の学習・棋力評価とモデル対局は残っている。
- [先行ルール調査](RULE_VARIANTS_RESEARCH.md)と[R0実測](NINE_KINGS_EXPERIMENT.md)を分け、M1以降の研究候補を実装済みと扱わない。R0の手作り探索評価は、将来の強化学習の報酬設計とは別である。

## ルール（一次資料）

- 準拠先は、将棋ったー「三次元将棋」（rule id 166、ページの最終更新日 2026-10-09、**2026-10-17 に角の遮り方を改定**）。
- ルールページ・駒の動きページの記述と、同サイトが配信しているルール定義（初期配置、利き、遮り判定、二歩判定）を読解した。
- その結果、桂は x と z を両方±1する「×型」であること、銀は同じ層の斜め後ろへ動けないことを確定できた。
- 第三者のコードはコピーしていない。

## 既存実装

| 実装 | ライセンス | ルールの一致 | 再利用 |
|---|---|---|---|
| tomikan1208-code/3D_shogi | **なし（全権利留保）** | 異なる（飛車は6方向、角は12方向、桂は「+型」、170枚/側） | アイデアのみ。重みは非公開 |
| m-tatsuto/3dshogi（空将） | 不明確（MITL ファイルはあるが GitHub 上は未検出） | 一部一致 | UI のアイデアのみ |
| guille0/space-chess | `docs/RELATED_WORK.md` 参照 | チェス | 表示のアイデア |

## AI 研究からの採用方針（案）

- Phase 5の自己対局ではGumbel AlphaZero系とKataGoのplayout cap randomizationを候補とする。M1はαβ探索、R0は幅制限付きnegamax＋αβであり、Gumbel探索は未実装。
- W/D/Lの3値Valueは自己対局学習の研究候補。M3で固定した現行契約は手番側のscalar tanh Value `[batch,1]` で、未学習の出力を勝率と扱わない。変更する場合はM6以降で契約・教師・検証を更新する。報酬は勝敗を基本とする案で、R0の手作り探索評価とは別に判断する。
- M3のPolicyはfrom/toの低rank射影2組（成りの有無）と駒打ち7種で、出力ラベルは1,067,985。方向ベースの行動空間を避ける初回案を具体化したが、学習・棋力による構造比較は未実施。[現行の入出力と変換契約](MODEL_CONTRACT.md)
- Geometry-aware バイアスを729トークンにそのまま適用すると、約1.36億パラメータの共有射影が必要になる。そのため、軸ごとに分解するか、静的な3D相対バイアス（ヘッドごとに4,913エントリ）を使う。
- 評価は、同じ FLOPs のもとでの Elo で行う。幾何を考慮すると精度は上がっても勝率は上がらない、という先行報告があるため。

## 技術上の主要リスク

1. 初回調査のWASMサイズ超過に対し、M3はORT Web1.31.1のAsyncify WASM（28,747,738 bytes）を16 MiB単位に分割し、SHA付きで取得・再結合する方式を採用した。同一originのStatic Assetsで実配信照合まで完了し、R2は不要だった。JSPI・独自reduced buildは未採用。[ADR-019](ARCHITECTURE_DECISIONS.md#adr-019-m3の精度形式backend配信方式2026-10-27)
2. M3の729トークンFull Attentionをopset18へ変換し、FP32／INT8重みの全演算がM1のWebGPUへ配置されたことを確認した。FP16×M1 WebGPUは数値基準未達、Conv3d・他GPU・Safari・batch8は未検証。古い演算表や小行列の成功だけで一般化しない。
3. GPU・PyTorch・CUDA・ドライバの組み合わせはM6で再確認する。初回調査ではRTX 5090向けにCUDA 13系のビルドを候補とした。
4. ディスクの初回約9GB、2026-10-26の約32GiB、2026-10-27の約27.2GiBは各時点の記録（[固定した確認元](experiments/documentation-baseline-2026-10-27.json)）。M4の依存導入・データ生成前に再確認する。M3では一度のHTTP 500も観測したため、読込エラーの表示・再試行と失敗記録を維持する。GPU総メモリは測定APIから取得できない。

各リスクに対応する順序とゴールは `docs/ROADMAP.md` を参照。1・2のM3先行検証は完了し、制約をM4／M6へ引き継ぐ。3はM6の有料GPU選定・承認前に再確認する。M1の教師用探索はαβ探索で、上記のGumbel AlphaZero案は後続の自己対局用である。
