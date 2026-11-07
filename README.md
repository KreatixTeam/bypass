# bypass

Self-hosted link bypasser. Paste a protected link, get the destination.

## Supported

- **Linkvertise** (all domains: linkvertise.com/.net, link-to.net, link-center.net, link-target.net, direct-link.net, file-link.net, up-to-down.net, link-hub.net)
- **AdMaven / Lootlabs** (lootlabs.gg, links.lootlabs.gg, lootlinks.co/.com, loot-links.com, lootlink.org, linksloot.net, lootdest.com/.info/.org, links-loot.com) — includes the Turnstile captcha step
- **Work.ink** (all domains)
- **Social unlock**: rekonise.com, sub2unlock.com, sub2unlock.net, sub4unlock.io/.com, ytsubme.com, sub2get.com, subfinal.com, unlocknow.net, mboost.me, social-unlock.com, socialwolvez.com, paster.so, paster.gg, adfoc.us, cuty.io
- **Boost**: boost.ink, bst.gg
- **Paste sites**: pastebin.com, rentry.org/.co, justpaste.it, paste-drop.com, pastecanyon.com, pastehill.com, pastemode.com
- **URL shorteners**: bit.ly, cl.gy, is.gd, rebrand.ly, rkns.link, shorter.me, t.co, t.ly, tiny.cc, tinylink.onl, tinyurl.com, v.gd, cutt.ly/us, rb.gy, shorturl.at — plus a generic redirect-follow + DOM-extract fallback for anything else

## API

```
POST /api/bypass
{"url": "https://links.lootlabs.gg/s?..."}
→ {"ok": true, "destination": "https://...", "ms": 8086}
```

## Run

```sh
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
patchright install chromium
# needs a display for the turnstile solver — on headless servers use xvfb:
xvfb-run -a uvicorn main:app --host 127.0.0.1 --port 8471
```

## Notes

- Lootlabs' "Confirm you are human" is Cloudflare Turnstile minted in a real
  Chromium via patchright (headed under Xvfb). Headless gets flagged.
- Linkvertise tasks: getContent → startTask/completeTask loop → target.
- Work.ink recaptcha accepts a random UUID; destination arrives over websocket.
- Rekonise enforces ~10s min delay before the unlock endpoint works; the
  adapter retries until it flips.
- Bypass logic ported/optimized from open source: shadows_v2 (lootlabs),
  FastForward (work.ink, rekonise, sub2unlock, boost), shortlink-bypass
  (linkvertise lineage).
