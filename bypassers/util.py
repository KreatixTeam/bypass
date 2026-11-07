import base64
import gzip
import re
import zlib
from urllib.parse import urlparse, urljoin

import requests

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)


def make_session(host=None):
    s = requests.Session()
    s.headers.update({
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    if host:
        s.headers.update({"Origin": f"https://{host}", "Referer": f"https://{host}/"})
    return s


def wildcard_search(text, pattern):
    regex = re.escape(pattern).replace(r"\*", "(.*?)")
    m = re.search(regex, text or "")
    return m.group(1) if m else None


def decode_resp(resp):
    enc = (resp.headers.get("Content-Encoding") or "").lower()
    content = resp.content
    try:
        if "gzip" in enc:
            return gzip.decompress(content).decode("utf-8")
        if "deflate" in enc:
            return zlib.decompress(content).decode("utf-8")
        return content.decode("utf-8", errors="ignore")
    except Exception:
        return content.decode("utf-8", errors="ignore")


def follow_redirect(url, session=None, timeout=15):
    s = session or make_session(urlparse(url).hostname)
    try:
        r = s.get(url, timeout=timeout, allow_redirects=True)
        return r.url
    except Exception:
        r = s.head(url, timeout=timeout, allow_redirects=True)
        return r.url


def b64d(s):
    s = s.strip()
    s += "=" * (-len(s) % 4)
    try:
        return base64.b64decode(s).decode("utf-8", errors="ignore")
    except Exception:
        try:
            return base64.urlsafe_b64decode(s).decode("utf-8", errors="ignore")
        except Exception:
            return ""


_URL_RE = re.compile(r"https?://[^\s\"'<>`\\)]+")


def extract_links(html, base=None):
    links = _URL_RE.findall(html or "")
    out = []
    for l in links:
        l = l.rstrip(".,;!")
        if base:
            l = urljoin(base, l)
        out.append(l)
    return out


_SKIP_HOSTS = {
    "google.com", "www.google.com", "gstatic.com", "www.gstatic.com",
    "cloudflare.com", "challenges.cloudflare.com", "ajax.cloudflare.com",
    "jquery.com", "jsdelivr.net", "cdn.jsdelivr.net", "unpkg.com",
    "cdnjs.com", "cdnjs.cloudflare.com", "bootstrapcdn.com", "maxcdn.bootstrapcdn.com",
    "fontawesome.com", "fonts.googleapis.com", "fonts.gstatic.com",
    "facebook.com", "www.facebook.com", "twitter.com", "x.com",
    "googleapis.com", "www.googleapis.com", "googletagmanager.com",
    "google-analytics.com", "www.google-analytics.com",
    "discord.com", "discord.gg", "discordapp.com", "youtube.com", "www.youtube.com",
    "youtu.be", "tiktok.com", "www.tiktok.com", "instagram.com", "twitch.tv",
    "schema.org", "w3.org", "www.w3.org", "w3schools.com",
    "paypal.com", "stripe.com", "adservice.google.com", "doubleclick.net",
    "googlesyndication.com", "ads.twitter.com", "analytics.twitter.com",
    "taboola.com", "outbrain.com", "amazon-adsystem.com",
}

_SKIP_PATHS = re.compile(
    r"\.(css|js|png|jpe?g|gif|svg|ico|woff2?|ttf|eot|map|webp|mp4|webm|xml|json)($|\?)"
    r"|/cdn-cgi/|/assets?/|/static/|/images?/|/img/|/fonts?/|/css/|/js/|favicon",
    re.I,
)


def guess_destination(html, page_url):
    """Generic fallback: find the most plausible outbound destination URL in HTML."""
    host = (urlparse(page_url).hostname or "").lower().lstrip("www.")

    # 1) explicit JS navigations
    for pat in (
        r'(?:window\.)?location(?:\.href)?\s*=\s*["\'](https?://[^"\']+)',
        r'window\.open\(\s*["\'](https?://[^"\']+)',
        r'meta[^>]+url=\s*(https?://[^\s"\'>]+)',
        r'(?:data-url|data-href|data-target|data-link|data-destination)=["\'](https?://[^"\']+)',
        r'(?:href|src)=["\'](https?://[^"\']+)["\'][^>]*id=["\'](?:link|getlink|theLink|dest)',
    ):
        m = re.search(pat, html or "", re.I)
        if m:
            u = m.group(1)
            h = (urlparse(u).hostname or "").lower().lstrip("www.")
            if h and h != host and h not in _SKIP_HOSTS:
                return u

    # 2) first plausible outbound link
    for u in extract_links(html, page_url):
        p = urlparse(u)
        h = (p.hostname or "").lower().lstrip("www.")
        if not h or h == host or h in _SKIP_HOSTS:
            continue
        if _SKIP_PATHS.search(p.path):
            continue
        return u
    return None
