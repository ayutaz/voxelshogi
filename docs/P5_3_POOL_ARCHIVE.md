# P5-3：中断した並列評価の保存と復元

## 目的とゴール

150局の比較を時間上限のある実機で続行できるよう、停止したpoolの確定済み指し手と先後の進捗を保存する。1局面の黒側だけ確定した場合も、元ファイルのbyte・hashを保持し、未完了の白側だけを再開する。目標の5 cohort・75 opening-pair・150局を、途中で完了した件数へ縮めない。

[実装](../training/evaluation_pool_archive.py)は固定plan、全cohortのprotocol、各jobのreceiptと棋譜を検査する。未知のjob、protocol・hash・runtime不一致、作成結果不明／生存中の子、symlink、検証中のreceipt変更を拒否する。空のpoolを成功したdatasetにしない。metadata／fake portsはMacの軽量テスト、実Parquet・Rust再生・subprocessでの再開はLinuxのNativeテストへ分ける。

## 停止・保存・HF転送

1. `run_case_plan`に停止を伝え、所有する子を回収してpoolのleaseが解放されるまで待つ。未完了対局を打切りの棋譜として確定させない。
2. Linuxで`pack_pool(pool, archive, expected_plan=plan, owner=owner)`を呼ぶ。`owner`は制御側がAPIで確認した`provider="vast.ai"`・`instance_id`・専用`tag`の3項目である。
3. 元のJSON bytesを`pool.parquet`の`path:string`・`data:binary`へ保存し、全件roundtrip、各memberのbytes／SHA-256と全確定棋譜のRust再生を確認する。checkpoint・モデル・ログ・資格情報は含めない。過去の起動観測はmetadataとして保持する。
4. Dataset Cardの4節、実source・plan hash・確定数／目標数・列の意味・復元方法・制約とCC-BY-4.0のLICENSEを用意する。公開先は`voxelshogi/voxelshogi-generation-evaluation-resume-v1`。既存[HF公開ハーネス](HF_PUBLICATION.md)でpublic/manual・Community OFFを確認し、Linuxから転送、返った固定revisionで全bytes／hashを照合する。
5. 検証済みreceiptを制御側へ回収し、旧実機の削除ACKと全件一覧での不在を確認する。Macへ回収するのは小さいmanifest・Card・receiptだけで、Parquetを中継しない。

archiveは再開用であり、全棋譜が入っても`pipeline_complete=false`のままとする。cohortの最終集約、全学習入力との重複監査、世代比較の最終reportは別に行う。8局試行を150局へ混ぜない。

## 別の所有実機で復元する

固定revisionの公開plan／receiptを検証して取得したarchiveと、元と同じ全planを使う。制御側で旧実機の削除を実際に確認し、次の情報を凍結したworkloadへ結ぶ。

- `parent_release.owner`はarchiveの旧ownerと一致する。
- `destruction_acknowledged=true`と`inventory_absent=true`は実APIの応答と完全な一覧確認に基づく。`evidence_sha256`はその制御記録のhashであり、空欄を埋めるための任意文字列ではない。
- `current_owner`はAPIで確認した別の所有instanceである。providerキーをLinuxのデータ処理hostへ渡さない。libraryは制御側のprovider照合を代行しない。

Linuxで`restore_pool(archive, new_pool, expected_plan=plan, artifacts=artifacts, parent_release=proof, current_owner=owner)`を呼ぶ。移動したモデルのpathはcohort／roleごとの絶対pathで渡し、固定重みのhashと実行source・runtimeを確認する。runtimeが異なれば新しい対局の前に拒否する。

確定棋譜の元byteを新しいpoolへ復元し、古いPIDは`restoration.json`内の履歴にだけ残す。新しい`launches/`へ旧PIDを復元しない。その後、`run_case_plan(plan, artifacts, new_pool, resume=True)`で欠けた仕事だけを実行する。現在生きているpoolを複製して2重に走らせる操作には使わない。同じ実機・同じpoolの通常再開は既存の`run_case_plan(..., resume=True)`を使う。

## 検証の範囲

[metadataテスト](../training/tests/test_evaluation_pool_archive.py)は4局目標のうち後半局面の黒側1局を確定させ、全planと元byteの維持、未知の起動・不一致・空集合の拒否を独立した入力で確認する。偽のportが成功してもRust実行の証拠とはしない。

[Linux Nativeテスト](../training/tests/test_evaluation_pool_archive_native.py)は実Rustの片色中断→Parquet→別ownerへの復元→実subprocess poolで残り3局を実行する。完了時は手計算の4局＝1勝1敗2打切りとなり、元の黒側ファイルのSHAが変わらないことを確認する。改変Parquet、重複／foreign member、coverage・plan・release・runtime不一致と使用中leaseも拒否する。このCI検証を実GPUの150局や並列性能の完了とは扱わない。
