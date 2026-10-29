# M6のGPU利用・保存・公開の具体案

2026-10-29 07:03 UTCの読み取り調査。**以下は未承認の提案で、M6のレンタル・実学習・モデルrepo作成は未実施。** HF資格情報の一時送信・アップロードの継続承認はそのまま使う。[M6計画](M6_PLAN.md)の完了条件に従う。

## GPUと上限

CloudRift米国の`rtx59-3-24-750-xam.1`、RTX5090×1、RAM24 GiB、ローカルdisk約750 GiBを候補にする。公式APIは100 cents/時＝**US$1/時**、空き1台、public IP対応。48 GiB版は同単価で空き0台。空きは予約ではなく、起動直前に条件を再確認する。値上がりしたら起動しない。

M6専用の提案総枠は**GPU24時間・US$24まで**。最初の試行は環境構築・固定データ監査・cache作成・少量CUDA学習と再開・退避復旧を含めて最大4時間／US$4とし、総枠に含める。本学習・固定評価・全3変換・実ブラウザ検証・HF転送は、試行の実測で見積もり直してから、残り20時間／US$20以内で実施できる設定を選ぶ。24時間で完了するという予測ではない。足りなければ未完了の状態を保持して停止し、追加課金しない。

各レンタルの上限を累積ledgerへ予約し、外部guardianを起動してから課金操作をする。終了・退避の余裕を設けて計算を止め、実機終了とresources releasedを確認する。開発・CI待ちでGPUを保持しない。M4の過去の予約上限US$41と合算するとUS$65だが、M4承認をM6へ転用しない。実請求と予約上限は別に記録する。

[M6専用の起動制御](M6_RENTAL_CONTROL.md)で、M4の24時間quoteを試行へ流用しないこと、用途別／全体の累積上限、mainの実測report hash、M6のtagを持つguardianのreadyを検査する。実行用の承認記録はまだ作成していない。

## 外部保存

CloudRiftの永続volume種別は現在空のため、永続volumeは使わない。Macへcheckpointを落とさず、[JSON＋safetensorsの再開archive](M6_RESUME_ARCHIVE.md)を外部LinuxからHFへ直接保存する案とする。

候補repoは`voxelshogi/voxelshogi-transformer-s-training-state`、**public/manual・Community OFF**。optimizer・乱数・学習位置・latest/best・構造化した学習履歴を、再現実験に必要な公開成果物としてCardに明記する。公開モデルの`voxelshogi/voxelshogi-transformer-s`とは分ける。pickle／`.pt`、生ログ、資格情報、`.env`、providerキーは送らない。この再開状態の公開方針は別に確定し、通常モデル用ハーネスの拒否を無効化して送らない。

GPU終了前に固定Hub revisionの全bytes・SHA-256を照合し、新しいLinux runへ再取得・復元して継続結果を比較する。小さい単体テストを外部復旧の証拠に置き換えない。試行用と本学習のlatest/bestに絞り、新規アップロード総量は履歴分も含め1 GiBを上限とする。最終状態は再現実験用に保持し、容量上限に達したら削除・履歴書き換え・有料追加をせず止める。

保存費案は**有料追加なし（US$0）**。[HF公式public storage](https://huggingface.co/docs/hub/main/storage-limits)はfree account/orgでbest-effortのため、容量保証・永続性保証とは扱わない。無料枠で受け付けられない場合はGPU起動前に保存方法を再検討する。研究成果の再利用を目的とし、全epochやデータを重複保存しない。

## ライセンスとCard

学習済みモデルと再開状態の自作成果物は**Apache-2.0を提案**する。コードやM3の未学習モデルの許可が自動適用されたとは扱わない。M4データのCC-BY-4.0・生成commit・固定revision・帰属は両Cardへ記載する。

Model Cardには学習設定・教師splitの実集計・seed・コード・依存、初期モデルとの同じ評価集合での損失比較、固定test、Random40局／M1探索20局、cutoffを分けた生カウントとpaired区間を記載する。FP32・FP16・INT8重み版の実ファイルhash・数値差・精度・棋力・対応backend・性能を示し、基準未達も残す。再開用Cardはarchive schema、step・epoch、固定入力・元checkpoint／archive hash、復旧手順と一致結果、公開範囲を記載する。未測定値を埋めず、実測後に完成させて公開する。

## M6-5への接続

取得承認済みの利用者がHFから取得したモデルフォルダーを選ぶ。ONNXと同形式の照合入力／全出力を専用Workerで検査してから、両AIに各形式を選べるようにする。公開catalogは小さい識別情報とhashだけで、重みをCloudflareへ複製しない。各実行可能版をそのまま試せ、unsupportedの形式／backendは理由を表示する。実GPUブラウザでWebGPUと3Dの同時動作、公開E2Eと配信SHAまで照合してM6-5を完了とする。

必要な判断は、M6専用US$24の上限、両成果物のApache-2.0、再開状態を上記別repoへpublic/manualで公開する方針の3点。確定後は同目的・上限内の各操作やHFトークン引き渡しごとに再承認を求めない。
