# M6のVast.aiへの切替

目的は、CloudRiftの既知RTX5090構成に空きがないときも、承認済みのVast.aiでM6の変換・評価・実機検証を続けること。**この制御の単体テストは料金・metadataの検査であり、Vast.aiの実機を借りた証拠ではない。** 実機の認証・残高・在庫・CUDA・ブラウザはレンタル時に別途確認する。Macで計算へ切り替えない。

## 構成と上限

[制御コード](../training/vast_rental_control.py)は、同じM6承認検査と累積ledgerを使う。既存US$100内のM6基本枠US$24、次の実行の最大4時間／US$4を維持する。不足時追加US$100は有効化しない。レンタル前に次を実際のofferから検査する。

- RTX5090×1、VRAM30,000 MB以上、ホストRAM24,576 MB以上、実効CPU6以上。CUDA13対応・driver580以上、検証済みホスト・reliability2 0.99以上、直接SSHポートがある。
- 必須の一時ディスク80 GBを検索・作成の両方へ指定する。単価は`max(dph_total, dph_base + storage_total_cost)`で保守的に採り、ディスク込みUS$1/時以下。別の永続volumeや予約払いは追加しない。
- up/downの転送単価がどちらも0のofferだけを受け付ける。有料・不明の転送料金をこの固定見積もりへ暗黙に含めない。対象がなければ、料金条件を再計算してから制御を変更する。
- on-demand、`cancel_unavail=true`。作成直前に同じofferを再取得する。CloudRiftの稼働中VoxelShogi実機と、Vast.aiの停止中を含む既存VoxelShogiインスタンスがないことも確認する。
- 認証アカウントIDを固定し、残高が4時間分の実単価を賄えることを確認する。APIキーやアカウントのSSH鍵を保存・出力しない。停止・削除の確認時も同じアカウントを要求する。

イメージはNVIDIA公式`13.0.0-cudnn-devel-ubuntu24.04`のLinux amd64 digest `sha256:e3fd439288969c0c78d52768cda4a10ab20f408180d6fa2933f94f7af7810cb0`を固定する。2026-10-29 UTCに[Docker Hubのtag metadata](https://hub.docker.com/v2/repositories/nvidia/cuda/tags/13.0.0-cudnn-devel-ubuntu24.04)で存在・architecture・digestを確認した。`NVIDIA_DRIVER_CAPABILITIES=all`を要求するが、指定しただけで物理WebGPU／WebGL対応済みとはしない。host driverの更新は行わず、起動後の[CUDA検査](M6_CUDA.md)と[ブラウザ基礎検査](M6_TRIAL.md)を実行する。

## ローカル制御と外部Linuxの役割

ユーザーがプロジェクトの`.env`へ`VAST_API_KEY`を保存する。キーはMacの制御プロセスが公式`console.vast.ai`のAuthorization headerでだけ使用し、URL・引数・ログへ入れない。redirectは拒否する。CloudRiftキーは同社APIの稼働確認にだけ使う。どちらのproviderキーもGPUへ渡さない。

```bash
# 料金・metadataの読み取りだけ。受理できるofferのIDと単価を保存する。
uv run --locked python -m training.vast_rental_control runs/m6/vast-control search
# 同じフォルダーに専用id_ed25519.pubを用意してから、選択した実offerを指定する。
uv run --locked python -m training.vast_rental_control runs/m6/vast-control rent --offer OFFER_ID --approval runs/m6/retry-approval.json
uv run --locked python -m training.vast_rental_control runs/m6/vast-control attach-key
uv run --locked python -m training.vast_rental_control runs/m6/vast-control status
# HF退避と全hash照合後、その所有実機だけを削除する。
uv run --locked python -m training.vast_rental_control runs/m6/vast-control terminate
```

上記のMac実行はAPI・ledger・SSH制御だけ。データ取得・cache・学習・全評価・変換・HF公開・実機計測はVast.aiのLinux内で行う。Python3.14.9とCUDA用lockを維持し、HF credentialは必要時のSSH標準入力から環境／メモリだけへ渡す。

課金APIを呼ぶ前に共有ledgerを予約し、独立した終了guardianのPID／deadline hash／readinessを照合する。Macはそのguardianの存命中だけcaffeinateでアイドル休止を抑止する。上限15分前からcleanupを開始し、終了未確認のまま期限を過ぎても再確認を続ける。CI待ち・開発待ちのために実機を保持しない。

作成APIの応答が途切れた場合は、保存したrequestと完全一致の専用labelから同じ実機を調べる。新しい作成リクエストを重ねない。`new_contract`をIDとして固定し、受信した一般的な`id`へ取り違えない。専用の公開SSH鍵だけを作成したDocker instanceへattachし、他の既存インスタンスへ鍵を一括登録しない。

Vast.aiの`stopped`／`exited`はディスク料金終了の証拠にしない。HF退避・固定revisionの全hash・復旧可能性を確認後、IDとlabelと認証アカウントが一致する自分の実機だけをdestroyし、完全なページ付き一覧から消えたことを確認する。一覧は現行の`GET /api/v1/instances`を使い、ページ数・件数・cursorの不一致を拒否する。status保存はID・label・状態・SSH接続先だけとし、Jupyter token等は保存しない。

## 検証

Macはモデルを動かさず、手書きprovider／料金／ledgerのfixtureで新41件、既存のM6承認・終了制御30件、計71件を確認する。新9変異と、共有化した既存承認検査6変異も実行時の失敗で検出した。全Python・モデル・Web・E2Eは必須Linux CIで検証する。API認証や実GPUの実測値へ読み替えない。

一次資料：[検索とallocated_storage](https://docs.vast.ai/api-reference/search/search-offers)、[作成](https://docs.vast.ai/api-reference/instances/create-instance)、[現行のページ付き一覧](https://docs.vast.ai/api-reference/instances/show-instances)、[instanceへのSSH鍵attach](https://docs.vast.ai/api-reference/instances/attach-ssh-key)、[destroy](https://docs.vast.ai/api-reference/instances/destroy-instance)、[料金と停止中のディスク課金](https://docs.vast.ai/guides/instances/pricing)。
