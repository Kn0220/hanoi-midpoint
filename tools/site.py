"""Turn the artifact page into a standalone site folder (index.html + data files)."""
import sys, shutil, os
src, out = sys.argv[1], sys.argv[2]
live_db = sys.argv[3] if len(sys.argv) > 3 else ""
page = open(os.path.join(src, "index.html"), encoding="utf-8").read()
cut = page.index("</style>") + len("</style>")
head, body = page[:cut], page[cut:]
if live_db:
    marker = "const LIVE_DB = '';"
    assert body.count(marker) == 1, "LIVE_DB marker missing"
    body = body.replace(marker, "const LIVE_DB = '%s';" % live_db)
icon = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%23E8B33C'/%3E%3Cpath d='M16 7l2.6 5.6 6.1.7-4.5 4.2 1.2 6-5.4-3-5.4 3 1.2-6-4.5-4.2 6.1-.7z' fill='%2317211E'/%3E%3C/svg%3E"
doc = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
       '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
       '<meta name="description" content="Find the fairest place in Hanoi for a group of friends to meet, by real road travel time.">\n'
       '<link rel="icon" href="' + icon + '">\n'
       '<style>:root{color-scheme:light;padding:env(safe-area-inset-top,0px) 0 env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}</style>\n'
       + head + '\n</head>\n<body>' + body + '\n</body>\n</html>\n')
os.makedirs(out, exist_ok=True)
open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(doc)
for f in ("hanoi-v2.json", "hanoi-v2-places.json"):
    shutil.copyfile(os.path.join(src, f), os.path.join(out, f))
open(os.path.join(out, ".nojekyll"), "w").close()
print("site built:", out, len(doc), "bytes", "live" if live_db else "no live database")
