# Paste sites — return raw paste content (they're payload holders, not lockers).

import re
from urllib.parse import urlparse

from .util import make_session, wildcard_search


def _raw(url, raw_url):
    s = make_session(urlparse(url).hostname)
    r = s.get(raw_url, timeout=15)
    return r.text


def bypass_pastebin(url, log):
    vid = urlparse(url).path.strip("/")
    return _raw(url, f"https://pastebin.com/raw/{vid}")


def bypass_rentry(url, log):
    vid = urlparse(url).path.strip("/")
    return _raw(url, f"https://rentry.org/{vid}/raw")


def bypass_justpaste(url, log):
    s = make_session("justpaste.it")
    r = s.get(url, timeout=15)
    m = re.search(r'<div[^>]+id="(?:articleContent|pasteContent|content)"[^>]*>(.*?)</div>', r.text, re.S)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return r.text


def bypass_generic_paste(url, log):
    host = urlparse(url).hostname or ""
    s = make_session(host)
    # try common raw endpoints first
    vid = urlparse(url).path.strip("/").split("/")[-1]
    for cand in (f"https://{host}/raw/{vid}", f"https://{host}/{vid}/raw", f"https://{host}/api/raw/{vid}"):
        try:
            r = s.get(cand, timeout=8)
            if r.status_code == 200 and "<html" not in r.text[:300].lower():
                return r.text
        except Exception:
            pass
    r = s.get(url, timeout=15)
    html = r.text
    for pat in (r'<textarea[^>]*>(.*?)</textarea>',
                r'<pre[^>]*>(.*?)</pre>',
                r'<div[^>]+class="[^"]*(?:paste|content|raw)[^"]*"[^>]*>(.*?)</div>'):
        m = re.search(pat, html, re.S | re.I)
        if m:
            return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return html[:20000]


PASTE_HOSTS = {
    "pastebin.com": bypass_pastebin,
    "rentry.org": bypass_rentry,
    "rentry.co": bypass_rentry,
    "justpaste.it": bypass_justpaste,
    "paste-drop.com": bypass_generic_paste,
    "pastedrop.com": bypass_generic_paste,
    "pastecanyon.com": bypass_generic_paste,
    "pastehill.com": bypass_generic_paste,
    "pastemode.com": bypass_generic_paste,
    "paster.so": bypass_generic_paste,
    "paster.gg": bypass_generic_paste,
}
