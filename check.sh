#!/bin/sh
# Gate for committing: every generator must agree with what is on disk.
# Written after pushing a stale lineage appendix twice, because chaining
# `a --check && b --check` then calling git on the next line does not gate
# anything -- git runs whatever the chain returned.
set -e
python3 generate-charts.py  >/dev/null
python3 generate-atlas.py    --check
python3 generate-lineages.py --check
python3 generate-ruled-out.py --check
python3 - <<'PY'
import re, collections
from html.parser import HTMLParser
VOID={'area','base','br','col','embed','hr','img','input','link','meta','source','track','wbr'}
SVG={'path','rect','line','text','tspan','g','svg','circle','sup'}
class P(HTMLParser):
    def __init__(s):
        super().__init__(convert_charrefs=True); s.st=[]; s.err=[]
    def handle_starttag(s,t,a):
        if t not in VOID and t not in SVG: s.st.append(t)
    def handle_endtag(s,t):
        if t in VOID or t in SVG: return
        if t in s.st:
            if s.st[-1]!=t: s.err.append('mismatch '+t)
            else: s.st.pop()
        else: s.err.append('stray '+t)
bad=0
for f in ('index.html','ruled-out.html'):
    h=open(f,encoding='utf-8').read(); p=P(); p.feed(h)
    if p.st or p.err:
        print(f'  {f}: unclosed={p.st} errors={p.err[:3]}'); bad=1
    ids=[k for k,v in collections.Counter(re.findall(r'\sid="([^"]+)"',h)).items() if v>1]
    if ids: print(f'  {f}: duplicate ids {ids}'); bad=1
    for n in ('Gregory Mushen','Robert Mushen','Deborah Campbell'):
        if n in h: print(f'  {f}: LIVING PERSON NAMED — {n}'); bad=1
    brit=sum(len(re.findall(x,h,re.I)) for x in
             (r'colour',r'gaol',r'organis',r'centre\b',r'artefact',r'labell',r'practis(ing|ed)'))
    if brit: print(f'  {f}: {brit} British spellings'); bad=1
raise SystemExit(bad)
PY
echo "  all checks pass"
