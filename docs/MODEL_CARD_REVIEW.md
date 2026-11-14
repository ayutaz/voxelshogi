# S Model Cardの見直し

2026-11-15 JST。目的は、モデルを初めて見る人が用途・使い方・評価をすぐ把握できる説明にすること。ゴールはHFへの反映、公式metadata検査、匿名README照合、他ファイルと公開設定の不変確認。すべて完了した。

## 参考にしたカード

- [HF公式Model Cardsガイド](https://huggingface.co/docs/hub/model-cards)：概要・用途・学習・評価・制約とmetadataの役割。
- [HuggingFaceTB/SmolVLM-256M-Instruct](https://huggingface.co/HuggingFaceTB/SmolVLM-256M-Instruct)：冒頭のモデル説明、概要・使い方・学習・評価を順に案内する構成。
- [google/vit-base-patch16-224](https://huggingface.co/google/vit-base-patch16-224)：モデル説明、使い方、学習・評価情報を分ける構成。
- [amanm10000/chess-policy-net](https://huggingface.co/amanm10000/chess-policy-net)：同じpolicy/value系ゲームモデルとして、合法手選択・棋力と模倣精度の違いを説明する構成。

文章やベンチマークは転用せず、Sのmanifest・固定評価に照合して書き直した。

## 修正した点

旧版は学習の来歴が使い方より先にあり、英語見出しと日本語本文、公開作業の説明が混在していた。新しい[Card](model-cards/transformer-s.md)は日本語の見出しで概要表とWebの入口を先に置き、形式・評価・学習・制約・ライセンスへ続ける。Community設定・今回重みを変更していない旨・旧Cardへの案内は本文から外した。

非言語のpolicy/valueモデルなので、自然言語の対応言語と誤読される`language: ja`は外し、実際の学習datasetをmetadataへ追加した。ONNXモデルであり、汎用Transformers pipelineの動作例は掲載しない。容量と速度、教師一致率と勝率、FP16／INT8重みとFP32演算を区別し、未実証の強さは主張しない。

## 反映と確認

既存の`PublicationApi.commit_public_s_card`を使い、READMEへだけ送った。今回の用途にも合うよう、同adapterのHF commit説明文を一般的なCard更新の表現へ変更した。送信内容・設定の動作は変えていない。

ログイン済みアカウントと組織、既存公開planと親revisionを確認。送信前後の38項目のsize・Git blob ID・LFS hashを比較し、差分がREADMEのみであることを確認した。変更したREADMEは認証なしで取得してbytes／SHA-256が一致し、public・gateなし・Community OFFも維持。HF公式のModelCard.validateと既存公開ハーネスの単体10件が成功した。モデル本体はMacへ取得していない。

Webは引き続き`6ab524574d36536348dbe323a2b779b9cebe37ed`の検証済みパッケージと旧Card hashを参照する。`export/public-s-model-card.md`はその固定版用の原本なので保存する。表示用Cardの編集更新と、推論パッケージの更新を区別し、新しいrevisionの全モデルを再ダウンロードしたとは扱わない。アプリの再デプロイや動画の再制作は不要である。

```json
{
  "schema": 1,
  "kind": "public-s-editorial-card-update",
  "repo": "voxelshogi/voxelshogi-transformer-s",
  "parentRevision": "6ab524574d36536348dbe323a2b779b9cebe37ed",
  "revision": "3ec81d037ee78e801838a185c0c2f9689e5a7dc6",
  "cardSource": "docs/model-cards/transformer-s.md",
  "cardBytes": 3569,
  "cardSha256": "63d31728337903d673878ae20ded554b7322ed8d156ad6c475a1b43d75162c9a",
  "metadataOnly": true,
  "verified": true,
  "recordedAt": "2026-11-14T16:38:49.622259+00:00",
  "browserPackageRevision": "6ab524574d36536348dbe323a2b779b9cebe37ed",
  "anonymousCardReadback": true,
  "changedPaths": [
    "README.md"
  ],
  "unchangedOtherEntries": 37,
  "private": false,
  "gated": false,
  "communityDisabled": true,
  "modelFileMetadataUnchanged": true
}
```
