import importlib.util, json, tempfile, threading, unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer

MODULE = Path(__file__).with_name("server.py")
spec = importlib.util.spec_from_file_location("alkamel_server", MODULE)
app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app)

class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        app.DB_PATH=Path(cls.tmp.name)/"test.db"
        app.ADMIN_PASSWORD="test-password"
        app.SESSIONS.clear()
        app.init_db()
        cls.http=ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True); cls.thread.start()
        cls.base="http://127.0.0.1:%d"%cls.http.server_port
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.tmp.cleanup()
    def call(self,path,method="GET",data=None,token=None):
        headers={}
        raw=None
        if data is not None:
            raw=json.dumps(data).encode(); headers["Content-Type"]="application/json"
        if token: headers["Authorization"]="Bearer "+token
        req=Request(self.base+path,data=raw,headers=headers,method=method)
        try:
            with urlopen(req,timeout=3) as r: return r.status,json.loads(r.read())
        except HTTPError as e: return e.code,json.loads(e.read())
    def test_health_and_auth(self):
        self.assertEqual(self.call("/api/health")[0],200)
        self.assertEqual(self.call("/api/sections")[0],401)
    def test_login_create_toggle_and_poll(self):
        code,login=self.call("/api/login","POST",{"password":"test-password"})
        self.assertEqual(code,200); token=login["token"]
        code,created=self.call("/api/sections","POST",{"title":"الأخبار","visible":True},token)
        self.assertEqual(code,201)
        sid=created["id"]
        code,poll=self.call("/api/poll?device=unit-test&since=0",token=token)
        self.assertEqual(code,200)
        self.assertTrue(any(s["id"]==sid for s in poll["sections"]))
        self.assertEqual(self.call("/api/sections/%d"%sid,"PATCH",{"visible":False},token)[0],200)
        code,poll=self.call("/api/poll?device=unit-test&since=0",token=token)
        self.assertFalse(any(s["id"]==sid for s in poll["sections"]))
    def test_message_delivery(self):
        _,login=self.call("/api/login","POST",{"password":"test-password"})
        token=login["token"]
        code,msg=self.call("/api/messages","POST",{"title":"اختبار","body":"رسالة محلية"},token)
        self.assertEqual(code,201)
        code,poll=self.call("/api/poll?device=phone-1&since=0",token=token)
        self.assertTrue(any(m["id"]==msg["id"] for m in poll["messages"]))

if __name__=="__main__": unittest.main()
