#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İkiler B2B → Supabase IKILER_MANN
Marka: MANN-FILTER
Kullanım : python3 ikiler_mann_supabase_fiyat_stok.py
cookie.txt: script ile aynı dizinde olmalı
"""

import requests
import json
import os
import re
import time
from datetime import datetime, timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─── AYARLAR ────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE  = os.path.join(SCRIPT_DIR, 'cookie.txt')

# Supabase proje ayarları ortam değişkenlerinden okunur; secret key dosyaya yazılmaz.
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lrjphkajdkipwjizzxsc.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY", "")
TABLO        = os.getenv("SUPABASE_TABLE", "IKILER_MANN")
MARKA        = "MANN-FILTER"
IKILER_URL   = "https://b4b.ikilerotomotiv.com/Search/SearchProduct"
BATCH_SIZE   = 50
MAX_PRODUCTS = int(os.getenv("MAX_PRODUCTS", "0"))  # 0 = stoklu ürünlerin tamamı
# ────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def configure_retries(session):
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(('POST',)),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session

def clean_price(text):
    if not text or not isinstance(text, str):
        return ''
    text = re.sub(r'<[^>]+>', '', text).replace('&nbsp;', ' ').strip()
    m = re.search(r'[\d]+[.,\d]*', text)
    return m.group(0) if m else ''

def parse_price(p):
    if not p:
        return 0.0
    p = p.strip()
    if ',' in p and '.' in p:
        p = p.replace('.', '').replace(',', '.') if p.index('.') < p.index(',') else p.replace(',', '')
    else:
        p = p.replace(',', '.')
    try:
        return float(p)
    except:
        return 0.0

def clean_mann_code(raw):
    """MANN kodunu normalize eder; boşluklu filtre kodunu korur."""
    if not raw:
        return ''
    k = raw.strip()
    # Kaynak örnekleri: "MANN-FILTER M.W 712/95", "MANN M.W 712/95".
    # Marka öneki kod alanından çıkarılır; marka kolonu ayrıca korunur.
    k = re.sub(r'^\s*(?:YD[.\s-]*)?(?:MANN[-\s]?FILTER|MANN)\s*', '', k, flags=re.IGNORECASE)
    k = re.sub(r'^\s*M\s*[.:\-]\s*', '', k, flags=re.IGNORECASE).strip()
    k = re.sub(r'\s+', ' ', k).strip()
    toks = k.split()
    if len(toks) >= 3 and toks[0].upper() == 'C' and toks[1].upper() == 'U' and toks[2].upper() == 'K':
        k = 'CUK ' + ' '.join(toks[3:])
    elif len(toks) >= 2 and toks[0].upper() == 'H' and toks[1].upper() == 'U':
        k = 'HU ' + ' '.join(toks[2:])
    elif len(toks) >= 2 and toks[0].upper() == 'W' and toks[1].upper() == 'K':
        k = 'WK ' + ' '.join(toks[2:])
    elif len(toks) >= 2 and toks[0].upper() == 'C' and toks[1].upper() == 'U':
        k = 'CU ' + ' '.join(toks[2:])
    return k.strip()

def to_sku(kod):
    return re.sub(r'[\s\.\/\-]', '', kod).upper()

def parse_filter_type(product_name):
    name_upper = product_name.upper()
    if 'YAĞ' in name_upper or 'YAG' in name_upper:
        return 'Yağ Filtresi'
    if 'HAVA' in name_upper:
        return 'Hava Filtresi'
    if 'YAKIT' in name_upper or 'MAZOT' in name_upper or 'BENZİN' in name_upper or 'DIESEL' in name_upper:
        return 'Yakıt Filtresi'
    if 'POLEN' in name_upper or 'KABİN' in name_upper:
        return 'Polen Filtresi'
    if 'ŞANZIMAN' in name_upper:
        return 'Şanzıman Filtresi'
    return 'Filtre'

BANNED_NAMES = ['SIVI CONTA', 'KOL YATAK STD', 'TEK STD', 'KURUTUCU', 'SU FİLTRE', 'SU FILTRE']
BANNED_PREFIXES = ['ACP', 'CR', 'AH']


def is_banned(product_name, code):
    name_upper = (product_name or '').upper()
    code_upper = (code or '').upper()
    if any(banned in name_upper for banned in BANNED_NAMES):
        return True
    if any(code_upper.startswith(prefix) for prefix in BANNED_PREFIXES):
        return True
    return False

def get_warehouse_name(raw):
    if not raw:
        return ''
    u = raw.upper()
    if 'Y.PARÇA' in u or 'Y.PARCA' in u:
        return 'DENİZLİ MERKEZ'
    if 'DENİZLİ' in u or 'DENIZLI' in u:
        return 'DENİZLİ ÇARDAK'
    return raw

def supabase_upsert(rows, session):
    if not rows:
        return True
    try:
        resp = session.post(
            f"{SUPABASE_URL}/rest/v1/{TABLO}",
            json=rows,
            headers={
                'apikey':        SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Content-Type':  'application/json',
                'Prefer':        'resolution=merge-duplicates'
            },
            timeout=30
        )
        if resp.status_code in (200, 201):
            log(f"  ✅ {len(rows)} satır Supabase'e yazıldı")
            return True
        else:
            log(f"  ❌ Supabase hata {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        log(f"  ❌ Supabase bağlantı hatası: {e}")
        return False

def main():
    log("=" * 50)
    log(f"İKİLER B2B → SUPABASE | MARKA: {MARKA}")
    log("=" * 50)

    if not SUPABASE_KEY:
        log("❌ SUPABASE_SECRET_KEY veya SUPABASE_KEY ortam değişkeni tanımlı değil")
        return

    if not os.path.exists(COOKIE_FILE):
        log(f"❌ cookie.txt bulunamadı: {COOKIE_FILE}")
        return
    with open(COOKIE_FILE, encoding='utf-8') as f:
        cookie = f.read().strip()
    log(f"✅ Cookie yüklendi ({len(cookie)} karakter)")

    ikiler = configure_retries(requests.Session())
    ikiler.headers.update({
        'Accept':       'application/json, text/plain, */*',
        'Content-Type': 'application/json;charset=UTF-8',
        'User-Agent':   'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Cookie':       cookie
    })
    supa = configure_retries(requests.Session())

    buffer     = []
    data_count = 0
    page_num   = 0
    total_ok   = 0
    total_skip = 0
    total_selected = 0

    log(f"\n🚀 Scrape başlıyor...\n")

    while True:
        page_num += 1

        try:
            resp = ikiler.post(IKILER_URL, json={
                "dataCount":         data_count,
                "manufacturer":      MARKA,
                "vehicleCategory":   None,
                "vehicleBrand":      None,
                "vehicleModel":      None,
                "productGroup1":     None,
                "productGroup2":     None,
                "productGroup3":     None,
                "campaign":          False,
                "newArrival":        False,
                "newProduct":        False,
                "comparsionProduct": False,
                # Yalnızca stokta olan ürünleri al.
                "onQuantity":        True,
                "onWay":             False,
                "isOem":             0,
                "isTop50":           False,
                "isCode":            0
            }, timeout=30)
            resp.raise_for_status()
            items = resp.json().get('ProductList', [])
        except Exception as e:
            log(f"❌ Sayfa {page_num} hata: {e}")
            break

        batch_size = len(items)
        log(f"📄 Sayfa {page_num}: {batch_size} ürün | toplam yazılan: {total_ok}")

        if batch_size == 0:
            log("Son sayfa — döngü bitti.")
            break

        limit_reached = False
        for item in items:
            mfr = (item.get('Manufacturer') or '').upper()
            if MARKA not in mfr:
                total_skip += 1
                continue

            name = item.get('Name', '')
            temiz_kod = clean_mann_code(item.get('Code', ''))
            if not temiz_kod:
                total_skip += 1
                continue

            if is_banned(name, temiz_kod):
                total_skip += 1
                continue

            kategori = parse_filter_type(name)

            raw_camp = clean_price(item.get('CampaignPriceCustomerStr', ''))
            raw_net  = clean_price(item.get('PriceNetCustomerStr', ''))
            raw_list = clean_price(item.get('PriceListStr', ''))

            if raw_camp and raw_camp not in ('0,00', '0'):
                son_fiyat = raw_camp
            elif raw_net and raw_net not in ('0,00', '0'):
                son_fiyat = raw_net
            else:
                son_fiyat = raw_list

            toplam_stok   = 0
            depo_isimleri = []
            for wh in item.get('WarehouseQuantity', []):
                qty = int(wh.get('Quantity', 0))
                toplam_stok += qty
                if qty > 0:
                    wh_name = get_warehouse_name((wh.get('Warehouse') or {}).get('Name', ''))
                    if wh_name not in depo_isimleri:
                        depo_isimleri.append(wh_name)

            # Yalnızca stoklu ürünler Supabase'e yazılır.
            if toplam_stok <= 0:
                total_skip += 1
                continue

            if MAX_PRODUCTS > 0 and total_selected >= MAX_PRODUCTS:
                limit_reached = True
                break

            buffer.append({
                'sku':               to_sku(temiz_kod),
                'kod':               temiz_kod,
                'marka':             item.get('Manufacturer', 'MANN-FILTER'),
                'kategori':          kategori,
                'fiyat':             parse_price(son_fiyat),
                'depo_merkezi':      ' | '.join(depo_isimleri) if depo_isimleri else 'Stok Yok',
                'toplam_stok':       toplam_stok,
                # Görsel ve katalog URL kolonları Aşama 02 tarafından korunur.
                'guncelleme_tarihi': datetime.now(timezone.utc).isoformat()
            })
            total_selected += 1

            if len(buffer) >= BATCH_SIZE:
                if supabase_upsert(buffer, supa):
                    total_ok += len(buffer)
                buffer = []

        if limit_reached or (MAX_PRODUCTS > 0 and total_selected >= MAX_PRODUCTS):
            log(f"Test ürün sınırına ulaşıldı: {MAX_PRODUCTS} stoklu ürün")
            break

        data_count += batch_size
        time.sleep(0.2)

    if buffer:
        if supabase_upsert(buffer, supa):
            total_ok += len(buffer)

    log("\n" + "=" * 50)
    log(f"✅ TAMAMLANDI")
    log(f"   Supabase'e yazılan : {total_ok} ürün")
    log(f"   Atlanan (filtre)   : {total_skip} ürün")
    log(f"   Zaman              : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 50)

if __name__ == '__main__':
    main()
