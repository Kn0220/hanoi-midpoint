"""Repack the v2 map data into the smaller v3 files. Nothing is dropped or rounded:
whole numbers are written as text-safe variable-length codes instead of JSON number lists,
street-name links are coded by how recently a name was last used, and the street list that
only search needs moves into the search file."""
import json, sys, zlib, os
src, out = sys.argv[1], sys.argv[2]
d = json.load(open(os.path.join(src, 'hanoi-v2.json'), encoding='utf-8'))
p = json.load(open(os.path.join(src, 'hanoi-v2-places.json'), encoding='utf-8'))
AL = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
POS = {c: i for i, c in enumerate(AL)}
def pack(arr):
    o = []
    for v in arr:
        assert isinstance(v, int), v
        u = v * 2 if v >= 0 else -v * 2 - 1
        while u >= 32:
            o.append(AL[(u & 31) | 32]); u >>= 5
        o.append(AL[u])
    return ''.join(o)
def unpack(s):
    o, u, sh = [], 0, 0
    for ch in s:
        c = POS[ch]; u |= (c & 31) << sh
        if c & 32: sh += 5
        else: o.append((u >> 1) ^ -(u & 1)); u = 0; sh = 0
    return o
def delta(a):
    o, pr = [], 0
    for v in a: o.append(v - pr); pr = v
    return o

# street names, renumbered in the order the roads first use them
names, en = d['names'], d['en']
new, order, codes = {0: 0}, [''], []
for n in en:
    if n == 0: codes.append(0)
    elif n not in new: new[n] = len(order); order.append(names[n]); codes.append(1)
    else: codes.append(2 + len(order) - 1 - new[n])
for n in range(len(names)):
    if n not in new: new[n] = len(order); order.append(names[n])
assert len(order) == len(names) and names[0] == ''
back, cnt = [], 0
for c in codes:
    if c == 0: back.append(0)
    elif c == 1: cnt += 1; back.append(cnt)
    else: back.append(cnt - (c - 2))
assert [order[b] for b in back] == [names[n] for n in en]

main = {'v': 3, 'city': d['city'], 'bbox': d['bbox'], 'origin': d['origin'], 'q': d['q'], 'ec': d['ec'], 'rk': d['rk'],
        'vx': pack(d['vx']), 'vy': pack(d['vy']), 'vf': d['vf'], 'ea': pack(d['ea']), 'eb': pack(d['eb']), 'ef': d['ef'],
        'en': pack(codes), 'eg': pack(d['eg']), 'names': order,
        'px': pack(d['px']), 'py': pack(d['py']), 'pk': d['pk'], 'pn': d['pn'],
        'pv': pack(delta(d['pv'])), 'pc': pack([c - v for c, v in zip(d['pc'], d['pv'])]),
        'areas': d['areas'], 'wlabels': d['wlabels'], 'glabels': d['glabels']}
for k in ('water', 'rivers', 'green', 'rail', 'runway'):
    main[k] = [pack(ring) for ring in d[k]]
    assert [unpack(s) for s in main[k]] == d[k]
for k in ('vx', 'vy', 'ea', 'eb', 'eg', 'px', 'py'):
    assert unpack(main[k]) == d[k], k

sn = [new[n] for n in d['sn']]; sc = [new[n] for n in d['sc']]
places = {'v': 3, 'n': p['n'], 'x': pack(p['x']), 'y': pack(p['y']), 'k': p['k'], 'ti': pack(p['ti']), 'tt': p['tt'],
          'as': p['as'], 'ai': pack(p['ai']), 'ah': p['ah'], 'ax': pack(p['ax']), 'ay': pack(p['ay']),
          'sn': pack(delta(sn)), 'sx': pack(d['sx']), 'sy': pack(d['sy']), 'sc': pack(sc)}
extra = set(p) - set(places) - {'v'}; assert not extra, extra
extra = set(d) - set(main) - {'sn', 'sx', 'sy', 'sc'}; assert not extra, extra
for name, obj in (('hanoi-v3.json', main), ('hanoi-v3-places.json', places)):
    raw = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    open(os.path.join(out, name), 'wb').write(raw)
    print(name, len(raw), 'bytes;', 'gzip level 5 (what the site host does):', len(zlib.compress(raw, 5)), '; level 9:', len(zlib.compress(raw, 9)))
