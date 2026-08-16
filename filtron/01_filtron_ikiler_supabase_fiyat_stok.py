#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İkiler B2B → Supabase IKILER_FILTRON
Marka: FILTRON
Kullanım : python3 ikiler_filtron_supabase.py
cookie.txt: script ile aynı dizinde olmalı
"""

import requests
import json
import os
import re
import time
from datetime import datetime, timezone

# ─── AYARLAR ────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE  = os.path.join(SCRIPT_DIR, 'cookie.txt')

# Supabase proje ayarları ortam değişkenlerinden okunur; secret key dosyaya yazılmaz.
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lrjphkajdkipwjizzxsc.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY", "")
TABLO        = os.getenv("SUPABASE_TABLE", "IKILER_FILTRON")
MARKA        = "FILTRON"
IKILER_URL   = "https://b4b.ikilerotomotiv.com/Search/SearchProduct"
BATCH_SIZE   = 50
# ────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

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

def clean_code(code_str, brand_name):
    """Kodun başındaki 'YD.FILTRON', 'FILTRON.' gibi ekleri siler."""
    if not code_str:
        return ''
    brand_escaped = re.escape(brand_name)
    pattern = rf'^(YD\.|YD\s)?{brand_escaped}[\.\s]*'
    cleaned = re.sub(pattern, '', code_str, flags=re.IGNORECASE)
    return cleaned.strip()

def to_sku(kod):
    return re.sub(r'[\s\.\/\-]', '', kod).upper()

def parse_filter_type(product_name):
    name_upper = product_name.upper()
    if 'YAĞ' in name_upper or 'YAG' in name_upper:
        return 'YAĞ FİLTRESİ'
    if 'HAVA' in name_upper:
        return 'HAVA FİLTRESİ'
    if 'YAKIT' in name_upper or 'MAZOT' in name_upper or 'BENZİN' in name_upper or 'DIESEL' in name_upper:
        return 'YAKIT FİLTRESİ'
    if 'POLEN' in name_upper or 'KABİN' in name_upper:
        return 'POLEN FİLTRESİ'
    if 'ŞANZIMAN' in name_upper:
        return 'ŞANZIMAN FİLTRESİ'
    return 'FİLTRE'

def is_banned(product_name):
    name_upper = product_name.upper()
    if 'KURUTUCU' in name_upper:
        return True
    if 'SU' in name_upper and 'FILTRE' in name_upper:
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

    ikiler = requests.Session()
    ikiler.headers.update({
        'Accept':       'application/json, text/plain, */*',
        'Content-Type': 'application/json;charset=UTF-8',
        'User-Agent':   'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Cookie':       cookie
    })
    supa = requests.Session()

    buffer     = []
    data_count = 0
    page_num   = 0
    total_ok   = 0
    total_skip = 0

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
                # Sıfır stokları da al; Supabase'teki eski pozitif stoklar sıfırlanabilsin.
                "onQuantity":        False,
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

        for item in items:
            mfr = (item.get('Manufacturer') or '').upper()
            if MARKA not in mfr:
                total_skip += 1
                continue

            name = item.get('Name', '')
            if is_banned(name):
                total_skip += 1
                continue

            temiz_kod = clean_code(item.get('Code', ''), MARKA)
            if not temiz_kod:
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

            # Sıfır stok ürünleri de yaz: Supabase'teki eski stok değeri temizlensin.
            if toplam_stok <= 0:
                depo_isimleri = []

            buffer.append({
                'sku':               to_sku(temiz_kod),
                'kod':               temiz_kod,
                'marka':             item.get('Manufacturer', 'FILTRON'),
                'kategori':          kategori,
                'fiyat':             parse_price(son_fiyat),
                'depo_merkezi':      ' | '.join(depo_isimleri) if depo_isimleri else 'Stok Yok',
                'toplam_stok':       toplam_stok,
                # Görsel ve katalog URL kolonları Aşama 02 tarafından korunur.
                'guncelleme_tarihi': datetime.now(timezone.utc).isoformat()
            })

            if len(buffer) >= BATCH_SIZE:
                supabase_upsert(buffer, supa)
                total_ok += len(buffer)
                buffer = []

        data_count += batch_size
        if batch_size < 24:
            log("Son sayfa tespit edildi (batch < 24).")
            break

        time.sleep(0.2)

    if buffer:
        supabase_upsert(buffer, supa)
        total_ok += len(buffer)

    log("\n" + "=" * 50)
    log(f"✅ TAMAMLANDI")
    log(f"   Supabase'e yazılan : {total_ok} ürün")
    log(f"   Atlanan (filtre)   : {total_skip} ürün")
    log(f"   Zaman              : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 50)

if __name__ == '__main__':
    main()