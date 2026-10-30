# M6の数値検証付きPolicy session

専用Worker内の`PolicySession`は端末内の検証済み実モデルを実行する。学習済み3形式、公開観戦、実機GPUの検証まで完了（[M6完了記録](M6_COMPLETION.md)）。以下は現行sessionの境界と初期実装時の検証記録。

## 起動してよいsession

1つのsessionをmodel ID・manifest hash・精度形式・backendへ固定する。選択の不一致や未対応の形式を、FP32や別backendへ暗黙に切り替えない。ONNXは検証済みの端末内bytesそのものからsessionを作り、同じsessionを対局中に再利用する。

起動時にはmanifestの全fixtureをRustで履歴付き再生し、43chの特徴量を作る。入力全bytesが同じPython参照と一致したことを確認し、各同形式のPolicy全1,067,985要素とValueを学習済み専用の`numericContract=voxelshogi-trained-numeric-v1`と出力別の固定誤差基準で照合する（[数値契約](M6_MAIN.md#fp32変換の失敗と次の基準)）。実行providerのprofileも確認し、CPU実行をWebGPU成功に置き換えない。全fixtureを検証し終えるまで対局の指し手を返さない。

ORT 1.31.1のnative profileは終了時に出力される。全fixtureの照合後に`endProfiling`を一度呼んで実providerの記録を確定し、同じsessionを解放せず対局で再利用する。記録は起動時の参照局面を対象とし、各着手の新しいprofileやkernel実行時間とは表示しない。M3の1回ごとにsessionを解放する推論では、従来どおり解放後のprofileを使う。WebGPUのCPU fallback禁止も維持する。

## 1手を返す

要求は履歴を含む棋譜、cursor、revision、局面hash、手番、rulesetで識別する。棋譜の文字数・bytesと整数範囲も制限する。Rustの`Game.fromRecordJson`と`goto(cursor)`で復元し、hash・手番・手数が一致した場合だけ特徴量と合法手を取得する。終局なら推論せず`choice=null`を返す。

非終局では同じsessionへ特徴量を渡し、[Policy契約](M6_POLICY.md)に従って合法手のみから選ぶ。応答に局面の識別情報とmodel／精度／backendを残す。UIの現在のrevisionとの照合と着手は後続client／arena controllerの責任であり、自己整合した古い棋譜であるだけでは現在の画面への適用を許可しない。

## 中断と資源

RustのGameは特徴量・合法手を取得したら、成功・失敗ともにfreeする。推論出力は毎回disposeし、sessionとbackendは通常終了・数値基準未達・推論失敗で解放する。同時要求は拒否する。model／精度／backendの変更は新しいWorkerへ切り替える設計で、異なる形式を既存sessionへ混ぜない。

中断フラグはファイル読込・session作成・推論のawait後にも確認する。作成や推論が遅れて完了した場合、その結果を返さず資源を解放する。進行中のkernelが決して完了しない場合の停止は、clientのWorker終了で担保し、フラグだけで即座にGPU資源が解放されたとは主張しない。

## 初期実装時の検証

MacではfakeのGame／backend／sessionと静的な配列だけを使う13テストを実行し、起動検証、同形式選択、入力・最後の出力の改変、provider誤表示、cursor／hash、終局、再入、中断・同期／非同期失敗時の解放を確認した。新規12変異も実行済みassertionで検出。関連する純粋な検証は計104テスト。モデルや実Tensor runtimeはMacで実行しない。

Linux CIには実WASM用の4テストも追加する。`export/fixtures/positions.json`をRustで再生してから特徴量を作り、M3最終manifest `412f9e6877f7138be9e205d42e8f27558b0766a1408d84c803bb3640c7598f80`のPython入力SHA-256へ照合する。M3の[固定完了記録](experiments/m3-completion-publication.json)に結び付いた、今回のTypeScript実装から作り直さない期待値である。全80 Web変異とWASM／E2EもCIで確認する。実ONNX・GPUでの結果と、M6学習済みモデルの実機対応は別途測定する。

FP16重み版はmanifestの`fp16-weight-only`を検査し、FP32計算としてbackendを開く。`computePrecision=float32`と返却証拠の同フラグを照合する。混合精度FP16と区別し、`shader-f16`を要求しない理由をモデルの変換方式へ結び付ける。
