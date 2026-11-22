"""Turn raw Overpass JSON into the two data files the meeting-point page loads.

usage: build.py <data_dir> <out_prefix> "<City name>" "south,west,north,east"
writes <out_prefix>.json (roads, venues, map shapes) and <out_prefix>-places.json (search index)
"""
import json, math, os, re, sys, unicodedata
from collections import defaultdict

DATA, OUT, CITY, BBOX = sys.argv[1], sys.argv[2], sys.argv[3], [float(x) for x in sys.argv[4].split(",")]
S, W, N, E = BBOX
Q = 1e5                      # coordinate quantum: 1e-5 degrees (about 1.1 m)
LAT0, LON0 = (S + N) / 2, (W + E) / 2
MY = 111320.0 / Q            # metres per quantum, north-south
MX = MY * math.cos(math.radians(LAT0))

def load(prefix):
    """All elements from <prefix>.json or the tiles <prefix>_*.json, without duplicates."""
    out, seen = [], set()
    for fn in sorted(os.listdir(DATA)):
        if fn == prefix + ".json" or (fn.startswith(prefix + "_") and fn.endswith(".json")):
            with open(os.path.join(DATA, fn), "rb") as f:
                j = json.load(f)
            if j.get("remark"):
                print("WARNING", fn, "remark:", j["remark"][:120])
            for el in j["elements"]:
                k = (el["type"], el["id"])
                if k not in seen:
                    seen.add(k)
                    out.append(el)
    return out

def q(lat, lon):
    return (round((lon - LON0) * Q), round((lat - LAT0) * Q))

def dist_m(a, b):
    return math.hypot((a[0] - b[0]) * MX, (a[1] - b[1]) * MY)

def line_m(pts):
    return sum(dist_m(pts[i], pts[i + 1]) for i in range(len(pts) - 1))

def fold(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.replace("đ", "d").replace("Đ", "D").lower()

def simplify(pts, tol):
    """Douglas-Peucker on quantised points, tolerance in metres."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        ax, ay = pts[i][0] * MX, pts[i][1] * MY
        bx, by = pts[j][0] * MX, pts[j][1] * MY
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        best, bi = -1.0, -1
        for k in range(i + 1, j):
            px, py = pts[k][0] * MX - ax, pts[k][1] * MY - ay
            if L2 == 0:
                d = math.hypot(px, py)
            else:
                t = max(0.0, min(1.0, (px * dx + py * dy) / L2))
                d = math.hypot(px - t * dx, py - t * dy)
            if d > best:
                best, bi = d, k
        if best > tol:
            keep[bi] = True
            stack.append((i, bi))
            stack.append((bi, j))
    return [p for p, k in zip(pts, keep) if k]

def center(el):
    if "lat" in el:
        return el["lat"], el["lon"]
    c = el.get("center")
    return (c["lat"], c["lon"]) if c else None

def inside(lat, lon):
    return S <= lat <= N and W <= lon <= E

# ---------------------------------------------------------------- roads
# class 7 = alleys and other small ways: service roads, pedestrian streets, named paths
CLS = {"motorway": 0, "motorway_link": 0, "trunk": 1, "trunk_link": 1, "primary": 2, "primary_link": 2,
       "secondary": 3, "secondary_link": 3, "tertiary": 4, "tertiary_link": 4,
       "unclassified": 5, "residential": 5, "living_street": 6,
       "service": 7, "pedestrian": 7, "footway": 7, "path": 7, "track": 7}
NCLS = 8
STREETISH = re.compile(r"^(ngõ|ngách|hẻm|ngo|ngach|hem|phố|đường|xóm|thôn|tổ|lối)\b", re.I)
ALLEY = re.compile(r"^(ngõ|ngách|hẻm|ngo|ngach|hem)\b", re.I)
GENERIC = re.compile(r"^(ngõ|ngách|hẻm|ngo|ngach|hem)\s*\d+\w*(\s*/\s*\d+\w*)*$", re.I)

ways = []
use = defaultdict(int)
for w in load("roads"):
    t = w.get("tags", {})
    hw = t.get("highway")
    if w["type"] != "way" or hw not in CLS:
        continue
    if t.get("access") in ("private", "no") or t.get("area") == "yes":
        continue
    name = t.get("name", "").strip()
    if hw == "service" and (t.get("service") in ("parking_aisle", "drive-through", "emergency_access") or t.get("access") in ("customers", "delivery")):
        continue
    if hw in ("footway", "path", "track") and not STREETISH.match(name):
        continue
    nodes, geom = w["nodes"], w["geometry"]
    if len(nodes) < 2 or any(g is None for g in geom):
        continue
    cls = CLS[hw]
    ow = t.get("oneway", "")
    oneway = ow in ("yes", "1", "true") or t.get("junction") in ("roundabout", "circular") or (hw == "motorway" and ow != "no")
    if ow == "-1":
        nodes, geom, oneway = nodes[::-1], geom[::-1], True
    nobike = cls == 0 or t.get("motorroad") == "yes" or t.get("motorcycle") == "no" or t.get("motor_vehicle") == "no"
    nocar = t.get("motorcar") == "no" or t.get("motor_vehicle") == "no"
    if cls == 7 and t.get("motorcar") != "yes" and (hw != "service" or t.get("service") == "alley" or ALLEY.match(name)):
        nocar = True
    ways.append((nodes, geom, cls, oneway, nobike, nocar, name))
    for i, n in enumerate(nodes):
        use[n] += 2 if i in (0, len(nodes) - 1) else 1

vid = {}
vpos = []
def vertex(n, g):
    if n not in vid:
        vid[n] = len(vpos)
        vpos.append(q(g["lat"], g["lon"]))
    return vid[n]

edges = []   # [a, b, cls, oneway, nobike, nocar, name, pts]
for nodes, geom, cls, oneway, nobike, nocar, name in ways:
    start = 0
    for i in range(1, len(nodes)):
        if use[nodes[i]] >= 2:
            a, b = vertex(nodes[start], geom[start]), vertex(nodes[i], geom[i])
            pts = [q(g["lat"], g["lon"]) for g in geom[start:i + 1]]
            if a != b:
                edges.append([a, b, cls, oneway, nobike, nocar, name, pts])
            start = i
print("raw vertices", len(vpos), "edges", len(edges))

def largest_scc(nv, arcs):
    """Kosaraju, iterative. arcs: list of (u, v). Returns set of vertices in the largest SCC."""
    fwd, rev = [[] for _ in range(nv)], [[] for _ in range(nv)]
    for u, v in arcs:
        fwd[u].append(v)
        rev[v].append(u)
    seen, order = [False] * nv, []
    for s in range(nv):
        if seen[s]:
            continue
        seen[s] = True
        st = [(s, 0)]
        while st:
            u, i = st[-1]
            if i < len(fwd[u]):
                st[-1] = (u, i + 1)
                v = fwd[u][i]
                if not seen[v]:
                    seen[v] = True
                    st.append((v, 0))
            else:
                order.append(u)
                st.pop()
    comp, best, bestc = [-1] * nv, 0, -1
    c = 0
    for s in reversed(order):
        if comp[s] != -1:
            continue
        comp[s], size, st = c, 0, [s]
        while st:
            u = st.pop()
            size += 1
            for v in rev[u]:
                if comp[v] == -1:
                    comp[v] = c
                    st.append(v)
        if size > best:
            best, bestc = size, c
        c += 1
    return {i for i in range(nv) if comp[i] == bestc}

def arcs_of(es, pred):
    out = []
    for a, b, cls, oneway, nobike, nocar, name, pts in es:
        if pred(nobike, nocar):
            out.append((a, b))
            if not oneway:
                out.append((b, a))
    return out

nv = len(vpos)
bike_ok = largest_scc(nv, arcs_of(edges, lambda nb, nc: not nb))
car_ok = largest_scc(nv, arcs_of(edges, lambda nb, nc: not nc))
any_ok = bike_ok | car_ok
# an edge stays if at least one way of travelling can use it inside its connected network
edges = [e for e in edges if (not e[4] and e[0] in bike_ok and e[1] in bike_ok) or (not e[5] and e[0] in car_ok and e[1] in car_ok)]
any_ok = {e[0] for e in edges} | {e[1] for e in edges}

# reindex vertices in a spatially coherent order so deltas stay small
keep = sorted(any_ok, key=lambda i: (vpos[i][1] // 400, vpos[i][0]))
remap = {old: new for new, old in enumerate(keep)}
vpos2 = [vpos[i] for i in keep]
vflag = [(1 if i in bike_ok else 0) | (2 if i in car_ok else 0) for i in keep]
for e in edges:
    e[0], e[1] = remap[e[0]], remap[e[1]]
    e[7] = simplify(e[7], 2.5 if e[2] < 7 else 3.5)
edges.sort(key=lambda e: (e[2], e[0]))
elen = [line_m(e[7]) for e in edges]
print("kept vertices", len(vpos2), "edges", len(edges), "bike ok", sum(1 for f in vflag if f & 1), "car ok", sum(1 for f in vflag if f & 2))

names = [""]
name_ix = {"": 0}
by_name = defaultdict(list)
for ei, e in enumerate(edges):
    nm = e[6]
    if nm not in name_ix:
        name_ix[nm] = len(names)
        names.append(nm)
    if nm:
        by_name[nm].append(ei)

# One search entry per separate street of a given name ("Ngõ 12" exists many times over).
vedges = defaultdict(list)
for ei, e in enumerate(edges):
    vedges[e[0]].append(ei)
    vedges[e[1]].append(ei)

def mid(ei):
    p = edges[ei][7]
    return p[len(p) // 2]

streets = []      # (name index, x, y, context name index, metres)
for nm, eis in by_name.items():
    parent = {i: i for i in eis}
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[a] = b
    byv, cell = defaultdict(list), defaultdict(list)
    for i in eis:
        byv[edges[i][0]].append(i)
        byv[edges[i][1]].append(i)
        m = mid(i)
        cell[(m[0] // 300, m[1] // 300)].append(i)
    for l in byv.values():
        for i in l[1:]:
            union(l[0], i)
    for (cx, cy), l in cell.items():
        for i in l[1:]:
            union(l[0], i)
        for d in ((1, 0), (0, 1), (1, 1), (-1, 1)):
            o = cell.get((cx + d[0], cy + d[1]))
            if o:
                union(l[0], o[0])
    groups = defaultdict(list)
    for i in eis:
        groups[find(i)].append(i)
    for g in groups.values():
        ms = [mid(i) for i in g]
        cx, cy = sum(p[0] for p in ms) / len(ms), sum(p[1] for p in ms) / len(ms)
        rep = min(ms, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
        ctx = 0
        if GENERIC.match(nm):
            mine, best = set(g), None
            for i in g:
                for v in (edges[i][0], edges[i][1]):
                    for o in vedges[v]:
                        on = edges[o][6]
                        if o in mine or not on or on == nm:
                            continue
                        key = (1 if ALLEY.match(on) else 0, edges[o][2], -elen[o])
                        if best is None or key < best[0]:
                            best = (key, on)
            if best:
                ctx = name_ix[best[1]]
        streets.append((name_ix[nm], rep[0], rep[1], ctx, sum(elen[i] for i in g)))
streets.sort(key=lambda r: (r[0], -r[4]))
print("street names", len(names) - 1, "street entries", len(streets), "with context", sum(1 for s in streets if s[3]))

def delta(seq):
    out, prev = [], 0
    for x in seq:
        out.append(x - prev)
        prev = x
    return out

geo = []
for a, b, cls, oneway, nobike, nocar, name, pts in edges:
    inner = pts[1:-1]
    geo.append(len(inner))
    px, py = pts[0]
    for x, y in inner:
        geo.extend((x - px, y - py))
        px, py = x, y

cls_runs = [0] * NCLS
for e in edges:
    cls_runs[e[2]] += 1
print("edges per class", cls_runs)

# ------------------------------------------------- nearest vertex lookup
CELL = 300
grid = defaultdict(list)
for i, (x, y) in enumerate(vpos2):
    grid[(x // CELL, y // CELL)].append(i)

def nearest(p, mask=1, maxr=4):
    cx, cy = p[0] // CELL, p[1] // CELL
    best, bi = 1e18, -1
    for r in range(maxr + 1):
        for gx in range(cx - r, cx + r + 1):
            for gy in range(cy - r, cy + r + 1):
                if max(abs(gx - cx), abs(gy - cy)) != r:
                    continue
                for i in grid.get((gx, gy), ()):
                    if not vflag[i] & mask:
                        continue
                    d = dist_m(p, vpos2[i])
                    if d < best:
                        best, bi = d, i
        if bi != -1 and best < r * CELL * MX:
            break
    return bi, best

# ---------------------------------------------------------------- venues and the place index
VENUE = {"cafe": 0, "ice_cream": 0, "restaurant": 1, "fast_food": 1, "food_court": 1, "bar": 2, "pub": 2, "biergarten": 2}
# index kinds: 0 area, 1 homes, 2 school, 3 health, 4 shop, 5 transit, 6 sight, 7 address, 8 other
def kind_of(t):
    a = t.get("amenity", "")
    if a in VENUE:
        return None
    if "place" in t:
        return 0
    if t.get("landuse") == "residential" or t.get("building") in ("apartments", "residential", "dormitory", "house") or "residential" in t:
        return 1
    if a in ("school", "kindergarten", "university", "college", "language_school", "library"):
        return 2
    if a in ("hospital", "clinic", "doctors", "pharmacy", "dentist") or "healthcare" in t:
        return 3
    if "shop" in t or a == "marketplace":
        return 4
    if t.get("railway") in ("station", "halt", "stop") or "public_transport" in t or a in ("bus_station", "ferry_terminal") or "aeroway" in t:
        return 5
    if t.get("tourism") in ("attraction", "museum", "viewpoint", "zoo", "theme_park", "gallery", "artwork") or "historic" in t or t.get("leisure") in ("park", "garden", "stadium", "sports_centre", "water_park") or a in ("place_of_worship", "theatre", "cinema"):
        return 6
    return 8

def alt_names(t, nm):
    """Other names people search by (English, short, former, official), minus anything the main name already contains."""
    base, out = fold(nm), []
    for k in ("alt_name", "short_name", "name:en", "official_name", "old_name", "name:vi", "loc_name"):
        for part in t.get(k, "").split(";"):
            part = " ".join(part.split())
            f = fold(part)
            if part and len(part) <= 70 and f not in base and all(f not in fold(o) for o in out):
                out.append(part)
    return " / ".join(out)[:120]

named = load("named")
pois, seen = [], set()
idx, seeni = [], set()
RANK = {"city": 0, "town": 1, "suburb": 2, "quarter": 3, "village": 3, "neighbourhood": 4, "hamlet": 4}
areas, seena = [], set()
for el in named:
    t = el.get("tags", {})
    c = center(el)
    nm = " ".join(t.get("name", "").split())
    if not c or not nm or len(nm) > 70 or not inside(*c):
        continue
    p = q(*c)
    a = t.get("amenity", "")
    if a in VENUE:
        key = (nm.lower(), p[0] // 30, p[1] // 30)
        if key in seen:
            continue
        seen.add(key)
        vb, db = nearest(p, 1)
        vc, dc = nearest(p, 2, 6)
        if vb == -1 or db > 250:
            continue
        pois.append((p[0], p[1], VENUE[a], nm, vb, vc if dc < 600 else -1))
        continue
    if t.get("place") in RANK and el["type"] == "node":
        key = (nm.lower(), p[0] // 200, p[1] // 200)
        if key not in seena:
            seena.add(key)
            areas.append((nm, p[0], p[1], RANK[t["place"]]))
    k = kind_of(t)
    key = (fold(nm), p[0] // 90, p[1] // 90)
    if key in seeni:
        continue
    seeni.add(key)
    idx.append((nm, p[0], p[1], k, alt_names(t, nm)))
for el in load("admin"):
    t = el.get("tags", {})
    c = center(el)
    nm = t.get("name", "").strip()
    if not c or not nm or not inside(*c):
        continue
    p = q(*c)
    key = (nm.lower(), p[0] // 200, p[1] // 200)
    if key not in seena:
        seena.add(key)
        areas.append((nm, p[0], p[1], 2 if t.get("admin_level") in ("5", "6") else 3))
    key = (fold(nm), p[0] // 90, p[1] // 90)
    if key not in seeni:
        seeni.add(key)
        idx.append((nm, p[0], p[1], 0, alt_names(t, nm)))
pois.sort(key=lambda r: (r[1] // 400, r[0]))
areas.sort(key=lambda r: (r[3], r[0]))
idx.sort(key=lambda r: (r[2] // 500, r[1]))
print("venues", len(pois), [sum(1 for r in pois if r[2] == k) for k in range(3)], "no car access", sum(1 for r in pois if r[5] < 0))
print("areas", len(areas), {r: sum(1 for p in areas if p[3] == r) for r in sorted({p[3] for p in areas})})
print("index", len(idx), {k: sum(1 for p in idx if p[3] == k) for k in range(9)})

# addresses: "12 Phố Hàng Bài"
addr, seenad = [], set()
for el in load("addr"):
    t = el.get("tags", {})
    c = center(el)
    hn, st = " ".join(t.get("addr:housenumber", "").split()), " ".join(t.get("addr:street", "").split())
    if not c or not hn or not st or len(hn) > 14 or len(st) > 60 or not inside(*c):
        continue
    key = (fold(hn), fold(st))
    if key in seenad:
        continue
    seenad.add(key)
    p = q(*c)
    addr.append((st, hn, p[0], p[1]))
ast = sorted({a[0] for a in addr})
ast_ix = {s: i for i, s in enumerate(ast)}
addr.sort(key=lambda a: (ast_ix[a[0]], a[2], a[3]))
print("addresses", len(addr), "on", len(ast), "streets")

# ---------------------------------------------------------------- water, green, rail
PAD = 0.04
cl = (q(S - PAD, W - PAD), q(N + PAD, E + PAD))
def clamp(p):
    return (min(max(p[0], cl[0][0]), cl[1][0]), min(max(p[1], cl[0][1]), cl[1][1]))

def area_m2(ring):
    a = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        a += x1 * MX * y2 * MY - x2 * MX * y1 * MY
    return abs(a) / 2

def stitch(parts):
    """Join open line parts into closed rings by matching end points."""
    rings, parts = [], [p for p in parts if len(p) >= 2]
    while parts:
        cur = parts.pop()
        changed = True
        while cur[0] != cur[-1] and changed:
            changed = False
            for i, p in enumerate(parts):
                if p[0] == cur[-1]:
                    cur = cur + p[1:]
                elif p[-1] == cur[-1]:
                    cur = cur + p[::-1][1:]
                elif p[-1] == cur[0]:
                    cur = p + cur[1:]
                elif p[0] == cur[0]:
                    cur = p[::-1] + cur[1:]
                else:
                    continue
                parts.pop(i)
                changed = True
                break
        if cur[0] == cur[-1] and len(cur) >= 4:
            rings.append(cur)
    return rings

def in_box(p):
    return cl[0][0] < p[0] < cl[1][0] and cl[0][1] < p[1] < cl[1][1]

polys, rivers, wlabels, walt = [], [], [], {}
def add_poly(ring, name, alt=""):
    if name and alt:
        walt[name] = alt
    ring = [clamp(p) for p in ring]
    a = area_m2(ring)
    if a < 6000:
        return
    ring = simplify(ring, 6 if a < 3e5 else 12)
    if len(ring) < 4:
        return
    polys.append(ring)
    if name and a > 5e4:
        cx, cy = sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
        wlabels.append((name, round(cx), round(cy), a))

river_parts = defaultdict(list)
for el in load("water"):
    t = el.get("tags", {})
    if el["type"] == "way":
        g = [q(p["lat"], p["lon"]) for p in el.get("geometry", []) if p]
        if t.get("natural") == "water" and len(g) >= 4 and g[0] == g[-1]:
            add_poly(g, t.get("name", ""), alt_names(t, t.get("name", "")))
        elif t.get("waterway") in ("river", "canal") and len(g) >= 2:
            if t.get("tunnel") in ("yes", "culvert"):
                continue
            g = simplify([clamp(p) for p in g], 10)
            rivers.append((g, 1 if t["waterway"] == "river" else 0))
            if t.get("name"):
                river_parts[t["name"]].append(g)
                if alt_names(t, t["name"]):
                    walt[t["name"]] = alt_names(t, t["name"])
    elif el["type"] == "relation":
        parts = []
        for m in el.get("members", []):
            if m.get("type") == "way" and m.get("role") in ("outer", "") and m.get("geometry"):
                parts.append([q(p["lat"], p["lon"]) for p in m["geometry"] if p])
        for ring in stitch(parts):
            add_poly(ring, t.get("name", ""), alt_names(t, t.get("name", "")))
best = {}
for nm, x, y, a in wlabels:
    if nm not in best or a > best[nm][3]:
        best[nm] = (nm, x, y, a)
wlabels = sorted(best.values(), key=lambda r: -r[3])[:60]
# river names: put the label on the middle of the longest stretch that lies inside the map
vis = (q(S, W), q(N, E))
for nm, parts in river_parts.items():
    total = sum(line_m(p) for p in parts)
    if total < 2500 or nm in best:
        continue
    cands = []
    for p in parts:
        ins = [pt for pt in p if vis[0][0] < pt[0] < vis[1][0] and vis[0][1] < pt[1] < vis[1][1]]
        if len(ins) >= 2:
            cands.append((line_m(ins), ins[len(ins) // 2]))
    if cands:
        L, pt = max(cands)
        wlabels.append((nm, pt[0], pt[1], total * 60))
wlabels.sort(key=lambda r: -r[3])
print("water polygons", len(polys), "water lines", len(rivers), "water labels", len(wlabels), [w[0] for w in wlabels[:12]])

greens, glabels, rails, runways = [], [], [], []
for el in load("green"):
    t = el.get("tags", {})
    if el["type"] != "way":
        continue
    g = [q(p["lat"], p["lon"]) for p in el.get("geometry", []) if p]
    if len(g) < 2:
        continue
    if t.get("railway") in ("rail", "subway", "light_rail"):
        if t.get("service") in ("yard", "siding", "spur", "crossover") or t.get("tunnel") == "yes":
            continue
        rails.append(simplify([clamp(p) for p in g], 6))
        continue
    if t.get("aeroway") == "runway":
        runways.append(simplify(g, 6))
        continue
    if t.get("aeroway"):
        continue
    if len(g) < 4 or g[0] != g[-1]:
        continue
    ring = [clamp(p) for p in g]
    a = area_m2(ring)
    grass = t.get("landuse") == "grass"
    if a < (25000 if grass else 7000):
        continue
    ring = simplify(ring, 7 if a < 3e5 else 14)
    if len(ring) < 4:
        continue
    greens.append(ring)
    if t.get("name") and a > 3e4 and not grass:
        cx, cy = sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
        glabels.append((t["name"], round(cx), round(cy), a))
glabels.sort(key=lambda r: -r[3])
glabels = glabels[:60]
print("green polygons", len(greens), "labels", len(glabels), "rail lines", len(rails), "runways", len(runways))

def flat(line):
    out, px, py = [], 0, 0
    for x, y in line:
        out.extend((x - px, y - py))
        px, py = x, y
    return out

core = {
    "v": 2, "city": CITY, "bbox": BBOX, "origin": [LAT0, LON0], "q": Q,
    "vx": delta([p[0] for p in vpos2]), "vy": delta([p[1] for p in vpos2]),
    "vf": "".join(str(f) for f in vflag),
    "ea": delta([e[0] for e in edges]), "eb": [e[1] - e[0] for e in edges],
    "ef": "".join(str((1 if e[3] else 0) | (2 if e[4] else 0) | (4 if e[5] else 0)) for e in edges),
    "en": [name_ix[e[6]] for e in edges],
    "ec": cls_runs, "eg": geo,
    "names": names,
    "sn": [s[0] for s in streets], "sx": [s[1] for s in streets], "sy": [s[2] for s in streets], "sc": [s[3] for s in streets],
    "px": delta([r[0] for r in pois]), "py": delta([r[1] for r in pois]),
    "pk": "".join(str(r[2]) for r in pois), "pn": [r[3] for r in pois], "pv": [r[4] for r in pois], "pc": [r[5] for r in pois],
    "areas": [list(p) for p in areas],
    "water": [flat(r) for r in polys], "rivers": [flat(r[0]) for r in rivers], "rk": "".join(str(r[1]) for r in rivers),
    "wlabels": [[w[0], w[1], w[2], round(w[3]), walt.get(w[0], "")] for w in wlabels],
    "green": [flat(r) for r in greens], "glabels": [[g[0], g[1], g[2]] for g in glabels],
    "rail": [flat(r) for r in rails], "runway": [flat(r) for r in runways],
}
places = {
    "v": 2,
    "n": [r[0] for r in idx], "x": delta([r[1] for r in idx]), "y": delta([r[2] for r in idx]), "k": "".join(str(r[3]) for r in idx),
    "ti": delta([i for i, r in enumerate(idx) if r[4]]), "tt": [r[4] for r in idx if r[4]],
    "as": ast, "ai": delta([ast_ix[a[0]] for a in addr]), "ah": [a[1] for a in addr],
    "ax": delta([a[2] for a in addr]), "ay": delta([a[3] for a in addr]),
}
for path, doc in ((OUT + ".json", core), (OUT + "-places.json", places)):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print("wrote", path, os.path.getsize(path), "bytes")
