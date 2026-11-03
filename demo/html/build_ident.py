"""ident.html: the identifier shown with its evidence. Three acts on a JS timeline (seconds):
   0–20  An Afternoon in Astoria: the pages sent, the record filling in field by field with the page it came from,
         then the verification (checksum, Open Library title match) turning green;
   20–31 the gold scores on all 757 catalogues;
   31–44 Focus: Elizabeth Murray: the record from the pages, then MoMA's own sheet with its 1987 against the pages' 2005."""
import os, json
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.join(HERE, "..", "ident")
def img(n): return "file://" + os.path.join(P, n)
HTML = r"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:Plex;src:url(ibm-plex-serif-latin-normal-600-182f05.woff2);font-weight:600}
@font-face{font-family:Plex;src:url(ibm-plex-serif-latin-normal-400-51510a.woff2);font-weight:400}
@font-face{font-family:Plex;src:url(ibm-plex-serif-latin-italic-400-8bf354.woff2);font-weight:400;font-style:italic}
html,body{margin:0;height:100%;background:#0f1114;color:#f3eadb;font-family:Plex;overflow:hidden}
.act{position:absolute;inset:0;opacity:0;transition:opacity .6s}
.act.on{opacity:1}
h2{position:absolute;left:70px;top:44px;margin:0;font-weight:400;font-size:26px;letter-spacing:.14em;text-transform:uppercase;color:#9a9283}
h2 b{font-weight:600;color:#f3eadb;letter-spacing:0;text-transform:none;font-size:34px;margin-left:18px}
.pages{position:absolute;left:70px;top:120px;display:flex;gap:26px}
.pg{position:relative;width:250px;height:330px;border:2px solid #2b2f36;border-radius:4px;overflow:hidden;background:#000;transition:border-color .3s,box-shadow .3s}
.pg img{width:100%;height:100%;object-fit:cover}
.pg.wide{width:390px}
.pg span{position:absolute;left:0;bottom:0;background:rgba(0,0,0,.7);color:#f3eadb;font-size:22px;padding:4px 12px}
.pg.hot{border-color:#ffd866;box-shadow:0 0 0 3px rgba(255,216,102,.35)}
.crop{position:absolute;left:70px;top:486px;width:820px;border:2px solid #2b2f36;border-radius:4px;overflow:hidden;background:#fff;opacity:0;transition:opacity .5s}
.crop img{width:100%;display:block}
.crop.on{opacity:1}
.rec{position:absolute;left:960px;top:120px;width:890px}
.row{display:flex;align-items:baseline;gap:18px;padding:13px 0;border-bottom:1px solid #22262c;opacity:0;transform:translateX(16px);transition:opacity .45s,transform .45s}
.row.on{opacity:1;transform:none}
.k{width:170px;font-style:italic;color:#9a9283;font-size:26px}
.v{flex:1;font-size:32px}
.p{font-size:20px;color:#ffd866;background:rgba(255,216,102,.12);padding:3px 10px;border-radius:12px;white-space:nowrap}
.ver{margin-top:28px;padding:22px 26px;border-radius:8px;background:#161a1f;border:1px solid #22262c;font-size:26px;line-height:1.5;opacity:0;transition:opacity .5s}
.ver.on{opacity:1}
.ok{color:#7bd88f}.warn{color:#ffb454}
.big{font-weight:600;font-size:30px}
/* the chart */
.chart{position:absolute;left:160px;right:160px;top:170px}
.chart h3{font-weight:400;font-style:italic;font-size:34px;margin:0 0 40px;color:#cfc4b2;line-height:1.4}
.bar{display:flex;align-items:center;gap:26px;margin:22px 0}
.bar .k{width:260px;font-style:normal;font-size:34px;color:#f3eadb}
.bar .t{flex:1;height:44px;background:#1b1f25;border-radius:6px;overflow:hidden}
.bar .f{height:100%;width:0;background:linear-gradient(90deg,#8a7a52,#ffd866);transition:width 1.6s cubic-bezier(.2,.8,.2,1)}
.bar .n{width:120px;font-size:40px;font-weight:600;text-align:right}
.bar .s{width:230px;font-size:22px;color:#9a9283;font-style:italic}
.chart .note{margin-top:34px;font-size:24px;color:#9a9283;font-style:italic}
/* act 3 */
.sheet{position:absolute;left:70px;top:486px;width:820px;opacity:0;transition:opacity .5s}
.sheet.on{opacity:1}
.sheet .crop2{border:2px solid #ffb454;border-radius:4px;overflow:hidden;background:#fff;margin-top:12px}
.sheet .crop2 img{width:100%;display:block}
.sheet .cap{font-size:24px;color:#ffb454;font-style:italic}
</style></head><body>

<div class="act on" id="a1">
 <h2>The identifier <b>An Afternoon in Astoria</b></h2>
 <div class="pages">
  <div class="pg wide" id="p2"><img src="__P13206_2__"><span>p. 2 · cover</span></div>
  <div class="pg wide" id="p6"><img src="__P13206_6__"><span>p. 6 · half-title</span></div>
 </div>
 <div class="crop" id="c9"><img src="__C13206_9__"></div>
 <div class="rec">
  <div class="row" data-p="p6"><div class="k">Title</div><div class="v">An Afternoon in Astoria</div><div class="p">p. 6</div></div>
  <div class="row" data-p="p2"><div class="k">Author</div><div class="v">Rudolph Burckhardt</div><div class="p">p. 2</div></div>
  <div class="row" data-p="c9"><div class="k">Editor</div><div class="v">David Frankel</div><div class="p">p. 9</div></div>
  <div class="row" data-p="c9"><div class="k">Publisher</div><div class="v">The Museum of Modern Art, New York</div><div class="p">p. 9</div></div>
  <div class="row" data-p="c9"><div class="k">Year</div><div class="v">2002</div><div class="p">p. 9</div></div>
  <div class="row" data-p="c9"><div class="k">ISBN</div><div class="v">0-87070-436-2</div><div class="p">p. 9</div></div>
  <div class="row" data-p="c9"><div class="k">Colophon</div><div class="v" style="font-size:26px;font-style:italic">Printed and bound by Trifolio S.R.L., Verona</div><div class="p">p. 9</div></div>
  <div class="ver" id="ver">
   <div>ISBN 0870704362 &nbsp;·&nbsp; checksum <span class="ok">✓</span></div>
   <div>Open Library title for it: <i>An afternoon in Astoria</i> &nbsp;=&nbsp; the title page <span class="ok">✓</span></div>
   <div class="big ok" style="margin-top:8px">verified</div>
  </div>
 </div>
</div>

<div class="act" id="a2">
 <h2>The identifier <b>scored on all 757 catalogues</b></h2>
 <div class="chart">
  <h3>against MoMA's own record sheet, page 1 of every PDF, withheld from the model</h3>
  <div class="bar"><div class="k">title</div><div class="t"><div class="f" data-w="94"></div></div><div class="n">94 %</div><div class="s">75 % word for word</div></div>
  <div class="bar"><div class="k">year</div><div class="t"><div class="f" data-w="90"></div></div><div class="n">90 %</div><div class="s">81 % word for word</div></div>
  <div class="bar"><div class="k">publisher</div><div class="t"><div class="f" data-w="86"></div></div><div class="n">86 %</div><div class="s"></div></div>
  <div class="bar"><div class="k">author</div><div class="t"><div class="f" data-w="85"></div></div><div class="n">85 %</div><div class="s">MoMA files the artist as author</div></div>
  <div class="bar"><div class="k">ISBN</div><div class="t"><div class="f" data-w="92"></div></div><div class="n">92 %</div><div class="s">of the 220 that have one</div></div>
  <div class="note">convention-aware: MoMA folds the series line into the title, files the artist as author, and sometimes gives the exhibition year</div>
 </div>
</div>

<div class="act" id="a3">
 <h2>The identifier <b>Focus: Elizabeth Murray</b></h2>
 <div class="pages">
  <div class="pg" id="m2"><img src="__P13185_2__"><span>p. 2</span></div>
  <div class="pg" id="m5"><img src="__P13185_5__"><span>p. 5</span></div>
  <div class="pg" id="m1" style="opacity:.35"><img src="__P13185_1__"><span>p. 1 · MoMA's sheet, withheld</span></div>
 </div>
 <div class="crop" id="c5"><img src="__C13185_EXH__"></div>
 <div class="sheet" id="sh"><div class="cap">MoMA's own record sheet says 1987</div><div class="crop2"><img src="__C13185_SHEET__"></div></div>
 <div class="rec">
  <div class="row" data-p="m2"><div class="k">Series</div><div class="v">Focus</div><div class="p">p. 2</div></div>
  <div class="row" data-p="m2"><div class="k">Title</div><div class="v">Elizabeth Murray</div><div class="p">p. 2</div></div>
  <div class="row" data-p="m2"><div class="k">Artist</div><div class="v">Elizabeth Murray</div><div class="p">p. 2</div></div>
  <div class="row" data-p=""><div class="k">Author</div><div class="v">Sarah Suzuki</div><div class="p">p. 4</div></div>
  <div class="row" data-p="c5"><div class="k">Year</div><div class="v">2005</div><div class="p">p. 5 · ©2005</div></div>
  <div class="row" data-p="c5"><div class="k">Exhibition</div><div class="v">October 19, 2005 – January 9, 2006</div><div class="p">p. 5</div></div>
  <div class="ver" id="ver3">
   <div>the sheet: <span class="warn big">1987</span> &nbsp;·&nbsp; the pages: <span class="ok big">2005</span></div>
   <div style="color:#9a9283;font-style:italic;font-size:23px;margin-top:6px">the copyright line and the exhibition dates agree; the sheet is wrong</div>
  </div>
 </div>
</div>

<script>
const T = __TIMELINE__;
const at = (s, f) => setTimeout(f, s * 1000);
function showRows(act, start, gap){
  const rows = document.querySelectorAll('#' + act + ' .row');
  rows.forEach((r, i) => at(start + i * gap, () => {
    r.classList.add('on');
    document.querySelectorAll('#' + act + ' .pg, #' + act + ' .crop').forEach(e => e.classList.remove('hot'));
    const p = r.dataset.p; if (p){ const el = document.getElementById(p); if (el){ el.classList.add('hot'); if (el.classList.contains('crop')) el.classList.add('on'); } }
  }));
}
showRows('a1', T.rows1, T.gap1);
at(T.ver1, () => document.getElementById('ver').classList.add('on'));
at(T.chart, () => { document.getElementById('a1').classList.remove('on'); document.getElementById('a2').classList.add('on');
  setTimeout(() => document.querySelectorAll('#a2 .f').forEach(f => f.style.width = f.dataset.w + '%'), 500); });
at(T.murray, () => { document.getElementById('a2').classList.remove('on'); document.getElementById('a3').classList.add('on'); });
showRows('a3', T.rows3, T.gap3);
at(T.sheet, () => { document.getElementById('sh').classList.add('on'); document.getElementById('c5').classList.remove('on');
  document.getElementById('m1').style.opacity = 1; document.getElementById('m1').classList.add('hot'); document.getElementById('ver3').classList.add('on'); });
</script></body></html>"""
T = json.load(open(os.path.join(HERE, "ident-timeline.json"))) if os.path.exists(os.path.join(HERE, "ident-timeline.json")) else \
    {"rows1": 1.2, "gap1": 1.1, "ver1": 13.5, "chart": 21.0, "murray": 31.5, "rows3": 32.5, "gap3": 0.9, "sheet": 38.5}
out = (HTML.replace("__P13206_2__", img("13206-0002.jpg")).replace("__P13206_6__", img("13206-0006.jpg")).replace("__C13206_9__", img("crop-13206-copyright.jpg"))
       .replace("__P13185_2__", img("13185-0002.jpg")).replace("__P13185_5__", img("13185-0005.jpg")).replace("__P13185_1__", img("13185-0001.jpg"))
       .replace("__C13185_EXH__", img("crop-13185-exhibition.jpg")).replace("__C13185_SHEET__", img("crop-13185-sheet-date.jpg"))
       .replace("__TIMELINE__", json.dumps(T)))
open(os.path.join(HERE, "ident.html"), "w").write(out); print("wrote ident.html", T)
