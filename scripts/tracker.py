import json, re, sys, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'docs/data'; DATA.mkdir(parents=True,exist_ok=True)
NOW=datetime.now(timezone.utc).isoformat(timespec='seconds')
SHOPS={'mediamarkt':'mediamarkt.de','amazon':'amazon.de','otto':'otto.de'}
HEADERS={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36','Accept-Language':'de-DE,de;q=0.9'}
def load(path,default):
 try:return json.loads(path.read_text(encoding='utf8'))
 except (OSError,ValueError):return default
def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def amount(v):
 if isinstance(v,(float,int)):return float(v) if 0<float(v)<1000000 else None
 if not isinstance(v,str):return None
 s=re.sub(r'[^0-9,.]','',v)
 if ',' in s and '.' in s:s=s.replace('.','').replace(',','.') if s.rfind(',')>s.rfind('.') else s.replace(',','')
 elif ',' in s:s=s.replace(',','.')
 try:return float(s) if 0<float(s)<1000000 else None
 except ValueError:return None
def offers(obj):
 if isinstance(obj,list):
  for x in obj:yield from offers(x)
 if isinstance(obj,dict):
  types=obj.get('@type',[]);types=[types] if isinstance(types,str) else types
  if any(t in ('Offer','AggregateOffer') for t in types) and obj.get('priceCurrency','EUR')=='EUR':
   p=amount(obj.get('price') or obj.get('lowPrice'))
   if p:yield p
  for key in ('@graph','offers','mainEntity'):
   if key in obj:yield from offers(obj[key])
def extract(html):
 soup=BeautifulSoup(html,'html.parser')
 for tag in soup.find_all('script',type='application/ld+json'):
  try:
   vals=list(offers(json.loads(tag.string or tag.get_text())))
   if vals:return vals[0]
  except (ValueError,TypeError):pass
 for selector in ('meta[property="product:price:amount"]','meta[property="og:price:amount"]','meta[itemprop="price"]','[itemprop="price"]'):
  for tag in soup.select(selector):
   v=amount(tag.get('content') or tag.get_text(' ',strip=True))
   if v:return v
 raise ValueError('No reliable structured EUR price found; page may require JavaScript or block bots')
def check(shop,url):
 domain=SHOPS[shop]; parsed=urlparse(url)
 if parsed.scheme!='https' or not (parsed.hostname==domain or (parsed.hostname or '').endswith('.'+domain)):raise ValueError('Invalid URL/domain')
 r=requests.get(url,headers=HEADERS,timeout=22);r.raise_for_status()
 host=urlparse(r.url).hostname or ''
 if not (host==domain or host.endswith('.'+domain)):raise ValueError('Redirected outside shop')
 if 'captcha' in r.url.lower():raise ValueError('CAPTCHA')
 return round(extract(r.text),2)
def main():
 products=load(ROOT/'products.json',[]);previous=load(DATA/'latest.json',{});history=load(DATA/'history.json',[])
 if not isinstance(products,list) or not isinstance(history,list):raise ValueError('Invalid data files')
 latest={};success=failed=configured=0
 for p in products:
  if p.get('enabled',True) is False:continue
  pid=p['id']; old=previous.get(pid,{}).get('shops',{});row={'name':p['name'],'updated_at':NOW,'shops':{}}
  for shop,url in p.get('links',{}).items():
   if shop not in SHOPS or not url:continue
   configured+=1;prev=old.get(shop,{}) if old.get(shop,{}).get('url')==url else {}
   state={'url':url,'price':prev.get('price'),'last_success':prev.get('last_success'),'checked_at':NOW}
   try:
    price=check(shop,url);state.update(status='ok',price=price,last_success=NOW)
    history.append({'time':NOW,'product_id':pid,'shop':shop,'price':price});success+=1
    print(f'{pid} {shop}: EUR {price:.2f}')
   except Exception as e:
    state.update(status='error',error=f'{type(e).__name__}: {str(e)[:200]}');failed+=1
    print(f'WARNING {pid} {shop}: {state["error"]}',file=sys.stderr)
   row['shops'][shop]=state;time.sleep(.3)
  latest[pid]=row
 cutoff=(datetime.now(timezone.utc)-timedelta(days=90)).isoformat()
 history=[x for x in history if isinstance(x,dict) and x.get('time','')>=cutoff]
 save(DATA/'products.json',products);save(DATA/'latest.json',latest);save(DATA/'history.json',history)
 print(f'Finished: {configured} configured, {success} succeeded, {failed} failed')
 return 1 if configured and not success else 0
if __name__=='__main__':sys.exit(main())
