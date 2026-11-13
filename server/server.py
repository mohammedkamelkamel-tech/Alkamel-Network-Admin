#!/usr/bin/env python3
"""Local-only administration server for Alkamel Network. Python standard library only."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import hashlib, hmac, json, os, secrets, sqlite3, time, mimetypes

ROOT = Path(__file__).resolve().parent
WEB = ROOT.parent / "web"
DB_PATH = ROOT / "data" / "alkamel_admin.db"
HOST = os.environ.get("ALKAMEL_HOST", "0.0.0.0")
PORT = int(os.environ.get("ALKAMEL_PORT", "8080"))
ADMIN_PASSWORD = os.environ.get("ALKAMEL_ADMIN_PASSWORD", "ChangeThis-Admin-2026")
TOKEN_TTL = 12 * 60 * 60
SESSIONS = {}

def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS sections(
          id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT DEFAULT '',
          icon TEXT DEFAULT 'grid', target TEXT DEFAULT '', visible INTEGER NOT NULL DEFAULT 1,
          sort_order INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages(
          id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL,
          audience TEXT NOT NULL DEFAULT 'all', target TEXT DEFAULT '', created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit(
          id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, details TEXT DEFAULT '', created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS devices(
          device_id TEXT PRIMARY KEY, display_name TEXT DEFAULT '', last_seen INTEGER NOT NULL
        );
        """)
        if c.execute("SELECT COUNT(*) FROM sections").fetchone()[0] == 0:
            now=int(time.time())
            c.execute("INSERT INTO sections(title,description,icon,visible,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                      ("القسم التجريبي","قسم تجريبي يمكنك تعديله أو إخفاؤه","grid",0,1,now,now))

def audit(action, details=""):
    with db() as c:
        c.execute("INSERT INTO audit(action,details,created_at) VALUES(?,?,?)",(action,details[:1000],int(time.time())))

def send_json(h, code, data):
    raw=json.dumps(data,ensure_ascii=False).encode()
    h.send_response(code); h.send_header("Content-Type","application/json; charset=utf-8")
    h.send_header("Content-Length",str(len(raw))); h.send_header("Cache-Control","no-store")
    h.send_header("X-Content-Type-Options","nosniff"); h.end_headers(); h.wfile.write(raw)

class Handler(BaseHTTPRequestHandler):
    server_version="AlkamelAdmin/0.1"
    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))
    def body(self):
        n=int(self.headers.get("Content-Length","0"))
        if n>65536: raise ValueError("حجم الطلب كبير")
        return json.loads(self.rfile.read(n) or b"{}")
    def auth(self):
        token=self.headers.get("Authorization","").removeprefix("Bearer ").strip()
        expiry=SESSIONS.get(token,0)
        if not token or expiry < time.time():
            SESSIONS.pop(token,None); return False
        return True
    def do_GET(self):
        p=urlparse(self.path)
        if p.path=="/api/health":
            return send_json(self,200,{"ok":True,"service":"Alkamel Network Admin","time":int(time.time())})
        if p.path=="/api/public/sections":
            with db() as c: rows=c.execute("SELECT id,title,description,icon,target,sort_order FROM sections WHERE visible=1 ORDER BY sort_order,id").fetchall()
            return send_json(self,200,{"sections":[dict(x) for x in rows]})
        if p.path.startswith("/api/"):
            if not self.auth(): return send_json(self,401,{"error":"يلزم تسجيل دخول المدير"})
            if p.path=="/api/sections":
                with db() as c: rows=c.execute("SELECT * FROM sections ORDER BY sort_order,id DESC").fetchall()
                return send_json(self,200,{"sections":[dict(x) for x in rows]})
            if p.path=="/api/messages":
                with db() as c: rows=c.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 100").fetchall()
                return send_json(self,200,{"messages":[dict(x) for x in rows]})
            if p.path=="/api/audit":
                with db() as c: rows=c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100").fetchall()
                return send_json(self,200,{"events":[dict(x) for x in rows]})
            if p.path=="/api/stats":
                with db() as c:
                    sections=c.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
                    visible=c.execute("SELECT COUNT(*) FROM sections WHERE visible=1").fetchone()[0]
                    messages=c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
                    devices=c.execute("SELECT COUNT(*) FROM devices WHERE last_seen>?",(int(time.time())-90,)).fetchone()[0]
                return send_json(self,200,{"sections":sections,"visible_sections":visible,"messages":messages,"online_devices":devices})
            if p.path=="/api/poll":
                q=parse_qs(p.query); since=int(q.get("since",["0"])[0]); device=(q.get("device",[""])[0] or "")[:100]
                now=int(time.time())
                if device:
                    with db() as c: c.execute("INSERT INTO devices(device_id,last_seen) VALUES(?,?) ON CONFLICT(device_id) DO UPDATE SET last_seen=excluded.last_seen",(device,now))
                with db() as c:
                    rows=c.execute("SELECT * FROM messages WHERE id>? AND (audience='all' OR target=?) ORDER BY id",(since,device)).fetchall()
                    secs=c.execute("SELECT id,title,description,icon,target,sort_order FROM sections WHERE visible=1 ORDER BY sort_order,id").fetchall()
                return send_json(self,200,{"messages":[dict(x) for x in rows],"sections":[dict(x) for x in secs],"server_time":now})
            return send_json(self,404,{"error":"المسار غير موجود"})
        path=(WEB/"index.html") if p.path in ("/","/index.html") else (WEB/p.path.lstrip("/"))
        try:
            resolved=path.resolve()
            if WEB.resolve() not in resolved.parents and resolved != WEB.resolve(): raise FileNotFoundError()
            raw=resolved.read_bytes()
            typ=mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
            self.send_response(200); self.send_header("Content-Type",typ+("; charset=utf-8" if typ.startswith("text/") or typ in ("application/javascript","application/json") else ""))
            self.send_header("Content-Length",str(len(raw))); self.send_header("X-Content-Type-Options","nosniff"); self.end_headers(); self.wfile.write(raw)
        except Exception: send_json(self,404,{"error":"الملف غير موجود"})
    def do_POST(self):
        p=urlparse(self.path)
        try: data=self.body()
        except Exception as e: return send_json(self,400,{"error":str(e)})
        if p.path=="/api/login":
            supplied=str(data.get("password",""))
            if not hmac.compare_digest(supplied,ADMIN_PASSWORD): return send_json(self,403,{"error":"كلمة المرور غير صحيحة"})
            token=secrets.token_urlsafe(32); SESSIONS[token]=time.time()+TOKEN_TTL
            audit("login","تم تسجيل دخول المدير")
            return send_json(self,200,{"token":token,"expires_in":TOKEN_TTL})
        if not self.auth(): return send_json(self,401,{"error":"يلزم تسجيل دخول المدير"})
        now=int(time.time())
        if p.path=="/api/sections":
            title=str(data.get("title","")).strip()
            if not title: return send_json(self,400,{"error":"اسم القسم مطلوب"})
            with db() as c:
                cur=c.execute("INSERT INTO sections(title,description,icon,target,visible,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                  (title,str(data.get("description",""))[:500],str(data.get("icon","grid"))[:40],str(data.get("target",""))[:120],int(bool(data.get("visible",True))),int(data.get("sort_order",0)),now,now))
                sid=cur.lastrowid
            audit("section_created",title); return send_json(self,201,{"id":sid})
        if p.path=="/api/messages":
            title=str(data.get("title","")).strip(); body=str(data.get("body","")).strip()
            audience=str(data.get("audience","all")); target=str(data.get("target",""))[:100]
            if not title or not body: return send_json(self,400,{"error":"العنوان ونص الرسالة مطلوبان"})
            if audience not in ("all","device"): return send_json(self,400,{"error":"نوع المستلمين غير صحيح"})
            if audience=="device" and not target: return send_json(self,400,{"error":"معرّف الجهاز مطلوب"})
            with db() as c:
                cur=c.execute("INSERT INTO messages(title,body,audience,target,created_at) VALUES(?,?,?,?,?)",(title,body,audience,target,now))
            audit("message_sent",title); return send_json(self,201,{"id":cur.lastrowid})
        return send_json(self,404,{"error":"المسار غير موجود"})
    def do_PATCH(self):
        p=urlparse(self.path)
        if not self.auth(): return send_json(self,401,{"error":"يلزم تسجيل دخول المدير"})
        try: data=self.body()
        except Exception as e: return send_json(self,400,{"error":str(e)})
        parts=p.path.strip("/").split("/")
        if len(parts)==3 and parts[:2]==["api","sections"]:
            try: sid=int(parts[2])
            except: return send_json(self,400,{"error":"معرّف غير صحيح"})
            allowed={"title","description","icon","target","visible","sort_order"}
            fields={k:v for k,v in data.items() if k in allowed}
            if not fields: return send_json(self,400,{"error":"لا توجد تغييرات"})
            if "visible" in fields: fields["visible"]=int(bool(fields["visible"]))
            fields["updated_at"]=int(time.time())
            sql=",".join(k+"=?" for k in fields)
            with db() as c: cur=c.execute("UPDATE sections SET "+sql+" WHERE id=?",(*fields.values(),sid))
            if not cur.rowcount: return send_json(self,404,{"error":"القسم غير موجود"})
            audit("section_updated",str(sid)); return send_json(self,200,{"ok":True})
        return send_json(self,404,{"error":"المسار غير موجود"})
    def do_DELETE(self):
        p=urlparse(self.path)
        if not self.auth(): return send_json(self,401,{"error":"يلزم تسجيل دخول المدير"})
        parts=p.path.strip("/").split("/")
        if len(parts)==3 and parts[:2]==["api","sections"]:
            try: sid=int(parts[2])
            except: return send_json(self,400,{"error":"معرّف غير صحيح"})
            with db() as c: cur=c.execute("DELETE FROM sections WHERE id=?",(sid,))
            if not cur.rowcount: return send_json(self,404,{"error":"القسم غير موجود"})
            audit("section_deleted",str(sid)); return send_json(self,200,{"ok":True})
        return send_json(self,404,{"error":"المسار غير موجود"})

if __name__=="__main__":
    init_db()
    print("Alkamel Admin server: http://0.0.0.0:%d" % PORT)
    print("Database:",DB_PATH)
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
