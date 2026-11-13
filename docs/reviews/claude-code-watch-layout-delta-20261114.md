# 中断ボタン固定のClaude Code差分レビュー

source `35ff493`のAppと差分をReadで確認した原文。画像・実機を再確認したものではない。E2Eのscroll anchoringに関する指摘は、後続でwindow.scrollYとmain.scrollTopの固定も検証するよう補った。CIの結果は[公開確認](../PUBLIC_LAUNCH_PROGRESS.md)を参照。

**結論**：fix.diffとApp.tsxを読んだ範囲では、P1の原因は解消されています。原因は、思考中だけ`cancel-search`をマウントしていたことでした。修正後は、ボタンが常に`ai-step`と同じ`.row`内にあります（`App.tsx:345-346`）。思考中かどうかで変わるのは`ai-phase`の文言だけです。テストの実行、実画面、実スマホでの確認はしていません。

**中断できる条件とfocus**
- 中断できるのは従来どおり思考中（`phase==='thinking'`）だけです。`onClick`のガードと`aria-disabled`が同じ条件を使っています。
- `disabled`ではなく`aria-disabled`なので、中断後も同じ要素が残り、focusは失われません。単体テストの`toBe(interrupt)`がこれを確認しています。
- 押せない時の見た目はCSS次第ですが、CSSは今回読んでいないため確認していません。

**テストが空の観測で通らないか**
- **単体**：旧コードでは最初の`getByTestId`で失敗します。ガードを外せば`not.toHaveBeenCalled`で、属性を外せば`aria-disabled`の検証で失敗します。前提は、`fake.paused`の呼び出し記録がテスト間でリセットされることです。リセットされない場合も、テストが失敗する側に倒れます。
- **E2E**：思考中の記録1件以上、`次の着手待ち`の記録2件以上、合計3件以上を必須にしているので、観測が空なら通りません。座標はMutationObserverのコールバック内で`getBoundingClientRect`を呼んで測るので、同じ描画の結果を読めます。旧コードなら約35pxの差を検出できるはずです。
- **E2Eの弱点**：座標が画面基準なので、スクロール位置が0でないと、ブラウザのscroll anchoringがずれを打ち消す余地があります。`scrollY`も記録して一定かを確認すれば、この穴は塞げます。
- `scripts/ci/mutation-web.mjs`の変更はfix.diffに含まれていないため見ていません。

**CIで残る確認**
- Linuxの実NormalでこのE2Eが通ること。
- 思考中の記録が実際に取れていること。Workerの応答が速すぎて記録が抜けた場合も、テストは失敗する側に倒れます。
- 分析文の折り返しで誤って失敗しないこと。

なお、モデル対Normalの対局では分析欄が4行と3行で交互に変わります。これはこの差分とE2Eの対象外です。
