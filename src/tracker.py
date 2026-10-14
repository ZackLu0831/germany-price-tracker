#!/usr/bin/env python3
"""Best-effort public-page price collection. Failures are recorded, never invented."""
import json, os, re, sys, time, random, html
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs' / 'data'
PLATFORMS = {'mediamarkt':'MediaMarkt', 'amazon':'Amazon.de', 'otto':'OTTO.de'}
DOMAINS = {'mediamarkt':('mediamarkt.de',), 'amazon':('amazon.de',), 'otto':('otto.de',)}
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36', 'Accept-Language':'de-DE,de;q=0.9,en;q=0.7', 'Accept':'text/html,application/xhtml+xml'}
MAX_HISTORY_DAYS = 365

def load(path, default):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError): return default

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def valid_url(url, shop):
    try:
        p=urlparse(url)
        return p.scheme=='https' and any(p.hostname == d or p.hostname.endswith('.'+d) for d in DOMAINS[shop])
    except Exception: return False

def amount(value):
    if value is None or isinstance(value,bool): return None
    if isinstance(value,(float,int)): return round(float(value),2) if 0<float(value)<100000 else None
    s=html.unescape(str(value)).strip().replace('\xa0','').replace('€','').replace('EUR','')
    m=re.search(r'\d[\d.,\s]*',s)
    if not m: return None
    s=m.group(0).strip().replace(' ','')
    if ',' in s and '.' in s:
        s=s.replace('.','').replace(',','.') if s.rfind(',')>s.rfind('.') else s.replace(',','')
    elif ',' in s: s=s.replace(',','.')
    elif s.count('.')>1: s=s.replace('.','')
    elif '.' in s and len(s.split('.')[-1])==3: s=s.replace('.','')
    try:
        n=float(s)
        return round(n,2) if 0<n<100000 else None
    except ValueError: return None

def walk_ld(obj):
    if isinstance(obj,list):
        for x in obj: yield from walk_ld(x)
    elif isinstance(obj,dict):
        yield obj
        for k in ('@graph','mainEntity','itemListElement'):
            if k in obj: yield from walk_ld(obj[k])

def parse_price(soup, shop):
    # Prefer structured Product offers, then shop-specific price metadata.
    for script in soup.select('script[type="application/ld+json"]'):
        try: data=json.loads(script.string or script.get_text())
        except (ValueError,TypeError): continue
        for obj in walk_ld(data):
            types=obj.get('@type',[])
            if isinstance(types,str): types=[types]
            if 'Product' not in types: continue
            offers=obj.get('offers',[])
            if isinstance(offers,dict): offers=[offers]
            for offer in offers:
                if not isinstance(offer,dict): continue
                currency=offer.get('priceCurrency','EUR')
                if currency != 'EUR': continue
                price=amount(offer.get('price'))
                if price: return price, 'json-ld'
                ps=offer.get('priceSpecification',{})
                if isinstance(ps,dict):
                    price=amount(ps.get('price'))
                    if price:return price,'json-ld-price-spec'
    for selector,attr in [
        ('meta[property="product:price:amount"]','content'),
        ('meta[property="og:price:amount"]','content'),
        ('meta[itemprop="price"]','content'),
        ('[itemprop="price"][content]','content'),
        ('[data-testid="price"]','text'),
        ('[data-testid="product-price"]','text'),
    ]:
        for el in soup.select(selector)[:5]:
            value=el.get(attr) if attr!='text' else el.get_text(' ',strip=True)
            p=amount(value)
            if p: return p, selector
    # Do not use generic euro-regex: may select installment, RRP or accessories.
    return None,None

def fetch_price(url,shop):
    if not valid_url(url,shop): raise ValueError('invalid shop URL/domain')
    r=requests.get(url,headers=HEADERS,timeout=22,allow_redirects=True)
    if not valid_url(r.url,shop): raise ValueError('redirected outside approved shop')
    if r.status_code in (403,429,503): raise RuntimeError(f'HTTP {r.status_code} (possible anti-bot/rate limit)')
    r.raise_for_status()
    if 'html' not in r.headers.get('content-type','').lower(): raise RuntimeError('response is not HTML')
    soup=BeautifulSoup(r.text,'html.parser')
    title=soup.title.get_text(' ',strip=True)[:180] if soup.title else ''
    lower=(title+' '+r.text[:3000]).lower()
    if any(x in lower for x in ('captcha','robot check','access denied','automatisierte zugriffe')):
        raise RuntimeError('anti-bot/challenge page')
    price,method=parse_price(soup,shop)
    if price is None: raise RuntimeError('price not found (JS-rendered, changed markup, or blocked)')
    return price,title,method

def main():
    products=load(ROOT/'products.json',[])
    if not isinstance(products,list): raise ValueError('products.json must contain a list')
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    history=load(DATA/'history.json',[])
    if not isinstance(history,list):history=[]
    results=[]; attempted=0; succeeded=0
    for product in products[:100]:
        if not product.get('enabled',True):continue
        links=product.get('links') or {}
        for shop in PLATFORMS:
            url=links.get(shop)
            if not url:continue
            attempted+=1
            result={'time':now,'product_id':product['id'],'shop':shop,'url':url,'status':'error','price':None,'error':None}
            try:
                price,title,method=fetch_price(url,shop)
                result.update(status='ok',price=price,title=title,method=method,error=None)
                history.append({'time':now,'product_id':product['id'],'shop':shop,'price':price})
                succeeded+=1
                print(f"OK {product['name']} {shop}: EUR {price:.2f} ({method})",flush=True)
            except Exception as exc:
                result['error']=str(exc)[:240]
                print(f"FAIL {product['name']} {shop}: {result['error']}",flush=True)
            results.append(result)
            time.sleep(0.4+random.random()*0.5)
    cutoff=datetime.now(timezone.utc)-timedelta(days=MAX_HISTORY_DAYS)
    history=[x for x in history if isinstance(x,dict) and x.get('time','')>=cutoff.isoformat()]
    write(DATA/'products.json',products)
    write(DATA/'latest.json',{'generated_at':now,'attempted':attempted,'succeeded':succeeded,'results':results})
    write(DATA/'history.json',history)
    print(f'Finished: {attempted} attempted, {succeeded} succeeded, {attempted-succeeded} failed',flush=True)
    # Make failure explicit in GitHub Actions, but commit diagnostics first via workflow `if: always()`.
    if attempted and succeeded==0:
        print('ERROR: all configured shop scrapes failed',file=sys.stderr)
        return 2
    return 0

if __name__=='__main__':sys.exit(main())
