# M6のCUDA起動前準備

2026-10-29の[実RTX5090試行](M6_TRIAL.md)で、固定依存・演算・少量学習・再開と外部復旧を確認済み。以下はその環境と試行手順。本学習と学習済みモデルの実機検証はこれから行う。

M6-2のための依存・検査コード。実装をLinux CPU CIで先に検証し、その後に上記の実GPU試行を行った。[全体の計画](M6_PLAN.md)と[学習CLI・再開基準](M6_RUNTIME.md)に従う。

## CPU CIとCUDAを別の環境に固定する

通常の`pyproject.toml`／`uv.lock`はLinux CPU版torchのまま維持する。外部Linux x86_64の環境は`infrastructure/cuda/`に置き、Python3.14.9、公式`cu130` indexの`torch==2.14.1+cu130`と、その依存を別lockで固定した。学習・監査・変換の直接依存はCPU環境と同じ版にする。MacへCUDAのwheelやデータをインストールしない。

初回CIではCUDA側に解決されたsetuptools78.1.0の既知脆弱性を依存監査とdependency reviewが検出し、mergeを停止した。公式wheelの条件`setuptools>=77.0.3`を満たす修正版84.1.0をCUDA側だけへ明示固定し、古い版への逆戻りもメタデータ検査で拒否する。[修正版の公式advisory](https://github.com/pypa/setuptools/security/advisories/GHSA-xmj3-9gf7-h52w)。修正後はPR #50の必須CI・dependency review・CPU/GPU両lockの脆弱性監査が成功し、main `0e9875d`へ取り込み済み。Pythonの281テストと92既知変異も成功した。監査のignoreや保護の解除は使わない。

外部Linuxでrepoのルートから実行する。

```bash
uv sync --project infrastructure/cuda --locked
uv run --project infrastructure/cuda --locked python -m training.cuda_preflight runs/m6/cuda-preflight.json
```

`--project`で使うPython環境を選び、作業ディレクトリはrepoルートに保つ。以降の`training.feature_cache`／`training.fit`も同じ`uv run --project infrastructure/cuda --locked`から実行する。Linux CIではCUDA環境をインストールせず、lockの整合・全依存の脆弱性・静的な固定値を検査する。実数値の小さい学習テストは従来のCPU環境で行う。

## 実機で止める条件

最初の候補はCloudRiftのRTX5090・1GPU。検査器はこの構成のPython・torch/CUDA版、Linux x86_64、GPU名・compute capability 12.0、wheelに含まれる`sm_120`、driver 580以上、実VRAM 31,000 MiB以上を確認する。CPU版torchや別GPUで通過させない。候補を変更する場合は、見積もりと検査の期待値も先に変更する。

続いて実GPUで2×2の行列積とbackwardを行う。`[[1,2],[3,4]] @ [[5,6],[7,8]] = [[19,22],[43,50]]`、総和の勾配は左が`[[11,15],[11,15]]`・右が`[[4,4],[6,6]]`という独立した期待値に完全一致させる。CPU CIの同じ小試験は算術の回帰用で、GPUを検証した証拠にはしない。

このprobeに成功しても、代表モデルの学習・VRAM・ブラウザWebGPUへの対応は未確認である。実データ監査、少量学習、保存再開、実ブラウザのGPU識別と描画併用を同じ試行で別々に記録する。

## 実データでの試行コード

入力を監査して作成したcacheに対して、外部Linuxで実行する。batch1とbatch4の64 stepは上記試行で成功済み。

```bash
uv run --project infrastructure/cuda --locked python -m training.cuda_trial runs/m6/cache runs/m6/trial-b1 --batch-size 1 --steps 64 --max-seconds 600
```

同じ代表モデルで64 stepを連続して更新するrunと、32 stepで保存し、model／optimizerを作り直してから残り32 stepを再開するrunを比較する。入力順序・step・乱数は完全一致、浮動小数点のパラメータ・optimizer・固定val入力の出力は事前の`atol=1e-6, rtol=1e-5`に入ることを要求し、最大誤差を残す。optimizerのstep counterは浮動小数点Tensorでも完全一致を要求する。testは読まない。

全trainを一巡する前の試行に限定し、64 stepの停止を1 epoch完了やval選択済みモデルと呼ばない。小さいval入力は再開前後の出力比較だけに使う。batch 4も別runで確認する予定で、OOM・途中停止を成功へ変えたり、自動で上限を延ばしたりしない。

各runのstep・例数・経過時間から、ログとcheckpoint保存を含むstep/s・局面/sを記録する。モデル生成前からの全経過時間は別に残す。Torchの最大allocated／reserved VRAMと、ローカルの`nvidia-smi`・RSS観測を区別する。2秒間隔の内部資源記録はクラウドAPI／CIの再取得ではない。これらの性能値は実GPUで実行するまで未測定で、Linux CPUの数値テストから換算しない。

## 費用・保持先の調査

2026-10-29 01:31 UTCの公式APIでは、`rtx59-3-24-750-xam.1`（API上は3物理／6論理CPU、24 GiB RAM、約750 GiBローカルdisk、1GPU）が$1/時・空き1台。48 GiB RAM版は同単価で空き0台だった。空きは予約ではなく、起動直前に再確認する。GPUの性能値や本学習時間はこの価格・CPU本生成実績から推定しない。

同01:41 UTCの全28 instance typeのカタログでは、提供される永続volume種別がすべて空だった。保存先の第一案だった同サービスvolumeは現時点では使える前提にしない。停止VMの課金・耐久性は未確認で、terminate後の旧diskの猶予期間も恒久的な退避には数えない。**保存方法・保持期限・費用を確定するまで有料試行は始めない。**

2026-10-29にM6基本枠US$24（既存US$100内）、初回最大4時間／US$4、成果物のApache-2.0、別HF repoへの再開状態公開を個別承認済み。不足時の追加GPU予算US$100も承認済みで、実測による不足を記録してから使う。保存方針は[確定案](M6_RUN_PROPOSAL.md)、承認元は[実行承認記録](../export/m6-approval.json)。既存のHF送信承認も利用する。開発やCI待ちの間はGPUを保持しない。

一次資料：[uvのPyTorch index設定](https://docs.astral.sh/uv/guides/integration/pytorch/)、[公式CUDA13.0 torch index](https://download.pytorch.org/whl/cu130/torch/)、[NVIDIAのCUDA13.x／driver580互換性](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)、[CloudRiftの料金方針](https://www.cloudrift.ai/pricing)。料金と空きの具体値は一般の広告価格ではなく、上記時点のAPI結果を用いた。
