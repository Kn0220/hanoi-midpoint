"""Fetch OpenStreetMap data for a city bbox from Overpass, with retries across mirrors."""
import sys, time, urllib.request, urllib.parse, json, os

OUT = sys.argv[1]
BBOX = sys.argv[2]  # "south,west,north,east"
ONLY = sys.argv[3:]

HW = "motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|pedestrian|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link"
KEYS = "amenity|shop|tourism|leisure|office|building|landuse|place|railway|public_transport|historic|craft|healthcare|aeroway|man_made|residential"
_s, _w, _n, _e = [float(x) for x in BBOX.split(",")]
def tiles(T):
    for i in range(T):
        for j in range(T):
            yield i, j, f"{_s + (_n - _s) * i / T:.5f},{_w + (_e - _w) * j / T:.5f},{_s + (_n - _s) * (i + 1) / T:.5f},{_w + (_e - _w) * (j + 1) / T:.5f}"
QUERIES = {
    "water": f'[out:json][timeout:170];(way["natural"="water"]({BBOX});relation["natural"="water"]({BBOX});way["waterway"~"^(river|canal)$"]({BBOX}););out geom;',
    "green": f'[out:json][timeout:170];(way["leisure"~"^(park|garden|golf_course|nature_reserve)$"]({BBOX});way["landuse"~"^(forest|cemetery|recreation_ground|grass)$"]({BBOX});way["natural"="wood"]({BBOX});way["aeroway"~"^(runway|taxiway)$"]({BBOX});way["railway"~"^(rail|subway|light_rail)$"]({BBOX}););out geom;',
    "admin": f'[out:json][timeout:170];relation["boundary"="administrative"]["admin_level"~"^(5|6|7|8)$"]({BBOX});out center tags;',
    "addr": f'[out:json][timeout:170];nwr["addr:housenumber"]({BBOX});out center tags;',
}
for i, j, b in tiles(2):
    QUERIES[f"named_{i}{j}"] = f'[out:json][timeout:170];nwr["name"][~"^({KEYS})$"~"."]({b});out center tags;'
for i, j, b in tiles(4):
    QUERIES[f"roads_{i}{j}"] = (f'[out:json][timeout:170];(way["highway"~"^({HW})$"]({b});'
                               f'way["highway"~"^(footway|path|track)$"]["name"]({b}););out geom;')

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]

def fetch(name, q):
    path = os.path.join(OUT, name + ".json")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        print(name, "already present", flush=True)
        return True
    for attempt in range(14):
        url = MIRRORS[attempt % len(MIRRORS)]
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                         headers={"User-Agent": "meetup-finder/0.1"})
            with urllib.request.urlopen(req, timeout=200) as r:
                body = r.read()
            j = json.loads(body)
            if "elements" not in j or (j.get("remark") and not j["elements"]):
                raise RuntimeError("bad payload: " + str(j.get("remark"))[:200])
            with open(path, "wb") as f:
                f.write(body)
            print(name, "ok", len(j["elements"]), "elements", len(body), "bytes via", url, j.get("remark", ""), flush=True)
            return True
        except Exception as e:
            print(name, "attempt", attempt, url, "failed:", str(e)[:150], flush=True)
            time.sleep(min(60, 6 + attempt * 6))
    return False

ok = True
for name, q in QUERIES.items():
    if ONLY and name not in ONLY:
        continue
    ok = fetch(name, q) and ok
print("DONE" if ok else "INCOMPLETE", flush=True)
