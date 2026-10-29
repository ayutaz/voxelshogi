# M6の実機ブラウザ計測の記録検査

目的は、学習済み3形式を対象実機で比較した記録について、未完了の測定を完了扱いにしないこと。[検査コード](../scripts/trained-browser-evidence.mjs)はmetadataだけを検査し、GPUやモデルを実行しない。実モデルの読み込み・推論・実機操作の証拠は別に採取する。

## 完了として受理する記録

- Linux実機、固定したアプリcommit、学習済みモデルのsource／Hub revision／manifestと全3ONNXのhashを記録する。
- FP32／FP16／INT8重み版×WASM／WebGPU×固定4局面×3Dあり／なしの48条件を列挙し、欠落・重複を拒否する。初回、準備10回、測定30回を区別する。
- 成功した条件には、Rustの合法な手とaction、全4入力・Policy全1,067,985要素とValueの同形式参照照合、実行providerとoperatorの記録を要求する。[学習済み数値契約](M6_MAIN.md#fp32変換の失敗と次の基準)のmarkerと出力別atol／rtolを照合し、広い上限や非有限な差を拒否する。
- WebGPUはNVIDIAのadapter、3DはNVIDIAのrendererを確認する。実際に準備・推論したbackendと選択条件を照合する。
- 3Dありでは、反復推論中の実描画・trusted camera入力を記録する。描画と資源観測の5秒超の空白、資源サンプル不足を完了へ含めない。RSSは共有ページを重複計上し得る観測値、main JS heapはWorker／GPUを含まない値として扱う。
- WASMの全3形式を測定する。GPUの未対応・数値基準未達は実際の初期化エラーとして残し、404や一般的な実行失敗を未対応へ分類しない。GPUモデルの成功条件も必要。
- WASMとWebGPUで各20回、直前と異なる実行可能版へ切り替え、各回の同形式照合と資源観測を記録する。初回ロードは回数へ含めない。未対応形式を成功した切替として数えない。

`candidate=true`の記録は候補パッケージの私的な事前検証としてだけ受理し、最終の公開証拠とは区別する。smokeや未完了の行を全量の結果へ昇格させない。HFのmanual gateは維持し、モデルをCloudflareへ複製しない。

## ローカルとCI

手書きのopaque metadataによる7テストをREDから実装した。欠落・重複、CPU代替、数値照合不一致、別モデル混入、初回を含む切替、未対応の誤分類、描画／資源観測不足、候補・smoke・Macの混同を拒否する。Macではこの小さいmetadataテストだけを実行し、モデル・GPU・ブラウザ計測を行わない。

追加14件の既知変異は`mutation-controls.mjs`に含め、CI制御の合計33変異を実行する。通常の`node --test scripts/ci/*.test.mjs`と必須CIへ自動で含まれる。これらのテスト成功自体は実モデルの実機検証ではない。
