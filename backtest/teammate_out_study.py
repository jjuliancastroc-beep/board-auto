import json, collections, math, statistics
B=json.load(open('box.json'))
games=collections.defaultdict(list)
for r in B: games[(r['d'],r['g'],r['team'])].append(r)
order=sorted(games, key=lambda k:k[0])
hist=collections.defaultdict(list)   # player id -> list of played rows
teamg=collections.defaultdict(int); teamp=collections.defaultdict(set)
res=collections.defaultdict(lambda: collections.defaultdict(lambda:[0,0]))
bump=collections.defaultdict(list)
for k in order:
    d,g,team=k; rows=games[k]
    played={r['id'] for r in rows if not r['dnp']}
    # team's top-2 scorers so far (>=5 games, played >=60% of team games)
    cand=[(statistics.mean(x['pts'] for x in hist[p]),p) for p in teamp[team] if len(hist[p])>=5 and len(hist[p])>=0.6*teamg[team]]
    stars=[p for _,p in sorted(cand,reverse=True)[:2] if _>=18]
    out=[p for p in stars if p not in played]
    for r in rows:
        if r['dnp'] or r['id'] in stars: continue
        h=hist[r['id']][-15:]
        if len(h)<5 or statistics.mean(x['min'] for x in h)<20: continue
        for s in ('pts','reb','ast','pra'):
            val=lambda x: x['pts']+x['reb']+x['ast'] if s=='pra' else x[s]
            avg=statistics.mean(val(x) for x in h); line=math.floor(avg)+0.5
            v=val(r); key='star out' if out else 'normal'
            res[s][key][0 if v>line else 1]+=1
            bump[(s,key)].append(v-avg)
    for r in rows:
        teamp[team].add(r['id'])
        if not r['dnp']: hist[r['id']].append({**r,'pra':r['pts']+r['reb']+r['ast']})
    teamg[team]+=1
for s in ('pts','reb','ast','pra'):
    for key in ('normal','star out'):
        o,u=res[s][key]; n=o+u
        print(f"{s:4s} {key:9s} over {o}-{u} = {o/n*100:5.1f}%  avg vs his average {statistics.mean(bump[(s,key)]):+.2f}  n={n}")
