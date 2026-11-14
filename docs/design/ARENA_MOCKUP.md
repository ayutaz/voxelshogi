# 観戦画面の操作モック

2026-11-14。現行問題と設計意図は[UI/UXレビュー](SPECTATOR_UX_REVIEW.md)。**本番のUI変更・新機能の完成物ではなく、配置と操作を比較する提案**。HTMLは外部依存・モデル・API接続なしで開ける。上部の「画面例」で初回／観戦中／停止／履歴／終局例／モデル失敗例を切り替える。

ユーザー承認済み。[本番実装の目的・ゴール・PR分割](ARENA_IMPLEMENTATION_PLAN.md)へ進む。以下は承認したモックの確認範囲であり、本番の達成結果ではない。

## 見られること

- 9層の全体像を入口にし、立体を眺める表示と断面を読む表示を切り替える。3D部分はSVG投影の図解で、現行WebGLの描画結果ではない。
- 実際のEasy対局6手を再生・停止・前後送りし、層の移動元と先を文字・形で追う。層を手動選択すると追従OFF、ONで着手先へ戻る。
- 対局設定、モデル案内、棋譜、狭幅用の断面／履歴シートを開く。ユーザーの追加指定により送信の表示とON/OFF切替を置かず、自動保存を前提とする。モックはAPI未接続で、実データを収集しない。
- 上部の「AIと対戦」→先手／後手・相手AI→「対戦をはじめる」で対戦画面の例へ進む。中央V層の2D盤と自分／AIの手番を表示する。AIを観戦へも戻れる。
- 人間対AIは導線・画面だけのモックで、実際の着手・合法手・成り・持ち駒・AI応答は未接続。全表示設定・研究ログも未接続。対戦画面ではAI同士の参考棋譜やその保存を隠す。
- 終局例は架空のレイアウト状態と明記する。参考6手の実際の終局や、棋力・勝率の証拠にしない。

## 開く方法

所有者向けHTMLは`runs/ux-review-20261114/spectator-mockup.html`へ書き出した。別のcheckoutでも次の標準Nodeだけで再生成できる（モデルや依存追加は不要）。生成したHTMLをブラウザで開く。

```sh
node --input-type=module <<'JS'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
const text = readFileSync('docs/design/ARENA_MOCKUP.md', 'utf8');
const html = text.split('```html\n')[1].split('\n```')[0];
mkdirSync('runs/ux-review-20261114', { recursive: true });
writeFileSync('runs/ux-review-20261114/spectator-mockup.html', html + '\n');
JS
```


## 追加指定の反映

「研究用Alpha・PC推奨・スマホ未確認」と送信状態のフッターを削除し、ヘッダーのAlphaバッジも除いた。「棋譜」はヘッダーから開き、端末へのダウンロードだけを扱う。送信状態・ON/OFF・同意フォームを観戦画面やシートへ置かない。

ユーザー指定は「データ送信は常にON、画面上の説明は不要」。本実装では棋譜を自動保存する方式に変更する。公開中のサービスは今回変更しておらず、現行の任意送信APIを実際に切り替えたという意味ではない。

## 確認した範囲

表示削除後のHTMLをjsdomで読み込み、フッター文言・送信表示・切替が残っていないこと、初回／観戦中／停止／履歴／終局例／エラー例の全6状態、設定と再開、棋譜シート、履歴を見ていても全6手を保存することを確認。runtime error 0。

旧稿の62 assertionsと3変異検出は、[レビューと改稿履歴](SPECTATOR_UX_REVIEW.md)に対象版を残す。削除した同意フォームの旧テストを現行モックの成功へ数えない。実ブラウザの描画・寸法、実スマホ、実AIと自動保存APIは未検証。

```json
{
  "kind": "mock-human-entry-check",
  "at": "2026-11-14T02:53:44.398Z",
  "bytes": 31893,
  "sha256": "c3d4fc219a2e12bbf5d5f754d76843de02a2022036c8d16b6b684a67e2d8b3b4",
  "checks": [
    "watch/human entry and setup visible",
    "human settings routes to same setup",
    "duplicate unconnected mode selector removed",
    "return to watch without runtime errors"
  ],
  "runtimeErrors": 0,
  "priorCoreCheck": {
    "kind": "mock-human-entry-and-core-ui-check",
    "at": "2026-11-14T02:52:57.959Z",
    "bytes": 31919,
    "sha256": "55926cf43770e1fe095cc1818127a6360c4c5660ce458ebb904a1f0d76e98ca3",
    "checks": [
      "two visible entry buttons",
      "human setup defaults and start",
      "human black/white and opponent seat labels",
      "human board centered on V layer",
      "reference replay/export hidden in human screen",
      "return to watching",
      "six watch scenarios and full-record export",
      "removed footer/submission UI remains absent"
    ],
    "runtimeErrors": 0,
    "scope": "jsdom only; human screen is a layout example, with no legal-move engine or AI connection; real browser layout and automatic upload unverified"
  },
  "scope": "jsdom only; actual human legal moves/AI and browser layout are not connected/verified"
}
```


人間対AIの入口追加では、先後・相手AIの選択と対戦画面例への遷移、対局設定から同じ設定画面へ戻ること、観戦への復帰、既存の参考棋譜を対戦棋譜と誤認させないことを軽量確認した。描画寸法と実際の人間対AIは本実装で検証する。

## モックのHTMLソース

設計文書の添付ソース。アプリの公開コードへは未接続。

```html
<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; connect-src 'none'; font-src 'none'"><title>VoxelShogi — 観戦画面のデザインモック</title>
<style>
:root{color-scheme:dark;--bg:#10191c;--surface:#19262a;--line:#34474b;--ink:#f1f4f0;--sub:#adc2c5;--mint:#a3e8d1;--gold:#ffd18b;--wood:#e4d0ad;font:15px/1.5 system-ui,-apple-system,'Hiragino Sans','Yu Gothic',sans-serif}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink)}button,select,input{font:inherit}button,select{border:1px solid var(--line);border-radius:9px;background:transparent;color:var(--ink);padding:9px 13px;min-height:44px;cursor:pointer}button:hover:enabled{background:#253b40}button:disabled{opacity:.4;cursor:default}button:focus-visible,select:focus-visible,input:focus-visible,a:focus-visible{outline:3px solid var(--gold);outline-offset:3px}button[aria-pressed=true]{background:#31584f;color:#e6fff6;border-color:#8bd4bd}button.primary{background:var(--mint);color:#102d25;border-color:var(--mint);font-weight:750}button.primary:hover:enabled{background:#c0f4e3}button.quiet{border-color:transparent;color:var(--sub)}p,h1,h2,h3{margin:0}a{color:var(--mint)}small,.sub{color:var(--sub);font-size:12px}.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}[hidden]{display:none!important}.designbar{background:#ded6c5;color:#253238;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:6px 24px;font-size:12px}.designbar select{color:#253238;background:#f1ece2;font-size:12px;min-height:32px;padding:3px 8px;border-color:#a6a59c}.designbar label{display:flex;align-items:center;gap:7px}.shell{max-width:1512px;margin:auto;padding:0 28px}.masthead{height:68px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line)}.brand{font-size:20px;font-weight:800;letter-spacing:-.6px}.brand span{color:var(--mint)}.nav{display:flex;gap:7px}.nav button{font-size:13px}.intro{display:flex;justify-content:space-between;align-items:end;gap:20px;padding:22px 0 18px}.intro h1{font-size:clamp(20px,2.2vw,30px);letter-spacing:-.7px}.intro p{margin-top:5px;color:var(--sub);font-size:13px}.tinylabel{font-size:11px;letter-spacing:1.6px;color:var(--mint);font-weight:700}.agents{display:flex;justify-content:space-between;align-items:center;gap:16px;min-width:220px}.agent{font-size:14px;white-space:nowrap}.agent b{display:block;font-size:16px}.agent .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:var(--gold)}.agent.white .dot{background:#d5e7ed}.versus{color:var(--sub);font-size:11px}.workspace{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:24px}.arena{min-width:0}.stagehead{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.viewbuttons{display:flex;gap:5px}.viewbuttons button{min-height:36px;padding:5px 11px;font-size:12px}.state{color:var(--mint);font-size:12px;font-weight:650}.stage{height:clamp(360px,calc(100svh - 310px),590px);position:relative;background:radial-gradient(ellipse at 50% 40%,#233c40 0%,#142226 65%);border:1px solid var(--line);border-radius:14px;overflow:hidden}.stage svg{width:100%;height:100%;display:block}.stage .stagehint{position:absolute;left:17px;top:14px;font-size:11px;color:var(--sub)}.reference{position:absolute;left:17px;bottom:13px;font-size:11px;color:var(--sub)}.rail{position:absolute;right:12px;top:50%;transform:translateY(-50%);display:flex;flex-direction:column;gap:3px}.rail button{width:36px;min-height:32px;padding:3px;font-size:11px;border-color:transparent;border-radius:6px}.rail button[aria-pressed=true]{border-color:var(--mint)}.movebar{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:13px 2px;min-height:76px}.movebar h2{font-size:17px}.movebar p{font-size:12px;color:var(--sub);margin-top:2px}.follow{display:flex;align-items:center;gap:6px;font-size:12px;white-space:nowrap}.follow input{width:19px;height:19px;accent-color:var(--mint)}.transport{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:13px 0;border-top:1px solid var(--line)}.playgroup{display:flex;gap:7px;align-items:center}.playgroup .primary{min-width:156px}.speed{display:flex;gap:7px;align-items:center;font-size:12px}.speed select{min-height:36px;padding:5px}.sidebar{border-left:1px solid var(--line);padding-left:24px;min-width:0}.sidebar h2{font-size:16px;margin-bottom:5px}.section{padding:14px 0;border-bottom:1px solid var(--line)}.section:first-child{padding-top:0}.section h3{font-size:13px;font-weight:650;margin-bottom:9px}.section p{color:var(--sub);font-size:12px}.move-route{display:grid;grid-template-columns:1fr 25px 1fr;align-items:center;gap:4px;margin:12px 0}.squarelabel small{display:block}.squarelabel strong{font-size:23px;line-height:1.2}.squarelabel.destination strong{color:var(--gold)}.mini{width:100%;display:block;margin-top:6px;max-height:249px}.layerbadge{border:1px solid var(--line);color:var(--gold);border-radius:4px;padding:2px 6px;font-size:11px}.history{list-style:none;margin:6px 0 0;padding:0;max-height:145px;overflow:auto}.history button{display:flex;align-items:center;gap:12px;min-height:32px;border:0;width:100%;border-radius:6px;padding:4px 8px;text-align:left;font-size:12px}.history button[aria-current=true]{background:#2c4544}.history .number{color:var(--sub);width:16px;font-variant-numeric:tabular-nums}.mobiletools{display:none}.message{border:1px solid #c69358;background:#31291f;padding:10px 14px;border-radius:8px;margin-bottom:12px;font-size:13px}.message button{min-height:32px;padding:3px 8px;margin-left:8px}dialog{background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:16px;width:min(520px,calc(100vw - 28px));max-height:85svh;padding:24px}dialog::backdrop{background:#050d10b8}.dialoghead{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:16px}.dialoghead h2{font-size:20px}.dialogbody{display:grid;gap:18px}.field{display:grid;gap:6px;font-size:13px}.field select{width:100%}.dialogbody p{font-size:13px;color:var(--sub)}.dialogbody .note{padding:10px 0;border-top:1px solid var(--line)}.dialogbody button{width:100%}.sheetmini{max-width:300px;margin:auto}.ended{padding:12px 0;color:var(--gold)}@media(prefers-reduced-motion:no-preference){.active-mark{animation:arrival .4s ease-out}@keyframes arrival{from{opacity:.2;stroke-width:5}to{opacity:1;stroke-width:2}}}@media(max-width:1050px){.shell{padding:0 20px}.workspace{grid-template-columns:minmax(0,1fr) 275px;gap:18px}.sidebar{padding-left:18px}.intro{align-items:center}.intro h1{font-size:23px}.agents{min-width:180px;gap:10px}.playgroup .primary{min-width:140px}.speed span{display:none}}@media(max-width:720px){.shell{padding:0 14px}.designbar{padding:5px 14px;gap:7px;font-size:10px}.designbar .designnote{max-width:185px;line-height:1.35}.designbar select{width:112px}.masthead{height:56px}.brand{font-size:18px}.nav button{min-height:36px;padding:5px 8px;font-size:12px}.nav .lab{display:none}.intro{display:block;padding:14px 0 12px}.intro h1{font-size:22px}.intro p{font-size:11px;margin-top:3px}.agents{margin-top:11px;justify-content:flex-start;gap:18px;min-width:0}.agent{display:flex;align-items:center;gap:9px;font-size:11px}.agent b{font-size:13px}.agent small{font-size:10px}.workspace{display:block}.sidebar{display:none}.stagehead{margin-bottom:7px}.stagehead .tinylabel{font-size:9px;letter-spacing:1px}.viewbuttons button{min-height:36px;padding:5px 9px;font-size:11px}.stage{height:310px;border-radius:12px}.stage .stagehint{font-size:10px;left:11px;top:9px}.rail{right:7px;gap:1px}.rail button{min-height:27px;width:29px;font-size:10px}.reference{font-size:9px;left:11px;bottom:8px}.movebar{padding:10px 0;min-height:68px}.movebar h2{font-size:14px}.movebar p{font-size:10px}.follow{font-size:11px;gap:4px}.transport{padding:10px 0;gap:6px}.playgroup{gap:5px;flex:1}.playgroup .primary{min-width:0;flex:1}.playgroup button{padding:8px;font-size:12px}.speed select{font-size:11px;padding:5px;min-width:58px}.mobiletools{display:flex;gap:8px;padding-bottom:10px}.mobiletools button{flex:1;min-height:40px;font-size:12px}.stage svg{max-width:100%}dialog{padding:20px}.message{font-size:12px}.intro .tinylabel{display:none}}@media(max-width:360px){.brand{font-size:16px}.stage{height:285px}.speed{display:none}}
.rail .layer-from:not([aria-pressed=true]){border:1px dashed #b2dbed}.rail .layer-to{color:var(--gold);font-weight:800}.rail button{width:48px}.stage[data-view=2d] .rail{position:absolute;top:0;left:0;right:0;transform:none;flex-direction:row;justify-content:center;padding:5px;background:#142226}.stage[data-view=2d] svg{height:calc(100% - 42px);margin-top:42px}.stage[data-view=2d] .stagehint{display:none}.stage[data-view=2d] .reference{display:none}.stage[data-view=2d] .rail button{width:44px;min-height:32px}.stage[data-view=2d] svg{max-width:620px;margin-left:auto;margin-right:auto}@media(max-width:720px){body[data-view=2d] .intro h1,body[data-view=2d] .intro p{display:none}body[data-view=2d] .intro{padding:0 0 8px}body[data-view=2d] .intro .agents{margin-top:10px}.stage[data-view=2d]{height:404px}.stage[data-view=2d] .rail{gap:2px;padding:4px 0}.stage[data-view=2d] .rail button{font-size:9px;width:34px;padding:0;min-height:30px}.stage[data-view=3d] .rail button{width:35px;font-size:9px}}
.masthead{height:56px}.intro{padding:12px 0}.intro .tinylabel{display:none}.intro h1{font-size:26px;line-height:1.25}.intro p{font-size:12px;margin-top:3px}.stage{height:clamp(260px,calc(100svh - 535px),480px)}.movebar{min-height:64px;padding:9px 0}.transport{padding:9px 0}.follow{min-height:44px}.history button{min-height:44px}.speed select{min-height:44px}.viewbuttons button{min-height:44px}#history-position{padding:4px 0;min-height:36px}#history-position button{min-height:36px;font-size:11px;padding:4px 9px}@media(max-width:720px){.intro h1{font-size:22px}.intro{padding:12px 0}.stage{height:310px}.speed{display:flex}.speed select,.field select{font-size:16px}.speed select{max-width:80px}.transport .playgroup button{min-height:44px}.viewbuttons button{min-height:44px}.follow{font-size:11px}.stage[data-view=2d]{height:404px}.designbar select{font-size:16px;max-width:125px}.rail button{font-size:10px!important;line-height:1.15}.stage[data-view=3d] .rail button{width:42px;min-height:28px}.stage[data-view=2d] .rail button{min-height:32px}.nav .lab{display:none}}
.entry-tabs{display:flex;gap:6px;padding-top:12px}.entry-tabs button{min-height:44px;padding:8px 24px;font-weight:700}@media(max-width:720px){.entry-tabs{padding-top:10px}.entry-tabs button{flex:1;padding:8px 12px}.entry-tabs+section.intro{padding-top:10px}}
</style></head><body>
<div class="designbar"><span class="designnote">デザインモック · 参考棋譜の再生のみ／AI未接続</span><label>画面例<select id="scenario" aria-label="確認する画面"><option value="initial">初回</option><option value="playing">観戦中</option><option value="paused">一時停止</option><option value="history">履歴を確認</option><option value="finished">終局（表示例）</option><option value="error">モデル取得失敗</option></select></label></div>
<div class="shell"><header class="masthead"><div class="row"><div class="brand"><span>▱</span> VoxelShogi</div></div><nav class="nav" aria-label="メニュー"><button class="quiet lab" data-open="about">モデル・研究</button><button data-open="record">棋譜</button><button data-open="settings">対局設定</button></nav></header>
<nav class="entry-tabs" aria-label="遊び方"><button type="button" data-entry="watch" aria-pressed="true">AIを観戦</button><button type="button" data-entry="human" aria-pressed="false">AIと対戦</button></nav>
<section class="intro"><div><div class="tinylabel">A DIFFERENT DIMENSION OF SHOGI</div><h1>次の一手は、別の層へ。</h1><p>9層の将棋を、AI同士で。相手の玉を詰ませたら勝ち。</p></div><div class="agents"><div class="agent"><b><span class="dot"></span>先手</b><small>Easy · ランダム</small></div><span class="versus">VS</span><div class="agent white"><b><span class="dot"></span>後手</b><small>Easy · ランダム</small></div></div></section>
<div id="error" class="message" role="alert" hidden>モデルを読み込めませんでした。モデルなしでも観戦できます。<button id="fallback">Easyで参考棋譜を再生</button></div><div class="workspace"><main class="arena"><div class="stagehead"><div class="viewbuttons" role="group" aria-label="盤の見方"><button data-view="3d" aria-pressed="true">立体で眺める</button><button data-view="2d" aria-pressed="false">断面を読む</button></div><span id="status" class="state" role="status">開始前</span></div><div class="stage"><span class="stagehint" id="stagehint">9層の全体像 · 図解モック</span><svg id="board" viewBox="0 0 660 520" role="img" aria-label="9層の盤面。選択中の層を明るく表示"></svg><div id="layers" class="rail" role="group" aria-label="注目する層"></div><span class="reference">参考棋譜：実対局の6手 · Easy vs Easy</span></div><div id="history-position" class="row sub" hidden><span id="history-caption"></span><button id="latest">記録の末尾へ</button></div><section class="movebar" aria-label="表示中の着手"><div><h2 id="move-title">準備できました</h2><p id="move-description">モデルを用意せず、そのまま観戦を始められます。</p></div><label class="follow"><input id="follow" type="checkbox" checked>着手を追う</label></section><div class="transport"><div class="playgroup"><button id="prev" aria-label="記録を1手戻る">← 戻る</button><button id="play" class="primary">観戦をはじめる</button><button id="next" aria-label="記録を1手進む">1手進む →</button></div><label class="speed"><span>着手間隔</span><select id="speed" aria-label="着手間隔"><option value="1800">ゆっくり</option><option value="1000" selected>標準</option><option value="450">速く</option></select></label></div><div class="mobiletools"><button data-open="detail">この層の断面</button><button data-open="history">棋譜を見る</button></div></main>
<aside class="sidebar" aria-label="局面の詳細"><section class="section"><div class="row" style="justify-content:space-between"><h2>この一手を見る</h2><span id="ply" class="layerbadge">開始局面</span></div><div id="route" class="move-route"></div><p id="route-note">開始すると、動いた駒と層をここに表示します。</p></section><section class="section"><div class="row" style="justify-content:space-between"><h3>選択中の断面</h3><span id="layer-title" class="layerbadge">VI層</span></div><svg id="mini" class="mini" viewBox="0 0 300 300" role="img" aria-label="選択中の層の2D断面"></svg><p>移動元は点線、移動先は太枠と「着地」で表示。</p></section><section class="section"><h3>棋譜</h3><ol id="history" class="history"></ol></section></aside></div>
</div>
<dialog id="sheet"><div class="dialoghead"><h2 id="sheet-title"></h2><button id="close" aria-label="閉じる">閉じる</button></div><div id="sheet-body" class="dialogbody"></div></dialog>
<script>
(()=>{'use strict';
const $=id=>document.getElementById(id),R=['I','II','III','IV','V','VI','VII','VIII','IX'],K=['一','二','三','四','五','六','七','八','九'],names={P:'歩',L:'香',N:'桂',S:'銀',G:'金',B:'角',R:'飛',K:'玉'};
const record={"ruleset_id":"voxelshogi-standard-v1","initial":"lllllllll/9/ppppppppp/9/9/9/PPPPPPPPP/9/LLLLLLLLL|lnnnnnnnl/1rbbbbbb1/ppppppppp/9/9/9/PPPPPPPPP/1BRRRRRR1/LNNNNNNNL|lnsssssnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSSSSSNL|lnsgggsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGGGSNL|lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL|lnsgggsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGGGSNL|lnsssssnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSSSSSNL|lnnnnnnnl/1rrrrrrb1/ppppppppp/9/9/9/PPPPPPPPP/1BBBBBBR1/LNNNNNNNL|lllllllll/9/ppppppppp/9/9/9/PPPPPPPPP/9/LLLLLLLLL b - 1","moves":["286486","939949","797786","731741","872862","225326"],"result":null,"termination":null};
const snapshots=[];let board=Array(729).fill(null);
record.initial.split(' ')[0].split('|').forEach((layer,z)=>layer.split('/').forEach((rank,y)=>{let col=0;for(const c of rank){if(/[1-9]/.test(c)){col+=Number(c);continue}board[z*81+y*9+(8-col)]={kind:c.toUpperCase(),white:c===c.toLowerCase()};col++}}));
snapshots.push(board.map(p=>p&&({...p})));const coords=s=>({x:Number(s[0])-1,y:Number(s[1])-1,z:Number(s[2])-1}),index=p=>p.z*81+p.y*9+p.x;
record.moves.forEach(move=>{const a=coords(move.slice(0,3)),b=coords(move.slice(3,6));board=board.map(p=>p&&({...p}));board[index(b)]=board[index(a)];board[index(a)]=null;snapshots.push(board)});
let entryMode='watch',youSide='b',opponent='Normal';
let cursor=0,layer=5,follow=true,running=false,view='3d',ended=false,reviewing=false,timer=null,returnFocus=null;
const square=p=>`${p.x+1}${K[p.y]}`,where=p=>`${square(p)}・${R[p.z]}層`,last=()=>cursor?{a:coords(record.moves[cursor-1].slice(0,3)),b:coords(record.moves[cursor-1].slice(3,6))}:null;
const project=(x,y,z)=>[312+(4-x)*27+(y-4)*17,260+(y-4)*9-(4-x)*4-(z-4)*42];
const points=items=>items.map(p=>p.join(',')).join(' '),pt=(x,y,z)=>project(x,y,z);
function scene(){const state=snapshots[cursor],m=last();let s='<title>9層の将棋盤の図解</title><desc>注目する層は'+R[layer]+'。実装時は本物の立体盤を表示します。</desc>';
for(let z=0;z<9;z++){const active=z===layer,from=m&&m.a.z===z;const opacity=active?1:from?.65:.32;
s+=`<g opacity="${opacity}"><polygon points="${points([pt(-.5,-.5,z),pt(8.5,-.5,z),pt(8.5,8.5,z),pt(-.5,8.5,z)])}" fill="${active?'#243f41':'#1a3035'}" stroke="${active?'#9ddbc9':'#77969b'}" stroke-width="${active?1.5:.7}"/>`;
for(let a=0;a<=9;a++){s+=`<path d="M${pt(a-.5,-.5,z)} L${pt(a-.5,8.5,z)} M${pt(-.5,a-.5,z)} L${pt(8.5,a-.5,z)}" stroke="#80a5a7" stroke-width=".55" opacity=".5"/>`}
state.forEach((piece,i)=>{if(!piece||Math.floor(i/81)!==z)return;const x=i%9,y=Math.floor(i/9)%9,[px,py]=pt(x,y,z);s+=`<polygon points="${px-10},${py+3} ${px-9},${py-5} ${px},${py-10} ${px+9},${py-5} ${px+10},${py+3}" fill="${piece.white?'#c2d8df':'#e8cfa5'}"/><text x="${px}" y="${py-1}" text-anchor="middle" font-family="serif" font-size="10" font-weight="bold" fill="#182527">${names[piece.kind]}</text>`});
const [lx,ly]=pt(9.7,8.5,z);s+=`<text x="${lx-12}" y="${ly+5}" fill="${active?'#c5f4e5':'#c4d6d8'}" font-size="12" font-family="system-ui">${R[z]}</text></g>`;}
if(m){const a=pt(m.a.x,m.a.y,m.a.z),b=pt(m.b.x,m.b.y,m.b.z);s+=`<path d="M${a} Q${a[0]+60},${b[1]-30} ${b}" fill="none" stroke="#ffd18b" stroke-width="3" stroke-dasharray="5 4"/><circle cx="${a[0]}" cy="${a[1]}" r="13" fill="none" stroke="#b2dbed" stroke-width="2" stroke-dasharray="3 3"/><circle class="active-mark" cx="${b[0]}" cy="${b[1]}" r="15" fill="none" stroke="#ffd18b" stroke-width="3"/><rect x="${b[0]+18}" y="${b[1]-18}" width="39" height="22" rx="4" fill="#ffd18b"/><text x="${b[0]+37.5}" y="${b[1]-3}" text-anchor="middle" font-size="11" fill="#202d27">着地</text>`}return s;}
function slice(){const m=last();let s='<title>'+R[layer]+'層の断面</title>';for(let y=0;y<9;y++)for(let c=0;c<9;c++){const x=8-c,i=layer*81+y*9+x,p=snapshots[cursor][i],a=m&&index(m.a)===i,b=m&&index(m.b)===i;const left=23+c*28,top=21+y*28;s+=`<rect x="${left}" y="${top}" width="27" height="27" fill="${b?'#ffe0a4':'#deccae'}" stroke="#a28f72" stroke-width=".6"/>`;if(p)s+=`<text x="${left+13.5}" y="${top+19}" fill="${p.white?'#354b61':'#182527'}" font-family="serif" font-size="19" text-anchor="middle" ${p.white?`transform="rotate(180 ${left+13.5} ${top+13.5})"`:''}>${names[p.kind]}</text>`;if(a||b)s+=`<rect x="${left+1.5}" y="${top+1.5}" width="24" height="24" fill="none" stroke="${b?'#7c4406':'#365e76'}" stroke-width="${b?3:2}" ${a?'stroke-dasharray="3 2"':''}/>`}for(let i=0;i<9;i++){s+=`<text x="${36.5+i*28}" y="13" fill="#c0d4d6" font-size="10" text-anchor="middle">${9-i}</text><text x="12" y="${40+i*28}" fill="#c0d4d6" font-size="10" text-anchor="middle">${K[i]}</text>`}return s;}
function renderBoard(){const focused=document.activeElement;const restoreLayer=focused?.dataset?.layer,restoreCursor=focused?.dataset?.cursor;const m=last();$('board').parentElement.dataset.view=view;document.body.dataset.view=view;$('board').innerHTML=view==='3d'?scene():slice();$('board').setAttribute('viewBox',view==='3d'?'0 0 660 520':'0 0 280 280');$('mini').innerHTML=slice();$('stagehint').textContent=view==='3d'?'9層の全体像 · 図解モック':R[layer]+'層の断面 · 読むための表示';$('layer-title').textContent=R[layer]+'層';$('history-position').hidden=!reviewing;$('history-caption').textContent='記録 '+cursor+' / '+record.moves.length+'手を表示中';$('status').textContent=ended?'終局画面の例'+(reviewing?' · 記録を確認中':''):running?'参考棋譜を再生中':reviewing?'履歴 '+cursor+' / '+record.moves.length+'手':cursor===0?'開始前':cursor<record.moves.length?'一時停止 · '+cursor+'手目':'参考棋譜の末尾';$('ply').textContent=cursor?cursor+'手目':'開始局面';$('play').textContent=ended?'新しい観戦をはじめる':running?'一時停止':cursor===0?'観戦をはじめる':cursor===record.moves.length?'最初から見る':'記録の続きを再生';$('prev').disabled=running||cursor===0;$('next').disabled=running||cursor===record.moves.length;$('follow').checked=follow;
$('move-title').textContent=ended?'終局の表示例':m?`${cursor%2?'先手':'後手'} ${square(m.a)} ${R[m.a.z]} → ${square(m.b)} ${R[m.b.z]}`:'準備できました';$('move-description').textContent=ended?'参考棋譜の実際の終局ではありません。':m?(m.a.z!==m.b.z?R[m.a.z]+'層から'+R[m.b.z]+'層へ。':'同じ層の中を移動。')+(follow?' 着手先を表示中。':' 手動で'+R[layer]+'層を表示中。'):'モデルを用意せず、そのまま観戦を始められます。';
$('route').innerHTML=m?`<div class="squarelabel"><small>移動元 · ${R[m.a.z]}層</small><strong>${square(m.a)}</strong></div><span aria-hidden="true">→</span><div class="squarelabel destination"><small>着地 · ${R[m.b.z]}層</small><strong>${square(m.b)}</strong></div>`:'<p class="sub">まだ着手はありません</p>';$('route-note').textContent=m?(m.a.z===m.b.z?'同じ層の中の一手。':'駒が別の層へ移動しました。'):'開始すると、動いた駒と層をここに表示します。';
$('layers').innerHTML=R.map((r,z)=>`<button data-layer="${z}" aria-label="${r}層を見る${m&&m.a.z===z?'、移動元の層':''}${m&&m.b.z===z?'、着地した層':''}" aria-pressed="${z===layer}" class="${m&&m.a.z===z?'layer-from':''} ${m&&m.b.z===z?'layer-to':''}">${r}${m&&m.b.z===z?' 着':m&&m.a.z===z?' 元':''}</button>`).reverse().join('');$('history').innerHTML='<li><button data-cursor="0" aria-current="'+(cursor===0)+'"><span class="number">0</span>開始局面</button></li>'+record.moves.map((move,i)=>{const a=coords(move.slice(0,3)),b=coords(move.slice(3,6));return `<li><button data-cursor="${i+1}" aria-current="${cursor===i+1}"><span class="number">${i+1}</span>${i%2?'☖':'☗'} ${where(a)} → ${where(b)}</button></li>`}).join('');document.querySelectorAll('button[data-view]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.view===view));if(restoreLayer!==undefined)document.querySelector('[data-layer="'+restoreLayer+'"]')?.focus();if(restoreCursor!==undefined)document.querySelector('#history [data-cursor="'+restoreCursor+'"]')?.focus();}
function stop(){running=false;clearTimeout(timer);timer=null}function go(n){cursor=Math.max(0,Math.min(record.moves.length,n));if(follow&&last())layer=last().b.z;render()}function tick(){if(!running)return;if(cursor===record.moves.length){stop();render();return}go(cursor+1);timer=setTimeout(tick,Number($('speed').value))}function play(){reviewing=false;if(ended||cursor===record.moves.length){ended=false;stop();go(0)}if(running){stop();render()}else{running=true;tick()}}
$('play').onclick=()=>entryMode==='human'?open('human',$('play')):play();$('prev').onclick=()=>{stop();reviewing=true;go(cursor-1)};$('next').onclick=()=>{stop();reviewing=true;go(cursor+1)};$('latest').onclick=()=>{stop();reviewing=false;go(record.moves.length)};$('follow').onchange=e=>{follow=e.target.checked;if(follow&&last())layer=last().b.z;render()};$('layers').onclick=e=>{const b=e.target.closest('[data-layer]');if(!b)return;layer=Number(b.dataset.layer);follow=false;render()};document.querySelectorAll('button[data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;render()});$('history').onclick=e=>{const b=e.target.closest('[data-cursor]');if(b){stop();reviewing=true;go(Number(b.dataset.cursor))}};
const contents={settings:['対局設定',`<p>観戦を主役にし、設定は必要なときだけ開きます。以下は画面設計用で、AIの起動は行いません。</p><p>遊び方は画面上部の「AIを観戦」「AIと対戦」から選べます。</p><label class="field">先手のAI<select><option>Easy · ランダム</option><option>Normal · 探索</option><option>学習済みS · モデルの準備へ</option></select></label><label class="field">後手のAI<select><option>Easy · ランダム</option><option>Normal · 探索</option><option>学習済みS · モデルの準備へ</option></select></label><p>細かな探索上限・描画設定は「詳細」にまとめます。</p><button id="restart">参考棋譜を最初から見る</button>`],about:['モデル・研究',`<p>Easy／Normalはモデル不要。学習済みSはHugging Faceで取得申請→ダウンロード→この端末で読み込みます。</p><p>このモックは配置と案内の確認用です。モデルの取得・推論は実行しません。</p><p class="note">棋力や勝率を推測したメーターは表示しません。実装ではモデルID・精度形式・backendを詳細情報に保持します。</p>`],record:['棋譜',`<button id="download">参考棋譜を端末へ保存</button><p>この端末へ棋譜JSONをダウンロードします。</p>`]};
function open(type,trigger){
  if(type==='settings'&&entryMode==='human')type='human';
  const wasRunning=running;stop();render();returnFocus=trigger;
  if(type==='human'){
    $('sheet-title').textContent='AIと対戦';
    $('sheet-body').innerHTML='<label class="field">あなたの先後<select id="human-side"><option value="b">先手（最初に指す）</option><option value="w">後手（AIが先に指す）</option></select></label><label class="field">相手のAI<select id="human-ai"><option value="Easy">Easy · ランダム</option><option value="Normal">Normal · 探索</option><option disabled>学習済みS · モデル設定から追加</option></select></label><button id="start-human" class="primary">対戦をはじめる</button><p>ここでは対戦画面への導線を確認できます。着手・AI応答は本実装で接続します。</p>';
    $('human-side').value=youSide;$('human-ai').value=opponent;
    $('start-human').onclick=()=>{youSide=$('human-side').value;opponent=$('human-ai').value;entryMode='human';ended=false;reviewing=false;view='2d';layer=4;go(0);close();$('play').focus()};
  }else if(type==='detail'){
    $('sheet-title').textContent=R[layer]+'層の断面';
    $('sheet-body').innerHTML='<svg class="sheetmini" viewBox="0 0 300 300" role="img" aria-label="'+R[layer]+'層の2D断面">'+slice()+'</svg><p>移動元は点線、移動先は太枠。層の変更はこのシートを閉じ、盤の層番号から行えます。</p>';
  }else if(type==='history'){
    $('sheet-title').textContent='棋譜をたどる';
    $('sheet-body').innerHTML='<ol class="history" style="max-height:60svh">'+$('history').innerHTML+'</ol>';
    $('sheet-body').querySelector('ol').onclick=e=>{const b=e.target.closest('[data-cursor]');if(b){reviewing=true;go(Number(b.dataset.cursor));close()}};
  }else{
    const content=contents[type];$('sheet-title').textContent=content[0];$('sheet-body').innerHTML=content[1];
    if(type==='settings')$('restart').onclick=()=>{ended=false;reviewing=false;go(0);close()};
    if(type==='record')$('download').onclick=()=>{
      const blob=new Blob([JSON.stringify(record,null,2)],{type:'application/json'});
      const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='voxelshogi-reference-record.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),0);
    };
  }
  if(wasRunning)$('sheet-body').insertAdjacentHTML('afterbegin','<p>参考棋譜の再生を一時停止しました。閉じた後、再生ボタンで続きを見られます。</p>');
  $('sheet').showModal();$('close').focus();
}
function render(){renderBoard();renderEntry()}
function renderEntry(){
  const human=entryMode==='human';
  document.querySelectorAll('[data-entry]').forEach(button=>button.setAttribute('aria-pressed',button.dataset.entry===entryMode));
  $('prev').hidden=human;$('next').hidden=human;$('speed').closest('label').hidden=human;
  document.querySelector('[data-open="record"]').disabled=human;
  document.querySelector('.sidebar .section:last-child').hidden=human;
  document.querySelector('.reference').hidden=human;
  document.querySelector('.intro h1').textContent=human?'あなたの一手も、別の層へ。':'次の一手は、別の層へ。';
  document.querySelector('.intro p').textContent=human?'駒を選んで、移動先へ。相手の玉を詰ませたら勝ち。':'9層の将棋を、AI同士で。相手の玉を詰ませたら勝ち。';
  const agents=document.querySelectorAll('.agent');
  agents.forEach((agent,i)=>{const side=i===0?'b':'w',you=human&&side===youSide;agent.querySelector('b').innerHTML='<span class="dot"></span>'+(i===0?'先手':'後手')+(you?' · あなた':'');agent.querySelector('small').textContent=human?(you?'人間':opponent+(opponent==='Normal'?' · 探索':' · ランダム')):'Easy · ランダム'});
  if(human){$('status').textContent=youSide==='b'?'あなたの手番 · 画面例':'AIの手番 · 画面例';$('play').textContent='対戦設定を変更';$('move-title').textContent=youSide==='b'?'あなたは先手です':'あなたは後手です';$('move-description').textContent='対戦画面のモックです。駒の操作とAI応答はまだ接続していません。';$('route-note').textContent=youSide==='b'?'着手する駒と移動先を選ぶ画面です。':'AIが最初に指した後、あなたの番になります。';}
}
document.querySelectorAll('[data-entry]').forEach(button=>button.onclick=()=>{
  if(button.dataset.entry==='human'){open('human',button);return}
  stop();entryMode='watch';ended=false;reviewing=false;go(0);
});
function close(){$('sheet').close();returnFocus?.focus()}$('close').onclick=close;$('sheet').addEventListener('cancel',()=>returnFocus?.focus());document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>open(b.dataset.open,b));$('fallback').onclick=()=>{$('error').hidden=true;go(0);play()};$('scenario').onchange=e=>{entryMode='watch';stop();$('error').hidden=true;follow=true;view='3d';layer=5;ended=false;reviewing=false;switch(e.target.value){case'initial':go(0);break;case'playing':go(2);running=true;tick();break;case'paused':go(3);break;case'history':reviewing=true;go(2);break;case'finished':go(6);ended=true;render();break;case'error':go(0);$('error').hidden=false;break}};render();
})();
</script></body></html>
```
