import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "..")   # title-a.jpg / title-b.jpg beside this folder

TERM_TPL = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%;background:#0b0d10;color:#d6dbe0;font:24px/1.45 Menlo,"SF Mono",monospace;overflow:hidden}
#bar{height:44px;background:#15181d;display:flex;align-items:center;padding:0 20px;gap:8px;font:15px -apple-system,Helvetica,sans-serif;color:#8b949e}
#bar i{width:13px;height:13px;border-radius:50%;display:inline-block}
#t{position:absolute;top:44px;left:0;right:0;bottom:0;padding:30px 56px;box-sizing:border-box;overflow:hidden;white-space:pre-wrap;word-break:break-word}
.p{color:#7bd88f}.c{color:#fff}.o{color:#c9d1d9}.dim{color:#8b949e}.k{color:#ffd866}.g{color:#7bd88f}
.cur{display:inline-block;width:13px;height:27px;background:#d6dbe0;vertical-align:-5px;animation:b 1s steps(1) infinite}
@keyframes b{50%{opacity:0}}
</style></head><body><div id="bar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i><i style="background:#28c840"></i><span style="margin-left:14px">__TITLE__</span></div><div id="t"></div><script>
const S = __SCRIPT__; const P = __PROMPT__;
const t = document.getElementById('t'); const sleep = ms => new Promise(r => setTimeout(r, ms));
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;')}
let cur = null; let first = true;
function bottom(){ t.scrollTop = t.scrollHeight; }
function prompt(){ t.insertAdjacentHTML('beforeend', '<span class="p">'+esc(P)+'</span><span class="c" id="cmd"></span>'); cur=document.createElement('span'); cur.className='cur'; t.appendChild(cur); bottom(); }
async function run(){
  await sleep(600);
  for (const it of S){
    if (it.pause){ await sleep(it.pause*1000); continue; }
    if (it.cmd !== undefined){
      if (!first) t.insertAdjacentHTML('beforeend','\\n'); first = false; prompt();
      const el = document.getElementById('cmd'); el.removeAttribute('id');
      for (const ch of it.cmd){ el.textContent += ch; bottom(); await sleep(it.speed||28); }
      await sleep(350); cur.remove(); t.insertAdjacentHTML('beforeend','\\n'); bottom();
    }
    if (it.out !== undefined){
      for (const line of it.out){ t.insertAdjacentHTML('beforeend','<span class="'+(it.cls||'o')+'">'+line+'</span>\\n'); bottom(); await sleep(it.speed||55); }
    }
    if (it.end){ t.insertAdjacentHTML('beforeend','\\n'); prompt(); }
  }
}
run();
</script></body></html>"""

def hl(s):   # colour keys, numbers and strings in JSON-ish output
    import re
    s = s.replace("&", "&amp;").replace("<", "&lt;")
    s = re.sub(r'("[^"]*")(\s*:)', r'<span class="k">\1</span>\2', s)
    s = re.sub(r'(:\s*)("[^"]*")', r'\1<span class="g">\2</span>', s)
    return s

def term(name, title, prompt, script):
    html = TERM_TPL.replace("__TITLE__", title).replace("__SCRIPT__", json.dumps(script)).replace("__PROMPT__", json.dumps(prompt))
    open(os.path.join(HERE, name + ".html"), "w").write(html)

# ── 02a: the SAM worker on spark1 ──────────────────────────────────────────────────────────────────
term("t02a", "spark1 — SAM 3.1 worker", "colophon@spark1:~/scratch $ ", [
  {"cmd": "python worker_sam.py --local pages/13187/0017.jpg pages/13187/0022.jpg", "speed": 22},
  {"pause": 0.4},
  {"out": [hl("INFO loaded ~/models/sam3/sam3.1_multiplex_fp16.safetensors (1133 tensors)")], "cls": "dim", "speed": 300},
  {"out": [hl("INFO model ready in 5.2s: sam3.1-multiplex, prompts=['painting', 'photograph', 'drawing', 'print', 'sculpture', 'map', 'diagram', 'illustration'], score_min=0.30")], "cls": "dim", "speed": 900},
  {"out": ["INFO pages/13187/0017.jpg: <span class=\"k\">9 detections</span> {'photograph': 9}, 1.14s"], "speed": 1100},
  {"out": ["INFO pages/13187/0022.jpg: <span class=\"k\">31 detections</span> {'photograph': 31}, 1.19s"], "speed": 900},
  {"out": [hl("INFO summary: {'pages': 2, 'mean_s_per_page': 1.19, 'peak_gpu_mem_gb': 4.26}")], "cls": "dim", "speed": 100},
  {"end": True},
])
# ── 02c: what the run did (the coordinator's status) ─────────────────────────────────────────────
term("t02c", "hub — coordinator", "colophon@hub:/srv/colophon $ ", [
  {"cmd": "curl -s http://hub:8101/status | jq '{pages, figures, workers: (.workers | map_values(.done))}'", "speed": 18},
  {"pause": 0.5},
  {"out": [hl(l) for l in [
    "{",
    '  "pages":   {"done": 77750, "queued": 0, "leased": 0, "failed": 0},',
    '  "figures": {"total": 93527, "pages_with_figures": 48961},',
    '  "workers": {"spark1": 27882, "spark2": 25452, "winbox": 24416}',
    "}"]], "speed": 120},
  {"end": True},
])
# ── 06: the identifier ───────────────────────────────────────────────────────────────────────────
term("t06", "hub — identifier", "colophon@hub:/srv/colophon $ ", [
  {"cmd": "jq '.record | {title, authors, editors, publisher, place, year, isbns}' ident/13206.json", "speed": 24},
  {"pause": 0.3},
  {"out": [hl(l) for l in [
    "{",
    '  "title": "An Afternoon in Astoria",',
    '  "authors": ["Rudolph Burckhardt"],',
    '  "editors": ["David Frankel"],',
    '  "publisher": "The Museum of Modern Art",',
    '  "place": "New York",',
    '  "year": "2002",',
    '  "isbns": ["0870704362"]',
    "}"]], "speed": 70},
  {"pause": 5},
  {"cmd": "jq '.verification' ident/13206.json", "speed": 24},
  {"pause": 0.3},
  {"out": [hl(l) for l in [
    "{",
    '  "isbns": [{"isbn": "0870704362", "checksum": true,',
    '             "lookup_title": "An afternoon in Astoria", "match": true}],',
    '  "status": "verified"',
    "}"]], "speed": 70},
  {"pause": 7},
  {"cmd": "tail -2 logs/gold-all.log; jq '.accuracy | map_values(.accuracy)' ident/_gold_summary.json", "speed": 22},
  {"pause": 0.3},
  {"out": [hl(l) for l in [
    "verification: {'no_isbn': 544, 'verified': 169, 'unverifiable': 38, 'isbn_mismatch': 6}  cost $23.21  median 7.46 s/book",
    "FINISHED",
    "{",
    '  "title": 0.752,  "title_conv": 0.937,',
    '  "year": 0.813,   "year_conv": 0.902,',
    '  "publisher": 0.858,',
    '  "author": 0.400, "author_conv": 0.853,',
    '  "isbn": 0.923',
    "}"]], "speed": 110},
  {"pause": 6},
  {"cmd": "jq '.record | {series, title, artists, authors, year, exhibition_dates}' ident/13185.json; grep '13185 year' logs/gold-all.log", "speed": 20},
  {"pause": 0.3},
  {"out": [hl(l) for l in [
    "{",
    '  "series": "Focus", "title": "Elizabeth Murray",',
    '  "artists": ["Elizabeth Murray"], "authors": ["Sarah Suzuki"],',
    '  "year": "2005",',
    '  "exhibition_dates": "October 19, 2005-January 9, 2006"',
    "}",
    "13185 year        wrong                  gold='1987'  read='2005'"]], "speed": 90},
  {"end": True},
])
# ── 07: the cost ─────────────────────────────────────────────────────────────────────────────────
term("t07", "hub — the spend guard", "colophon@hub:/srv/colophon $ ", [
  {"cmd": "cat logs/spend-total.txt; tail -2 logs/spend-guard.log", "speed": 22},
  {"pause": 0.4},
  {"out": [hl(l) for l in [
    "39.516",
    "2026-11-03T14:52:40Z total_api_spend_usd=39.516 limit=98",
    "2026-11-03T14:57:40Z total_api_spend_usd=39.516 limit=98"]], "speed": 200},
  {"end": True},
])

# ── title cards ──────────────────────────────────────────────────────────────────────────────────
CARD = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:Plex;src:url(ibm-plex-serif-latin-normal-600-182f05.woff2);font-weight:600}
@font-face{font-family:Plex;src:url(ibm-plex-serif-latin-normal-400-51510a.woff2);font-weight:400}
@font-face{font-family:Plex;src:url(ibm-plex-serif-latin-italic-400-8bf354.woff2);font-weight:400;font-style:italic}
html,body{margin:0;height:100%;background:#000;overflow:hidden}
#bg{position:absolute;inset:0;background:url(__IMG__) center/cover;opacity:0;animation:fi 1.6s ease-out forwards __DELAY__}
#sh{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.25) 0%,rgba(0,0,0,.55) 60%,rgba(0,0,0,.85) 100%)}
#tx{position:absolute;left:0;right:0;bottom:120px;text-align:center;color:#f3eadb;font-family:Plex;opacity:0;animation:fi 1.4s ease-out 1.1s forwards}
h1{font-weight:600;font-size:140px;margin:0;letter-spacing:.01em;text-shadow:0 2px 24px rgba(0,0,0,.8)}
p{font-weight:400;font-style:italic;font-size:40px;margin:14px 0 0;text-shadow:0 2px 18px rgba(0,0,0,.8)}
small{display:block;font-style:normal;font-size:26px;margin-top:26px;color:#cfc4b2;letter-spacing:.06em}
@keyframes fi{to{opacity:1}}
</style></head><body><div id="bg"></div><div id="sh"></div><div id="tx"><h1>Colophon</h1><p>__SUB__</p><small>__SMALL__</small></div></body></html>"""
open(os.path.join(HERE, "card_open.html"), "w").write(CARD.replace("__IMG__", os.path.join(ART, "title-a.jpg")).replace("__DELAY__", "0s")
    .replace("__SUB__", "A visual index and an identifier for a scanned library").replace("__SMALL__", "Meta Global AI Developer Hackathon 2026 &nbsp;·&nbsp; built on SAM 3.1 and Muse Spark"))
open(os.path.join(HERE, "card_close.html"), "w").write(CARD.replace("__IMG__", os.path.join(ART, "title-b.jpg")).replace("__DELAY__", "0s")
    .replace("__SUB__", "A library that knows what is on its pages.").replace("__SMALL__", "github.com/rtgconde/colophon"))
print("wrote", sorted(f for f in os.listdir(HERE) if f.endswith(".html")))
