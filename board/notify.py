"""Email alerts through GitHub: the run opens an issue in this repo that @mentions you, and GitHub emails it.
Free, no keys. Only for things worth an email: a new cash pick, a PULL on a cash pick, a broken feed, the weekly report."""
import os, json, urllib.request
from .common import load, save, now_ct

OWNER = "jjuliancastroc-beep"


def _api(method, path, body=None):
    tok = os.environ.get("GITHUB_TOKEN"); repo = os.environ.get("GITHUB_REPOSITORY")
    if not tok or not repo:
        return None
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}{path}", method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "User-Agent": "board-auto"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:
        print("notify failed:", e); return None


def send(key, title, lines, label="alert"):
    """key de-duplicates: the same alert is never sent twice."""
    sent = load("notified.json", [])
    if key in sent:
        return False
    page = "https://jjuliancastroc-beep.github.io/board-auto/"
    body = "\n".join(f"- {l}" for l in lines) + f"\n\nOpen The Board: {page}\n\n@{OWNER}"
    if os.environ.get("GITHUB_TOKEN"):
        r = _api("POST", "/issues", {"title": title, "body": body, "labels": [label]})
        if not r:
            return False
    else:
        print("[local, not sent]", title, lines)
    sent.append(key); save("notified.json", sent[-500:])
    return True
