"""Change settings from your phone: comment on any issue in the repo (or open one). Only the repo owner's comments count.

  bankroll 650          set the bankroll to $650 (from today on, cash tickets add to it)
  approve NBA           allow cash picks for NBA once its kind of pick passes the test (your graduation call)
  unapprove NBA         back to paper
  skip Raptors          you did NOT place that cash ticket - it stops counting toward the bankroll
  goal 10000            change the goal
  help                  list commands
"""
import os, json, sys, re
from .common import load, save, today_ct, SPORTS
from .notify import _api, OWNER


def handle(text):
    st = load("settings.json", {}); out = []
    for line in text.splitlines():
        w = line.strip().split()
        if not w:
            continue
        cmd = w[0].lower(); arg = " ".join(w[1:])
        if cmd == "bankroll" and re.fullmatch(r"\$?\d+(\.\d+)?", arg):
            st["bankroll_base"] = float(arg.lstrip("$")); st["base_date"] = today_ct(); out.append(f"Bankroll set to ${st['bankroll_base']:.2f} as of {st['base_date']}.")
        elif cmd == "goal" and arg.replace(",", "").isdigit():
            st["goal"] = int(arg.replace(",", "")); out.append(f"Goal set to ${st['goal']:,}.")
        elif cmd in ("approve", "unapprove") and arg.upper() in SPORTS:
            s = set(st.get("cash_approved") or [])
            (s.add if cmd == "approve" else s.discard)(arg.upper()); st["cash_approved"] = sorted(s)
            out.append(f"{arg.upper()} {'approved for cash (still needs every pick to pass the gate)' if cmd == 'approve' else 'back to paper'}.")
        elif cmd == "skip" and arg:
            picks = load("picks.json", []); hit = [p for p in picks if p["decision"] == "CASH" and arg.lower() in p["pick"].lower()]
            for p in hit[-1:]:
                p["skipped"] = True; p["pl"] = 0.0; out.append(f"Marked not placed: {p['pick']} ({p['date']}).")
            save("picks.json", picks)
            if not hit:
                out.append(f"No cash pick matching '{arg}'.")
        elif cmd == "help":
            out.append(__doc__)
    if out:
        save("settings.json", st)
    return out


if __name__ == "__main__":
    ev = json.load(open(os.environ["GITHUB_EVENT_PATH"]))
    sender = (ev.get("sender") or {}).get("login")
    if sender != OWNER:
        print("ignored: not the owner"); sys.exit(0)
    body = ((ev.get("comment") or {}).get("body")) or ((ev.get("issue") or {}).get("body")) or ""
    if "comment" not in ev:
        body = ((ev.get("issue") or {}).get("title") or "") + "\n" + body
    res = handle(body)
    if res:
        log = load("requests_log.json", []); log.append({"date": today_ct(), "text": body.strip()[:200], "result": res}); save("requests_log.json", log[-100:])
    num = (ev.get("issue") or {}).get("number")
    if res and num:
        _api("POST", f"/issues/{num}/comments", {"body": "Done:\n" + "\n".join(f"- {r}" for r in res)})
    print(res)
