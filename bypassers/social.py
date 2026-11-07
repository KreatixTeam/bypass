# Social-unlock style sites — ported from FastForward + observed live behavior.

import json
import re
from urllib.parse import urlparse

from .util import (b64d, extract_links, follow_redirect, guess_destination,
                   make_session, wildcard_search)


def bypass_rekonise(url, log):
    path = urlparse(url).path
    s = make_session("rekonise.com")
    r = s.get(f"https://api.rekonise.com/social-unlocks{path}", timeout=15)
    data = r.json()
    if data.get("url"):
        return data["url"]
    ut = data.get("unlock_token")
    if ut:
        # server enforces a minimum delay before unlock succeeds — retry
        import time
        deadline = time.time() + 45
        while time.time() < deadline:
            time.sleep(5)
            r2 = s.get(f"https://api.rekonise.com/social-unlocks{path}/unlock",
                       params={"token": ut}, timeout=15)
            if r2.status_code == 200:
                d2 = r2.json()
                if d2.get("url"):
                    return d2["url"]
    dest = guess_destination(json.dumps(data), url)
    if dest:
        return dest
    raise RuntimeError(f"rekonise: unlock failed")


def bypass_sub2unlock_com(url, log):
    # fetch the unlock endpoint page; dest is in a#link
    vid = urlparse(url).path.strip("/").split("/")[-1]
    s = make_session("sub2unlock.com")
    r = s.get(f"https://sub2unlock.com/link/unlock/{vid}", timeout=15)
    m = re.search(r'<a[^>]+id="link"[^>]+href="([^"]+)"', r.text) \
        or re.search(r'href="(https?://[^"]+)"[^>]+id="link"', r.text)
    if m:
        return m.group(1)
    dest = guess_destination(r.text, url)
    if dest:
        return dest
    raise RuntimeError("sub2unlock.com: no dest")


def bypass_sub2unlock_net(url, log):
    # dest sits in hidden divs + inline countdown attr("href","<dest>")
    s = make_session("sub2unlock.net")
    r = s.get(url, timeout=15)
    for pat in (
        r'attr\("href",\s*"(https?://[^"]+)"',
        r'id="theLinkID"[^>]*>([^<]+)<',
        r'id="theGetLink"[^>]*href="([^"]+)"',
        r'href="([^"]+)"[^>]*id="theGetLink"',
    ):
        m = re.search(pat, r.text)
        if m:
            u = m.group(1).strip()
            if u.startswith("http"):
                return u
    dest = guess_destination(r.text, url)
    if dest:
        return dest
    raise RuntimeError("sub2unlock.net: no dest")


def bypass_ytsubme(url, log):
    s = make_session("ytsubme.com")
    r = s.get(url, timeout=15)
    m = re.search(r'<a[^>]+id="link"[^>]+href="([^"]+)"', r.text) \
        or re.search(r'href="(https?://[^"]+)"[^>]+id="link"', r.text)
    if m:
        return m.group(1)
    dest = guess_destination(r.text, url)
    if dest:
        return dest
    raise RuntimeError("ytsubme: no dest")


def bypass_sub4unlock(url, log):
    # fun2() calls window.open(dest) — find the URL in the inline JS
    s = make_session(urlparse(url).hostname)
    r = s.get(url, timeout=15)
    for pat in (
        r'window\.open\(["\'](https?://[^"\']+)',
        r'fun2\s*=\s*function[^}]*?["\'](https?://[^"\']+)',
        r'(?:var|let|const)\s+\w+\s*=\s*["\'](https?://[^"\']+)["\']\s*;\s*window\.open',
    ):
        m = re.search(pat, r.text)
        if m:
            return m.group(1)
    dest = guess_destination(r.text, url)
    if dest:
        return dest
    raise RuntimeError("sub4unlock: no dest")


def bypass_generic_social(url, log):
    # unlocknow.net, sub2get.com, subfinal.com, mboost.me, social-unlock.com,
    # socialwolvez.com, paster.so, paster.gg, cuty.io, adfoc.us, mendationforc.info
    host = urlparse(url).hostname or ""
    s = make_session(host)
    try:
        r = s.get(url, timeout=20)
    except Exception as e:
        raise RuntimeError(f"fetch failed: {e}")
    html = r.text

    # common patterns on unlock sites
    patterns = (
        r'window\.location\.href\s*=\s*["\'](https?://[^"\']+)',
        r'window\.open\(["\'](https?://[^"\']+)',
        r'(?:var|let|const)\s+(?:dest|target|url|link|redirect|destination|final_url)\w*\s*=\s*["\'](https?://[^"\']+)',
        r'attr\(["\']href["\'],\s*["\'](https?://[^"\']+)',
        r'<a[^>]+id="(?:link|getlink|thelink|dest|unlock|continue)[^"]*"[^>]+href="([^"]+)"',
        r'<a[^>]+href="([^"]+)"[^>]+id="(?:link|getlink|thelink|dest|unlock|continue)[^"]*"',
        r'class="[^"]*(?:get-link|btn-get|destination|unlock-btn)[^"]*"[^>]+href="([^"]+)"',
        r'href="([^"]+)"[^>]*class="[^"]*(?:get-link|btn-get|destination|unlock-btn)',
        r'data-captcha-url=["\'](https?://[^"\']+)',
    )
    for pat in patterns:
        m = re.search(pat, html, re.I)
        if m and m.group(1).startswith("http"):
            return m.group(1)

    # base64 blobs that decode to URLs
    for m in re.finditer(r'atob\(["\']([A-Za-z0-9+/=_-]{20,})["\']\)', html):
        dec = b64d(m.group(1))
        if dec.startswith("http"):
            return dec

    # some sites expose a JSON api
    for ep in ("/api/link", "/api/unlock", "/api/get", "/unlock", "/get-link"):
        try:
            r2 = s.post(f"https://{host}{ep}", json={"id": urlparse(url).path.strip("/")}, timeout=8)
            if r2.headers.get("Content-Type", "").startswith("application/json"):
                d = r2.json()
                for k in ("url", "destination", "link", "target"):
                    if isinstance(d, dict) and isinstance(d.get(k), str) and d[k].startswith("http"):
                        return d[k]
        except Exception:
            pass

    # final redirect hop or dom guess
    if r.url != url and not r.url.rstrip("/").endswith(host):
        return r.url
    dest = guess_destination(html, url)
    if dest:
        return dest
    raise RuntimeError(f"{host}: no destination found")


SOCIAL_HOSTS = {
    "rekonise.com": bypass_rekonise,
    "sub2unlock.com": bypass_sub2unlock_com,
    "www.sub2unlock.com": bypass_sub2unlock_com,
    "sub2unlock.net": bypass_sub2unlock_net,
    "www.sub2unlock.net": bypass_sub2unlock_net,
    "ytsubme.com": bypass_ytsubme,
    "sub4unlock.io": bypass_sub4unlock,
    "sub4unlock.com": bypass_sub4unlock,
}
