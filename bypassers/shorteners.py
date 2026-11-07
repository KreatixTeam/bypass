# URL shorteners — follow redirects. Also covers simple countdown interstitials.

import re
from urllib.parse import urlparse

from .util import b64d, follow_redirect, guess_destination, make_session

SHORTENER_HOSTS = {
    "bit.ly", "bitly.com", "cl.gy", "goo.gl", "is.gd", "rebrand.ly",
    "rkns.link", "shorter.me", "t.co", "t.ly", "tiny.cc", "tinylink.onl",
    "tinyurl.com", "v.gd", "cutt.ly", "cutt.us", "rb.gy", "shorturl.at",
    "mboost.me", "bst.gg", "booo.st",
}


def bypass(url, log=lambda m: None):
    dest = follow_redirect(url)
    if dest and dest != url:
        return dest
    s = make_session(urlparse(url).hostname)
    r = s.get(url, timeout=15, allow_redirects=True)
    if r.url != url:
        return r.url
    html = r.text
    m = re.search(r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+url=\s*([^\s"\'>]+)', html, re.I) \
        or re.search(r'url=([^\s"\'>]+)["\'][^>]*http-equiv', html, re.I)
    if m:
        return m.group(1)
    dest = guess_destination(html, url)
    if dest:
        return dest
    raise RuntimeError("shortener: no redirect found")


def bypass_boost(url, log=lambda m: None):
    # boost.ink/bst.gg embed the dest as base64 in a weird attr
    host = urlparse(url).hostname or "boost.ink"
    s = make_session(host)
    r = s.get(url, timeout=15)
    for pat in (r'bufpsvdhmjybvgfncqfa="([^"]+)"',
                r'kekw\s*=\s*["\']([^"\']+)',
                r'atob\(["\']([A-Za-z0-9+/=_-]{20,})["\']\)',
                r'data-dest=["\']([A-Za-z0-9+/=_-]{20,})'):
        m = re.search(pat, r.text)
        if m:
            dec = b64d(m.group(1))
            if dec.startswith("http"):
                return dec
            if m.group(1).startswith("http"):
                return m.group(1)
    if r.url != url:
        return r.url
    dest = guess_destination(r.text, url)
    if dest:
        return dest
    raise RuntimeError("boost: no dest")


BOOST_HOSTS = {"boost.ink", "bst.gg", "booo.st", "boostink.gg"}
