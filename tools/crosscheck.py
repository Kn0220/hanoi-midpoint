"""Independent check of the page's answer: plain heapq Dijkstra on the same data file."""
import json, math, heapq, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
SPEED = {"bike": [0, 30, 23, 21, 18, 15, 10, 8], "car": [55, 32, 21, 19, 16, 11, 6, 5]}
MY = 111320 / d["q"]; MX = MY * math.cos(math.radians(d["origin"][0]))
V = len(d["vx"]); E = len(d["ea"])
qx, qy, x, y = [], [], 0, 0
for i in range(V):
    x += d["vx"][i]; y += d["vy"][i]; qx.append(x); qy.append(y)
ea, eb, a = [], [], 0
for i in range(E):
    a += d["ea"][i]; ea.append(a); eb.append(a + d["eb"][i])
cls = [c for c, n in enumerate(d["ec"]) for _ in range(n)]
flag = [int(ch) for ch in d["ef"]]; vflag = [int(ch) for ch in d["vf"]]
length, k = [], 0
for i in range(E):
    n = d["eg"][k]; k += 1
    px, py = qx[ea[i]], qy[ea[i]]; pts = [(px, py)]
    for j in range(n):
        px += d["eg"][k]; py += d["eg"][k + 1]; k += 2; pts.append((px, py))
    pts.append((qx[eb[i]], qy[eb[i]]))
    L = sum(math.hypot((pts[j][0] - pts[j - 1][0]) * MX, (pts[j][1] - pts[j - 1][1]) * MY) for j in range(1, len(pts)))
    length.append(max(L, 1.0))
def run(mode, goal, src):
    bit = 1 if mode == "bike" else 2
    adj = [[] for _ in range(V)]
    for i in range(E):
        if mode == "bike":
            if flag[i] & 2 or SPEED["bike"][cls[i]] == 0: continue
        elif flag[i] & 4: continue
        w = length[i] / (SPEED[mode][cls[i]] / 3.6)
        adj[ea[i]].append((eb[i], w))
        if not flag[i] & 1: adj[eb[i]].append((ea[i], w))
    dists = []
    for s in src:
        dist = [math.inf] * V; dist[s] = 0.0; h = [(0.0, s)]
        while h:
            du, u = heapq.heappop(h)
            if du > dist[u]: continue
            for v, w in adj[u]:
                nd = du + w
                if nd < dist[v]: dist[v] = nd; heapq.heappush(h, (nd, v))
        dists.append(dist)
    ok = [v for v in range(V) if vflag[v] & bit and all(dd[v] < math.inf for dd in dists)]
    worst = {v: max(dd[v] for dd in dists) for v in ok}; tot = {v: sum(dd[v] for dd in dists) for v in ok}
    lo = min(worst.values())
    best = min(tot, key=tot.get) if goal == "total" else min((v for v in ok if worst[v] <= lo + 20), key=tot.get)
    return {"best": best, "times": [round(dd[best], 2) for dd in dists], "worst": round(worst[best], 2), "sum": round(tot[best], 2), "true_min_worst": round(lo, 2), "true_min_sum": round(min(tot.values()), 2), "reachable": len(ok)}
page = json.loads(sys.argv[2])
for key, pg in page.items():
    mode, goal = key.split("-")
    mine = run(mode, goal, pg["src"])
    dt = max(abs(a - b) for a, b in zip(mine["times"], pg["times"]))
    verdict = "MATCH" if mine["best"] == pg["best"] and dt < 0.5 else ("SAME VALUE, different vertex" if abs(mine["worst"] - pg["worst"]) < 0.5 and abs(mine["sum"] - pg["sum"]) < 0.5 else "MISMATCH")
    print(key, verdict, "page", pg["best"], pg["worst"], pg["sum"], "| python", mine["best"], mine["worst"], mine["sum"], "| max time diff", round(dt, 3), "s | lowest possible longest ride", mine["true_min_worst"], "| lowest possible total", mine["true_min_sum"], "| reachable", mine["reachable"])
