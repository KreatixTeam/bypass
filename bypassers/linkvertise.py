# linkvertise bypass — modern flow (reverse-engineered from live traffic):
# getContent → ContentAccessTaskSet → loop: startTask + completeTask on each
# non-premium task (WaitTask → AdTask ×N) → getContent → DetailPageTargetData.url

import re
import time
from urllib.parse import urlparse

import requests

LINKVERTISE_HOSTS = {
    "linkvertise.com", "linkvertise.net", "link-to.net", "link-center.net",
    "link-target.net", "direct-link.net", "file-link.net", "up-to-down.net",
    "link-hub.net", "linkvertise.download",
}

GQ = "https://publisher.linkvertise.com/graphql"

GC_Q = """query getContent($identifier: PublicLinkIdentificationInput!, $task_args: TaskArgument) {
  getContent(input: $identifier, task_args: $task_args) {
    __typename
    ... on ContentAccessTaskSet { tasks { __typename id
      ... on WaitTask { status remainingWaitingTime adsTotal }
      ... on PremiumTask { status }
      ... on AdTask { status adsTotal } } }
    ... on DetailPageTargetData { type url paste }
  }
}"""


def _mk_sess():
    s = requests.Session()
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"),
        "Origin": "https://linkvertise.com", "Referer": "https://linkvertise.com/",
        "Content-Type": "application/json",
    })
    return s


def _post(sess, op, variables, query):
    r = sess.post(GQ, params={"name": op},
                  json={"operationName": op, "variables": variables, "query": query}, timeout=20)
    return r.json()


def bypass(url, log=lambda m: None):
    parts = [p for p in urlparse(url).path.split("/") if p]
    uid = pid = None
    for i, p in enumerate(parts):
        if p.isdigit() and i + 1 < len(parts):
            uid, pid = p, parts[i + 1]
            break
    if not uid:
        raise RuntimeError("linkvertise: can't parse uid/slug")
    sess = _mk_sess()
    ident = {"userIdAndUrl": {"url": pid, "user_id": uid}}
    task_args = {
        "additional_data": {"taboola": {"user_id": "fallbackUserId", "consent_string": "",
                                        "url": url, "external_referrer": "", "session_id": None}},
        "action_id": "",
    }
    for round in range(12):
        d = _post(sess, "getContent", {"identifier": ident, "task_args": task_args}, GC_Q)
        gc = (d.get("data") or {}).get("getContent") or {}
        if gc.get("__typename") == "DetailPageTargetData":
            dest = gc.get("url") or gc.get("paste")
            if dest:
                return dest
            raise RuntimeError("linkvertise: empty target")
        tasks = gc.get("tasks") or []
        log(f"tasks: {[t.get('__typename') for t in tasks]}")
        todo = [t for t in tasks if t.get("__typename") != "PremiumTask"]
        if not todo:
            raise RuntimeError("linkvertise: premium only")
        progressed = False
        for t in todo:
            tid = t.get("id")
            if not tid:
                continue
            for op in ("startTask", "completeTask"):
                q = (f'mutation {op}($input: PublicLinkIdentificationInput!, $task_id: String!, $task_args: TaskArgument) '
                     f'{{ {op}(input: $input, task_id: $task_id, task_args: $task_args) {{ __typename }} }}')
                for attempt in range(4):
                    r = _post(sess, op, {"input": ident, "task_id": tid, "task_args": task_args}, q)
                    errs = r.get("errors") or []
                    if not errs:
                        progressed = True
                        break
                    if "Task Not Found" in str(errs):
                        time.sleep(0.7)
                        continue
                    break
                time.sleep(0.4)
        if not progressed:
            time.sleep(1.5)
    raise RuntimeError("linkvertise: task loop exhausted")
