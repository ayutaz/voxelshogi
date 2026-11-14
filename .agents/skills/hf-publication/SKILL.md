---
name: hf-publication
description: VoxelShogiのHF公開・取得条件の更新に使う。S推論用はpublicで申請不要、その他はmanual、Community OFFと来歴・hash・Card・Mac保存制限を守る。
---

# VoxelShogiのHF公開

- 公開先は`https://huggingface.co/voxelshogi`配下。通常は`private=false`・`gated="manual"`。**2026-11-14の明示指示により、既存の`voxelshogi/voxelshogi-transformer-s`推論用だけは`gated=false`とし、Webから誰でも申請・ログインなしで使えるようにする。** [承認記録](../../../export/public-s-approval.json)とハーネスの`public-s-inference-v1` profileを使う。データセット・再開state・Mモデルへ例外を広げない。manualは取得申請の承認方式であり、アップロード前の承認とは別。
- Community（Discussions／Pull Requests）はOFFにする（`discussionsDisabled=true`）。対象profileの取得条件と合わせ、repo準備・送信前・転送後に確認する。一般的な403を無効状態の証拠にしない。
- データ公開にはrootの`README.md`をDataset Cardとして必ず書く。HFのYAMLメタデータ（license・configs・実際のsplitとファイル）と本文を用意し、生成元commit／ruleset／schema／seed・探索条件、config別の対局数・行数・重複除外数・教師数、分割方法、列の意味と読み込み例、用途・制約・重複や不完全教師、検証・再生成とhash、取得条件・ライセンス・帰属を記載する。試料を本生成や学習済みモデルと呼ばない。数字・列名はmanifest・検証結果・データ契約と照合する。本文はハーネスの4節（`Generation and provenance`、`Usage and schema`、`Verification`、`Access and license`）にまとめ、空欄を残さない。意味の正しさは人が読める内容としてレビューする。
- ユーザーの既存の作成・公開指示を再承認待ちにしない。ただし対象データ／モデルのライセンスが未確定なら、カード・検証・ファイル一覧を用意してから確認する。コードやM3のライセンスを新しいデータ・学習済みモデルへ流用しない。
- 読み取り確認には接続済みHFツールを優先し、認証アカウント・組織所属・対象repoを確かめる。外部ホストの転送に必要な権限は、そのホストで使う認証でも確認する。別ユーザー名前空間へ代替公開しない。
- 作成・アップロードは[公開ハーネス](../../../training/hub_release.py)を使う。[実行手順](../../../docs/HF_PUBLICATION.md)を読み、取得元の検証済みファイルからplanを作る。dry-runは外部変更なし。新規repoはpublicで作成し、manual・Community OFF設定を確認してからファイルを送る。既存private repoの公開切り替え・repo削除・アクセス申請の自動承認は行わない。
- データ生成、学習、公開用staging、アップロード、ダウンロード検証はVast.ai／CloudRiftのLinuxで行う。Macにデータセット、学習checkpoint、全モデル世代を落とさない。Macへ保存するのは必要な検証用モデルと小さいmanifest・hash・集計だけ。既存の大きいファイルはユーザーの許可なく一括削除しない。
- 2026-10-28の継続承認により、承認済みVoxelShogiのHF公開に必要なHF CLI認証の一時送信・HFへのアップロードは都度確認しない。管理下のVast.ai／CloudRift実機へのSSH標準入力による引き渡し、同目的・承認済み予算内の所有実機の置き換え・再接続も対象。環境／メモリだけで使い、値を保存しない。認証アカウント・所有先・公式HF宛先・成果物のライセンス・予算・設定は実際に確認し、別目的や別サービスへの送信許可に拡大しない。
- provider APIキーは制御側だけに置く。HF書き込み資格情報はアップロード時の環境／メモリでだけ使い、コマンド引数・履歴・ログ・plan・Gitへ含めない。転送のためにMacへデータを中継しない。
- アップロード成功だけで完了にしない。返されたHub commitへrevisionを固定し、Linux上で全ファイルのbytes・SHA-256とpublic/manual・Community OFF設定を確認する。検証済みreceiptを残してから外部作業データの整理・インスタンス終了を進める。
- Model Cardは人間向けに簡潔にする。Sは[短いカード](../../../export/public-s-model-card.md)を原本とし、遊び方・学習元・形式別容量と教師一致率・棋力の制約・利用条件を優先する。詳細hash・構造・評価条件はmanifestと固定記録へリンクする。
- 既存Sの取得設定と小さいCardだけの変更は[専用ハーネス](../../../training/public_s_release.py)を使う。Macでは既存重みをstage／取得せず、このメタデータだけを更新できる。親HF commitを固定し、別アカウント・private repo・変更済み親revisionを拒否する。その後、外部Linux／GitHub Actionsで匿名取得と全37ファイルのhashを検査するまで配布完了とはしない。
- manual対象の取得ゲートを、別配布先やWebデモで迂回しない。Sは上記の明示承認に基づく直接HF取得とする。過去のM3配布・旧Sのmanual公開は履歴として保持する。

ハーネスは送信先・ライセンス・ファイル一覧・hash・実行OS・Hub設定を検査する。生のAPIや別ツールを使った操作までOSレベルで禁止するものではないため、repo作成とアップロードの経路をこの手順へそろえる。ローカル純粋テストと既知変異は通常CIで実行し、実アップロードをCIのテストとして走らせない。
