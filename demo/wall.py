import json, os, random
from PIL import Image
os.chdir("/srv/colophon"); random.seed(1929)
os.makedirs("/tmp/wall", exist_ok=True)
books = [b for b in json.load(open("books.json")) if (b.get("pages") or 0) > 8]
picked = 0
while picked < 240:
    b = random.choice(books); p = random.randint(2, b["pages"])
    src = "pages/%d/%04d.jpg" % (b["id"], p)
    if not os.path.exists(src): continue
    im = Image.open(src); im.thumbnail((260, 260)); im.save("/tmp/wall/%03d.jpg" % picked, quality=80); picked += 1
print("thumbs", picked)
