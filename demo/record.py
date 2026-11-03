import os, sys, time, shutil
from playwright.sync_api import sync_playwright
S = os.path.dirname(os.path.abspath(__file__)); H = os.path.join(S, "html"); OUT = os.path.join(S, "rec"); os.makedirs(OUT, exist_ok=True)
BASE = "http://hub:8102"
CURSOR = open(os.path.join(S, "cursor.js")).read()
def rec(name, seconds, fn, cursor=True, scheme="dark"):
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=OUT, record_video_size={"width": 1920, "height": 1080}, color_scheme=scheme)
        if cursor: ctx.add_init_script(CURSOR)
        page = ctx.new_page(); t0 = time.time()
        try:
            fn(page)
            left = seconds - (time.time() - t0)
            if left > 0: page.wait_for_timeout(int(left * 1000))
        finally:
            path = page.video.path(); ctx.close(); b.close()
        dest = os.path.join(OUT, name + ".webm"); shutil.move(path, dest); print(f"{name:12} {time.time()-t0:5.1f}s", flush=True)
def html(name): return "file://" + os.path.join(H, name)
def wheel(page, x, y, dy, steps, ms):
    page.mouse.move(x, y)
    for _ in range(steps): page.mouse.wheel(0, dy); page.wait_for_timeout(ms)
def hover_cards(page, n, ms):
    cards = page.locator(".grid .card")
    for i in range(min(n, cards.count())):
        bb = cards.nth(i).bounding_box()
        if bb: page.mouse.move(bb["x"] + bb["width"]/2, bb["y"] + bb["height"]/2, steps=12); page.wait_for_timeout(ms)
def term(f):
    def go(page): page.goto(html(f))
    return go
def search1(page):   # the opening: one query, the first hit, the page view, the PDF link
    page.goto(BASE + "/"); page.wait_for_timeout(900)
    page.click("#q"); page.type("#q", "a woman reading a letter", delay=60); page.keyboard.press("Enter")
    page.wait_for_selector(".grid .card"); page.wait_for_timeout(1800)
    hover_cards(page, 3, 1000)
    page.locator(".grid .card").first.click(); page.wait_for_selector("text=Caption as printed", timeout=10000); page.wait_for_timeout(2600)
    page.mouse.move(1000, 430, steps=25); page.wait_for_timeout(1800)      # the record
    page.mouse.move(900, 528, steps=22); page.wait_for_timeout(2600)       # the MoMA PDF link
def search2(page):   # the second query, then the Works tab, slowly
    page.goto(BASE + "/"); page.wait_for_timeout(600)
    page.click("#q"); page.type("#q", "a city street at night", delay=55); page.keyboard.press("Enter")
    page.wait_for_selector(".grid .card"); page.wait_for_timeout(3200)      # let the lazy thumbnails land
    hover_cards(page, 2, 1200)
    tab = page.locator('.tabs button[data-tab="works"]'); bb = tab.bounding_box()
    page.mouse.move(bb["x"]+bb["width"]/2, bb["y"]+bb["height"]/2, steps=20); page.wait_for_timeout(300); tab.click()
    page.wait_for_selector(".works .work"); page.wait_for_timeout(2500)
    strips = page.locator(".works .work .strip .card")
    for i in range(min(6, strips.count())):                                 # along Green Still Life's six plates
        bb = strips.nth(i).bounding_box()
        if bb: page.mouse.move(bb["x"]+bb["width"]/2, bb["y"]+bb["height"]/2, steps=14); page.wait_for_timeout(700)
    wheel(page, 960, 600, 50, 44, 150)                                      # Silence, The Bathers, Rayograph...
    page.wait_for_timeout(800)
jobs = {"card_open": (5.5, term("card_open.html"), False), "search1": (22, search1, True), "search2": (32, search2, True),
        "ident": (48.5, term("ident.html"), False), "stats": (9, term("stats.html"), False), "card_close": (6, term("card_close.html"), False)}
for n in (sys.argv[1:] or list(jobs)):
    sec, fn, cur = jobs[n]; rec(n, sec, fn, cursor=cur)
