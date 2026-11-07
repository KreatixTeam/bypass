# AdMaven/Lootlabs/Lootlinks bypass — ported from shadows_v2 (open source).
# Flow: session uuid -> CDN params -> /tc task config -> ws result.
# The "Confirm you are human" task is a Cloudflare Turnstile minted in a real
# (non-headless, undetected) Chromium via patchright — headless gets flagged.

import ast
import base64
import hashlib
import json
import math
import os
import random
import re
import threading
import time
from urllib.parse import urlparse

import websocket
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .util import (DEFAULT_UA, decode_resp, make_session, wildcard_search)

LOOT_HOSTS = {
    "lootlabs.gg", "links.lootlabs.gg", "lootlinks.co", "lootlinks.com",
    "loot-links.com", "loot-link.com", "lootlink.org", "linksloot.net",
    "lootdest.com", "lootdest.info", "lootdest.org", "links-loot.com",
    "lootlabs.com", "lootlink.io",
}


def _fract(r6, n1):
    n_ = 43758.5453 * math.sin(12.9898 * r6 + 78.233 * n1)
    return n_ - math.floor(n_)


def solve_webgl_nonce(uuid_str):
    y6 = int(uuid_str.replace("-", "")[:8], 16) / 4294967295.0
    for nonce in range(100000):
        o4 = _fract(y6, nonce)
        o4 = _fract(o4, nonce + 1)
        o4 = _fract(o4, nonce + 2)
        if o4 < 0.001:
            return nonce
    return 99999


def transform_uuid(uuid_str):
    m = re.findall(r"[A-Z]", uuid_str)
    key_str = "".join(m[:4]) if m else "KEY1"
    ub = uuid_str.encode()
    kb = key_str.encode()
    return base64.b64encode(bytes(b ^ kb[i % len(kb)] for i, b in enumerate(ub))).decode()


def make_botd(session_uuid):
    nonce = solve_webgl_nonce(session_uuid)
    botd = {
        "bot": False,
        "timestamp": int(time.time() * 1000),
        "webGLSolution": {
            "uuid": session_uuid,
            "nonce": nonce,
            "time": int(nonce * random.uniform(1.15, 1.4) + random.randint(20, 80)),
        },
    }
    aes_key = hashlib.sha256(transform_uuid(session_uuid).encode()).digest()
    iv = os.urandom(12)
    ct = AESGCM(aes_key).encrypt(iv, json.dumps(botd, separators=(",", ":")).encode(), None)
    botd["encrypted"] = base64.b64encode(iv + ct).decode()
    return json.dumps(botd, separators=(",", ":"))


def decrypt_data(encoded, key_length=5):
    try:
        raw = base64.b64decode(encoded)
        key, blob = raw[:key_length], raw[key_length:]
        return bytes(b ^ key[i % key_length] for i, b in enumerate(blob)).decode().strip()
    except Exception:
        return encoded.strip()


def get_cdn_tid(content):
    cdn = wildcard_search(content, "p['CDN_DOMAIN'] = '*'")
    tid = wildcard_search(content, "p['TID'] = '*'")
    key = wildcard_search(content, 'p["KEY"] = "*"')
    if not (cdn and tid and key):
        m1 = re.search(r"p\['CDN_DOMAIN'\]\s*=\s*'([^']*)'", content or "")
        m2 = re.search(r"p\['TID'\]\s*=\s*(\d+)", content or "")
        m3 = re.search(r"p\['KEY'\]\s*=\s*\"([^\"]*)\"", content or "")
        cdn, tid, key = (m1 and m1.group(1)), (m2 and m2.group(1)), (m3 and m3.group(1))
    if cdn and tid and key:
        return cdn.strip(), str(tid).strip(), key.strip()
    return None, None, None


def get_p_vars(content):
    pvars = {}
    for m in re.finditer(r"p\['(\w+)'\]\s*=\s*([^\n;]+)", content or ""):
        k, v = m.group(1), m.group(2).strip().rstrip(";").strip()
        if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
            v = v[1:-1]
        pvars[k] = v
    return pvars


def get_parameters(raw):
    text = (raw or "").strip()
    try:
        data = json.loads("[" + text[1:-2] + "]")
    except Exception:
        if text.endswith(";"):
            text = text[:-1]
        text = text.replace("false", "False").replace("true", "True").replace("null", "None")
        data = ast.literal_eval(text)
    return {
        "websocket_domain": data[9],
        "websocket_backup": data[10],
        "websocket_bckup2": data[11],
        "tc_domain": data[29],
        "allow_unlocker": data[30],
    }


def _as_bool(v, default=True):
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("1", "true")
    return bool(v)


def _fire(fn, *a, **kw):
    threading.Thread(target=lambda: _silent(fn, *a, **kw), daemon=True).start()


def _silent(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except Exception:
        pass


def _get(session, url, **kw):
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    kw.setdefault("timeout", 6)
    return session.get(url, **kw)


def _beacon_post(session, url):
    if not url:
        return
    if url.startswith("//"):
        url = "https:" + url
    session.post(url, data=b"", headers={"Content-Type": "text/plain;charset=UTF-8"}, timeout=4)


def _parse_r_payload(msg):
    if not isinstance(msg, str) or not msg.startswith("r:"):
        return None
    payload = "".join(ch for ch in msg[2:].strip() if 32 <= ord(ch) <= 126)
    if payload.startswith("http"):
        return payload
    return decrypt_data(payload)


def ws_wait_result(session, server, task, p_key, tid, session_id, page_origin, done, tleft=90):
    urid = str(task.get("urid", ""))
    cat = str(task.get("task_id", 0))
    try:
        shard = int(urid[-5:]) % 3
    except Exception:
        shard = 0
    origin = page_origin if str(page_origin).startswith("http") else f"https://{page_origin}"
    ws_url = f"wss://{shard}.{server}/c?uid={urid}&cat={cat}&key={p_key}&session_id={session_id}&is_loot=1&tid={tid}"
    ws = None
    stop = threading.Event()
    try:
        ws = websocket.create_connection(
            ws_url, timeout=8,
            header=[f"User-Agent: {session.headers.get('User-Agent', DEFAULT_UA)}",
                    "Accept-Language: en-US,en;q=0.9", "Cache-Control: no-cache", "Pragma: no-cache"],
            origin=origin,
        )
        ws.settimeout(0.5)

        def _ping():
            while not stop.wait(10):
                try:
                    ws.send("0")
                except Exception:
                    return

        threading.Thread(target=_ping, daemon=True).start()
        deadline = time.time() + max(int(tleft), 10)
        while time.time() < deadline and not done.get("result"):
            try:
                msg = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                break
            if isinstance(msg, bytes):
                try:
                    msg = msg.decode()
                except Exception:
                    continue
            if msg == "Refresh Page":
                break
            res = _parse_r_payload(msg)
            if res:
                done["result"] = res
                return
    except Exception:
        return
    finally:
        stop.set()
        if ws:
            try:
                ws.close()
            except Exception:
                pass


# ---- turnstile minting via real browser -----------------------------------
# playwright's sync api is bound to the thread/greenlet that started it, so a
# persistent browser breaks across uvicorn's worker threads. spin up a fresh
# instance per mint (serialized via _lock); ~2s extra launch cost per crack.

_lock = threading.Lock()


def _mint_via_capsolver(cap_url, sitekey, timeout):
    """Turnstile tokens aren't IP-bound, so an external solve works fine —
    needed on datacenter IPs where CF refuses the widget outright."""
    import requests as rq
    key = os.environ.get("CAPSOLVER_KEY")
    if not key:
        return None
    r = rq.post("https://api.capsolver.com/createTask", json={
        "clientKey": key,
        "task": {"type": "AntiTurnstileTaskProxyLess", "websiteURL": cap_url,
                 "websiteKey": sitekey, "metadata": {"action": "managed"}},
    }, timeout=15).json()
    tid_ = r.get("taskId")
    if not tid_:
        return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2.5)
        res = rq.post("https://api.capsolver.com/getTaskResult",
                      json={"clientKey": key, "taskId": tid_}, timeout=15).json()
        if res.get("status") == "ready":
            return (res.get("solution") or {}).get("token")
        if res.get("status") not in (None, "idle", "processing"):
            return None
    return None


def mint_turnstile(cap_url, timeout=60, session=None):
    sitekey = None
    if os.environ.get("CAPSOLVER_KEY"):
        try:
            html = (session or make_session("challenges.cloudflare.com")).get(cap_url, timeout=10).text
            sitekey = (re.search(r'sitekey="(0x[0-9a-zA-Z_-]+)"', html)
                       or re.search(r'sitekey\s*[:=]\s*["\'](0x[0-9a-zA-Z_-]+)', html))
            sitekey = sitekey.group(1) if sitekey else None
        except Exception:
            pass
        if sitekey:
            tok = _mint_via_capsolver(cap_url, sitekey, timeout)
            if tok:
                return tok

    from patchright.sync_api import sync_playwright
    with _lock:
        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(headless=False)
            try:
                ctx = browser.new_context(viewport={"width": 800, "height": 700}, locale="en-US")
                page = ctx.new_page()
                try:
                    page.goto(cap_url, wait_until="domcontentloaded", timeout=30000)
                    deadline = time.time() + timeout
                    clicked = False
                    while time.time() < deadline:
                        token = page.evaluate(
                            "() => window.TOKEN || document.querySelector('input[name=cf-turnstile-response]')?.value"
                        )
                        if token:
                            return token
                        if not clicked:
                            # datacenter IPs get the interactive checkbox — it never
                            # auto-solves, so click it with real mouse coords. the
                            # box sits ~28px from the left edge of the widget frame.
                            try:
                                el = page.wait_for_selector(
                                    "iframe[src*='challenges.cloudflare.com'], .cf-turnstile iframe, iframe",
                                    timeout=4000)
                                if el:
                                    box = el.bounding_box()
                                    if box:
                                        page.mouse.click(box["x"] + 28, box["y"] + box["height"] / 2)
                                        clicked = True
                            except Exception:
                                clicked = True  # no widget iframe; keep polling anyway
                        time.sleep(1.5)
                    return None
                finally:
                    try:
                        ctx.close()
                    except Exception:
                        pass
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
        finally:
            try:
                pw.stop()
            except Exception:
                pass


def bypass(url, log=lambda m: None):
    hostname = urlparse(url).hostname
    session = make_session(hostname)
    session.headers.update({
        "Accept-Encoding": "gzip, deflate",
        "Sec-CH-UA": '"Chromium";v="139", "Not:A-Brand";v="24", "Google Chrome";v="139"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
    })
    origin = f"https://{hostname}"
    initial = session.get(url, headers={"Origin": origin}, timeout=15)
    sess_uuid = wildcard_search(initial.text, "<script>document.session = '*'</script>")
    if not sess_uuid:
        raise RuntimeError("session uuid not found")
    log("session ok")
    _fire(session.post, f"{origin}/verify", data=json.dumps({"session": sess_uuid}),
          headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": origin}, timeout=6)

    cdn, tid, key = get_cdn_tid(initial.text)
    if not all([cdn, tid, key]):
        raise RuntimeError("cdn/tid/key missing")
    pvars = get_p_vars(initial.text)
    params = get_parameters(decode_resp(session.get(f"https://{cdn}/?tid={tid}&params_only=1",
                                                  headers={"Origin": origin}, timeout=10)))
    mess_session = str(random.randint(1, 9)) + "".join(str(random.randint(0, 9)) for _ in range(16)) + str(random.randint(0, 9))
    tcdata = {
        "tid": int(tid), "bl": [18, 2, 33, 7, 21, 49], "session": mess_session,
        "max_tasks": 1, "design_id": 135, "cur_url": url, "doc_ref": "", "tier_id": "0",
        "num_of_tasks": "1", "is_loot": True, "rkey": key,
        "cookie_id": str(random.randint(100000000, 999999999)),
        "botd": make_botd(sess_uuid), "botds": sess_uuid,
        "offer": pvars.get("OFFER", "0"), "ver": pvars.get("WIDGET_VERSION") or "v1",
        "tasks_timer": pvars.get("TASKS_TIMER") or "-1",
        "test_unlocker_app": int(pvars.get("TEST_UNLOCKER_APP", -1) or -1),
        "allow_unlocker": _as_bool(params.get("allow_unlocker"), True),
        "show_unlocker": _as_bool(pvars.get("SHOW_UNLOCKER"), True),
        "desktop_design": 1 if pvars.get("DESKTOP_DESIGN") in ("1", "true") else 0,
        "unlocker_only": int(pvars.get("UNLOCKER_ONLY", "0") or 0),
        "additional_info": {}, "taboola_user_sync": "0",
    }
    syncer = params.get("tc_domain") or "nerventualken.com"
    saved = dict(session.headers)
    try:
        session.headers.clear()
        session.headers.update({
            "User-Agent": saved.get("User-Agent", ""), "Accept": "*/*",
            "Content-Type": "application/json", "Origin": origin, "Referer": f"{origin}/",
            "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "cross-site",
        })
        rawr = session.post(f"https://{syncer}/tc", json=tcdata, timeout=15)
    finally:
        session.headers.clear()
        session.headers.update(saved)
    if rawr.status_code != 200:
        raise RuntimeError(f"tc status {rawr.status_code}")
    tcp_list = json.loads(decode_resp(rawr))
    if not isinstance(tcp_list, list):
        tcp_list = [tcp_list]
    if not tcp_list:
        raise RuntimeError("empty tc response")
    cap = next((i for i in tcp_list if i.get("title") == "Confirm you are human" or str(i.get("task_id")) == "41"), None)
    bind = cap or tcp_list[0]
    urid = bind.get("urid")
    task_id = bind.get("task_id", 0)
    if not urid:
        raise RuntimeError("no urid")
    log(f"urid={urid} task={task_id}")

    ws_session = bind.get("session_id") or "undefined"
    ws_domain = params.get("websocket_domain") or "onsultingco.com"
    for idx, item in enumerate(tcp_list):
        _fire(_get, session, f"https://enaightdecipie.com/?event=task_clicked&session_id={item.get('task_id')}&info={idx + 1}")
    done = {"result": None}
    t = threading.Thread(target=ws_wait_result,
                         args=(session, ws_domain, bind, key, tid, ws_session, origin, done),
                         kwargs={"tleft": 90}, daemon=True)
    t.start()
    try:
        shard = int(str(urid)[-5:]) % 3
    except Exception:
        shard = 0
    _fire(_beacon_post, session, f"https://{shard}.{ws_domain}/st?uid={urid}&cat={task_id}")
    ap = bind.get("action_pixel_url") or tcp_list[0].get("action_pixel_url")
    if ap:
        _fire(_get, session, ap)
    _fire(_get, session, f"https://{syncer}/td?ac=auto_complete&urid={urid}&cat={task_id}&tid={tid}")

    if cap:
        cap_url = cap.get("ad_url") or f"https://{syncer}/captcha?urid={urid}"
        if not str(cap_url).startswith("http"):
            cap_url = f"https://{syncer}/captcha?urid={urid}"
        log("minting turnstile")
        token = mint_turnstile(cap_url, session=session)
        if not token:
            raise RuntimeError("turnstile mint failed")
        vrf = session.post(f"https://{syncer}/captcha/verify",
                           json={"urid": str(urid), "token": token},
                           headers={"Origin": f"https://{syncer}", "Referer": cap_url,
                                    "Content-Type": "application/json"}, timeout=10)
        log(f"verify {vrf.status_code}")
        _fire(_get, session, f"https://{syncer}/td?ac=captcha&urid={urid}&=&cat={task_id}&tid={tid}")

    t.join(timeout=90)
    if done["result"]:
        return done["result"]
    raise RuntimeError("ws timed out")
