import csv
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'data' / 'prices.sqlite3'
CSV = ROOT / 'docs' / 'prices.csv'
STATUS = ROOT / 'docs' / 'status.json'
PRODUCTS = ROOT / 'products.json'


def valid_url(url):
    host = (urlparse(url).hostname or '').lower()
    return urlparse(url).scheme == 'https' and any(host == d or host.endswith('.'+d) for d in ('mediamarkt.de','amazon.de','otto.de'))


def euro_number(value):
    if isinstance(value, (float, int)):
        n = float(value)
    elif isinstance(value, str):
        s = value.strip().replace('\u00a0', '').replace('€', '').replace('EUR', '').replace(' ', '')
        s = re.sub(r'[^\d,.]', '', s)
        if not s:
            return None
        if ',' in s:
            s = s.replace('.', '').replace(',', '.')
        elif s.count('.') > 1:
            s = s.replace('.', '')
        elif re.fullmatch(r'\d{1,3}\.\d{3}', s):
            s = s.replace('.', '')
        try:
            n = float(s)
        except ValueError:
            return None
    else:
        return None
    return round(n, 2) if 0.01 <= n <= 1000000 else None


def walk_json(obj):
    if isinstance(obj, list):
        for x in obj:
            yield from walk_json(x)
    elif isinstance(obj, dict):
        if obj.get('@type') in ('Product', 'Offer', 'AggregateOffer') or 'offers' in obj:
            if 'price' in obj:
                yield obj['price']
            if 'lowPrice' in obj:
                yield obj['lowPrice']
            if 'offers' in obj:
                yield from walk_json(obj['offers'])
        for key in ('@graph', 'mainEntity'):
            if key in obj:
                yield from walk_json(obj[key])


def extract_price(html):
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            for raw in walk_json(json.loads(script.string or script.get_text())):
                price = euro_number(raw)
                if price is not None:
                    return price, 'json-ld'
        except (ValueError, TypeError):
            continue
    for selector in ('meta[property="product:price:amount"]', 'meta[itemprop="price"]', '[itemprop="price"][content]'):
        el = soup.select_one(selector)
        if el:
            price = euro_number(el.get('content'))
            if price is not None:
                return price, 'meta'
    return None, 'unavailable'



def extract_amazon_buybox(html):
    """Only accept a NEW item in the main Buy Box sold by Amazon itself.

    Fail closed on unknown layouts or conflicting seller signals.
    """
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.get_text(' ', strip=True).lower()
    if any(x in title for x in ('captcha', 'robot check', 'geben sie die angezeigten zeichen ein')):
        raise ValueError('amazon_blocked')
    buybox = soup.select_one('#desktop_buybox, #buybox, #mobile_buybox')
    if buybox is None:
        raise ValueError('amazon_buybox_missing')
    seller = buybox.select_one('#sellerProfileTriggerId, #merchantInfo, #tabular-buybox-text-merchant-info, #merchant-info')
    if seller is None:
        raise ValueError('seller_unverified')
    seller_text = seller.get_text(' ', strip=True).lower()
    seller_link = seller.get('href', '')
    # Amazon itself normally has no third-party seller profile link.
    if seller_link and ('seller=' in seller_link or '/sp?' in seller_link):
        raise ValueError('seller_not_amazon')
    if not re.search(r'(verkauf|verkäufer|sold)\s*(durch|von|by)\s*amazon(?:\.de|\s*eu)?\b|^amazon(?:\.de|\s*eu)?$', seller_text):
        raise ValueError('seller_unverified' if 'amazon' in seller_text else 'seller_not_amazon')
    condition = buybox.select_one('#condition, #buyingOptionSelected, #newAccordionRow, #usedAccordionRow')
    if condition:
        condition_text = condition.get_text(' ', strip=True).lower()
        if any(x in condition_text for x in ('gebraucht', 'renewed', 'generalüberholt', 'refurbished', 'used')):
            raise ValueError('not_new')
    price_element = buybox.select_one('.a-price .a-offscreen, #price_inside_buybox, #buyBoxInner .a-price .a-offscreen')
    if not price_element:
        raise ValueError('amazon_buybox_price_missing')
    price = euro_number(price_element.get_text(' ', strip=True))
    if price is None:
        raise ValueError('amazon_buybox_price_invalid')
    return price, 'amazon-buybox-sold-by-amazon'

def fetch(product):
    if not valid_url(product['url']):
        raise ValueError('Only HTTPS MediaMarkt, Amazon.de and OTTO.de URLs are accepted')
    response = requests.get(product['url'], timeout=25, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; PersonalPriceMonitor/1.0)',
        'Accept-Language': 'de-DE,de;q=0.9',
        'Accept': 'text/html,application/xhtml+xml',
    })
    response.raise_for_status()
    price, source = (extract_amazon_buybox(response.text) if product.get('shop') == 'amazon' else extract_price(response.text))
    if price is None:
        raise ValueError('No reliable product price found (site may block automated access)')
    return price, source


def main():
    groups = json.loads(PRODUCTS.read_text(encoding='utf-8'))
    if len(groups) > 100:
        raise ValueError('Maximum 100 product groups supported')
    group_ids = [g['id'] for g in groups]
    if len(group_ids) != len(set(group_ids)):
        raise ValueError('Duplicate group IDs')
    products = []
    for group in groups:
        for shop, url in group.get('links', {}).items():
            if shop not in ('mediamarkt', 'amazon', 'otto'):
                raise ValueError('Unknown shop: '+shop)
            if url:
                products.append(dict(id=group['id']+'__'+shop, group_id=group['id'], shop=shop, name=group['name'], url=url, enabled=group.get('enabled', True), target_price=group.get('target_price')))
    ids = set()
    for p in products:
        if not all(k in p for k in ('id', 'name', 'url')) or not re.fullmatch(r'[a-zA-Z0-9_-]+', p['id']):
            raise ValueError('Each product requires a safe id, name and URL')
        if p['id'] in ids:
            raise ValueError('Duplicate product ID: ' + p['id'])
        ids.add(p['id'])
    DB.parent.mkdir(exist_ok=True, parents=True)
    CSV.parent.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(DB)
    conn.execute('CREATE TABLE IF NOT EXISTS observations (id INTEGER PRIMARY KEY, product_id TEXT NOT NULL, checked_at TEXT NOT NULL, price REAL NOT NULL, source TEXT NOT NULL)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_product_time ON observations(product_id, checked_at)')
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    status = {'checked_at': now, 'groups': groups, 'products': []}
    failures = 0
    for p in products:
        item = {k: p.get(k) for k in ('id', 'group_id', 'shop', 'name', 'url', 'target_price', 'enabled')}
        if not p.get('enabled', True):
            item['status'] = 'disabled'
        else:
            try:
                price, source = fetch(p)
                conn.execute('INSERT INTO observations(product_id, checked_at, price, source) VALUES (?, ?, ?, ?)', (p['id'], now, price, source))
                conn.commit()
                item.update(status='ok', price=price, source=source)
                if p.get('target_price') is not None and price <= float(p['target_price']):
                    item['alert'] = True
                    print(f"::warning title=Price alert::{p['name']} is now €{price:.2f}")
            except (requests.RequestException, ValueError, KeyError) as exc:
                item.update(status='error', error=str(exc)[:200])
                failures += 1
        status['products'].append(item)
        print(f"{p['id']}: {item['status']} {item.get('price', '')}")
        time.sleep(2)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    with CSV.open('w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['product_id', 'checked_at', 'price_eur', 'source'])
        writer.writerows(conn.execute('SELECT product_id, checked_at, price, source FROM observations ORDER BY checked_at ASC, id ASC'))
    conn.close()
    print(f'Finished: {len(products)} configured, {failures} failed')
    # Failed fetches are reported in the dashboard, but do not prevent history publication.
    return 0


if __name__ == '__main__':
    sys.exit(main())
