"""v3 pages: the wall of pages (wall.html), the two-jobs card (jobs.html), the how-it-works diagram (flow.html)."""
import os
HERE = os.path.dirname(os.path.abspath(__file__)); V = os.path.join(HERE, "..")
def f(p): return "file://" + os.path.join(V, p)
FONTS = """@font-face{font-family:Plex;src:url(ibm-plex-serif-latin-normal-600-182f05.woff2);font-weight:600}
@font-face{font-family:Plex;src:url(ibm-plex-serif-latin-normal-400-51510a.woff2);font-weight:400}
@font-face{font-family:Plex;src:url(ibm-plex-serif-latin-italic-400-8bf354.woff2);font-weight:400;font-style:italic}"""

# ── the wall: 20 × 12 thumbnails, the camera starting on one page and pulling back over 9 s ──────────────────
cells = "".join(f'<img src="{f("wall/%03d.jpg" % i)}">' for i in range(240))
WALL = f"""<!doctype html><html><head><meta charset="utf-8"><style>{FONTS}
html,body{{margin:0;height:100%;background:#0b0d10;overflow:hidden}}
#g{{position:absolute;left:0;top:0;width:1920px;height:1080px;display:grid;grid-template-columns:repeat(20,96px);grid-auto-rows:90px;gap:0;
    transform-origin:50% 50%;transform:scale(7.2) translate(0,0);animation:pull 7.5s cubic-bezier(.3,.1,.2,1) forwards}}
#g img{{width:96px;height:90px;object-fit:cover;display:block;filter:brightness(.92)}}
@keyframes pull{{to{{transform:scale(1) translate(0,0)}}}}
#v{{position:absolute;inset:0;background:radial-gradient(ellipse at center,rgba(0,0,0,0) 45%,rgba(0,0,0,.65) 100%)}}
</style></head><body><div id="g">{cells}</div><div id="v"></div></body></html>"""
open(os.path.join(HERE, "wall.html"), "w").write(WALL)

# ── two jobs ───────────────────────────────────────────────────────────────────────────────────────────────────
JOBS = f"""<!doctype html><html><head><meta charset="utf-8"><style>{FONTS}
html,body{{margin:0;height:100%;background:#0f1114;color:#f3eadb;font-family:Plex;overflow:hidden}}
h1{{position:absolute;left:0;right:0;top:70px;text-align:center;margin:0;font-weight:600;font-size:54px;opacity:0;animation:fi .8s ease-out .2s forwards}}
h1 i{{display:block;font-weight:400;font-size:30px;color:#cfc4b2;margin-top:10px}}
.col{{position:absolute;top:250px;width:760px;opacity:0;transform:translateY(16px);animation:up .8s ease-out forwards}}
#a{{left:150px;animation-delay:1.6s}} #b{{right:150px;animation-delay:4.6s}}
.col .n{{font-weight:600;font-size:28px;letter-spacing:.14em;text-transform:uppercase;color:#ffd866}}
.col h2{{font-weight:600;font-size:46px;margin:14px 0 10px;line-height:1.2}}
.col p{{font-style:italic;font-size:30px;color:#cfc4b2;margin:0 0 26px;line-height:1.4}}
.col .im{{height:380px;border-radius:6px;overflow:hidden;border:2px solid #2b2f36;background:#000}}
.col .im img{{width:100%;height:100%;object-fit:cover}}
@keyframes fi{{to{{opacity:1}}}} @keyframes up{{to{{opacity:1;transform:none}}}}
</style></head><body>
<h1>Two jobs<i>what a scanned library needs to behave like a catalogued one</i></h1>
<div class="col" id="a"><div class="n">1 · the visual index</div><h2>Find and read every picture on every page</h2><p>so you can search for what you remember</p><div class="im"><img src="{f('pages/0125.jpg')}"></div></div>
<div class="col" id="b"><div class="n">2 · the identifier</div><h2>Identify every book from its own pages</h2><p>so no scan stays anonymous</p><div class="im"><img src="{f('ident/13206-0009.jpg')}"></div></div>
</body></html>"""
open(os.path.join(HERE, "jobs.html"), "w").write(JOBS)

# ── how it works: two rows of steps, lit one after another ─────────────────────────────────────────────────────
FLOW = f"""<!doctype html><html><head><meta charset="utf-8"><style>{FONTS}
html,body{{margin:0;height:100%;background:#0f1114;color:#f3eadb;font-family:Plex;overflow:hidden}}
h1{{position:absolute;left:70px;top:44px;margin:0;font-weight:400;font-size:26px;letter-spacing:.14em;text-transform:uppercase;color:#9a9283}}
.row{{position:absolute;left:70px;right:70px;display:flex;align-items:center;gap:0}}
#r1{{top:150px}} #r2{{top:600px}}
.lbl{{position:absolute;left:70px;font-style:italic;font-size:28px;color:#cfc4b2}}
#l1{{top:106px}} #l2{{top:556px}}
.st{{flex:1;padding:22px 26px;border:2px solid #2b2f36;border-radius:10px;background:#141820;min-height:300px;opacity:.18;transition:opacity .5s,border-color .5s}}
.st.on{{opacity:1;border-color:#ffd866}}
.st .k{{font-weight:600;font-size:30px;margin-bottom:8px}}
.st .m{{font-size:22px;color:#ffd866;letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px}}
.st p{{font-size:24px;line-height:1.4;color:#cfc4b2;margin:0;font-style:italic}}
.st .im{{margin-top:14px;height:150px;border-radius:5px;overflow:hidden;background:#000}}
.st .im img{{width:100%;height:100%;object-fit:cover}}
.ar{{width:64px;text-align:center;font-size:44px;color:#3a3f47}}
</style></head><body>
<h1>How it works</h1>
<div class="lbl" id="l1">the visual index, every page</div>
<div class="row" id="r1">
 <div class="st"><div class="m">local · SAM 3.1</div><div class="k">Box every picture</div><p>eight prompts, every box kept; two DGX Sparks and a gaming PC, a page a second each</p><div class="im"><img src="{'file:///Users/rtgconde/dev_projects/03_lab/meta_hackaton/docs/img/reader-input.jpg'}"></div></div>
 <div class="ar">→</div>
 <div class="st"><div class="m">Meta Model API · Muse Spark</div><div class="k">Read the page</div><p>what each picture shows, and the caption as printed: artist, title, year, medium, credit</p><div class="im"><img src="{f('pages/0125.jpg')}"></div></div>
 <div class="ar">→</div>
 <div class="st"><div class="m">bge-m3 · Qdrant</div><div class="k">Search in plain words</div><p>every figure a point; a hit links to its page, its caption and MoMA's PDF; works joined across catalogues</p><div class="im"><img src="{'file:///Users/rtgconde/dev_projects/03_lab/meta_hackaton/docs/img/search.jpg'}"></div></div>
</div>
<div class="lbl" id="l2">the identifier, every book</div>
<div class="row" id="r2">
 <div class="st"><div class="m">the book's own pages</div><div class="k">Title page, copyright page, last pages</div><p>plus any page whose text shows an ISBN or a copyright line</p><div class="im"><img src="{f('ident/13206-0009.jpg')}"></div></div>
 <div class="ar">→</div>
 <div class="st"><div class="m">Meta Model API · Muse Spark</div><div class="k">One catalogue record</div><p>title, authors, publisher, year, ISBNs, series; the page each field came from; nothing guessed</p></div>
 <div class="ar">→</div>
 <div class="st"><div class="m">checksum · Open Library</div><div class="k">Verified, or not</div><p>an ISBN counts only when its checksum passes and Open Library's title matches the title page</p></div>
</div>
<script>
const steps = document.querySelectorAll('.st'); const order = [0,1,2,3,4,5]; const T = [0.5, 1.9, 3.3, 5.2, 6.6, 8.0];
order.forEach((i, k) => setTimeout(() => steps[i].classList.add('on'), T[k]*1000));
</script></body></html>"""
open(os.path.join(HERE, "flow.html"), "w").write(FLOW)
print("wrote wall.html, jobs.html, flow.html")
