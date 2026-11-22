"""Turn the artifact page into a standalone site folder (index.html + data files)."""
import sys, shutil, os, gzip
src, out = sys.argv[1], sys.argv[2]
live_db = sys.argv[3] if len(sys.argv) > 3 else ""
site_url = sys.argv[4] if len(sys.argv) > 4 else "https://kn0220.github.io/hanoi-midpoint/"  # where the site is served; link previews need full addresses
about = "Add a pin for each friend and get the fairest place in Hanoi to meet, by real ride time."
page = open(os.path.join(src, "index.html"), encoding="utf-8").read()
if live_db:
    marker = "const LIVE_DB = '';"
    assert page.count(marker) == 1, "LIVE_DB marker missing"
    page = page.replace(marker, "const LIVE_DB = '%s';" % live_db)
DATA = ("hanoi-v3.json", "hanoi-v3-places.json")
marker = "const PACKED = '';"  # the page then asks for name.json.gz first: the same bytes, squeezed harder than the host does on the way out
assert page.count(marker) == 1, "PACKED marker missing"
page = page.replace(marker, "const PACKED = '.gz';")
cut = page.index("</style>") + len("</style>")  # the head ends with the styles; the script that starts the map download sits above them
head, body = page[:cut], page[cut:]
icon = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%231B4B9B'/%3E%3Crect x='3' y='3' width='26' height='26' rx='4.5' fill='none' stroke='%23fff' stroke-width='1.4'/%3E%3Cpath d='M16 7.5l2.5 5.3 5.8.7-4.3 4 1.1 5.7-5.1-2.8-5.1 2.8 1.1-5.7-4.3-4 5.8-.7z' fill='%23F7C531'/%3E%3C/svg%3E"
doc = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
       '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
       '<meta name="description" content="' + about + '">\n'
       '<meta property="og:type" content="website">\n'
       '<meta property="og:site_name" content="Hanoi Midpoint">\n'
       '<meta property="og:title" content="Hanoi Midpoint">\n'
       '<meta property="og:description" content="' + about + '">\n'
       '<meta property="og:url" content="' + site_url + '">\n'
       '<meta property="og:image" content="' + site_url + 'og.png">\n'
       '<meta property="og:image:type" content="image/png">\n'
       '<meta property="og:image:width" content="1200">\n'
       '<meta property="og:image:height" content="630">\n'
       '<meta property="og:image:alt" content="A map of Hanoi with four friends\' routes meeting at one starred spot.">\n'
       '<meta name="twitter:card" content="summary_large_image">\n'
       '<meta name="theme-color" content="#1B4B9B">\n'
       '<link rel="icon" href="' + icon + '">\n'
       '<style>:root{color-scheme:light;padding:env(safe-area-inset-top,0px) 0 env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}</style>\n'
       + head + '\n</head>\n<body>' + body + '\n</body>\n</html>\n')
os.makedirs(out, exist_ok=True)
open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(doc)
for f in DATA + ("og.png",):  # og.png is the picture shown when the link is shared
    a, b = os.path.join(src, f), os.path.join(out, f)
    if os.path.exists(a) and os.path.abspath(a) != os.path.abspath(b):
        shutil.copyfile(a, b)
    assert os.path.exists(b), "missing " + f
for f in DATA:
    raw = open(os.path.join(out, f), "rb").read()
    with open(os.path.join(out, f + ".gz"), "wb") as fh:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fh, compresslevel=9, mtime=0) as z:  # no name or time inside, so the same data always gives the same file
            z.write(raw)
    print(f, len(raw), "bytes,", os.path.getsize(os.path.join(out, f + ".gz")), "squeezed")
open(os.path.join(out, ".nojekyll"), "w").close()
print("site built:", out, len(doc), "bytes", "live" if live_db else "no live database")
