#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İkiler B2B → Supabase IKILER_FILTRON (FILTRON)
=============================================================
AŞAMA 1: İkiler B2B'den tüm FILTRON ürünlerini çek → Supabase'e yaz
AŞAMA 2: Supabase'deki mann_url boş olan FILTRON kodlarını
          filtron.eu sitesinden requests+BeautifulSoup ile ara
          → URL + görsel çek → Supabase'i güncelle

Kullanım : python3 ikiler_filtron_supabase_full.py
cookie.txt: script ile aynı dizinde olmalı
"""

import requests
import os
import re
import time
from datetime import datetime, timezone
from bs4 import BeautifulSoup

# ─── AYARLAR ────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(SCRIPT_DIR, 'cookie.txt')

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lrjphkajdkipwjizzxsc.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY", "")
TABLO        = "IKILER_FILTRON"
MARKA        = "FILTRON"
IKILER_URL   = "https://b4b.ikilerotomotiv.com/Search/SearchProduct"

BATCH_SIZE   = 50
MAX_IMG      = 3
SLEEP_IKILER = 0.2
SLEEP_SCRAPE = 0.3

UA_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept":          "*/*",
}

# İstenmeyen ürün adları
BANNED_NAMES = ['KURUTUCU', 'SU FİLTRE', 'SU FILTRE', 'SU FİLTRESİ']
# ────────────────────────────────────────────────────────────


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ══════════════════════════════════════════════════════════════

def clean_code(code_str):
    """FILTRON ön ekini temizler. YD.FILTRON OE648/7 → OE648/7"""
    if not code_str:
        return ''
    cleaned = re.sub(r'^(YD\.|YD\s)?FILTRON[\.\s]*', '', code_str.strip(), flags=re.IGNORECASE)
    return cleaned.strip()

def to_sku(kod):
    """Boşluk/nokta/slash/tire kaldır → büyük harf"""
    return re.sub(r'[\s\.\/\-]', '', kod).upper()

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
    except Exception:
        return 0.0

def get_warehouse_name(raw):
    if not raw:
        return ''
    u = raw.upper()
    if 'Y.PARÇA' in u or 'Y.PARCA' in u:
        return 'DENİZLİ MERKEZ'
    if 'DENİZLİ' in u or 'DENIZLI' in u:
        return 'DENİZLİ ÇARDAK'
    return raw

def parse_filter_type(product_name):
    name_upper = product_name.upper()
    if 'YAĞ' in name_upper or 'YAG' in name_upper:
        return 'Yağ Filtresi'
    if 'HAVA' in name_upper:
        return 'Hava Filtresi'
    if 'YAKIT' in name_upper or 'MAZOT' in name_upper or 'BENZİN' in name_upper or 'DIESEL' in name_upper:
        return 'Yakıt Filtresi'
    if 'POLEN' in name_upper or 'KABİN' in name_upper:
        return 'Kabin Hava Filtresi'
    if 'ŞANZIMAN' in name_upper:
        return 'Şanzıman Filtresi'
    return 'Filtre'

def is_banned(name):
    nu = (name or '').upper()
    for b in BANNED_NAMES:
        if b in nu:
            return True
    return False


# ══════════════════════════════════════════════════════════════
# SUPABASE YARDIMCILARI
# ══════════════════════════════════════════════════════════════

def supabase_upsert(rows, supa):
    if not rows:
        return True
    try:
        resp = supa.post(
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

def supabase_get_empty_urls(supa):
    """mann_url boş olan FILTRON ürünlerini sayfalayarak çeker"""
    all_rows = []
    page_size = 1000
    offset = 0

    while True:
        try:
            resp = supa.get(
                f"{SUPABASE_URL}/rest/v1/{TABLO}",
                params={
                    'select': 'sku,kod',
                    'marka':  f'eq.{MARKA}',
                    'or':     '(mann_url.is.null,mann_url.eq.)',
                    'limit':  page_size,
                    'offset': offset,
                },
                headers={
                    'apikey':        SUPABASE_KEY,
                    'Authorization': f'Bearer {SUPABASE_KEY}',
                },
                timeout=30
            )
            if resp.status_code == 200:
                batch = resp.json()
                if not batch:
                    break
                all_rows.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
            else:
                log(f"❌ Supabase sorgu hatası {resp.status_code}: {resp.text[:200]}")
                break
        except Exception as e:
            log(f"❌ Supabase bağlantı hatası: {e}")
            break

    log(f"📋 Toplam {len(all_rows)} ürün bulundu (mann_url boş)")
    return all_rows

def supabase_update_img(sku, url, imgs, supa):
    """Ürünün mann_url ve img kolonlarını günceller"""
    payload = {
        'mann_url':          url,
        'img_url_1':         imgs[0] if len(imgs) > 0 else '',
        'img_url_2':         imgs[1] if len(imgs) > 1 else '',
        'img_url_3':         imgs[2] if len(imgs) > 2 else '',
        'guncelleme_tarihi': datetime.now(timezone.utc).isoformat()
    }
    try:
        resp = supa.patch(
            f"{SUPABASE_URL}/rest/v1/{TABLO}",
            json=payload,
            params={'sku': f'eq.{sku}'},
            headers={
                'apikey':        SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Content-Type':  'application/json',
                'Prefer':        'return=minimal'
            },
            timeout=30
        )
        if resp.status_code in (200, 204):
            return True
        else:
            log(f"  ❌ Güncelleme hatası {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        log(f"  ❌ Güncelleme bağlantı hatası: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# FILTRON SİTESİ SCRAPER
# ══════════════════════════════════════════════════════════════

def build_filtron_url(kod):
    """
    Filtron URL'si oluşturur.
    OE 648/7 → https://filtron.eu/tr/filtreyi-bul/arama-sonuçları/urun.html/oe648/7_filtron.html
    Sadece boşluklar silinir, slash (/) ve diğer karakterler korunur.
    """
    url_code = kod.strip().lower().replace(' ', '')
    return f"https://filtron.eu/tr/filtreyi-bul/arama-sonuclar%C4%B1/urun.html/{url_code}_filtron.html"

def scrape_filtron_page(kod):
    """
    Filtron ürün sayfasını çeker.
    Döndürür: (url, [img_url_1, img_url_2, img_url_3])
    Bulunamazsa: ('', [])
    """
    url = build_filtron_url(kod)

    try:
        r = requests.get(url, headers=UA_HEADERS, timeout=20)

        if r.status_code == 404:
            log(f"  ⚠️  404 → {kod}")
            return '', []

        if r.status_code != 200:
            log(f"  ⚠️  HTTP {r.status_code} → {kod}")
            return '', []

        soup = BeautifulSoup(r.text, "html.parser")
        images = []

        # 1. ÖNCELİK: img taglarında scene7.com görselleri
        img_attrs = ['src', 'data-src', 'data-lazy-src', 'data-original', 'data-image']
        for img in soup.find_all("img"):
            for attr in img_attrs:
                src = img.get(attr, '').strip()
                if not src:
                    continue
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = "https://filtron.eu" + src
                if "scene7.com" in src.lower() and src not in images:
                    images.append(src)

        # 2. JavaScript içinde scene7 URL'leri
        if not images:
            for script in soup.find_all("script"):
                text = script.string or ""
                matches = re.findall(r'https?://[^"\s]*scene7\.com[^"\s]*', text)
                for m in matches:
                    clean = m.split('"')[0].split("'")[0]
                    if clean not in images:
                        images.append(clean)

        # 3. Tüm HTML içinde scene7 ara
        if not images:
            matches = re.findall(r'https?://[^"\s]*scene7\.com[^"\s]*', r.text)
            for m in matches:
                clean = m.split('"')[0].split("'")[0].split(')')[0].split(',')[0]
                if clean not in images:
                    images.append(clean)

        # 4. Fallback: filtron.eu ürün görselleri
        if not images:
            for img in soup.find_all("img"):
                for attr in img_attrs:
                    src = img.get(attr, '').strip()
                    if not src:
                        continue
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = "https://filtron.eu" + src
                    if any(x in src.lower() for x in ['/assets/', '/uploads/', 'product', 'photo', 'filter']):
                        if src not in images:
                            images.append(src)

        return url, images[:MAX_IMG]

    except Exception as e:
        log(f"  ❌ Scrape hatası [{kod}]: {type(e).__name__}: {e}")
        return '', []


# ══════════════════════════════════════════════════════════════
# AŞAMA 1: İKİLER B2B → SUPABASE
# ══════════════════════════════════════════════════════════════

def asama1_ikiler(supa):
    log("=" * 55)
    log(f"AŞAMA 1: İkiler B2B → Supabase | MARKA: {MARKA}")
    log("=" * 55)

    if not os.path.exists(COOKIE_FILE):
        log(f"❌ cookie.txt bulunamadı: {COOKIE_FILE}")
        return 0

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

    buffer     = []
    data_count = 0
    page_num   = 0
    total_ok   = 0
    total_skip = 0
    seen_skus  = set()

    log("\n🚀 Scrape başlıyor...\n")

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
        log(f"📄 Sayfa {page_num}: {batch_size} ürün | yazılan: {total_ok}")

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

            temiz_kod = clean_code(item.get('Code', ''))
            if not temiz_kod:
                total_skip += 1
                continue

            sku = to_sku(temiz_kod)
            if sku in seen_skus:
                total_skip += 1
                continue
            seen_skus.add(sku)

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

            buffer.append({
                'sku':               sku,
                'kod':               temiz_kod,
                'marka':             item.get('Manufacturer', MARKA),
                'kategori':          parse_filter_type(name),
                'fiyat':             parse_price(son_fiyat),
                'depo_merkezi':      ' | '.join(depo_isimleri) if depo_isimleri else 'Stok Yok',
                'toplam_stok':       toplam_stok,
                'mann_url':          '',
                'img_url_1':         '',
                'img_url_2':         '',
                'img_url_3':         '',
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

        time.sleep(SLEEP_IKILER)

    if buffer:
        supabase_upsert(buffer, supa)
        total_ok += len(buffer)

    log(f"\n✅ AŞAMA 1 TAMAMLANDI → {total_ok} ürün yazıldı | {total_skip} atlandı")
    return total_ok


# ══════════════════════════════════════════════════════════════
# AŞAMA 2: FILTRON.EU → URL + GÖRSEL
# ══════════════════════════════════════════════════════════════

def asama2_images(supa):
    log("\n" + "=" * 55)
    log("AŞAMA 2: filtron.eu → URL + Görsel")
    log("=" * 55)

    rows = supabase_get_empty_urls(supa)
    if not rows:
        log("✅ Tüm ürünlerin URL'si zaten dolu, atlanıyor.")
        return 0

    log(f"📋 {len(rows)} ürün için URL + görsel çekilecek\n")

    ok = 0
    no = 0
    cache = {}

    for idx, row in enumerate(rows, 1):
        sku = row['sku']
        kod = row['kod']

        log(f"[{idx}/{len(rows)}] 🔍 {kod}")

        # Cache kontrolü
        if kod in cache:
            url, imgs = cache[kod]
            log(f"  [CACHE] url={'VAR' if url else 'YOK'} | imgs={len(imgs)}")
            if url:
                supabase_update_img(sku, url, imgs, supa)
                ok += 1
            else:
                no += 1
            time.sleep(0.05)
            continue

        url, imgs = scrape_filtron_page(kod)
        cache[kod] = (url, imgs)

        if url:
            supabase_update_img(sku, url, imgs, supa)
            ok += 1
            log(f"  ✅ TAMAM | sku={sku} | imgs={len(imgs)}")
        else:
            no += 1
            log(f"  ❌ Bulunamadı → {kod}")

        if ok % 10 == 0 and ok > 0:
            log(f"  📊 OK={ok} | Bulunamadı={no}")

        time.sleep(SLEEP_SCRAPE)

    log(f"\n✅ AŞAMA 2 TAMAMLANDI → OK={ok} | Bulunamadı={no}")
    return ok


# ══════════════════════════════════════════════════════════════
# ANA PROGRAM
# ══════════════════════════════════════════════════════════════

def main():
    log("=" * 55)
    log("İKİLER FILTRON FULL SYNC v1.0")
    log(f"Başlangıç: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 55)

    supa = requests.Session()

    # AŞAMA 1: Fiyat + Stok (atla)
    toplam1 = 0
    # toplam1 = asama1_ikiler(supa)

    # AŞAMA 2: URL + Görsel
    toplam2 = asama2_images(supa)

    log("\n" + "=" * 55)
    log("🏁 TÜM İŞLEMLER TAMAMLANDI")
    log(f"   Aşama 1 (fiyat/stok)  : {toplam1} ürün")
    log(f"   Aşama 2 (görsel/url)  : {toplam2} ürün güncellendi")
    log(f"   Bitiş: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 55)


if __name__ == '__main__':
    main()