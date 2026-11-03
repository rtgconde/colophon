import os, sys, time, json, shutil
from playwright.sync_api import sync_playwright
S = os.path.dirname(os.path.abspath(__file__)); H = os.path.join(S, "html"); OUT = os.path.join(S, "rec"); os.makedirs(OUT, exist_ok=True)  # html/ from build_html.py, rec/ gets the webm files
BASE = "http://hub:8102"
CURSOR = """
(() => { const c = document.createElement('div'); c.id='__cur';
c.style.cssText='position:fixed;left:-50px;top:-50px;width:22px;height:30px;z-index:2147483647;pointer-events:none;transition:none';
c.innerHTML='<svg width="22" height="30" viewBox="0 0 22 30"><path d="M2 2 L2 24 L8 18 L12 28 L16 26 L12 17 L20 17 Z" fill="#fff" stroke="#000" stroke-width="1.5"/></svg>';
const add=()=>document.body&&document.body.appendChild(c); if(document.body) add(); else document.addEventListener('DOMContentLoaded',add);
window.addEventListener('mousemove',e=>{c.style.left=e.clientX+'px';c.style.top=e.clientY+'px'},true); })();
"""
def rec(name, seconds, fn, cursor=True, scheme="dark"):
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=OUT, record_video_size={"width": 1920, "height": 1080},
                            color_scheme=scheme, device_scale_factor=1)
        if cursor: ctx.add_init_script(CURSOR)
        page = ctx.new_page(); t0 = time.time()
        try:
            fn(page)
            left = seconds - (time.time() - t0)
            if left > 0: page.wait_for_timeout(int(left * 1000))
        finally:
            path = page.video.path(); ctx.close(); b.close()
        dest = os.path.join(OUT, name + ".webm"); shutil.move(path, dest)
        print(f"{name:12} {time.time()-t0:5.1f}s -> {dest}", flush=True)

def html(name):  return "file://" + os.path.join(H, name)
def wheel(page, x, y, dy, steps, ms):
    page.mouse.move(x, y)
    for _ in range(steps): page.mouse.wheel(0, dy); page.wait_for_timeout(ms)
def hover_cards(page, n, ms):
    cards = page.locator(".grid .card")
    for i in range(min(n, cards.count())):
        bb = cards.nth(i).bounding_box()
        if bb: page.mouse.move(bb["x"] + bb["width"]/2, bb["y"] + bb["height"]/2, steps=12); page.wait_for_timeout(ms)

def card_open(page):  page.goto(html("card_open.html"))
def card_close(page): page.goto(html("card_close.html"))
def term(f):
    def go(page): page.goto(html(f))
    return go
def pageview(page):
    page.goto(BASE + "/page/13269/0125?k=0"); page.wait_for_timeout(1200)
    page.mouse.move(400, 500, steps=20); page.wait_for_timeout(1500)
    page.mouse.move(1000, 430, steps=25); page.wait_for_timeout(2500)   # the record
    page.mouse.move(900, 528, steps=20); page.wait_for_timeout(2500)    # MoMA PDF link
def search(page):
    page.goto(BASE + "/"); page.wait_for_timeout(1000)
    page.click("#q"); page.type("#q", "a woman reading a letter", delay=55); page.keyboard.press("Enter")
    page.wait_for_selector(".grid .card"); page.wait_for_timeout(1400)
    hover_cards(page, 3, 900)
    page.locator(".grid .card").first.click(); page.wait_for_selector("text=Caption as printed", timeout=10000); page.wait_for_timeout(2200)
    page.mouse.move(900, 528, steps=25); page.wait_for_timeout(1800)
    page.go_back(); page.wait_for_selector("#q"); page.wait_for_timeout(900)
    page.fill("#q", ""); page.click("#q"); page.type("#q", "a city street at night", delay=55); page.keyboard.press("Enter")
    page.wait_for_selector(".grid .card"); page.wait_for_timeout(1400)
    hover_cards(page, 2, 900)
    f = page.locator("#facets button", has_text="painting").first
    bb = f.bounding_box()
    if bb: page.mouse.move(bb["x"]+bb["width"]/2, bb["y"]+bb["height"]/2, steps=18); page.wait_for_timeout(400); f.click()
    page.wait_for_timeout(2500)
def works(page):
    page.goto(BASE + "/#works"); page.wait_for_selector(".works .work"); page.wait_for_timeout(1800)
    wheel(page, 960, 600, 60, 40, 140)          # ~5.6 s of slow scroll
    page.wait_for_timeout(600)
    tab = page.locator('.tabs button[data-tab="books"]'); bb = tab.bounding_box()
    page.mouse.move(bb["x"]+bb["width"]/2, bb["y"]+bb["height"]/2, steps=20); page.wait_for_timeout(300); tab.click()
    page.wait_for_selector(".books .book"); page.wait_for_timeout(1800)
    wheel(page, 960, 600, 60, 14, 120)
    bk = page.locator(".books .book", has_text="Bauhaus").first; bk.scroll_into_view_if_needed(); page.wait_for_timeout(500)
    bb = bk.bounding_box(); page.mouse.move(bb["x"]+bb["width"]/2, bb["y"]+bb["height"]/2, steps=20); page.wait_for_timeout(300); bk.click()
    page.wait_for_selector(".grid .card"); page.wait_for_timeout(1500)
    wheel(page, 960, 600, 60, 20, 130)
def readme(page):
    page.goto("https://github.com/rtgconde/colophon", wait_until="domcontentloaded"); page.wait_for_timeout(2500)
    wheel(page, 960, 700, 70, 60, 150)

jobs = {"card_open": (6, card_open, False), "t02a": (8.5, term("t02a.html"), False), "t02c": (8.5, term("t02c.html"), False),
        "pageview": (12, pageview, True), "search": (26, search, True), "works": (23, works, True),
        "t06": (43.5, term("t06.html"), False), "t07": (6, term("t07.html"), False), "readme": (16, readme, True),
        "card_close": (6, card_close, False)}
only = sys.argv[1:] or list(jobs)
for n in only:
    sec, fn, cur = jobs[n]; rec(n, sec, fn, cursor=cur, scheme="light" if n == "readme" else "dark")
