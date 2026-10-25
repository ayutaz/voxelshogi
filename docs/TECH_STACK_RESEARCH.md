# VoxelShogi 技術スタック調査（デューデリジェンス）

- 調査日: **2026-10-25**（JST）
- 対象: Rust コアルールエンジン → WASM（ブラウザ）/ Python（PyO3 + maturin）、Web（TypeScript + Vite + React + three.js / React Three Fiber）、ブラウザ内 NN 推論（ONNX Runtime Web: WebGPU、WASM フォールバック、Web Worker 内）、Cloudflare Workers Static Assets + R2、PyTorch DDP 学習（Vast.ai）、Hugging Face（モデル・データセット）
- 調査方法: crates.io API（`https://crates.io/api/v1/crates/<name>`）、`npm view`、PyPI JSON API、GitHub API / リリースタグのソース、Cloudflare 公式ドキュメント（`*.md` 版）。各数値の出典は末尾「出典」に記載。
- 凡例: **[確認済]** = 本日 一次情報（レジストリ・公式ドキュメント・タグ付きソース）で確認 / **[記憶ベース]** = 調査者の既存知識で本日未検証 / **[未確認]** = 確認できなかった・実測が必要

---

## 0. 結論サマリ

### 0.1 ピン留め推奨バージョン（2026-10-25 時点の最新安定版）

| 区分 | パッケージ | 最新安定版 | 公開日 | 推奨ピン | 備考 |
|---|---|---|---|---|---|
| Rust | `wasm-bindgen` | 0.2.129 | 2026-09-25 | `=0.2.129` | CLI と完全一致させる（後述） |
| Rust | `wasm-bindgen-cli` | 0.2.129 | 2026-09-25 | `0.2.129` | `wasm-bindgen` と同一バージョン必須 |
| Rust | `wasm-pack` | 0.15.0 | 2026-05-15 | `0.15.0` | 保守継続中（wasm-bindgen org へ移管） |
| Rust | `js-sys` / `web-sys` | 0.3.106 | 2026-09-25 | `0.3.106` | wasm-bindgen と同時リリース |
| Rust | `serde` | 1.0.229 | 2026-07-18 | `1` | |
| Rust | `serde-wasm-bindgen` | 0.6.5 | 2024-02-27 | `0.6.5` | 2 年以上リリースなし（後述） |
| Rust | `pyo3` | 0.30.1 | 2026-10-14 | `0.30` | MSRV 1.85 |
| Rust/Py | `maturin` | 1.15.0 | 2026-08-27（crates）/ 2026-08-24（PyPI） | `>=1.15,<2` | MSRV 1.89 |
| Rust | `trunk` | 0.22.0 | 2026-10-20 | 不採用 | 理由は後述 |
| npm | `vite` | 8.3.5 | 2026-10-21 | `~8.3` | Node `^20.19 \|\| >=22.12` |
| npm | `@vitejs/plugin-react` | 6.1.2 | 2026-10-05 | `~6.1` | peer: `vite ^8` |
| npm | `react` / `react-dom` | 19.3.1 | 2026-10-23 | `~19.3` | R3F の peer が `<19.4` |
| npm | `three` | 0.186.1 | 2026-09-24 | `~0.186` | 毎リリース破壊的変更あり得る |
| npm | `@types/three` | 0.186.0 | 2026-10-04 | `~0.186` | three とマイナーを揃える |
| npm | `@react-three/fiber` | 9.8.2 | 2026-10-21 | `~9.8` | 10.x は alpha |
| npm | `@react-three/drei` | 10.7.9 | 2026-09-25 | `~10.7` | 11.x は alpha |
| npm | `onnxruntime-web` | 1.30.0 | 2026-09-18 | `1.30.0`（完全固定） | Python 版 `onnxruntime` は 1.31.0 |
| npm | `vitest` | 5.0.5 | 2026-10-19 | `~5.0` | peer: `vite ^6.4\|\|^7\|\|^8` |
| npm | `@playwright/test` | 1.64.1 | 2026-10-24 | `1.64.1` | ブラウザバイナリ込みで固定 |
| npm | `wrangler` | 4.152.0 | 2026-10-22 | `^4.152` | Node `>=22` |
| npm | `typescript` | 7.0.2（latest） | 2026-07-08 | **`~6.0.3`** | typescript-eslint の peer が `<6.1.0` のため 7 は保留 |
| PyPI | `torch` | 2.14.1 | 2026-09-30 | `==2.14.1` | PyPI 既定 Linux ホイールは CUDA 13.0 |
| PyPI | `safetensors` | 0.8.0 | 2026-06-09 | `>=0.8,<0.9` | |
| PyPI | `huggingface_hub` | 2.3.0 | 2026-10-23 | `>=2.3,<3` | 2.0 で破壊的変更あり |
| PyPI | `pyarrow` | 26.0.0 | 2026-10-09 | `>=26,<27` | Python `>=3.11` |
| PyPI | `gymnasium` | 1.4.0 | 2026-10-05 | 任意 | 採用優先度低（後述） |
| PyPI | `onnx` | 1.23.2 | 2026-10-06 | `==1.23.2` | エクスポート検証用 |
| PyPI | `onnxruntime` | 1.31.0 | 2026-10-09 | `==1.30.*` 推奨 | **Web 版(1.30.0)と揃えて**挙動差を減らす |
| PyPI | `onnxscript` | 0.7.2 | 2026-09-09 | `==0.7.2` | torch.onnx(dynamo) が利用 |
| PyPI | `numpy` | 2.5.4 | 2026-10-10 | `>=2.2` | 2.5 系は Python `>=3.12` |

すべて [確認済]（各レジストリの最新安定版として本日取得）。

### 0.2 ブロッカー / 重大な注意点（優先度順）

1. **[確認済・最重要] ONNX Runtime Web の WebGPU 用 `.wasm` が Workers Static Assets の 25 MiB 上限を超える。**
   `onnxruntime-web@1.30.0` の `ort-wasm-simd-threaded.jsep.wasm` = 28,312,028 B（27.0 MiB）、`ort-wasm-simd-threaded.asyncify.wasm` = 26,781,914 B（25.54 MiB）。どちらも 1 ファイル 25 MiB 上限を超えるため、**Vite が自動でこれらを `dist/` に出力すると `wrangler deploy` が失敗する**。対策は §3.4.5 参照（R2 カスタムドメインから配信、または JSPI 版 16.0 MiB を使う、WASM 専用版 13.6 MiB はそのまま可）。
2. **[確認済] Conv3d は WebGPU で「動くが naive 実装」。グループ化（depthwise 含む）Conv3d は非対応。** 1.30.0 タグの WebGPU EP（C++）に `Conv3DNaiveProgram` があり 5 次元入力の Conv を実行できる（PR #27917、2026-04-03 マージ）。ただし `group != 1` はエラー、性能最適化はされていない（自動生成の演算子表にも "conv3d is not supported" の古い注記が残っており、ドキュメントと実装がずれている）。**9×9×9 盤面の主力演算に Conv3d を使う設計は、ブラウザ推論速度を早期に実測すべき最大リスク**。
3. **[確認済] ONNX 標準 `Attention`（opset 23）は WebGPU EP に登録がなく CPU にフォールバックする。** WebGPU で動くのは `com.microsoft` ドメインの `Attention` / `MultiHeadAttention` で、しかも mask・past/present 入力があると CPU フォールバック。→ **エクスポート opset は 18 を推奨**（SDPA が MatMul/Softmax に分解され、全て WebGPU 対応）。
4. **[確認済] TypeScript 7.0.2 が `latest` だが typescript-eslint は `typescript <6.1.0` を要求。** 当面 TS 6.0.3 に固定。
5. **[確認済] PyTorch の `cu126` ビルドは Blackwell（RTX 5090, sm_120）非対応。** 5090 を使うなら PyPI 既定（CUDA 13.0）か `cu130`/`cu132` を使い、Vast.ai のホストは `cuda_max_good >= 13.0`（ドライバ 580 系以上）で絞り込むこと（4090 の出品 64 件中 8 件は 13.0 未満だった）。
6. **[確認済] ローカル M1 の空きディスクは 9.2 GiB しかない**（`~/.cache/uv` が 12 GB を占有）。PyTorch/Playwright/Rust wasm ターゲットを入れる前に `uv cache prune` 等で空き確保を推奨（§6）。

---

## 1. Rust → WASM

### 1.1 wasm-bindgen（0.2.129）[確認済]

- **採用理由**: Rust⇔JS 間の事実上の標準 FFI。`#[wasm_bindgen]` で関数/構造体をエクスポートし、TypeScript 型定義（`.d.ts`）も生成される。リポジトリは `rustwasm` org の解散（2025）後、`github.com/wasm-bindgen/wasm-bindgen` に移管され、2026-10-24 にも push がある活発な状態。MSRV 1.81（ローカルの rustc 1.97.1 で問題なし）。
- **注意点**:
  - **`wasm-bindgen` クレートと `wasm-bindgen-cli` のバージョンは完全一致必須**。不一致だと「schema version mismatch」でビルド失敗。`Cargo.toml` で `wasm-bindgen = "=0.2.129"` と `=` 固定し、CI で同じ CLI を入れる。
  - ローカルには `wasm32-unknown-unknown` ターゲットが未インストール（`rustup target list --installed` は `aarch64-apple-darwin` のみ）。`rustup target add wasm32-unknown-unknown` が必要。
  - ルールエンジンで乱数（Zobrist ハッシュ等）を使う場合、`getrandom`（最新 0.4.3）は wasm32-unknown-unknown で追加の feature/cfg 設定が必要になる系統。**Zobrist キーは固定シードの自前 PRNG（例: SplitMix64）で生成し、`getrandom` 依存をコアから排除**するのが安全（0.4 系の具体的な設定方法は [未確認]）。
  - 盤面（729 マス）を JS へ毎手コピーするとオーバーヘッドになる。`Uint8Array` ビュー（`js_sys::Uint8Array::view` 等）やフラットなバッファ受け渡しを基本にする。

### 1.2 wasm-pack（0.15.0）— 保守状況と代替 [確認済]

- **保守状況**: 一時期「rustwasm org 解散で放置」と言われたが、**現在は `github.com/wasm-bindgen/wasm-pack` で保守継続中**（0.14.0: 2026-01-20、0.15.0: 2026-05-15、2026-10-24 にも commit あり、未アーカイブ）。0.14 で macOS ARM ネイティブバイナリ対応、0.15 で npm インストーラの 404 問題修正・wasm64 対応・`--panic-unwind` 追加。open issue は 389 件と多い。
- **代替**:
  - **wasm-bindgen-cli 直接**: `cargo build --target wasm32-unknown-unknown --release` → `wasm-bindgen --target web --out-dir pkg ...` → （任意）`wasm-opt -O3`。ツールの数は減り、バージョン固定が明示的。ただし `package.json` 生成や `wasm-opt` の取得は自前。
  - **trunk（0.22.0）**: Yew/Leptos 等「Rust 製フロントエンド」の HTML 起点バンドラ。**本プロジェクトのフロントは Vite + React（TS）なので用途が合わない**。MSRV も 1.96.1 と高い。→ 不採用。
- **推奨**: **開発初期は `wasm-pack build --target web`（0.15.0）**、CI では `wasm-bindgen-cli@0.2.129` 直接呼び出しに移行できるよう Makefile/justfile で薄くラップしておく。どちらでも成果物（`pkg/*.js` + `*.wasm` + `*.d.ts`）は同じ。
  - `--target web` を推奨（`bundler` ターゲットは ESM の wasm import 提案に依存し、Vite では追加プラグインが必要になりがち）。生成された `init()` を Web Worker 内で呼ぶ。
  - `wasm-opt` は wasm-pack が binaryen を自動ダウンロードする。オフライン/CI でキャッシュするなら `[package.metadata.wasm-pack.profile.release] wasm-opt = ["-O3"]` 等で明示。

### 1.3 serde / serde-wasm-bindgen [確認済]

- `serde` 1.0.229（2026-07-18）。`serde-wasm-bindgen` 0.6.5（**2024-02-27 以降リリースなし**、GitHub 最終 push 2025-10-01、未アーカイブ）。
- **採用理由**: Rust 構造体 ⇔ JS オブジェクトを JSON 文字列を経由せずに変換できる（`serde_json` + `JSON.parse` より軽い）。
- **注意点**:
  - 更新が止まり気味。機能は安定しているが、**ホットパス（探索中の盤面・合法手列挙）では使わない**。合法手は `Vec<u32>`（手のエンコード）→ `Uint32Array` で返すなどフラット化する。serde-wasm-bindgen は UI 向けの棋譜・設定など低頻度データに限定。
  - `u64`/`i64` は既定で JS の `number` に入らない（`BigInt` 化オプションあり）。Zobrist ハッシュ等 64bit 値を JS に出す場合は注意。
  - `HashMap` は既定で JS `Map` になる（`serialize_maps_as_objects(true)` でオブジェクト化）。

## 2. Rust → Python（PyO3 + maturin）[確認済]

- `pyo3` 0.30.1（2026-10-14、MSRV 1.85、最小 Python 3.9）、`maturin` 1.15.0（MSRV 1.89、PyPI でも配布）。
- **採用理由**: 学習側（自己対局・データ生成・特徴量化）で Rust のルールエンジンを Python から直接呼べる。maturin は `uv` と相性が良く（`uv tool install maturin` / `maturin develop --uv`）、abi3 ホイールを作れば Python マイナーバージョン毎のビルドが不要。
- **注意点**:
  - **abi3 を使う**（`pyo3 = { version = "0.30", features = ["abi3-py311"] }` 等）と Python 3.11〜3.14 を 1 ホイールで賄える。学習機（Vast.ai, Linux x86_64）とローカル（macOS arm64）で別ホイールが必要なので、Vast.ai 上では **ソースから `maturin build --release`** するのが簡単（Rust ツールチェーンを Docker イメージに入れる）。
  - 自己対局のホットループは **GIL を解放**（`py.allow_threads` / 0.30 系の名称は `Python::detach` 系へ移行中 [未確認]）して Rust 側でスレッド並列化し、Python には NumPy 配列（`numpy` クレート）でまとめて返す。1 局面ずつ Python 呼び出しするとオーバーヘッドが支配的になる。
  - PyO3 はリリース毎に API 破壊（Bound API 移行など）があるため、`0.30` でマイナー固定。
  - free-threaded Python（3.13t/3.14t）は当面不要。

## 3. Web フロントエンド

### 3.1 Vite 8.3.5 / @vitejs/plugin-react 6.1.2 [確認済]

- **採用理由**: 高速な dev サーバ、ESM ネイティブ、Web Worker（`new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })`）と `.wasm` アセットを標準サポート。Vite 8 は Rolldown ベース。
- **注意点**:
  - `@vitejs/plugin-react` 6.x は `vite ^8` 必須。Vite 7 系の古い記事の設定はそのまま使えない場合がある。
  - Node 要件 `^20.19.0 || >=22.12.0`。ローカルは Node v26.3.1 で OK。ただし **Node 26 が LTS 入りしているかは [未確認]**（偶数版は通常 10 月に LTS 化）。CI は Node 24 LTS を推奨。
  - **onnxruntime-web の既定インポートでは Vite が 25 MiB 超の `.wasm` を `dist/assets/` に出力してしまう可能性が高い**（§3.4.5）。`optimizeDeps.exclude: ['onnxruntime-web']` と `ort.env.wasm.wasmPaths` の明示設定でコピーを制御する。
  - dev サーバでもマルチスレッド WASM を試すなら `server.headers` に COOP/COEP を設定（§3.4.6）。

### 3.2 React 19.3.1 [確認済]

- **採用理由**: R3F 9 が React 19 必須。UI（棋譜、持ち駒、設定）と 3D ビューを同じコンポーネントモデルで書ける。
- **注意点**: `@react-three/fiber@9.8.2` の peer が `react >=19 <19.4`。**React 19.4 が出ても R3F 側の対応まで上げない**（`~19.3` 固定）。

### 3.3 three 0.186.1 / @react-three/fiber 9.8.2 / @react-three/drei 10.7.9 [確認済]

- **採用理由**: 9×9×9 = 729 マスの 3D 盤面表示、カメラ操作（drei の `OrbitControls`/`CameraControls`）、テキスト（`Text`）、ピッキング（R3F のレイキャストイベント）がすぐ使える。
- **注意点**:
  - three はほぼ毎月 `0.x` が上がり、マイナーでも破壊的変更がある。`@types/three` とマイナーを揃えて固定。
  - drei 11 / fiber 10 は alpha（WebGPU レンダラ寄りの変更）。**安定版 9.8 / 10.7 で固定**。
  - 729 マス＋駒を個別 `<mesh>` にすると描画コール過多。**`InstancedMesh`（drei `<Instances>`）でマス・駒種ごとにまとめる**。半透明レイヤ表示はソート問題が出るので、層スライス表示/ワイヤフレームを基本にする。
  - drei は依存が多い（`@mediapipe/tasks-vision`, `hls.js` 等）。tree-shaking は効くが、使うヘルパーを限定しバンドルサイズを確認する。
  - 描画（WebGL）と NN 推論（WebGPU, Worker）が同じ GPU を取り合う。推論中はフレームレートを落とす等の制御を検討。

### 3.4 onnxruntime-web 1.30.0（最重要コンポーネント）

#### 3.4.1 版・ビルド構成 [確認済]

- npm `latest` = 1.30.0（2026-09-18）、`dev` = 1.31.0-dev。Python 版 `onnxruntime` は 1.31.0（2026-10-09）が出ているが **Web は 1.30.0 が最新**。
- 1.30.0 の `exports` と同梱 wasm（`dist/`）:

| import パス | WebGPU 実装 | 使用する wasm | サイズ | 25 MiB 以下? |
|---|---|---|---|---|
| `onnxruntime-web`（既定） | JSEP（JS 実装の WebGPU） | `ort-wasm-simd-threaded.jsep.wasm` | 28,312,028 B（27.0 MiB） | **× 超過** |
| `onnxruntime-web/webgpu` | ネイティブ WebGPU EP（C++/Dawn 系, Asyncify） | `ort-wasm-simd-threaded.asyncify.wasm` | 26,781,914 B（25.54 MiB） | **× 超過** |
| `onnxruntime-web/jspi` | ネイティブ WebGPU EP（JSPI） | `ort-wasm-simd-threaded.jspi.wasm` | 16,758,545 B（16.0 MiB） | ○ |
| `onnxruntime-web/wasm` | なし（CPU のみ） | `ort-wasm-simd-threaded.wasm` | 14,239,897 B（13.6 MiB） | ○ |

  （`build.ts` の `DISABLE_JSEP` / `ENABLE_JSPI` 定義と `wasm-utils-import.ts` の分岐で確認）
- **推奨構成**: `onnxruntime-web/webgpu`（ネイティブ WebGPU EP。ORT の今後の主流で、Conv3D・3D ConvTranspose・新しい演算子の追加はこちらが先行）をメインにし、WebGPU 非対応環境では `executionProviders: ['webgpu', 'wasm']` の順で WASM へフォールバック。JSPI 版はブラウザの JSPI 対応状況次第（Chrome 系は対応済み、Safari/Firefox は [未確認]）なので、当面は機能検出して使う「オプション」扱い。

#### 3.4.2 WebGPU EP の状態と演算子サポート [確認済: 1.30.0 タグのソースと main の自動生成表]

| 演算子 | WebGPU 対応 | 注記 |
|---|---|---|
| **Conv (3D, NCDHW)** | △ 動作する（naive） | `rank == 5` で `Conv3DNaiveProgram`。**group≠1（depthwise 等）は非対応でエラー**。最適化なし（性能要実測）。JSEP 側も naive 実装あり、fp16 対応は PR #32357（2026-09-08 マージ、1.30.0 に含まれることをタグのソースで確認）。演算子表の "conv3d is not supported" 注記は古い |
| ConvTranspose 3D | ○（main のみ） | PR #32688（2026-10-08 マージ）→ **1.30.0 には未収録**、1.31 以降 |
| Conv 2D / 1D | ○ | 最適化済み（im2col/MatMul 系）。"need perf optimization" 注記あり |
| **ai.onnx `Attention`（opset 23）** | **× 未登録** | CPU フォールバック → GPU⇔CPU 転送が発生 |
| com.microsoft `MultiHeadAttention` | ○（制限付き） | mask・past/present 未実装（使うと CPU フォールバック） |
| com.microsoft `Attention` | ○（制限付き） | mask_index / past / present ありで CPU フォールバック |
| `GroupQueryAttention`, `RotaryEmbedding` | ○ | LLM 向け。本用途では不要 |
| **LayerNormalization** | ○ | ネイティブ EP は **opset 17 で登録**（17 未満の旧形式は不可）。`SkipLayerNormalization`/`SimplifiedLayerNormalization`/`RMSNormalization`(23) も可 |
| **GELU** | ○ | ai.onnx `Gelu` は opset 20+、com.microsoft `Gelu`/`FastGelu`/`BiasGelu`/`QuickGelu` も可。opset 18 なら `Erf` 分解（Erf は対応） |
| **Gather / GatherElements / GatherND** | ○ | |
| **ScatterND / ScatterElements** | ○ | opset 11〜18+ |
| Softmax / MatMul / Gemm / Einsum / Transpose / Concat / Slice / Pad / Where / Expand / Tile / CumSum / ReduceMean / BatchNormalization / InstanceNormalization / Relu / Sigmoid / Tanh / ArgMax | ○ | Transpose は "need perf optimization" |
| Shape / Reshape | CPU（メタデータ処理） | "no GPU kernel"。実データはコピーされないので通常は問題小 |
| MaxPool / AveragePool / GlobalAveragePool | ○ | 3D プーリングの可否は [未確認] |

- **動的形状**: WebGPU EP は動的形状を受け付けるが、**新しい形状ごとにシェーダ/パイプラインを生成するため初回が遅い**。バッチサイズは 1・8・32 など少数の固定値に限定し、`sessionOptions.freeDimensionOverrides` で固定するのが推奨。`enableGraphCapture`（コマンドバッファ再利用で高速化）は**全ノードが GPU 上かつ静的形状**であることが条件。
- **fp16**: WebGPU の `shader-f16` 機能がある環境でのみ有効。非対応 GPU 用に fp32 モデルも用意（または fp16 判定でモデルを切替）。
- **推奨 opset: 18**。
  - `torch.onnx.export`（torch 2.14 の既定は `dynamo=True`、torchlib の実装 opset = 18 [確認済]）の既定と一致し、変換経路が最も枯れている。
  - LayerNormalization（17+）が単一ノードで出る。
  - SDPA は opset 18 だと MatMul + Softmax に分解される → 全ノード WebGPU 上で実行。opset 23 にすると ONNX `Attention` が出て CPU フォールバックするので避ける。
  - 必要なら `onnxruntime.transformers` の optimizer で mask なし `MultiHeadAttention` に融合（要検証）。
- **モデル設計への提言（Conv3d リスク回避）**:
  1. 9×9×9 を **729 トークンの Transformer**（各マス=トークン、学習可能 3D 位置埋め込み）にする → MatMul/Softmax/LayerNorm 中心で WebGPU 最適化の恩恵が大きい。729² の注意行列は 1 層あたり約 53 万要素で、バッチ 1 なら十分現実的。
  2. Conv を使うなら **"2.5D" 化**（深さ軸をチャネルに畳み込み Conv2d を使う、または Conv3d を unfold + MatMul で表現）を検討。
  3. Conv3d を使う場合は depthwise（group≠1）を使わない。
  4. いずれも **最初の 1〜2 週間で「同パラメータ数の候補アーキテクチャを ORT Web(WebGPU/WASM) で ms/推論 計測」** してから学習に入る。
- **合法手マスク**: ポリシー出力への合法手マスクはグラフ外（JS/WASM 側）で行い、ScatterND 等をグラフに入れない方が単純。

#### 3.4.3 WebGPU のブラウザ対応 [記憶ベース・要再確認]

- Chrome / Edge 113+（デスクトップ）で既定有効、Android Chrome 121+。Safari 26（macOS/iOS）で既定有効、Firefox は 141 で Windows 既定有効、macOS/Linux は段階展開中。本日一次情報では未検証のため、**`navigator.gpu?.requestAdapter()` で機能検出し、失敗時は WASM EP** という実装を必須とする。
- Dedicated Worker 内での `navigator.gpu` 利用は Chrome 系で可（他ブラウザは [未確認]）。

#### 3.4.4 Web Worker 内での使い方 [確認済: exports / 記憶ベース: API 詳細]

- 既に自前の Worker で ORT を動かす設計なので **`ort.env.wasm.proxy = false`（既定）のまま**にする（proxy worker の二重化を避ける）。
- `ort.env.wasm.numThreads`: cross-origin isolated（`self.crossOriginIsolated === true`）でなければ自動的に 1 スレッド。WebGPU EP 使用時も一部 CPU 演算は wasm スレッドを使う。
- 推論セッションはページ寿命中 1 回だけ作成（作成コストが大きい）。

#### 3.4.5 Cloudflare での ORT wasm ファイルの配信方法 [確認済: サイズ制限 / 推奨案]

- Workers Static Assets の 1 ファイル上限 25 MiB（§4.1）に対し、WebGPU 版 wasm が超過する（上表）。選択肢:

| 案 | 内容 | 長所 | 短所 |
|---|---|---|---|
| **A（推奨）** | `ort-wasm-simd-threaded.asyncify.{mjs,wasm}`（WebGPU 用）を **R2 のカスタムドメイン**（例 `assets.<domain>/ort/1.30.0/`）に置き、`ort.env.wasm.wasmPaths` でそこを指す。WASM 専用版（13.6 MiB）は Static Assets 同居でも可 | 自前管理・バージョン固定・R2 egress 無料 | CORS 設定、COEP 対応（下記）、R2 Class B 操作数（キャッシュで軽減） |
| B | `onnxruntime-web/jspi`（16.0 MiB）を Static Assets に同居 | 同一オリジンで単純 | JSPI 非対応ブラウザでは使えない → A か WASM 版との併用が必要 |
| C | jsDelivr 等の公開 CDN から読む | 設定最小 | 外部依存、COEP 下では CORP/CORS ヘッダ次第 [未確認]、オフライン・改ざん耐性 |
| D | ORT を必要演算子だけで**カスタムビルド**（`--include_ops_by_config` の reduced build）して 25 MiB 未満に | 単一オリジン、軽量化 | Emscripten ビルド環境の保守コストが高い（ローカル 8 GB / 空き 9 GB では厳しい） |

- 実装メモ:
  - `ort.env.wasm.wasmPaths` には URL プレフィックス、または `{ mjs: URL, wasm: URL }` の個別指定を渡せる（1.19 以降の機能として記憶 [未確認]）。`.mjs`（グルーコード）は同一オリジン、`.wasm` だけ R2 という分離が可能なら COEP 周りが単純になる。
  - **Vite に巨大 wasm をコピーさせない**: `onnxruntime-web/webgpu` の既定エクスポート（`ort.webgpu.bundle.min.mjs`）は wasm を `new URL(..., import.meta.url)` で参照するため、Vite が `dist/assets/` に 25.54 MiB の wasm を出力する可能性が高い [要ビルド確認]。`onnxruntime-web-use-extern-wasm` 条件（exports に定義あり）か `ort.webgpu.min.mjs` を使い、`wasmPaths` を明示。デプロイ前に `find dist -size +25M` を CI でチェックする。
  - R2 カスタムドメイン側: CORS ポリシーで `AllowedOrigins` に本番オリジン、`AllowedMethods: GET, HEAD`。`.wasm`/`.onnx` は **Cloudflare の既定キャッシュ対象拡張子に含まれない可能性が高い**ため、Cache Rule（Cache Everything + 長い Edge TTL）を設定。ファイル名にバージョン/ハッシュを含めて immutable 扱いにする。
  - `.wasm` は `Content-Type: application/wasm` で配信されないと `WebAssembly.instantiateStreaming` が失敗する。R2 アップロード時に `--content-type application/wasm` を明示。
  - モデル（`.onnx`）も 25 MiB 超なら R2。25 MiB 以下なら Static Assets 同居も可だが、モデル更新でフロントの再デプロイが要らない R2 の方が運用は楽。

#### 3.4.6 マルチスレッド WASM と cross-origin isolation（COOP/COEP）[確認済: `_headers` 仕様 / 記憶ベース: ブラウザ挙動]

- マルチスレッド WASM は `SharedArrayBuffer` が必要 → ページが **cross-origin isolated** である必要がある:
  ```
  # dist/_headers（public/_headers に置いて Vite にコピーさせる）
  /*
    Cross-Origin-Opener-Policy: same-origin
    Cross-Origin-Embedder-Policy: require-corp
  ```
- COEP `require-corp` 下では、**クロスオリジンのサブリソース（R2 上の wasm/onnx、外部フォント、画像等）は CORS で取得されるか `Cross-Origin-Resource-Policy: cross-origin` を返す必要がある**。`fetch()` は既定で CORS モードなので R2 に CORS を設定すれば足りる。`<img>` などは `crossorigin` 属性が必要。Google Fonts 等の外部リソースは避ける。
- `COEP: credentialless` は Chrome/Firefox は対応、Safari は非対応（記憶ベース [未確認]）→ `require-corp` を採用。
- COOP `same-origin` によりポップアップ OAuth 等との `window.opener` 連携が切れる。将来ログイン機能を入れるときに注意。
- `_headers` の制約 [確認済]: ルール 100 件まで、1 行 2,000 文字まで、**Worker スクリプトが生成したレスポンスには適用されない**（`run_worker_first` で Worker を通す経路は Worker 側でヘッダ付与が必要）。SPA フォールバックで返る `index.html` に `/*` ルールが適用されるかはデプロイ後に `curl -I` で確認すること [未確認]。
- 隔離が崩れてもアプリは動くように（`crossOriginIsolated` が false なら `numThreads = 1`）実装する。

### 3.5 テスト

#### Vitest 5.0.5 [確認済]
- **採用理由**: Vite 設定を共有でき、TS/ESM をそのまま実行。Rust 側ロジックは `cargo test`、WASM バインディングの結合テストは Vitest（Node で `--target web` 生成物を `initSync` で読み込み）で行う。
- **注意点**: Node 要件 `^22.12 || ^24 || >=26`。ブラウザモードは `@vitest/browser-playwright` を別途インストール（バージョンは vitest と完全一致）。WebGPU を要するテストは CI（GPU なしランナー）では動かないので WASM EP でのテストに限定。

#### Playwright 1.64.1 [確認済]
- **採用理由**: E2E（盤面操作、Worker 起動、COOP/COEP ヘッダ確認、`crossOriginIsolated` の検証）。
- **注意点**:
  - ブラウザバイナリで数百 MB（ローカルの `~/Library/Caches/ms-playwright` は既に 520 MB）。ローカルでは `npx playwright install chromium` のみに限定。
  - ヘッドレス Chromium の WebGPU は GPU のない CI では基本的に使えない（SwiftShader 等のソフトウェア実装やフラグが必要で、挙動はバージョン依存 [未確認]）。WebGPU 経路はローカル手動テスト＋WASM 経路を CI で、と分ける。

## 4. デプロイ（Cloudflare）

### 4.1 wrangler 4.152.0 / Workers Static Assets [確認済: 公式 Limits ページ 2026-10-12 更新版]

| 項目 | Free | Paid |
|---|---|---|
| 1 ファイルの最大サイズ | **25 MiB**（確認済） | 25 MiB |
| Worker バージョンあたりのファイル数 | **20,000** | 100,000（wrangler 4.34.0 以上が必要） |
| `_headers` ルール数 / 1 行文字数 | 100 / 2,000 | 同左 |
| `_redirects` | 静的 2,000 / 動的 100 / 合計 2,100 | 同左 |
| Worker スクリプトサイズ | 64 MiB | 64 MiB |
| 静的アセットへのリクエスト | **無料・無制限** | 同左 |

- **採用理由**: 静的 SPA なら Worker スクリプト不要（assets-only）で、静的アセットへのリクエストは無料・無制限。Pages の後継として Cloudflare が推している構成。
- SPA フォールバック設定（`wrangler.jsonc`）:
  ```jsonc
  {
    "name": "voxelshogi",
    "compatibility_date": "2026-10-01",
    "assets": {
      "directory": "./apps/web/dist",
      "not_found_handling": "single-page-application"
    }
  }
  ```
  一致しないパスには `/index.html` を 200 で返す。compatibility_date が 2025-04-01 以降だとナビゲーションリクエスト（`Sec-Fetch-Mode: navigate`）は Worker スクリプトを起動しない。
- **注意点**:
  - **`run_worker_first` を使うと、Free プランで日次上限超過時にそのパスは 429 になる**（静的配信にフォールバックしない）。Worker スクリプトは極力持たない。
  - **Workers Caching を有効にすると、キャッシュから返した静的アセットのリクエストも課金対象になる**（Pricing の脚注 4）。有効化しない。
  - `_headers` は Worker が生成したレスポンスに効かない。
  - 25 MiB 判定が非圧縮サイズに対するものかは明記なし（[未確認]、非圧縮と見なして設計）。
  - `.assetsignore` で `dist` 内の不要ファイル（ソースマップ等）を除外可能。

### 4.2 Cloudflare R2 [確認済: R2 Pricing 2026-10-01 更新版]

| 項目 | Free tier（毎月） | 超過単価（Standard） |
|---|---|---|
| ストレージ | 10 GB-month | $0.015 / GB-month |
| Class A（書き込み・List 等） | 100 万リクエスト | $4.50 / 100 万 |
| Class B（読み取り） | 1,000 万リクエスト | $0.36 / 100 万 |
| Egress（インターネット向け転送） | **無料**（r2.dev / カスタムドメイン / Workers API / S3 API とも） | 無料 |

- Infrequent Access クラスは無料枠対象外・取り出し料金あり → 使わない。Delete は無料操作。
- **公開方法**:
  - `r2.dev` サブドメイン: **レート制限あり・開発用途のみ**と公式に明記。キャッシュ、WAF、アクセス制御が使えない。
  - **カスタムドメイン（推奨）**: Cloudflare Cache が効き（キャッシュヒットは R2 の Class B を消費しない）、WAF 等も使える。前提として**ドメインを Cloudflare のゾーンとして持つ必要がある** → 独自ドメイン費用が発生（COST_ESTIMATE 参照）。
- **注意点**: CORS はバケット単位で JSON 設定。`Content-Type` はアップロード時に指定。1 オブジェクト 100 MiB 超は multipart で Class A 操作が複数回発生。

## 5. 学習（Python / Vast.ai / Hugging Face）

### 5.1 PyTorch 2.14.1 [確認済]

- 最新安定 2.14.1（2026-09-30）。Python 3.10〜3.14 のホイールあり（cp313 あり）。
- **CUDA**: PyPI 既定の Linux ホイールは **CUDA 13.0**（`cuda-toolkit==13.0.3`, cuDNN 9.24, NCCL 2.30.7 に依存、x86_64 cp313 で 555 MB）。`download.pytorch.org` に `cu126` / `cu130` / `cu132` 版あり。
  - 公式サポート表（2.12/2.13 時点の記載）: CUDA 12.6 ビルドは Maxwell〜Hopper のみ（**Blackwell 非対応**）、CUDA 13.0/13.2 ビルドは Turing〜Hopper + Blackwell（10.0, 12.0+PTX）。→ RTX 5090（sm_120）、H100（sm_90）、RTX 4090（sm_89、sm_86 バイナリ互換）すべて CUDA 13.0 ビルドで可。
  - CUDA 13 ランタイムは NVIDIA ドライバ 580 系以上が必要（記憶ベース）。Vast.ai の検索で `cuda_max_good >= 13.0` を条件にする。
- **torch.compile**: 学習ループに適用し、初回コンパイル時間（数分）をコスト見積もりに含める。DDP と併用可（`DistributedDataParallel` を包んでから compile、または compile 後に DDP。推奨順序はバージョンにより変わるため 2.14 のドキュメントで要確認 [未確認]）。動的形状は再コンパイルの原因 → バッチサイズ・入力形状を固定。
- **SDPA / FlashAttention**: `torch.nn.functional.scaled_dot_product_attention` が FlashAttention-2 系・memory-efficient・cuDNN バックエンドを自動選択。H100 では cuDNN attention / FlashAttention が有効、4090/5090 でも Flash 系が使える（5090 は CUDA 13 ビルドが前提）。FlashAttention-3（Hopper 専用）を外部パッケージで使うのは任意。**バックエンドの実際の選択は `torch.backends.cuda.sdp_kernel` 系のコンテキストやプロファイラで実測確認すること**（[未確認]）。
  - 729 トークン（9³）程度なら標準 SDPA で十分。
- **BF16**: 4090 / 5090 / H100 / H200 すべてハードウェア BF16 対応。`torch.autocast("cuda", dtype=torch.bfloat16)` を基本にし、GradScaler 不要。TF32 は `torch.set_float32_matmul_precision("high")`。
- **DDP**: `torchrun --nproc_per_node=N`。コンシューマ GPU（4090/5090）は NVLink なし・P2P 制限があり、マルチ GPU 間通信は PCIe 経由で遅い → 小〜中規模モデルなら DDP 効率は高いが、**GPU 数を増やす前に 1→2→4 GPU のスケーリング効率を実測**。Vast.ai の 4090 機では P2P 無効化（`NCCL_P2P_DISABLE=1`）が必要な場合がある [記憶ベース]。
- **ローカル（M1 / 8 GB）**: macOS arm64 ホイールは 127 MB（展開後数百 MB）で、ディスク的にはインストール可能。CUDA は使えないので **CPU または MPS でスモークテストのみ**（1〜2 イテレーション、極小モデル、バッチ数件）。MPS は BF16 対応が限定的・`torch.compile` の MPS サポートも限定的 [未確認] → ローカルでは fp32・compile なしでテストし、BF16/compile/DDP の検証は Vast.ai の最小構成（1×4090）で行う。

### 5.2 safetensors 0.8.0 [確認済]
- **採用理由**: pickle を使わない安全・高速（mmap）な重み形式。HF Hub の標準。
- **注意点**: オプティマイザ状態・RNG 状態など任意オブジェクトは保存できない → 学習再開用チェックポイントは `torch.save`（自分の環境内のみで読む）、配布用重みは safetensors、と分ける。ONNX へのエクスポートは別工程。

### 5.3 huggingface_hub 2.3.0 / `hf` CLI [確認済]
- 2.0（2026-09-24）で破壊的変更: HTTP スタックが `httpx` → `httpx2`、**1.x で非推奨だった `upload_large_folder` が削除され `upload_folder` に統合**（CLI の `upload_large_folder` モジュールも 2.3.0 には存在しない）。古い記事の `huggingface-cli` / `hf upload-large-folder` は使えない前提で。
- 使い方: `hf auth login` → `hf upload <user>/<repo> ./local_dir . --repo-type=dataset`（データセット）/ `--repo-type=model`（モデル）。Vast.ai 上ではトークンを環境変数 `HF_TOKEN` で渡し、イメージに焼き込まない。
- **注意点**: 大量の小ファイルは Hub の制限（ファイル数・コミットあたりの操作数）に当たりやすい → 自己対局データは Parquet にまとめて数百 MB 単位のシャードで上げる。Private repo のストレージ無料枠・課金条件は本日 [未確認]（public は無料）。

### 5.4 pyarrow 26.0.0 / Parquet [確認済]
- **採用理由**: 自己対局局面（盤面テンソル・方策分布・価値）の列指向保存、圧縮（zstd）、HF Datasets / DuckDB / polars と互換。
- **注意点**: Python `>=3.11`。729 マス×チャネルの密テンソルを 1 行 1 局面の `FixedSizeList` で持つと読み込みが速い。行グループ 128〜512 MB 程度、zstd。学習時は Parquet → 事前に NumPy memmap / WebDataset 風シャードに変換した方が DataLoader が速い場合がある（実測）。1 局面あたりのバイト数は見積もりに直結するので要計測。

### 5.5 Gymnasium 1.4.0 [確認済: 版のみ]
- **評価**: 単一エージェント RL 用 API。AlphaZero 型の自己対局（MCTS + NN）では環境ラッパとしての必要性は低く、2 人対戦なら PettingZoo（AEC API）の方が適合（PettingZoo の版は本日未確認）。**採用は任意・低優先**。外部研究者向けに Gymnasium 互換ラッパを後から用意する程度で良い。

## 6. ローカル開発機（Apple M1 / 8 GB RAM / 空き約 9 GB）での注意

本日確認したローカル状態 [確認済]: rustc 1.97.1（ターゲットは `aarch64-apple-darwin` のみ）、node v26.3.1、npm 11.16.0、uv 0.11.23、uv 管理の Python 3.10〜3.14（3.13.9 あり）、メモリ 8 GiB、ルートボリューム空き 9.2 GiB、`~/.cache/uv` 12 GB、`~/.rustup` 563 MB、`~/.cargo` 435 MB、Playwright キャッシュ 520 MB。wasm-pack / wasm-bindgen / wasm-opt / wrangler / maturin は未インストール。

| 項目 | ローカルで可否 | 対応 |
|---|---|---|
| `rustup target add wasm32-unknown-unknown` | ○（数十〜百数十 MB） | |
| wasm-pack + binaryen 自動取得 | ○ | |
| Rust リリースビルドの `target/` | △ 数 GB に膨らむ | `cargo clean` を定期実行、`CARGO_TARGET_DIR` 共有 |
| Node 依存（vite/react/three/drei/ORT/wrangler） | ○ だが ORT だけで展開 145 MB、合計 1 GB 近く | pnpm でストア共有を推奨 |
| PyTorch（macOS arm64, 127 MB ホイール） | ○（CPU/MPS） | **CUDA 不可。DDP/BF16/compile/FlashAttention の検証はローカル不可** |
| PyTorch CUDA 版（Linux 555 MB + CUDA 依存で数 GB） | × | Vast.ai 上でのみ |
| ORT Web の WebGPU | ○（Chrome/Safari の Metal 経由） | M1 の GPU で推論速度の目安は取れる（実ユーザー端末とは別） |
| ORT のカスタムビルド（Emscripten） | × 実質不可（ディスク・メモリ不足） | 必要なら CI / クラウドで |
| Playwright 全ブラウザ | △ | chromium のみ |
| 大きなデータセット（数十 GB の Parquet） | × | HF / R2 / Vast.ai 上のみ。ローカルはサンプル数 MB |
| 学習のメモリ | △ 8 GB 共有メモリ | 極小モデル・小バッチでスモークのみ |

- **最初にやること**: `uv cache prune`（または `uv cache clean`）で 12 GB の uv キャッシュを整理すると空きがほぼ倍になる（ユーザー判断で実施）。

## 7. 未確認事項（要フォローアップ）

1. ORT Web WebGPU の Conv3d naive 実装の実速度（M1 / 一般的な Windows iGPU / dGPU）と、Transformer 案との比較。
2. Vite 8 + `onnxruntime-web/webgpu` で `dist/` に 25.54 MiB の wasm が出力されるか（実ビルドで確認）、`wasmPaths` の `{mjs, wasm}` 個別指定の挙動。
3. `_headers` の `/*` が SPA フォールバックの `index.html` 応答にも適用されるか（デプロイ後 `curl -I`）。
4. Static Assets の 25 MiB が非圧縮サイズ基準か。
5. WebGPU / JSPI / COEP credentialless の各ブラウザ対応状況（本日一次情報未確認）。
6. torch 2.14 での `torch.compile` × DDP の推奨順序、MPS での BF16/compile 対応。
7. Hugging Face private repo のストレージ無料枠。
8. `getrandom` 0.4 の wasm32-unknown-unknown での設定方法（コアから排除するなら不要）。
9. Node 26 の LTS 化状況。

## 出典（すべて 2026-10-25 取得）

- crates.io API: `https://crates.io/api/v1/crates/{wasm-bindgen,wasm-bindgen-cli,wasm-pack,serde,serde-wasm-bindgen,pyo3,maturin,trunk,js-sys,web-sys,getrandom}`（`max_stable_version`, `rust_version`）
- npm registry: `npm view <pkg> version / time / peerDependencies / engines / exports`（vite, react, react-dom, three, @types/three, @react-three/fiber, @react-three/drei, onnxruntime-web, vitest, @playwright/test, wrangler, typescript, typescript-eslint, @vitejs/plugin-react）
- jsDelivr パッケージ API（ORT wasm サイズ）: `https://data.jsdelivr.com/v1/packages/npm/onnxruntime-web@1.30.0?structure=flat`
- PyPI JSON: `https://pypi.org/pypi/{torch,safetensors,huggingface_hub,pyarrow,gymnasium,maturin,onnx,onnxruntime,onnxscript,numpy}/json`
- PyTorch: `https://raw.githubusercontent.com/pytorch/pytorch/v2.14.1/RELEASE.md`, `torch/onnx/_constants.py`, `torch/onnx/_internal/exporter/_constants.py`（TORCHLIB_OPSET=18）, `https://download.pytorch.org/whl/torch/`
- ONNX Runtime: `js/web/docs/webgpu-operators.md`（main, 2026-10-20 更新）、`v1.30.0` タグの `onnxruntime/core/providers/webgpu/nn/conv.cc`, `webgpu_execution_provider.cc`, `contrib_ops/webgpu/webgpu_contrib_kernels.cc`, `js/web/script/build.ts`, `js/web/lib/wasm/wasm-utils-import.ts`, `js/web/lib/wasm/jsep/webgpu/ops/3rd-party/conv3d_naive_webgpu.ts`; PR #27917, #32357, #32688
- GitHub: `wasm-bindgen/wasm-pack`（releases, commits）, `wasm-bindgen/wasm-bindgen`, `RReverser/serde-wasm-bindgen`, `huggingface/huggingface_hub`（v2.0.0 / v2.3.0 リリースノート, `src/huggingface_hub/cli/`）
- Cloudflare Docs: `https://developers.cloudflare.com/workers/platform/limits/`（2026-10-12 更新）, `/workers/platform/pricing/`, `/workers/static-assets/billing-and-limitations/`（2026-04-23 更新）, `/workers/static-assets/headers/`, `/workers/static-assets/routing/single-page-application/`（2026-10-12 更新）, `/r2/pricing/`（2026-10-01 更新）, `/r2/buckets/public-buckets/`, `/r2/buckets/cors/`
