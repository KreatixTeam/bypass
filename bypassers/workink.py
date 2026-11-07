# work.ink bypass — ported from FastForward (open source).
# The recaptcha check accepts any token; destination arrives over websocket.

import base64
import json
import time
import uuid
from urllib.parse import urlparse, parse_qs

import websocket

from .util import DEFAULT_UA

WORKINK_HOSTS = {"work.ink", "workink.net", "workink.me", "work.ink.net"}

_BASE = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _b62(s):
    v = _BASE.index(s[0])
    for c in s[1:]:
        v = 62 * v + _BASE.index(c)
    return v


def bypass(url, log=lambda m: None):
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    encoded_uid, link_custom = parts[-2], parts[-1]
    decoded_uid = _b62(encoded_uid)
    ws = websocket.create_connection(
        "wss://redirect-api.work.ink/v1/ws", timeout=15,
        header=[f"User-Agent: {DEFAULT_UA}", "Origin: https://work.ink"],
    )
    ws.settimeout(1.0)
    ws.send(json.dumps({"type": "c_announce", "payload": {
        "linkCustom": link_custom, "linkUserId": decoded_uid, "referer": "unknown"}}))
    socials, monos = [], set()
    result = None
    last_ping = time.time()
    deadline = time.time() + 60
    while time.time() < deadline and not result:
        if time.time() - last_ping > 10:
            try:
                ws.send(json.dumps({"type": "c_ping", "payload": {}}))
            except Exception:
                break
            last_ping = time.time()
        try:
            msg = ws.recv()
        except websocket.WebSocketTimeoutException:
            continue
        except Exception:
            break
        data = json.loads(msg)
        if data.get("error"):
            continue
        t, payload = data.get("type"), data.get("payload") or {}
        if t == "s_link_info":
            socials.extend(payload.get("socials") or [])
            ms = payload.get("monetizationScript") or ""
            for m in ("readArticles", "browserExtension"):
                if m in ms:
                    monos.add(m)
        elif t == "s_start_recaptcha_check":
            ws.send(json.dumps({"type": "c_recaptcha_response",
                                "payload": {"recaptchaResponse": str(uuid.uuid4())}}))
        elif t == "s_recaptcha_okay":
            for s in socials:
                ws.send(json.dumps({"type": "c_social_started", "payload": {"url": s.get("url")}}))
                time.sleep(3)
            for m in monos:
                if m == "readArticles":
                    for ev in ("start", "closeClicked"):
                        ws.send(json.dumps({"type": "c_monetization", "payload": {
                            "type": "readArticles", "payload": {"event": ev}}}))
                elif m == "browserExtension":
                    if "readArticles" in monos:
                        time.sleep(16)
                    ws.send(json.dumps({"type": "c_monetization", "payload": {
                        "type": "browserExtension", "payload": {"event": "start"}}}))
        elif t == "s_monetization":
            if payload.get("type") == "browserExtension":
                ws.send(json.dumps({"type": "c_monetization", "payload": {
                    "type": "browserExtension",
                    "payload": {"event": "confirm", "token": (payload.get("payload") or {}).get("token")}}}))
        elif t == "s_link_destination":
            u = payload.get("url", "")
            q = parse_qs(urlparse(u).query)
            if "duf" in q:
                u = base64.b64decode(q["duf"][0][::-1]).decode("utf-8", "ignore")
            result = u
    try:
        ws.close()
    except Exception:
        pass
    if not result:
        raise RuntimeError("work.ink ws timed out")
    return result
