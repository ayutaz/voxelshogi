---
name: hf-publication
description: VoxelShogiのHugging Faceリポジトリ作成とデータセット・モデル公開に使う。voxelshogi名前空間、public/manualの取得申請ゲート、Community OFF、Dataset Card、外部Linuxからの転送・hash照合とMacの保存制限を守る。
---

# VoxelShogiのHF公開

- 公開先は`https://huggingface.co/voxelshogi`配下。`dataset`と`model`を区別し、`private=false`・`gated="manual"`を設定する。manualはHFの**取得申請を人が承認する設定**であり、アップロード前の承認とは別。ユーザーが別の意味を指定した場合は、その指示を優先して設定を更新する。
- Community（Discussions／Pull Requests）はOFFにする（`discussionsDisabled=true`）。public/manualと合わせ、生成前のrepo準備・送信前・転送後に確認する。一般的な403を無効状態の証拠にしない。
- データ公開にはrootの`README.md`をDataset Cardとして必ず書く。HFのYAMLメタデータ（license・configs・実際のsplitとファイル）と本文を用意し、生成元commit／ruleset／schema／seed・探索条件、config別の対局数・行数・重複除外数・教師数、分割方法、列の意味と読み込み例、用途・制約・重複や不完全教師、検証・再生成とhash、取得条件・ライセンス・帰属を記載する。試料を本生成や学習済みモデルと呼ばない。数字・列名はmanifest・検証結果・データ契約と照合する。本文はハーネスの4節（`Generation and provenance`、`Usage and schema`、`Verification`、`Access and license`）にまとめ、空欄を残さない。意味の正しさは人が読める内容としてレビューする。
- ユーザーの既存の作成・公開指示を再承認待ちにしない。ただし対象データ／モデルのライセンスが未確定なら、カード・検証・ファイル一覧を用意してから確認する。コードやM3のライセンスを新しいデータ・学習済みモデルへ流用しない。
- 読み取り確認には接続済みHFツールを優先し、認証アカウント・組織所属・対象repoを確かめる。外部ホストの転送に必要な権限は、そのホストで使う認証でも確認する。別ユーザー名前空間へ代替公開しない。
- 作成・アップロードは[公開ハーネス](../../../training/hub_release.py)を使う。[実行手順](../../../docs/HF_PUBLICATION.md)を読み、取得元の検証済みファイルからplanを作る。dry-runは外部変更なし。新規repoはpublicで作成し、manual・Community OFF設定を確認してからファイルを送る。既存private repoの公開切り替え・repo削除・アクセス申請の自動承認は行わない。
- データ生成、学習、公開用staging、アップロード、ダウンロード検証はVast.ai／CloudRiftのLinuxで行う。Macにデータセット、学習checkpoint、全モデル世代を落とさない。Macへ保存するのは必要な検証用モデルと小さいmanifest・hash・集計だけ。既存の大きいファイルはユーザーの許可なく一括削除しない。
- provider APIキーは制御側だけに置く。HF書き込み資格情報はアップロード時の環境／メモリでだけ使い、コマンド引数・履歴・ログ・plan・Gitへ含めない。転送のためにMacへデータを中継しない。
- アップロード成功だけで完了にしない。返されたHub commitへrevisionを固定し、Linux上で全ファイルのbytes・SHA-256とpublic/manual・Community OFF設定を確認する。検証済みreceiptを残してから外部作業データの整理・インスタンス終了を進める。
- HFでの取得ゲートを、別配布先やWebデモへの無断再配布で迂回しない。過去に承認済みのM3配布は固定記録として扱い、新しい学習済みモデルの配布条件を別に決める。

ハーネスは送信先・ライセンス・ファイル一覧・hash・実行OS・Hub設定を検査する。生のAPIや別ツールを使った操作までOSレベルで禁止するものではないため、repo作成とアップロードの経路をこの手順へそろえる。ローカル純粋テストと既知変異は通常CIで実行し、実アップロードをCIのテストとして走らせない。
