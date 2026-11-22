"""Keep the start fast. Fails when the page or its data outgrow their limits, or when something is put back in the way of the first paint.
Run from the site folder after tools/site.py:  python3 tools/budget.py
The limits only go down: when a change makes something smaller, lower its limit here in the same change."""
import gzip, os, re, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
LIMITS = {  # bytes as they travel
    "index.html": 50_000,               # squeezed the way the host does it (gzip, level 5)
    "hanoi-v3.json.gz": 1_060_000,      # the road map: the one big download of a first visit
    "hanoi-v3-places.json.gz": 440_000, # place names: only fetched for a search or a close look
}
bad = []
for name, limit in LIMITS.items():
    raw = open(os.path.join(ROOT, name), "rb").read()
    size = len(gzip.compress(raw, 5)) if name.endswith(".html") else len(raw)
    print("%-26s %9d of %9d bytes%s" % (name, size, limit, "" if size <= limit else "   OVER"))
    if size > limit: bad.append(name + " is over its limit")
page = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
RULES = [  # each one is a start-up gain that a later edit could undo without anyone noticing
    ("the map download starts in the head, before the styles", lambda: 0 <= page.find("EARLY.map = EARLY.load()") < page.find("<body>")),
    ("no stylesheet tag holds up the first paint (the fonts are added by script)", lambda: not re.search(r"<link[^>]+rel=[\"']?stylesheet", page)),
    ("no outside script is needed to start", lambda: not re.search(r"<script[^>]+src=", page)),
    ("the join step is in the page as it arrives, not switched on later", lambda: '<div class="app joining" id="app">' in page and '<div class="join" id="join">' in page),
]
for what, ok in RULES:
    good = ok(); print(("ok    " if good else "BROKEN ") + what)
    if not good: bad.append(what)
if bad: sys.exit("start-up budget broken: " + "; ".join(bad))
print("start-up budget holds")
