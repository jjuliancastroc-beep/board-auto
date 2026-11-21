import json, datetime, urllib.request, concurrent.futures as cf, os
def get(u):
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(u, timeout=20))
        except Exception: pass
d0=datetime.date(2026,10,20); ids=[]
for i in range(33):
    d=(d0+datetime.timedelta(i)).strftime('%Y%m%d')
    s=get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d}") or {}
    for e in s.get('events',[]):
        if e['status']['type'].get('completed'): ids.append((d,e['id']))
print(len(ids))
def summ(x):
    d,i=x; return d,i,get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={i}")
out=[]
with cf.ThreadPoolExecutor(12) as ex:
    for d,i,s in ex.map(summ,ids):
        if not s: continue
        for t in s.get('boxscore',{}).get('players',[]):
            st=t['statistics'][0]; names=st['names']
            for a in st['athletes']:
                row={'d':d,'g':i,'team':t['team']['abbreviation'],'id':a['athlete']['id'],'n':a['athlete']['displayName'],'dnp':bool(a.get('didNotPlay')) or not a.get('stats')}
                if not row['dnp']:
                    v=dict(zip(names,a['stats']))
                    try: row.update(min=float(v.get('MIN') or 0),pts=float(v['PTS']),reb=float(v['REB']),ast=float(v['AST']),tpm=float(v['3PT'].split('-')[0]))
                    except Exception: row['dnp']=True
                out.append(row)
json.dump(out,open('box.json','w')); print(len(out))
