# 学習済みMモデルのWeb読込契約

[実行計画の5](P6_EXECUTION_PLAN.md)に使う、取得済みフォルダーとWorkerの読込経路。
これは読込コードと軽量検証の契約であり、実Mの学習・変換・HF公開・実機推論の完了記録ではない。
[選択済み重みのLinux変換と実ONNX評価経路](P6_MODEL_CONVERSION.md)も追加した。
実Mでの生成・形式別の最終評価、本番catalogへの登録、Linux公開ハーネスの専用roleと全ファイル照合は、引き続き必要である。

## 対象と取得方法

Sの既存公開は従来どおり、固定したSの来歴・5,021,064 parameters・1ファイル64MiBまでの検証を使う。
Mのcatalog entryにだけ`profile="research-m-v1"`と`architecture`を明記する。
未知のprofile、構造の欠落、MをSとして読み込む操作は拒否する。
catalogの配布元は既存の同一origin固定パスのままで、requestから別catalog URLへ変更できない。
Mの構造・パラメータ数・寸法は[実Mで固定した4構造](P6_OPERATOR_RESULTS.md)に一致させる。

HFのpublic/manual取得承認とCommunity OFFを維持する。
ブラウザへ認証tokenを渡したり、HFの取得ゲートを別サイトのモデル配信で迂回したりしない。
利用者が取得したフォルダーを既存のモデル選択画面へ渡し、両AIの選択・中断・切替へ接続する。
この実装では実Mのcatalog entryやモデル本体を追加していない。

## manifestと評価の結び付け

`parseResearchModel`は、catalogが固定したmanifest SHAの検証後に次を確認する。

- 共通特徴量`float32 [1,729,43]`、Policy`[1,1067985]`、Value`[1,1]`と標準1王ルール。
- `trained=true`、cleanな書き出しsource、Apache-2.0、seedと正確なMの構造・パラメータ数。
- `research.schema="voxelshogi-research-inference-v1"`、学習sourceとbinding SHA、
  全更新数・選択更新数、`selection.json`と元FP32重みのdescriptor。
  学習sourceと後続の書き出しsourceを同じものとして扱わない。
- 固定4 fixture、全3形式、各形式の全Policy／Value参照ファイル、非FP32の全FP32差分。
- 各形式の`evaluation/fp32.json`／`fp16.json`／`int8.json`。
  各評価は`scope="final-holdout-v1"`、完了済み24局（最終12 root×先後）、
  そのONNX SHAと元重みSHAに束縛する。共通の評価protocolと最終root集合のSHAも残す。

manifest内の主張を確認するparserだけでは、評価が実行されたことは証明できない。
Linux側の公開ハーネスが選択receipt・全評価結果・元重み・ONNX・参照値を照合し、
実公開の固定revision全hash確認後にcatalog entryを作る必要がある。
少量試行の開発48局を、最終評価の24局や3形式の評価として転用しない。
本比較・形式別評価の実行時間と費用は、起動前の見積もりへ含める。

## 3形式と読込時の検証

FP32は変換前の基準、FP16は`fp16-weight-only`、INT8は
`symmetric-per-tensor-weight-only-int8`として明記する。
両変換版の計算とactivationはFP32とし、実際の変換tensor数・要素数を残す。
全出力差分は有限な値で記録し、精度低下やargmax不一致を隠したり、
metadataの受理だけを数値合格に置き換えたりしない。

モデルを受理したWorkerも、既存の`PolicySession`で同形式の全fixture参照値、
実際のbackend配置と合法手選択を検証してから着手する。
数値不一致・未対応backendは失敗として表示し、別backendへ黙って切り替えない。
実Mの実ブラウザ8ケース、変換版の精度・棋力・速度・容量と実機切替・解放は別途測定する。

## ファイル上限と読み取り順序

Mだけ1ファイル512MiB、フォルダー合計1,536MiB、512ファイルまでとする。
manifest・Card・license・選択receipt・評価reportは各1MiB以下。
入力と全参照値は寸法から決まる正確なbyte数、ONNXと元重みは固定SHAで照合する。
Sの本体64MiB・フォルダー512MiBと、共通runtimeの既存上限は変更しない。

フォルダー選択とWorkerへの転送前にはFile handleのpath・sizeだけを検査する。
転送用indexには本体を読む機能を与えず、Workerが同じcatalogの承認とhashを再確認する。
読込時はmanifest→Card／license／選択・評価の小さい記録の順に照合する。
ONNX・参照値は存在とsizeを先に確認し、着手用Workerが必要な本体だけを読む。
元のFP32 safetensorsはLinux／HFに残し、browserの選択フォルダーへ含めることを要求しない。
来歴にある元重みdescriptorをbrowserから本体取得へ転用せず、不要な重みをMacへ保存させない。
本体を読むたびに実bytes・SHAを検査し、catalogが列挙していないファイルは読まない。

上限は対応端末の推奨メモリ量ではない。対象端末でロード・推論・描画・切替・解放を測り、
未測定の端末、特に未確保の実スマートフォンを対応済みとは表記しない。
Macで大きいモデルを生成・読み取り・実行して確認せず、実測は外部Linuxと対象実機で行う。

## 軽量検証

手書きの4構造のparameter数、既知のSHAと不透明なFile handleを使う。
大きいsizeはmetadataだけで表し、その大きさのbufferや本物のモデルは作らない。
Mの来歴・構造・選択・各形式の評価・全hashと、Sの上限維持、Worker転送前の本体未読を確認する。
検査を意図的に外した新規20変異と、変更した既存2変異も隔離copyで実行し、
import失敗やtimeoutを検出成功にせず、実際に失敗したassertionで検出する。


[M専用HF公開契約](P6_MODEL_PUBLICATION.md)は、元選択履歴・各実ONNXの最終24局・全入力監査と配布hashを結び付ける。公開roleとcatalog生成APIを実装した段階で、実M公開・最終manifestの組立・実catalog登録は未完了。
