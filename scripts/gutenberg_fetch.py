#!/usr/bin/env python3
"""Search Project Gutenberg and download plain-text ebooks.
Usage:
  gutenberg_fetch.py search "query"
  gutenberg_fetch.py get <ebook_id> "slug_name"
"""
import sys, os, re, urllib.parse, urllib.request

UA={"User-Agent":"Mozilla/5.0"}
OUT=os.path.join(os.path.dirname(__file__),"..","gutenberg_downloads")

def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=40).read()

def search(q):
    url="https://www.gutenberg.org/ebooks/search/?"+urllib.parse.urlencode({"query":q})
    html=fetch(url).decode("utf-8","replace")
    blocks=re.findall(r'<li class="booklink">.*?</li>', html, re.S)
    rows=[]
    for b in blocks:
        m=re.search(r'/ebooks/(\d+)"',b); 
        t=re.search(r'<span class="title">(.*?)</span>',b,re.S)
        s=re.search(r'<span class="subtitle">(.*?)</span>',b,re.S)
        dl=re.search(r'<span class="extra">([\d,]+) downloads</span>',b)
        if not m: continue
        clean=lambda x: re.sub(r'<[^>]+>','',x).strip() if x else ''
        rows.append((m.group(1),clean(t.group(1) if t else ''),clean(s.group(1) if s else ''),dl.group(1) if dl else '0'))
    return rows

def get(eid,slug):
    os.makedirs(OUT,exist_ok=True)
    urls=[f"https://www.gutenberg.org/cache/epub/{eid}/pg{eid}.txt",
          f"https://www.gutenberg.org/files/{eid}/{eid}-0.txt",
          f"https://www.gutenberg.org/files/{eid}/{eid}.txt"]
    for u in urls:
        try:
            data=fetch(u)
            if len(data)>2000:
                path=os.path.join(OUT,f"{slug}__pg{eid}.txt")
                open(path,"wb").write(data)
                print(f"OK {slug} <- {u} ({len(data)//1024} KB)")
                return True
        except Exception as e:
            continue
    print(f"FAIL {slug} (id {eid})")
    return False

if __name__=="__main__":
    if sys.argv[1]=="search":
        for r in search(sys.argv[2])[:8]:
            print(f"{r[0]:>7} | {r[3]:>7} dl | {r[1][:50]:50s} | {r[2][:25]}")
    elif sys.argv[1]=="get":
        get(sys.argv[2],sys.argv[3])
