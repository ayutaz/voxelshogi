# P5-2：自己対局3世代・HF保存・別VM継続の完了記録

2026-11-03 16:56:12 UTC。実行sourceは`1280dc40c61e4ba15f0f5996abc775d900b043a7`、protocolは`f4cc205d29a86ab02db9533e39f0001a0e2cdcfe414f14724a8123b7fab589ce`。[事前条件](P5_SELFPLAY_MAIN.md)の3世代×16対局＝48 episodeを実行し、世代ごとの学習・HF全hash照合・別の所有VMでの後続世代・資源解放を確認した。

本書はP5-2の実行結果を記録する。P5-3の棋力比較、複数GPU、Phase6の構造比較は未実施である。文書更新の取り込みと必須CIは、対応するPR／Actionsの結果で別に確認する。

## 目的と確認できた結果

自己対局から学習・子モデル更新・外部保存へ進み、元のVMを解放しても同じprotocolから後続世代を続けられることを確かめた。小規模運用試行の2対局・8更新、および[数値修正前に停止した旧run](P5_PRIOR_NORMALIZATION.md)の16対局・937更新は、この本条件48件へ含めない。

| 世代 | 新規対局 | 学習対象sample | 除外した保護入力 | 実更新数 | 子モデルSHA-256 |
|---|---:|---:|---:|---:|---|
| 0（第1世代） | 16 | 3,746 | 0 | 937 | `fec4445c2542e6a707f4658149efa1434985c28f2dbfb094c9c75738e7a5dcd4` |
| 1（第2世代） | 16 | 7,710 | 0 | 1,928 | `3074e6aa45e4fea3667f87cc5569428d52e0e93670ed812a4f541b5c0f6fd65e` |
| 2（第3世代） | 16 | 7,788 | 0 | 1,947 | `bf4fba2699d9d8578a821766b0fcaf861d56aab3effc296d87ec3a4e9408c8a4` |

学習対象は直近32 episodeを選ぶReplay windowであり、第2・第3世代の件数には過去世代の再利用を含む。本条件のraw sample総数は11,534、延べ学習sampleは19,244、追加学習更新は合計4,812回。対局の件数・raw sample・延べ学習件数を区別する。

終局内訳は自然勝敗0、ルール上の引分13、cutoff35で、合計48件。cutoffのValueは明示したモデルbootstrapであり、実終局の引分や観測勝率へ変換していない。損失やモデルhashの変化だけで棋力向上を主張しない。

| 世代 | bootstrap-v1 | terminal-v1 | train内の反復入力 | 実学習入力byte・metadataのSHA-256 |
|---|---:|---:|---:|---|
| 0 | 3,072 | 674 | 52 | `f27a760011aa8378c28034ab6de01b8b2f4774ce2b8f7bc58cc9824f63ec2843` |
| 1 | 5,888 | 1,822 | 162 | `234723ac549d2e01823a0f5b5f9cab247371a0512e2e12e95ad8398dd1a61e3e` |
| 2 | 5,888 | 1,900 | 185 | `e1cc5be4b7d53270631706e3577f9ef4e2376b2ebbd24e4857ddabbf9a45d132` |

Valueの2つの出所は別batchで学習した。反復入力は対象Replay内の延べ入力ID数から一意ID数を引いた件数で、train内の反復は保持する事前規則。独立した局面数や、自然勝敗の観測数とは扱わない。

## 条件と入力保護

両VMの実測環境はNVIDIA GeForce RTX 5090×1、VRAM 32,607 MiB、Linux x86_64、Python 3.14.9、Torch 2.14.1+cu130、CUDA 13.0、driver 610.43.02。同じCUDA lockと手計算forward／backwardの検査を通過した。未測定のGPU・DDP・別構造へ速度を一般化しない。

- M6の固定基点はSHA-256 `dcdf28431a7eab40d98f98a1f2ef7b80fbea1b7d9e66f98b6428cfaa67336c85`。運用試行の子モデルを基点へ差し替えていない。
- train専用の16開始局面、seed42000〜42015。16手×4・128手×6・256手×6の合法な開始履歴はsource `40ae236`のRustで生成・再生した。長い履歴を代表的な終盤とは呼ばない。root間重複・保護集合とのroot重複は0。
- Actor seed314159、32 simulations・最大深さ64、追加256手、最初16手の温度1・以降0。CUDA FP32、1epoch、batch4、learning rate0.0001、weight decay0.01、threads2、save_every128。各世代は新しいAdamWを使い、holdoutで選択しない。
- 合法手の確率正規化だけFP64を使う。モデル・logits・学習はFP32、探索の確率和許容差は1e-6を維持する。source変更後はM6基点から新protocolとし、旧runを継ぎ足さない。
- M4/M6全split・P5-0評価入力・P5-1 holdout全履歴の保護集合116,008件、全bytesのSHA-256 `364ee551512b1c98871308aafc939059f4a26743340b2aa904555c92d4a39944`を維持した。[固定HF index](https://huggingface.co/datasets/voxelshogi/voxelshogi-protected-inputs-v1/tree/ec3bfa0acfa6c5c9f59f98bf1750a3143c0007d8)を使い、VMごとの全コーパス再取得を省いた。除外範囲の縮小・P5-1未検証教師の採用は0。

## 全件の再生・入力hash・HF照合

全48 episodeの実着手・合法手・履歴・訪問回数・ラベル算術・seedと探索予算をRustで再検査した。さらに世代ごとにReplay windowを独立に数え直し、保護入力の除外・train内反復・Value出所別batchから期待する更新数を照合した。全特徴量byteと行metadataの入力SHA-256が、実学習のbindingと3世代すべて一致した。非空の116,008件を検査した上で、学習対象への保護入力重複は0だった。

HFの全世代Dataset／stateを固定revisionから再取得し、全ファイルのbytes／SHA-256、stateのdecode、子モデル再exportのhash、全Replayを照合した。ニューラル探索を再実行して訪問分布を独立測定した検査とは区別する。

復旧前後の保存モデル・Replay・stateの一致を確認した。本条件48対局全体を別runで再実行して無中断実行とGPUの最終hashを比較した検証は行っていない。小さいNative結合試験での無中断／再開一致と、本条件で実際に別VMへ復旧・継続した証拠の範囲を分ける。

| 世代 | Dataset固定revision | state固定revision |
|---|---|---|
| 0 | [e46e4535971d6079670171f92e74638f3d8de0ca](https://huggingface.co/datasets/voxelshogi/voxelshogi-selfplay-v1/tree/e46e4535971d6079670171f92e74638f3d8de0ca) | [4f1cc0db447f96c3488fd7af5838d8becd400467](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-selfplay-training-state-v1/tree/4f1cc0db447f96c3488fd7af5838d8becd400467) |
| 1 | [4359ae293eaff111a28b5b831322fd4c34490aa5](https://huggingface.co/datasets/voxelshogi/voxelshogi-selfplay-v1/tree/4359ae293eaff111a28b5b831322fd4c34490aa5) | [e69fccaa918aaaef21265ca70fb44c87dcacdb3b](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-selfplay-training-state-v1/tree/e69fccaa918aaaef21265ca70fb44c87dcacdb3b) |
| 2 | [cb509eed269b74f7138f7710d5bf95664d476a95](https://huggingface.co/datasets/voxelshogi/voxelshogi-selfplay-v1/tree/cb509eed269b74f7138f7710d5bf95664d476a95) | [127e41bc4cd3dffcf669855580ec7de9f307ef16](https://huggingface.co/voxelshogi/voxelshogi-transformer-s-selfplay-training-state-v1/tree/127e41bc4cd3dffcf669855580ec7de9f307ef16) |

- VM1の公開済みcursor snapshot：[固定revision](https://huggingface.co/datasets/voxelshogi/voxelshogi-selfplay-v1/tree/dbd3fdb90f8950abb57b0d31e7167560ea3d500d)。世代を増やした公開ではない。
- VM1の集計report：[固定revision](https://huggingface.co/datasets/voxelshogi/voxelshogi-selfplay-run-reports-v1/tree/4f85cce14ee1a46178921faaa724c1ca155cb890)。全3世代完了の判定は最後のVMのreportと全件監査で行う。
- VM2の公開済みcursor snapshot：[固定revision](https://huggingface.co/datasets/voxelshogi/voxelshogi-selfplay-v1/tree/e1f0e33e397eecbf2f2e494ff816d3553e118105)。世代を増やした公開ではない。
- VM2の集計report：[固定revision](https://huggingface.co/datasets/voxelshogi/voxelshogi-selfplay-run-reports-v1/tree/080bc5f218fe4f91ddd63ae9dfdf706b785ddd91)。全3世代完了の判定は最後のVMのreportと全件監査で行う。

Dataset・保護index・reportはCC-BY-4.0、モデル／再開状態はApache-2.0。各Card・public/manualの取得申請・Community OFFを確認した。データと重みは外部Linuxから直接転送し、Macへ保存したのは小さいprotocol・manifest・hash・集計だけである。

## 別VMでの継続と資源終了

最初の所有VM `58974467`で1世代を確定・HF保存した。削除ackと完全inventoryからの不在を確認した後、異なる所有VM `58979282`を作成し、HFから全Replay・親子モデル・必要なstateを復旧した。同じprotocolのまま2世代を実行・学習・HF公開した。元ディスクのコピーや同VMの別ディレクトリを別実機復旧と数えていない。

以下は作成要求から削除ackまでの観測時間と、固定単価を掛けた参考額。providerの確定利用秒数・請求書ではない。

| VM | 作成要求 | 削除ack | 観測時間 | 参考額 |
|---|---|---|---:|---:|
| VM1 `58974467` | 2026-11-03 14:45:35 UTC | 2026-11-03 15:29:46 UTC | 44.2分 | 約US$0.537 |
| VM2 `58979282` | 2026-11-03 15:30:38 UTC | 2026-11-03 16:55:32 UTC | 84.9分 | 約US$1.031 |

世代ごとの実測時間は次のとおり。探索・Actor・特徴量と学習をまとめた時間であり、純粋なNN推論や学習スループットではない。HF公開・入力監査・VMの準備／終了は別の工程として記録した。

| 世代 | 自己対局・特徴量・学習 |
|---|---:|
| 0 | 1586.7秒（約26.4分） |
| 1 | 1982.7秒（約33.0分） |
| 2 | 2127.4秒（約35.5分） |

独立停止は正確な所有labelと絶対期限を持つGitHub Actions、予備停止はMacの制御で実行した。今回の通常終了はHF退避・証拠回収後に早期解放したものであり、期限停止の実証は[初回試行](P5_SELFPLAY_TRIAL.md)の記録へ分けて保持する。

## 費用・残る課題・停止

保守的な累積予約は全体US$85／基本枠100、Phase5 US$24／配分24。Phase6配分は15、追加US$100は未適用。これらはサービス残高や確定請求額ではない。共通state upload ledgerは累積621,142,594 bytes／1 GiBで、過去の予約を消したり新しい空ledgerで再開していない。

棋力改善、自然終局率や学習効率の一般化、複数seed、DDPの1→2→4GPU、Phase6の構造・Mモデル比較は未確認である。Webで選べる学習モデルはM6の3形式。今回の自己対局モデルは研究・再開用stateとして公開しており、棋力評価・変換・Webへの採用は次の判断で扱う。

全MarkdownとHF Card・運用skillsの点検記録は[全Markdown・HF Card・skillsの点検記録](P5_2_DOCUMENTATION_AUDIT.md)を参照。P5-2の結果・費用・限界を共有し、ユーザー指定の区切りで停止する。P5-3・DDP・Phase6を自動で開始しない。
