import time
import threading
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from bypassers import route

app = FastAPI(title="kreatix bypass")


class BypassReq(BaseModel):
    url: str


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/bypass")
def api_bypass(req: BypassReq):
    url = req.url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    host = urlparse(url).hostname
    if not host:
        return JSONResponse({"ok": False, "error": "bad url"}, status_code=400)
    logs = []
    t0 = time.time()
    try:
        result = route(url, lambda m: logs.append(m))
        return {"ok": True, "destination": result, "ms": int((time.time() - t0) * 1000), "log": logs}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:300], "ms": int((time.time() - t0) * 1000), "log": logs},
                            status_code=502)
