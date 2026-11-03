"""The re-cut's new pages: the opening card (new tagline), the stats page, and the identifier card (ident.html, built by
build_ident.py once the crops exist)."""
import os
HERE = os.path.dirname(os.path.abspath(__file__)); ART = os.path.join(HERE, "..")
CARD = open(os.path.join(HERE, "card_open.html")).read()
# the opening card: plain-words tagline
s = CARD.replace("A visual index and an identifier for a scanned library", "Search a scanned library by what is in the pictures. Know what every scan is.")
s = s.replace("p{font-weight:400;font-style:italic;font-size:40px;", "p{font-weight:400;font-style:italic;font-size:36px;max-width:1500px;margin-left:auto;margin-right:auto;")
open(os.path.join(HERE, "card_open.html"), "w").write(s)

STATS = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:Plex;src:url(ibm-plex-serif-latin-normal-600-182f05.woff2);font-weight:600}
@font-face{font-family:Plex;src:url(ibm-plex-serif-latin-normal-400-51510a.woff2);font-weight:400}
@font-face{font-family:Plex;src:url(ibm-plex-serif-latin-italic-400-8bf354.woff2);font-weight:400;font-style:italic}
html,body{margin:0;height:100%;background:#0f1114;color:#f3eadb;font-family:Plex;overflow:hidden}
#g{position:absolute;inset:0;display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(2,1fr);gap:0;padding:110px 120px;box-sizing:border-box}
.c{opacity:0;transform:translateY(14px);animation:up .7s ease-out forwards;padding:0 24px;border-left:2px solid #3a3f47;margin:18px 0}
.n{font-weight:600;font-size:92px;line-height:1;letter-spacing:-.01em}
.l{font-style:italic;font-size:30px;color:#cfc4b2;margin-top:14px;line-height:1.3}
@keyframes up{to{opacity:1;transform:none}}
#f{position:absolute;left:0;right:0;bottom:46px;text-align:center;font-style:italic;font-size:30px;color:#9a9283;opacity:0;animation:up .8s ease-out 5.2s forwards}
</style></head><body><div id="g">
<div class="c" style="animation-delay:.3s"><div class="n">757</div><div class="l">MoMA catalogues, 1929–2016</div></div>
<div class="c" style="animation-delay:1.0s"><div class="n">77,750</div><div class="l">pages segmented by SAM 3.1<br>in 5 h 12 min, 0 failures</div></div>
<div class="c" style="animation-delay:1.7s"><div class="n">93,527</div><div class="l">figures found</div></div>
<div class="c" style="animation-delay:2.6s"><div class="n">½¢</div><div class="l">to read a page with Muse Spark</div></div>
<div class="c" style="animation-delay:3.3s"><div class="n">3¢</div><div class="l">to identify a book; all 757 for $23</div></div>
<div class="c" style="animation-delay:4.0s"><div class="n">53</div><div class="l">catalogues indexed so far;<br>the rest is a matter of running it</div></div>
</div><div id="f">Python and SQLite · three small servers · a coordinator any GPU can join · MIT</div></body></html>"""
open(os.path.join(HERE, "stats.html"), "w").write(STATS)
print("wrote card_open.html (new tagline), stats.html")
