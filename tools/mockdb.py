"""Local stand-in for the Firebase Realtime Database REST API (GET stream, PUT, PATCH, DELETE), for testing only.

mockdb.py <port> [lifetime in ms]: with a lifetime it also applies the access rules in firebase-rules.json, so a group
needs a start time under idx/ and stops answering once that time is older than the lifetime."""
import json, sys, threading, queue, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
TREE = {}; LOCK = threading.Lock(); LISTENERS = []   # (path keys, queue)
TTL = int(sys.argv[2]) if len(sys.argv) > 2 else 0
now = lambda: int(time.time() * 1000)
def keys_of(path): return [k for k in path.split("?")[0].removesuffix(".json").split("/") if k]
def get(keys):
    o = TREE
    for k in keys:
        if not isinstance(o, dict) or k not in o: return None
        o = o[k]
    return o
def put(keys, data):
    global TREE
    if not keys: TREE = data if isinstance(data, dict) else {}; return
    o = TREE
    for k in keys[:-1]: o = o.setdefault(k, {})
    if data is None: o.pop(keys[-1], None)
    else: o[keys[-1]] = data
def allowed(method, keys, query=""):
    if not TTL: return True
    born = lambda i: get(["idx", i])
    fresh = lambda i: isinstance(born(i), int) and born(i) > now() - TTL
    if keys[:1] == ["rooms"] and len(keys) >= 2:
        i = keys[1]
        if len(i) != 16 or born(i) is None: return False
        return fresh(i) or (method == "DELETE" and len(keys) == 2)
    if keys == ["idx"]:
        m = __import__("re").search(r"endAt=(\d+)\.\d", query)  # like the real database: a whole-number cut-off is refused
        return method == "GET" and "orderBy=%22%24value%22" in query and bool(m) and int(m.group(1)) < now() - TTL
    if keys[:1] == ["idx"] and len(keys) == 2:
        i = keys[1]
        if method == "GET": return True
        if method == "PUT": return len(i) == 16 and born(i) is None
        if method == "DELETE": return born(i) is not None and not fresh(i) and get(["rooms", i]) is None
    return False
def notify(keys, kind, data):
    for lk, q in list(LISTENERS):
        if keys[:len(lk)] == lk: q.put((kind, "/" + "/".join(keys[len(lk):]), data))
        elif lk[:len(keys)] == keys: q.put(("put", "/", get(lk)))
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Access-Control-Allow-Methods", "GET, PUT, PATCH, DELETE, OPTIONS"); self.send_header("Access-Control-Allow-Headers", "*")
    def do_OPTIONS(self): self.send_response(204); self.cors(); self.send_header("Content-Length", "0"); self.end_headers()
    def reply(self, obj):
        b = json.dumps(obj).encode(); self.send_response(200); self.cors(); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def body(self): return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"null")
    def deny(self):
        b = b'{"error":"Permission denied"}'; self.send_response(401); self.cors(); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def ok(self, method):
        keys = keys_of(self.path); q = self.path.partition("?")[2]
        with LOCK: yes = allowed(method, keys, q)
        if not yes: self.deny()
        return yes
    def do_GET(self):
        keys = keys_of(self.path)
        if not self.ok("GET"): return
        if keys == ["idx"] and TTL:
            cut = int(__import__("re").search(r"endAt=(\d+)", self.path).group(1))
            return self.reply({k: v for k, v in (get(["idx"]) or {}).items() if v <= cut})
        if "text/event-stream" not in self.headers.get("Accept", ""): return self.reply(get(keys))
        q = queue.Queue(); 
        with LOCK: LISTENERS.append((keys, q)); q.put(("put", "/", get(keys)))
        self.send_response(200); self.cors(); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache"); self.send_header("Connection", "close"); self.end_headers()
        try:
            while True:
                try: kind, path, data = q.get(timeout=15); msg = "event: %s\ndata: %s\n\n" % (kind, json.dumps({"path": path, "data": data}))
                except queue.Empty: msg = "event: keep-alive\ndata: null\n\n"
                self.wfile.write(msg.encode()); self.wfile.flush()
        except Exception: pass
        finally:
            with LOCK: LISTENERS[:] = [l for l in LISTENERS if l[1] is not q]
    def do_PUT(self):
        keys = keys_of(self.path); d = self.body()
        if not self.ok("PUT"): return
        if d == {".sv": "timestamp"}: d = now()
        with LOCK: put(keys, d); notify(keys, "put", d)
        self.reply(d)
    def do_PATCH(self):
        keys = keys_of(self.path); d = self.body()
        if not self.ok("PATCH"): return
        with LOCK:
            for k, v in d.items(): put(keys + [k], v)
            notify(keys, "patch", d)
        self.reply(d)
    def do_DELETE(self):
        keys = keys_of(self.path)
        if not self.ok("DELETE"): return
        with LOCK: put(keys, None); notify(keys, "put", None)
        self.reply(None)
ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
