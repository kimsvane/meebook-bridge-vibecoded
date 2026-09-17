import asyncio
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import uvicorn
from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from playwright.async_api import async_playwright

try:
    import paho.mqtt.client as mqtt

    HAS_PAHO = True
except Exception:
    HAS_PAHO = False

BASE_DIR = Path(os.environ.get("BRIDGE_BASE", "/app"))
DATA_DIR = Path(os.environ.get("BRIDGE_DATA", "/data"))
PROFILE_DIR = DATA_DIR / "profile"
STATE_PATH = DATA_DIR / "state.json"
COOKIE_PATH = DATA_DIR / "cookies.json"

VIEW_W = 1440
VIEW_H = 900

DEFAULTS = {
    "meebook_base": "https://app.meebook.com",
    "dashboard_url": "https://app.meebook.com/foraeldre/dashboard/",
    "navigate_urls": [
        "https://app.meebook.com/foraeldre/dashboard/",
        "https://app.meebook.com/foraeldre/arsplaner/",
        "https://app.meebook.com/foraeldre/ugeplaner/",
    ],
    "refresh_interval_minutes": 15,
    "page_settle_ms": 4000,
    "capture_patterns": ["/rest/", "/api/", "/graphql"],
    "login_hosts": ["broker.unilogin", "unilogin", "mitid", "idp."],
    "logged_in_paths": ["/foraeldre", "/dashboard"],
    "login_page_hints": ["log ind", "unilogin", "log på", "personale/elev/forælder"],
    "headless_refresh": True,
}


def load_config():
    cfg = dict(DEFAULTS)
    if Path("/data/options.json").exists():
        with open("/data/options.json") as f:
            opts = json.load(f)
        for k, v in opts.items():
            if v is not None and v != "":
                cfg[k] = v
    return cfg


CONFIG = load_config()

state = {
    "session_valid": False,
    "needs_login": True,
    "login_in_progress": False,
    "last_login": None,
    "last_refresh": None,
    "last_error": None,
    "resources": {},
    "student_ids": [],
    "year_span_id": None,
}
job_lock = asyncio.Lock()

login_view = {
    "page": None,
    "snapshot": None,
    "loop_running": False,
}

snapshot_lock = asyncio.Lock()
scheduler_task = None

mqtt_client = None
mqtt_enabled = False


def _make_mqtt_client(client_id):
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except AttributeError:
        return mqtt.Client(client_id=client_id)


def get_mqtt_settings():
    host = os.environ.get("MQTT_HOST")
    if host:
        port = int(os.environ.get("MQTT_PORT", "1883"))
        user = os.environ.get("MQTT_USERNAME") or os.environ.get("MQTT_USER")
        password = os.environ.get("MQTT_PASSWORD")
        return host, port, user, password
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    try:
        req = urllib.request.Request(
            "http://supervisor/services/mqtt",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        if not data.get("result"):
            return None
        d = data.get("data", {})
        return d.get("host"), int(d.get("port", 1883)), d.get("username"), d.get("password")
    except Exception:
        return None


def mqtt_start():
    global mqtt_client, mqtt_enabled
    if not HAS_PAHO:
        return
    settings = get_mqtt_settings()
    if not settings:
        return
    host, port, user, password = settings
    client = _make_mqtt_client("meebook_bridge")
    if user:
        client.username_pw_set(user, password)
    try:
        client.connect(host, port, 60)
        client.loop_start()
    except Exception:
        return
    mqtt_client = client
    mqtt_enabled = True


def sensor_values(resources):
    out = []

    body = resources.get("/rest/related/students")
    if body and body.get("items"):
        out.append(("elev", "Meebook Elev", body["items"][0]["name"]))

    plan_names = {}
    for k in ("/rest/annualplans/latest", "/rest/annualplans"):
        b = resources.get(k)
        if b:
            for it in b.get("items", []):
                try:
                    plan_names[int(it["id"])] = ", ".join(it.get("categories", []) or [])
                except (KeyError, ValueError):
                    pass

    body = resources.get("/rest/annualplans/latest")
    if body and body.get("items"):
        it = body["items"][0]
        label = f"{it.get('groupName','')} - {', '.join(it.get('categories', []) or [])}"
        out.append(("seneste_aarsplan", "Meebook Seneste Årsplan", label))
        out.append(("aarsplaner", "Meebook Antal Årsplaner", len(body["items"])))

    body = resources.get("/rest/annualplans")
    if body and body.get("items"):
        out.append(("aarsplaner_omraade", "Meebook Årsplaner", len(body["items"])))

    body = resources.get("/rest/notifications")
    if body and body.get("items"):
        d = body["items"][0].get("data", {})
        sender = d.get("senderName", "Ukendt")
        cats = ", ".join(d.get("categories", []) or [])
        out.append(("seneste_besked", "Meebook Seneste Besked", f"{sender} - {cats}" if cats else sender))
        out.append(("beskeder", "Meebook Beskeder", len(body["items"])))

    body = resources.get("/rest/weekplan/events")
    if body:
        out.append(("ugeplan_events", "Meebook Ugeplan Events", len(body.get("items", []))))

    body = resources.get("/rest/yearSpans")
    if body and body.get("items"):
        for y in body["items"]:
            if y.get("currentYear"):
                out.append(("skoleaar", "Meebook Skoleår", y.get("name", "")))

    for key, body in resources.items():
        m = re.match(r"/rest/annualplans/(\d+)$", key)
        if m and isinstance(body, dict):
            pid = int(m.group(1))
            acts = body.get("activities", []) or []
            label = plan_names.get(pid, str(pid))
            out.append((f"aarsplan_{pid}", f"Meebook Årsplan {label}", len(acts)))

    return out


def mqtt_publish():
    global mqtt_client
    if not mqtt_enabled or mqtt_client is None:
        return
    try:
        if not mqtt_client.is_connected():
            return
        for key, name, value in sensor_values(state["resources"]):
            st_topic = f"meebook/bridge/{key}"
            disc_topic = f"homeassistant/sensor/meebook_{key}/config"
            disc = {
                "name": name,
                "unique_id": f"meebook_bridge_{key}",
                "object_id": f"meebook_bridge_{key}",
                "state_topic": st_topic,
                "device": {
                    "identifiers": ["meebook_bridge"],
                    "name": "Meebook",
                    "manufacturer": "Meebook Bridge",
                    "sw_version": "v1.0.12",
                },
            }
            mqtt_client.publish(disc_topic, json.dumps(disc, ensure_ascii=False), qos=0, retain=True)
            mqtt_client.publish(st_topic, value, qos=0, retain=True)
    except Exception:
        pass


def save_state():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(
            {
                "session_valid": state["session_valid"],
                "needs_login": state["needs_login"],
                "last_login": state["last_login"],
                "last_refresh": state["last_refresh"],
                "last_error": state["last_error"],
                "student_ids": state["student_ids"],
                "year_span_id": state["year_span_id"],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def load_state():
    try:
        with open(STATE_PATH) as f:
            stored = json.load(f)
        state["student_ids"] = stored.get("student_ids", [])
        state["year_span_id"] = stored.get("year_span_id")
    except FileNotFoundError:
        pass


def path_of(url: str) -> str:
    return urllib.parse.urlparse(url).path


def is_login_host(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    return any(k in host for k in CONFIG["login_hosts"])


async def looks_like_login(page) -> bool:
    url = page.url
    if is_login_host(url):
        return True
    p = path_of(url)
    if any(fp in p for fp in CONFIG["logged_in_paths"]):
        return False
    try:
        text = await page.inner_text("body")
    except Exception:
        return True
    low = (text or "").lower()[:2000]
    return any(h in low for h in CONFIG["login_page_hints"])


async def launch_browser(pw, headless):
    ctx = await pw.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=headless,
        viewport={"width": VIEW_W, "height": VIEW_H},
        locale="da-DK",
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    return ctx, page


async def end_browser(ctx, pw):
    if ctx is not None:
        try:
            await ctx.close()
        except Exception:
            pass
    if pw is not None:
        try:
            await pw.stop()
        except Exception:
            pass


def attach_capture(page):
    patterns = CONFIG["capture_patterns"]
    pending = set()

    async def _capture(resp):
        try:
            ctype = resp.headers.get("content-type", "")
            url = resp.url
            if "json" in ctype and any(pat in url for pat in patterns):
                body = await resp.json()
                if isinstance(body, (dict, list)):
                    serialized = json.dumps(body, ensure_ascii=False)[:2_000_000]
                    state["resources"][path_of(url)] = json.loads(serialized)
        except Exception:
            pass

    def on_response(resp):
        try:
            ctype = resp.headers.get("content-type", "")
            url = resp.url
            if "json" in ctype and any(pat in url for pat in patterns):
                loop = asyncio.get_running_loop()
                task = loop.create_task(_capture(resp))
                pending.add(task)
                task.add_done_callback(pending.discard)
        except Exception:
            pass

    page.on("response", on_response)


def discover_ids_from_resources():
    student_ids = set(state["student_ids"])
    for key in state["resources"]:
        m = re.search(r"/related/students/(\d+)", key)
        if m:
            student_ids.add(int(m.group(1)))
        for qv in urllib.parse.parse_qsl(urllib.parse.urlparse(key).query):
            if qv[0] == "studentId" and qv[1].isdigit():
                student_ids.add(int(qv[1]))
    if student_ids:
        state["student_ids"] = sorted(student_ids)
    if not state["year_span_id"]:
        for key in state["resources"]:
            m = re.search(r"/yearSpans/(\d+)", key)
            if m:
                state["year_span_id"] = int(m.group(1))
                break
            for qv in urllib.parse.parse_qsl(urllib.parse.urlparse(key).query):
                if qv[0] == "yearSpanId" and qv[1].isdigit():
                    state["year_span_id"] = int(qv[1])
                    break


async def save_cookies(ctx):
    cookies = await ctx.cookies()
    with open(COOKIE_PATH, "w") as f:
        json.dump(cookies, f)


async def _enhance_data(page):
    base = CONFIG["meebook_base"]

    def store(path, body):
        if isinstance(body, (dict, list)):
            serialized = json.dumps(body, ensure_ascii=False)[:2_000_000]
            state["resources"][path] = json.loads(serialized)

    try:
        latest = await page.request.get(base + "/rest/annualplans/latest")
        if latest.status == 200:
            body = await latest.json()
            store(path_of(latest.url), body)
            for item in body.get("items", []):
                pid = item.get("id")
                if pid:
                    detail = await page.request.get(
                        base + f"/rest/annualplans/{pid}?include=books%2Cactivities%2Cteacher%2Cstatuses"
                    )
                    if detail.status == 200:
                        store(path_of(detail.url), await detail.json())
    except Exception:
        pass


async def refresh_job():
    async with job_lock:
        if state["needs_login"]:
            state["last_error"] = "Kræver login - kør /login"
            return False
        state["last_error"] = None
        pw = ctx = page = None
        try:
            cookies = []
            if COOKIE_PATH.exists():
                with open(COOKIE_PATH) as f:
                    cookies = json.load(f)
            pw = await async_playwright().start()
            ctx, page = await launch_browser(pw, headless=CONFIG["headless_refresh"])
            if cookies:
                await ctx.add_cookies(cookies)
            attach_capture(page)
            for url in CONFIG["navigate_urls"]:
                try:
                    await page.goto(url, wait_until="domcontentloaded")
                    await page.wait_for_timeout(CONFIG["page_settle_ms"])
                    if await looks_like_login(page):
                        state["session_valid"] = False
                        state["needs_login"] = True
                        state["last_error"] = "Session udløbet - kør /login"
                        return False
                except Exception:
                    continue
            await _enhance_data(page)
            await save_cookies(ctx)
            discover_ids_from_resources()
            state["session_valid"] = True
            state["needs_login"] = False
            state["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            save_state()
            mqtt_publish()
            return True
        except Exception as e:
            state["last_error"] = str(e)
            return False
        finally:
            await end_browser(ctx, pw)


async def remote_login_flow():
    async with job_lock:
        state["login_in_progress"] = True
        state["last_error"] = None
        login_view["loop_running"] = True
        pw = ctx = page = None
        try:
            pw = await async_playwright().start()
            ctx, page = await launch_browser(pw, headless=True)
            attach_capture(page)
            login_view["page"] = page
            await page.goto(CONFIG["dashboard_url"], wait_until="domcontentloaded")
            deadline = time.time() + 15 * 60
            logged_in = False
            while time.time() < deadline:
                await page.wait_for_timeout(700)
                try:
                    snap = await page.screenshot(type="jpeg", quality=65)
                    async with snapshot_lock:
                        login_view["snapshot"] = snap
                    if not await looks_like_login(page):
                        logged_in = True
                        break
                except Exception:
                    break
            if not logged_in:
                state["last_error"] = "Login tidsudløbet"
                return
            await page.wait_for_timeout(CONFIG["page_settle_ms"])
            await save_cookies(ctx)
            state["session_valid"] = True
            state["needs_login"] = False
            state["last_login"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            state["last_error"] = None
            save_state()
            asyncio.get_running_loop().create_task(refresh_job())
        except Exception as e:
            state["last_error"] = str(e)
        finally:
            state["login_in_progress"] = False
            login_view["page"] = None
            login_view["loop_running"] = False
            await end_browser(ctx, pw)


async def scheduler():
    while True:
        await asyncio.sleep(CONFIG["refresh_interval_minutes"] * 60)
        try:
            if not state["needs_login"]:
                await refresh_job()
        except Exception:
            pass


app = FastAPI(title="Meebook Bridge")


@app.middleware("http")
async def collapse_slashes(request, call_next):
    path = request.url.path
    if "//" in path:
        request.scope["path"] = re.sub(r"/{2,}", "/", path)
    return await call_next(request)


REMOTE_HTML = """<!doctype html>
<html lang="da"><head><meta charset="utf-8"><title>Meebook - login</title>
<style>
body{font-family:system-ui,sans-serif;margin:1rem;background:#111;color:#eee}
#wrap{position:relative;display:inline-block;max-width:100%}
#shot{max-width:100%;border:1px solid #333;border-radius:8px;display:block;background:#000}
#cursor{position:absolute;width:14px;height:14px;border:2px solid #f00;border-radius:50%;pointer-events:none;transform:translate(-50%,-50%);display:none}
.bar{display:flex;gap:8px;margin:10px 0;flex-wrap:wrap;align-items:center}
button,input,select{background:#1a1a1a;color:#eee;border:1px solid #444;border-radius:6px;padding:7px 12px}
button{background:#0a7;border-color:#0a7;cursor:pointer}
button:disabled{opacity:.4}
#txt{flex:1;min-width:180px}
.status{color:#8c8;margin-left:auto}
</style></head><body>
<div class="bar">
  <a href="."><button>← Tilbage</button></a>
  <button id="start" onclick="start()">Start login</button>
  <input id="txt" placeholder="Skriv tekst (fx MitID-navn)">
  <button onclick="typeText()">Skriv tekst</button>
  <button onclick="press('Enter')">Enter</button>
  <button onclick="press('Tab')">Tab</button>
  <button onclick="press('Escape')">Esc</button>
  <select id="scrollsel"><option value="0">Scroll...</option><option value="-400">Op</option><option value="400">Ned</option></select>
  <span id="st" class="status">Ikke aktiv</span>
</div>
<div id="wrap"><img id="shot" alt="Meebook login"><div id="cursor"></div></div>
<script>
var W=1440, H=900, poll=true;
function st(t){document.getElementById('st').textContent=t;}
async function start(){
  st('Starter...');
  await fetch('login',{method:'POST'});
  poll=true; loadShot();
}
function scaleXY(e){
  var img=document.getElementById('shot'), r=img.getBoundingClientRect();
  return {x:Math.round((e.clientX-r.left)*(W/r.width)), y:Math.round((e.clientY-r.top)*(H/r.height))};
}
document.getElementById('shot').addEventListener('click', async function(e){
  var c=scaleXY(e); var cur=document.getElementById('cursor');
  var r=this.getBoundingClientRect();
  cur.style.display='block';
  cur.style.left=(c.x*(r.width/W))+'px'; cur.style.top=(c.y*(r.height/H))+'px';
  await fetch('input/click',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)});
});
async function typeText(){
  var t=document.getElementById('txt').value;
  if(!t)return; await fetch('input/type',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});
}
async function press(k){await fetch('input/key',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:k})});}
document.getElementById('txt').addEventListener('keydown',function(e){if(e.key==='Enter')typeText();});
document.getElementById('scrollsel').addEventListener('change', async function(){
  if(this.value){await fetch('input/scroll',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({y:parseInt(this.value)})});this.value='0';}
});
function loadShot(){
  if(!poll)return;
  fetch('snapshot?t='+Date.now()).then(function(r){
    if(!r.ok){st('Ingen aktiv login');return;}
    return r.blob();
  }).then(function(b){
    if(!b)return;
    var u=URL.createObjectURL(b);
    var img=document.getElementById('shot');
    img.onload=function(){URL.revokeObjectURL(u);}; img.src=u;
    st('Login i gang...');
  }).catch(function(e){st('Fejl: '+e);}).finally(function(){setTimeout(loadShot,900);});
}
loadShot();
</script></body></html>"""

MAIN_HTML = """<!doctype html>
<html lang="da"><head><meta charset="utf-8"><title>Meebook Bridge</title>
<style>
body{font-family:system-ui,sans-serif;margin:2rem;background:#111;color:#eee}
h1{font-size:1.4rem}code{background:#222;padding:2px 5px;border-radius:4px}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #333;padding:6px 8px;text-align:left}
button{background:#0a7;color:#fff;border:0;padding:8px 14px;border-radius:6px;cursor:pointer;margin-right:6px}
.alert{background:#a30;padding:8px 12px;border-radius:6px}.ok{background:#083}
</style></head><body>
<h1>Meebook Bridge</h1>
<a id="loginbtn" href="remote"><button>Login (indlejret browser)</button></a>
<a href="data"><button>Se data (JSON)</button></a>
<div id="msg"></div>
<div id="health">Henter status...</div>
<script>
async function load(){const r=await fetch('health');const h=await r.json();
document.getElementById('health').innerHTML=
'<table><tr><th>Besked</th><th>Værdi</th></tr>'+
'<tr><td>Session gyldig</td><td>'+(h.session_valid?'<span class="ok">Ja</span>':'<span class="alert">Nej</span>')+'</td></tr>'+
'<tr><td>Kræver login</td><td>'+h.needs_login+'</td></tr>'+
'<tr><td>Sidste login</td><td>'+h.last_login+'</td></tr>'+
'<tr><td>Sidste opdatering</td><td>'+h.last_refresh+'</td></tr>'+
'<tr><td>Fejl</td><td>'+h.last_error+'</td></tr>'+
'<tr><td>Elev-ID</td><td>'+h.student_ids.join(', ')+'</td></tr>'+
'<tr><td>Årsplan-ID</td><td>'+h.year_span_id+'</td></tr>'+
'</table><h3>Fangede API-endpoints ('+h.resources.length+')</h3><ul>'+h.resources.slice(0,60).map(k=>'<li><code>'+k+'</code> <a href="data'+k+'">se data</a></li>').join('')+'</ul>';
}
load();setInterval(load,15000);
</script></body></html>"""


@app.on_event("startup")
async def startup():
    load_state()
    mqtt_start()
    global scheduler_task
    loop = asyncio.get_running_loop()
    scheduler_task = loop.create_task(scheduler())

    async def _initial_refresh():
        await asyncio.sleep(15)
        try:
            if not state["needs_login"]:
                await refresh_job()
            else:
                mqtt_publish()
        except Exception:
            pass

    loop.create_task(_initial_refresh())


@app.get("/", response_class=HTMLResponse)
async def index():
    return MAIN_HTML


@app.get("/remote", response_class=HTMLResponse)
async def remote():
    return REMOTE_HTML


@app.get("/health")
async def health():
    return {
        "session_valid": state["session_valid"],
        "needs_login": state["needs_login"],
        "login_in_progress": state["login_in_progress"],
        "last_login": state["last_login"],
        "last_refresh": state["last_refresh"],
        "last_error": state["last_error"],
        "student_ids": state["student_ids"],
        "year_span_id": state["year_span_id"],
        "resources": sorted(state["resources"].keys()),
    }


@app.post("/login")
async def login():
    if state["login_in_progress"]:
        return {"ok": False, "error": "Login er allerede i gang"}
    asyncio.get_running_loop().create_task(remote_login_flow())
    return {"ok": True}


@app.post("/refresh")
async def refresh():
    return {"ok": await refresh_job()}


@app.get("/login/status")
async def login_status():
    return {
        "running": state["login_in_progress"],
        "loop": login_view["loop_running"],
        "viewport": {"width": VIEW_W, "height": VIEW_H},
    }


@app.get("/snapshot")
async def snapshot():
    async with snapshot_lock:
        data = login_view["snapshot"]
    if data is None:
        return JSONResponse({"error": "Ingen aktiv login-session"}, status_code=404)
    return Response(content=data, media_type="image/jpeg")


async def require_login_page():
    page = login_view["page"]
    if page is None:
        return None
    return page


@app.post("/input/click")
async def input_click(payload: dict = Body(...)):
    page = await require_login_page()
    if page is None:
        return JSONResponse({"error": "Ingen aktiv login-session"}, status_code=400)
    try:
        await page.mouse.click(int(payload["x"]), int(payload["y"]))
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/input/type")
async def input_type(payload: dict = Body(...)):
    page = await require_login_page()
    if page is None:
        return JSONResponse({"error": "Ingen aktiv login-session"}, status_code=400)
    try:
        await page.keyboard.type(str(payload.get("text", "")), delay=30)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/input/key")
async def input_key(payload: dict = Body(...)):
    page = await require_login_page()
    if page is None:
        return JSONResponse({"error": "Ingen aktiv login-session"}, status_code=400)
    try:
        await page.keyboard.press(str(payload.get("key", "")))
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/input/scroll")
async def input_scroll(payload: dict = Body(...)):
    page = await require_login_page()
    if page is None:
        return JSONResponse({"error": "Ingen aktiv login-session"}, status_code=400)
    try:
        await page.mouse.wheel(0, int(payload.get("y", 0)))
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/data")
async def data():
    return JSONResponse(state["resources"])


@app.get("/data/{key:path}")
async def data_path(key: str):
    body = state["resources"].get("/" + key)
    if body is None:
        body = state["resources"].get(key)
    if body is None:
        matches = {k: v for k, v in state["resources"].items() if "/" + key in k}
        if matches:
            return JSONResponse(matches)
        return JSONResponse(
            {"error": "Ingen data fundet", "keys": sorted(state["resources"].keys())},
            status_code=404,
        )
    return JSONResponse(body)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8600, log_level="info")