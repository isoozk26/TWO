# -*- coding: utf-8 -*-

r"""
================================================================================
MANN FILTER SEO ENRICHER [V4.1 - MAHLE STYLE + JSON-LD]

INPUT: Supabase public.IKILER_MANN (MANN-FILTER ürünleri)
CROSS-REF: ufi_cross_referans_STABLE.csv
OUTPUT: Shopify ürün oluşturma/güncelleme

ÖZELLİKLER:
1) SKU INDEX - Shopify'dan tüm ürünleri çeker, SKU ile index yapar
2) HTML ŞABLON - MAHLE master template ile birebir aynı
3) DIŞ LİNKLER - Sadece MANN-FILTER (3 link → 1 link)
4) ŞASE NO - "Şase No ile Kontrol" (Şase/Marka-Model DEĞİL)
5) ETİKETLER - MANN, filtre tipi ve öncelikli eşdeğerler
6) EŞDEĞER BÖLÜMÜ - En fazla HENGST, BOSCH, MAHLE
7) STOK MANTIK - 0→0, 1→1, 2→2, 3→2, 4+→3
8) FİYAT - Supabase fiyatı × HTML PRICE_MULTIPLIER
9) BAŞLIK - 70 karaktere kadar, 1-3 araç
10) META - 160 karaktere kadar, MANN SEO şablonu
11) JSON-LD - custom.seo_structured_data metafield’ı

================================================================================
"""

import os
import json
import re
import time
import csv
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from openai import OpenAI


# =============================================================================
# CONFIG
# =============================================================================

SHOP_SUBDOMAIN = os.getenv("SHOP_SUBDOMAIN", "z42kyc-dt").strip()
STOREFRONT_DOMAIN = os.getenv("STOREFRONT_DOMAIN", "filtreoto.com").strip().rstrip("/")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN", "").strip()
API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01").strip()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lrjphkajdkipwjizzxsc.supabase.co").rstrip("/")
SUPABASE_KEY = (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY", "")).strip()
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "IKILER_MANN").strip()
SUPABASE_PAGE_SIZE = int(os.getenv("SUPABASE_PAGE_SIZE", "1000"))
SHOPIFY_VENDOR = os.getenv("SHOPIFY_VENDOR", "MANN").strip() or "MANN"
UFI_CROSS_REF_PATH = os.getenv("UFI_CROSS_REF_PATH", "ufi_cross_referans_STABLE.csv")

# HTML/ortam değişkeninden alınan fiyat çarpanı.
# 1.00 = Supabase fiyatını doğrudan kullanır; marka kuralı HTML'den değiştirilebilir.
PRICE_MULTIPLIER = float(os.getenv("PRICE_MULTIPLIER", "1.00"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Güvenli varsayılan: canlı Shopify yazması açıkça DRY_RUN=0 ile seçilir.
DRY_RUN = (os.getenv("DRY_RUN", "1") == "1")
CREATE_STATUS = os.getenv("CREATE_STATUS", "draft")
MAX_PRODUCTS = int(os.getenv("MAX_PRODUCTS", "0"))  # 0 = tüm Supabase kayıtları
RESUME_EXISTING = (os.getenv("RESUME_EXISTING", "0") == "1")

# Satır aralığı: START_ROW dahil, END_ROW hariç (Python slice gibi)
# Örnek: START_ROW=0 END_ROW=5  → 0,1,2,3,4 (5 ürün)
# Örnek: START_ROW=5 END_ROW=10 → 5,6,7,8,9 (5 ürün)
START_ROW = int(os.getenv("START_ROW", "0"))
END_ROW   = int(os.getenv("END_ROW",   "0"))   # 0 = sınır yok

WRITE_PRODUCT_TITLE = True
WRITE_BODY_HTML = True
WRITE_META = True
UPDATE_PRICE = True
UPDATE_TAGS = True
WRITE_SEO_STRUCTURED_METAFIELD = (os.getenv("WRITE_SEO_STRUCTURED_METAFIELD", "1") == "1")

TITLE_MAX_LEN = 70
BODY_MAX_TOTAL_MODELS = 160
BODY_MAX_MODELS_PER_BRAND = 25

SHOPIFY_SLEEP = float(os.getenv("SHOPIFY_SLEEP", "0.6"))
MANN_SLEEP = float(os.getenv("MANN_SLEEP", "0.2"))
OPENAI_SLEEP = float(os.getenv("OPENAI_SLEEP", "0.2"))

LOG_FILE = os.getenv("LOG_FILE", "mann_seo_debug.log")
FAILED_FILE = os.getenv("FAILED_FILE", "mann_failed.json")

UA_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept": "*/*",
}

# Shopify Collection Brands (Verilen liste + normalizasyon)
COLLECTION_BRANDS = {
    "ALFA ROMEO": "Alfa Romeo",
    "AUDI": "Audi",
    "BMW": "BMW",
    "CHEVROLET": "Chevrolet",
    "CHEVROLET EUROPE": "Chevrolet",
    "CHRYSLER": "Chrysler",
    "CITROEN": "Citroen",
    "DAIHATSU": "Daihatsu",
    "DODGE": "Dodge",
    "DS AUTOMOBILES": "DS Automobiles",
    "FIAT": "Fiat",
    "FORD": "Ford",
    "FSO MOTOR": "FSO Motor",
    "GEELY": "Geely",
    "HYUNDAI": "Hyundai",
    "INNOCENTI": "Innocenti",
    "ISUZU": "Isuzu",
    "IVECO": "Iveco",
    "JAGUAR": "Jaguar",
    "KIA MOTORS": "KIA Motors",
    "LANCIA": "Lancia",
    "LEXUS": "Lexus",
    "LOTUS": "Lotus",
    "MAZDA": "Mazda",
    "MEGA": "Mega",
    "MERCEDES-BENZ": "Mercedes-Benz",
    "NISSAN": "Nissan",
    "OPEL": "Opel",
    "PEUGEOT": "Peugeot",
    "RAVON": "Ravon",
    "RENAULT": "Renault",
    "SEAT": "Seat",
    "SKODA": "Skoda",
    "SSANGYONG": "SsangYong",
    "SUZUKI": "Suzuki",
    "TOYOTA": "Toyota",
    "UZ-DAEWOO": "Uz-Daewoo",
    "VAUXHALL": "Vauxhall",
    "VAUXHALL-BEDFORD": "Vauxhall-Bedford",
    "VOLVO CARS": "Volvo Cars",
    "VW": "VW",
    "VOLKSWAGEN": "VW",  # VW'ye normalize
    "ZASTAVA": "Zastava",
}


# =============================================================================
# SHOPIFY COLLECTION FUNCTIONS (MEVCUT KOLEKSIYONLAR - YENİ OLUŞTURMA YOK)
# =============================================================================

def load_all_collections() -> Dict[str, int]:
    """
    Shopify'daki TÜM custom collection'ları yükle (sayfalama ile)
    Return: {"Kabin Hava Filtresi": 123456, "Mercedes-Benz": 234567, ...}
    """
    log("📁 Shopify koleksiyonları yükleniyor...")
    collections_map = {}
    since_id = 0
    try:
        while True:
            params = {"limit": 250, "since_id": since_id}
            data = shopify_get(f"{BASE}/custom_collections.json", params=params, timeout=30)
            if not data or not data.get("custom_collections"):
                break
            batch = data["custom_collections"]
            if not batch:
                break
            for coll in batch:
                title   = coll.get("title", "").strip()
                coll_id = coll.get("id")
                if title and coll_id:
                    collections_map[title] = int(coll_id)
            since_id = batch[-1]["id"]
            if len(batch) < 250:
                break
            time.sleep(0.3)
        log(f"✅ {len(collections_map)} koleksiyon yüklendi")
        for title in sorted(collections_map.keys()):
            log(f"  - {title} (ID: {collections_map[title]})")
        return collections_map
    except Exception as e:
        log(f"❌ Koleksiyonlar yüklenemedi: {e}", "ERROR")
        return {}


def add_product_to_collection_by_title(product_id: int, collection_title: str, collections_map: Dict[str, int]) -> bool:
    """
    Ürünü koleksiyona ekle (koleksiyon title ile)

    Args:
        product_id: Shopify product ID
        collection_title: "Kabin Hava Filtresi", "Mercedes-Benz" vb.
        collections_map: load_all_collections() ile yüklenen map

    Return: True/False
    """
    if not product_id or not collection_title:
        return False

    # Koleksiyon ID'sini bul
    collection_id = collections_map.get(collection_title)

    if not collection_id:
        # Koleksiyon bulunamadı
        return False

    # Zaten ekliyse skip
    params = {"product_id": product_id, "collection_id": collection_id}
    data = shopify_get(f"{BASE}/collects.json", params=params, timeout=25)

    if data and data.get("collects"):
        return True  # Zaten ekli

    # Ekle
    if DRY_RUN:
        log(f"  [DRY_RUN] Koleksiyona eklenecek: {collection_title}")
        return True

    payload = {
        "collect": {
            "product_id": int(product_id),
            "collection_id": int(collection_id)
        }
    }

    ok, msg, _ = shopify_post(f"{BASE}/collects.json", payload, timeout=25)

    if not ok:
        log(f"  ❌ Koleksiyona eklenemedi ({collection_title}): {msg}", "ERROR")
        return False

    return True


def add_product_to_collections(
    product_id: int,
    filter_type: str,
    vehicles: Dict[str, List[str]],
    collections_map: Dict[str, int]
) -> None:
    """
    Ürünü uygun koleksiyonlara ekle

    1. Filtre tipine göre (Hava Filtresi, Yağ Filtresi, vb.)
    2. Araç markalarına göre (Mercedes-Benz, Audi, vb.)

    Args:
        product_id: Shopify product ID
        filter_type: "Hava filtresi", "Yağ filtresi", vb.
        vehicles: {"AUDI": [...], "BMW": [...]}
        collections_map: Mevcut koleksiyonlar
    """
    added_count = 0

    # 1. FİLTRE TİPİ KOLEKSİYONU
    if filter_type:
        # Normalize et
        filter_normalized = filter_type.strip()

        # Olası koleksiyon isimleri
        possible_names = [
            filter_normalized,  # "Hava filtresi"
            filter_normalized.title(),  # "Hava Filtresi"
            f"{filter_normalized.title()}",  # Tam eşleşme
        ]

        # Kabin hava filtresi özel durumu
        if "polen" in filter_normalized.lower() or "kabin" in filter_normalized.lower():
            possible_names.append("Kabin Hava Filtresi")

        for coll_name in possible_names:
            if coll_name in collections_map:
                if add_product_to_collection_by_title(product_id, coll_name, collections_map):
                    log(f"  ✓ Koleksiyona eklendi: {coll_name}")
                    added_count += 1
                    time.sleep(0.2)
                break

    # 2. ARAÇ MARKA KOLEKSİYONLARI
    if vehicles:
        for brand_raw in vehicles.keys():
            brand_upper = brand_raw.upper().strip()
            brand_normalized = format_brand_title_case(brand_raw)

            # Olası koleksiyon isimleri - geniş liste
            possible_names = [
                brand_raw,                   # "MERCEDES-BENZ"
                brand_normalized,            # "Mercedes-Benz"
                brand_raw.title(),           # "Mercedes-Benz"
                brand_raw.capitalize(),      # "Mercedes-benz"
            ]

            # Özel durum eşlemeleri
            BRAND_ALIASES = {
                "VW":               ["VW", "Volkswagen"],
                "VOLKSWAGEN":       ["VW", "Volkswagen"],
                "MERCEDES-BENZ":    ["Mercedes-Benz", "Mercedes Benz", "Mercedes"],
                "SSANGYONG":        ["SsangYong", "Ssangyong", "SSANGYONG"],
                "KIA MOTORS":       ["KIA Motors", "Kia Motors", "KIA", "Kia"],
                "LANDROVER":        ["Land Rover", "LandRover", "Landrover"],
                "LAND ROVER":       ["Land Rover", "LandRover"],
                "VOLVO CARS":       ["Volvo Cars", "Volvo"],
                "ROLLS-ROYCE":      ["Rolls-Royce", "Rolls Royce"],
                "BMW ALPINA":       ["BMW Alpina", "Alpina"],
                "DS AUTOMOBILES":   ["DS Automobiles", "DS"],
                "CHEVROLET EUROPE": ["Chevrolet"],
                "FSO MOTOR":        ["FSO Motor", "FSO"],
                "UZ-DAEWOO":        ["Uz-Daewoo", "Uz Daewoo"],
                "VAUXHALL-BEDFORD": ["Vauxhall-Bedford", "Vauxhall Bedford"],
            }

            if brand_upper in BRAND_ALIASES:
                possible_names.extend(BRAND_ALIASES[brand_upper])

            # Deduplicate koruyarak sırala
            seen_p = set()
            unique_names = []
            for n in possible_names:
                if n and n not in seen_p:
                    seen_p.add(n)
                    unique_names.append(n)

            matched = False
            for coll_name in unique_names:
                if coll_name in collections_map:
                    if add_product_to_collection_by_title(product_id, coll_name, collections_map):
                        log(f"  ✓ Koleksiyona eklendi: {coll_name} (kaynak={brand_raw})")
                        added_count += 1
                        time.sleep(0.2)
                    matched = True
                    break

            if not matched:
                log(f"  ⚠ Koleksiyon bulunamadı: {brand_raw} → denendi={unique_names[:4]}", "WARN")

    if added_count > 0:
        log(f"  ✅ Toplam {added_count} koleksiyona eklendi")
    else:
        log(f"  ⚠ Hiçbir araç koleksiyonuna eklenemedi", "WARN")


# =============================================================================
# ALLOWED VEHICLE BRANDS (MANN API için)
# =============================================================================

ALLOWED_VEHICLE_BRANDS = {
    "ALFA ROMEO", "ARO", "ASKAM", "ASTON", "AUDI", "BELLIER", "BENTLEY", "BESTURN",
    "BMW", "BMW ALPINA", "BOGDAN", "BRILLANCE", "BUICK", "BYD", "CADILLAC", "CHANGAN",
    "CHERY", "CHEVROLET", "CHEVROLET EUROPE", "CHRYSLER", "CITROEN", "CUPRA", "DACIA",
    "DAEWOO", "DAIHATSU", "DATSUN", "DERWAYS", "DODGE", "DS AUTOMOBILES", "ELARIS",
    "EXEED", "FERRARI", "FIAT", "FORD", "FSD", "FSM", "FSO MOTOR", "GEELY",
    "GENERAL MOTORS", "GENESIS", "GREAT WALL", "GRECAV", "HAFEI", "HAVAL", "HOLDEN",
    "HONDA", "HYUNDAI", "INFINITI", "INNOCENTI", "ISUZU", "IVECO", "IZH", "JAC",
    "JAGUAR", "JEEP", "KIA MOTORS", "KTM", "LADA", "LAMBORGHINI", "LANCIA", "LANDROVER",
    "LDV", "LEXUS", "LIGIER", "LOONDON TAXI INTERNATIONAL", "LOTUS", "MASERATI", "MAZDA",
    "MEGA", "MERCEDES-BENZ", "MG", "MICROCAR", "MINI", "MITSUBISHI", "MORGAN", "NISSAN",
    "OLDSMOBILE", "OPEL", "PERODUA", "PEUGEOT", "PIAGGIO", "PONTIAC", "PORSCHE", "PROTON",
    "RAVON", "RENAULT", "ROLLS-ROYCE", "ROVER", "SAAB", "SANTANA", "SATURN", "SEAT",
    "SKODA", "SMART", "SSANGYONG", "SUBARU", "SUZUKI", "TAGAZ", "TATA", "TESLA",
    "TOYOTA", "UAZ", "UZ-DAEWOO", "VAUXHALL", "VAUXHALL-BEDFORD", "VOLGA", "VOLVO CARS",
    "VW", "WIESMANN", "ZASTAVA", "ZAZ",
}


# =============================================================================
# LOGGING
# =============================================================================

def log(msg: str, level: str = "INFO") -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except Exception:
        pass


# =============================================================================
# ENV CHECK
# =============================================================================

if not SHOPIFY_TOKEN:
    log("❌ SHOPIFY_TOKEN boş!", "ERROR")
    raise SystemExit(1)

if not OPENAI_API_KEY:
    log("❌ OPENAI_API_KEY boş!", "ERROR")
    raise SystemExit(1)

BASE = f"https://{SHOP_SUBDOMAIN}.myshopify.com/admin/api/{API_VERSION}"
HEADERS = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

client = OpenAI(api_key=OPENAI_API_KEY)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def normalize_sku(sku: str) -> str:
    if not sku:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(sku).upper().strip())


def slugify_tr(text: str) -> str:
    tr_map = {
        'ı': 'i', 'İ': 'i', 'ğ': 'g', 'Ğ': 'g', 'ü': 'u', 'Ü': 'u',
        'ş': 's', 'Ş': 's', 'ö': 'o', 'Ö': 'o', 'ç': 'c', 'Ç': 'c',
    }
    for tr_char, en_char in tr_map.items():
        text = text.replace(tr_char, en_char)

    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


def parse_price(price_str: str) -> float:
    if not price_str:
        return 0.0
    try:
        cleaned = str(price_str).replace('.', '').replace(',', '.')
        return float(cleaned)
    except:
        return 0.0


def format_brand_title_case(brand: str) -> str:
    brand = brand.strip()

    if "(" in brand:
        brand = brand.split("(")[0].strip()

    if "-" in brand:
        parts = brand.split("-")
        return "-".join(p.title() for p in parts)

    if " " in brand:
        return " ".join(p.title() for p in brand.split())

    if len(brand) <= 3 and brand.isupper():
        return brand

    return brand.title()


# =============================================================================
# UFI CROSS-REFERENCE
# =============================================================================

def load_ufi_cross_reference() -> Dict[str, List[Dict[str, str]]]:
    log("📂 UFI cross-reference yükleniyor...")

    cross_ref_map = defaultdict(list)
    mann_master_map = {}

    try:
        with open(UFI_CROSS_REF_PATH, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            for row in reader:
                brand = row.get('Brand', '').strip()
                part_code = row.get('Part_Code', '').strip()
                master_id = row.get('Master_ID', '').strip()
                is_master = row.get('Is_Master', '').strip().upper()

                if brand in ['MANN+HUMMEL', 'MANN-FILTER'] and is_master == 'EVET':
                    mann_code_normalized = normalize_sku(part_code)
                    if master_id:
                        mann_master_map[master_id] = mann_code_normalized

                if master_id and is_master == 'HAYIR' and brand and part_code:
                    cross_ref_map[master_id].append({
                        'brand': brand,
                        'code': part_code
                    })

        final_map = defaultdict(list)
        for master_id, equivalents in cross_ref_map.items():
            mann_code = mann_master_map.get(master_id)
            if mann_code:
                final_map[mann_code] = equivalents

        log(f"✅ UFI cross-reference yüklendi: {len(final_map)} MANN kodu")
        return dict(final_map)

    except Exception as e:
        log(f"❌ UFI yüklenemedi: {e}", "ERROR")
        return {}


# =============================================================================
# SHOPIFY - SKU INDEX
# =============================================================================

def shopify_get(url: str, params: Optional[dict] = None, timeout: int = 25) -> Optional[dict]:
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
        if r.status_code != 200:
            log(f"Shopify GET {r.status_code}", "ERROR")
            return None
        return r.json()
    except Exception as e:
        log(f"Shopify GET error: {e}", "ERROR")
        return None


def shopify_post(url: str, payload: dict, timeout: int = 25) -> Tuple[bool, str, Optional[dict]]:
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=timeout)
        if r.status_code in (200, 201):
            return True, f"{r.status_code} OK", r.json()
        return False, f"{r.status_code}", None
    except Exception as e:
        return False, f"EXC {e}", None


def shopify_put(url: str, payload: dict, timeout: int = 25) -> Tuple[bool, str]:
    try:
        r = requests.put(url, headers=HEADERS, json=payload, timeout=timeout)
        if r.status_code == 200:
            return True, "200 OK"
        return False, f"{r.status_code}"
    except Exception as e:
        return False, f"EXC {e}"


def load_all_products_since_id(vendor: Optional[str] = SHOPIFY_VENDOR) -> List[dict]:
    """Shopify ürünlerini vendor kapsamıyla since_id pagination ile yükler."""
    all_products: List[dict] = []
    since_id = 0
    log(f"📦 Shopify {vendor} ürünleri yükleniyor (SKU index için)...")
    while True:
        params = {"limit": 250, "since_id": since_id}
        if vendor:
            params["vendor"] = vendor
        data = shopify_get(f"{BASE}/products.json", params=params, timeout=30)
        if not data:
            break
        products = data.get("products", [])
        if not products:
            break
        all_products.extend(products)
        since_id = products[-1]["id"]
        log(f"  ✓ +{len(products)} | Toplam: {len(all_products)}")
        time.sleep(0.35)
    log(f"✅ {len(all_products)} {vendor} ürünü yüklendi")
    return all_products


def build_sku_index(products: List[dict]) -> Dict[str, dict]:
    idx = {}
    for p in products:
        pid = p.get("id")
        title = p.get("title", "")

        for v in p.get("variants", []):
            raw_sku = v.get("sku")
            sku_norm = normalize_sku(raw_sku or "")

            if not sku_norm:
                continue

            if sku_norm not in idx:
                idx[sku_norm] = {
                    "product_id": int(pid),
                    "variant_id": int(v.get("id")),
                    "inventory_item_id": int(v.get("inventory_item_id")) if v.get("inventory_item_id") else None,
                    "title": title,
                }

    log(f"✅ SKU index: {len(idx)} SKU")
    return idx


def get_primary_location_id() -> Optional[int]:
    data = shopify_get(f"{BASE}/locations.json", timeout=25)
    if not data:
        return None

    locs = data.get("locations", [])
    for l in locs:
        if l.get("active", True):
            return int(l.get("id"))

    if locs:
        return int(locs[0].get("id"))

    return None


def set_inventory_available(inventory_item_id: int, location_id: int, available: int) -> bool:
    url = f"{BASE}/inventory_levels/set.json"
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": int(available),
    }

    if DRY_RUN:
        return True

    ok, msg, _ = shopify_post(url, payload, timeout=25)
    if not ok:
        log(f"Inventory set failed: {msg}", "ERROR")
    return ok


def create_product_mann(mann_code: str, title: str, filter_type: str, price: float, image_urls: List[str]) -> Optional[dict]:
    if DRY_RUN:
        return {
            "product": {
                "id": 999999,
                "variants": [{"id": 888888, "inventory_item_id": 777777}]
            }
        }

    images_payload = [{"src": url} for url in image_urls if url]

    payload = {
        "product": {
            "title": title,
            "vendor": "MANN",  # MANN-FILTER → MANN
            "product_type": filter_type or "Otomotiv Filtresi",
            "status": CREATE_STATUS,
            "images": images_payload[:10],
            "variants": [
                {
                    "sku": mann_code,
                    "price": f"{price:.2f}",
                    "inventory_management": "shopify",
                    "inventory_policy": "deny",
                }
            ]
        }
    }

    ok, msg, resp = shopify_post(f"{BASE}/products.json", payload, timeout=30)

    if not ok or not resp:
        log(f"❌ Product create failed: {msg}", "ERROR")
        return None

    return resp


def update_variant_price_sku(variant_id: int, sku: str, price: float) -> bool:
    if DRY_RUN:
        return True

    payload = {
        "variant": {
            "id": variant_id,
            "sku": sku,
            "price": f"{price:.2f}"
        }
    }

    ok, msg = shopify_put(f"{BASE}/variants/{variant_id}.json", payload, timeout=25)
    if not ok:
        log(f"Variant update failed: {msg}", "ERROR")
    return ok


def upsert_metafield(product_id: int, namespace: str, key: str, type_: str, value: str) -> bool:
    if DRY_RUN:
        return True

    payload = {
        "metafield": {
            "namespace": namespace,
            "key": key,
            "type": type_,
            "value": value
        }
    }

    url = f"{BASE}/products/{product_id}/metafields.json"
    ok, _, _ = shopify_post(url, payload)
    return ok


def update_product_images(product_id: int, image_urls: List[str]) -> bool:
    if not image_urls or DRY_RUN:
        return True

    data = shopify_get(f"{BASE}/products/{product_id}/images.json")
    if data and data.get('images'):
        for img in data['images']:
            requests.delete(f"{BASE}/products/{product_id}/images/{img['id']}.json", headers=HEADERS)

    for url in image_urls[:10]:
        if url and url.startswith('http'):
            payload = {"image": {"src": url}}
            shopify_post(f"{BASE}/products/{product_id}/images.json", payload)
            time.sleep(0.3)

    return True


def set_product_handle_safe(product_id: int, desired_handle: str, sku: str) -> bool:
    if DRY_RUN:
        return True

    base = slugify_tr(desired_handle)
    sku_suf = normalize_sku(sku).lower()

    candidates = [base, f"{base}-{sku_suf}", f"{base}-{sku_suf}-2"]

    for h in candidates:
        payload = {"product": {"id": int(product_id), "handle": h}}
        ok, msg = shopify_put(f"{BASE}/products/{product_id}.json", payload, timeout=25)

        if ok:
            log(f"  ✅ Handle: {h}")
            return True

        low = (msg or "").lower()
        if "handle" in low and ("taken" in low or "already been" in low):
            continue

        return False

    return False


# =============================================================================
# MANN API
# =============================================================================

def mann_scrape_fitment_from_url(mann_url: str) -> Dict[str, List[str]]:
    log(f"  🔍 MANN API: Araç bilgileri...")

    try:
        r = requests.get(mann_url, headers=UA_HEADERS, timeout=25)
        if r.status_code != 200:
            return {}
        html = r.text
    except:
        return {}

    soup = BeautifulSoup(html, "html.parser")

    def clean(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip())

    apps_head = None
    for tag in soup.find_all(["h2", "h3", "h4"]):
        t = clean(tag.get_text(" ", strip=True))
        if "Araçlar / Uygulamalar" in t or "Veicoli / Applicazioni" in t:
            apps_head = tag
            break

    if not apps_head:
        return {}

    stop_markers = ("OE Numaraları", "İndirilebilir Dosyalar", "Numeri OE", "Downloads")

    def normalize_brand_heading(txt: str) -> Optional[str]:
        s = clean(txt)
        if not s:
            return None
        up = s.upper()
        base = up.split("(")[0].strip() if "(" in up else up

        if up in ALLOWED_VEHICLE_BRANDS:
            return up
        if base in ALLOWED_VEHICLE_BRANDS:
            return base

        if "VOLKSWAGEN" in up or up.startswith("VW"):
            return "VW"
        if up == "VOLVO":
            return "VOLVO CARS"

        return None

    vehicles = defaultdict(list)
    current_brand = None
    seen = set()

    for tag in apps_head.find_all_next(["h2", "h3", "h4", "h5"]):
        t = clean(tag.get_text(" ", strip=True))
        if not t:
            continue
        if any(m in t for m in stop_markers):
            break

        norm_brand = normalize_brand_heading(t)
        if norm_brand:
            current_brand = norm_brand
            continue

        if current_brand:
            model = t.strip()
            key = (current_brand.lower(), model.lower())
            if key not in seen:
                seen.add(key)
                vehicles[current_brand].append(model)

    log(f"  ✓ {len(vehicles)} marka, {sum(len(v) for v in vehicles.values())} model")
    return dict(vehicles)


# =============================================================================
# TITLE & META BUILDERS
# =============================================================================

def shorten_brand_name(brand: str) -> str:
    brand_shortcuts = {
        "Mercedes-Benz": "Mercedes",
        "Volkswagen": "VW",
        "Alfa Romeo": "Alfa",
        "Chevrolet": "Chevy",
    }
    return brand_shortcuts.get(brand, brand)


def get_top_vehicles_for_title(vehicles: Dict[str, List[str]], limit: int = 3) -> List[Tuple[str, str]]:
    if not vehicles:
        return []

    brand_map = {
        "VW": "VW",
        "VOLKSWAGEN": "VW",
        "MERCEDES-BENZ": "Mercedes",
        "BMW": "BMW",
        "AUDI": "Audi",
        "FORD": "Ford",
        "VOLVO CARS": "Volvo",
        "OPEL": "Opel",
        "RENAULT": "Renault",
        "PEUGEOT": "Peugeot",
        "FIAT": "Fiat",
        "TOYOTA": "Toyota",
        "KIA MOTORS": "Kia",
    }

    sorted_brands = sorted(vehicles.items(), key=lambda x: len(x[1]), reverse=True)

    result = []
    for brand_raw, models in sorted_brands[:limit]:
        brand_short = brand_map.get(brand_raw, shorten_brand_name(format_brand_title_case(brand_raw)))

        if models:
            model = models[0]
            model_clean = model.split("(")[0].strip()
            model_short = model_clean[:15] if len(model_clean) > 15 else model_clean

            result.append((brand_short, model_short))

    return result


def make_mann_title(mann_code: str, filter_type: str, vehicles: Dict[str, List[str]], max_len: int = 70) -> str:
    type_map = {
        "Hava filtresi": "Hava Filtresi",
        "Yağ filtresi": "Yağ Filtresi",
        "Yakıt filtresi": "Yakıt Filtresi",
        "Polen filtresi": "Polen Filtresi",
    }
    type_full = type_map.get(filter_type, filter_type or "Filtre")

    base = f"MANN-FILTER {mann_code} {type_full}"

    top_vehicles = get_top_vehicles_for_title(vehicles, limit=3)

    if not top_vehicles:
        return base[:max_len]

    # STRATEJI 1: 3 Marka + Model
    if len(top_vehicles) >= 3:
        vehicle_text = f"{top_vehicles[0][0]} {top_vehicles[0][1]}, {top_vehicles[1][0]} {top_vehicles[1][1]}, {top_vehicles[2][0]} {top_vehicles[2][1]}"
        title = f"{base} | {vehicle_text}"
        if len(title) <= max_len:
            return title

    # STRATEJI 2: 2 Marka + Model
    if len(top_vehicles) >= 2:
        vehicle_text = f"{top_vehicles[0][0]} {top_vehicles[0][1]}, {top_vehicles[1][0]} {top_vehicles[1][1]}"
        title = f"{base} | {vehicle_text}"
        if len(title) <= max_len:
            return title

    # STRATEJI 3: 1 Marka + Model
    vehicle_text = f"{top_vehicles[0][0]} {top_vehicles[0][1]}"
    title = f"{base} | {vehicle_text}"
    if len(title) <= max_len:
        return title

    # STRATEJI 4: Sadece 1 Marka (Model kaldır) ← YENİ KURAL
    title = f"{base} | {top_vehicles[0][0]}"
    if len(title) <= max_len:
        return title

    # STRATEJI 5: 3 Marka (Model yok)
    if len(top_vehicles) >= 3:
        vehicle_text = f"{top_vehicles[0][0]}, {top_vehicles[1][0]}, {top_vehicles[2][0]}"
        title = f"{base} | {vehicle_text}"
        if len(title) <= max_len:
            return title

    # STRATEJI 6: 2 Marka (Model yok)
    if len(top_vehicles) >= 2:
        vehicle_text = f"{top_vehicles[0][0]}, {top_vehicles[1][0]}"
        title = f"{base} | {vehicle_text}"
        if len(title) <= max_len:
            return title

    # STRATEJI 7: Tip kısalt + 1 Marka
    type_short = type_full.replace(" Filtresi", "")
    base_short = f"MANN-FILTER {mann_code} {type_short}"
    title = f"{base_short} | {top_vehicles[0][0]}"
    if len(title) <= max_len:
        return title

    # Son çare: Sadece base
    return base[:max_len].rstrip(" -|/")


def build_meta_description_mann(mann_code: str, filter_type: str, vehicles: Dict[str, List[str]], index: int) -> str:
    """
    RANDOM meta templates - SADECE verilen 30 element
    Her ürün için 3-4 element random seçilir
    MİNİMUM 145 KARAKTER garantili
    KURAL: %100 ifadesi her metada maksimum 1 kez
    """
    import random

    # SADECE VERİLEN 30 ELEMENT - BAŞKA BİŞEY EKLEME!
    elements = [
        "📋 Şase No ile parça doğrulama",
        "🚚 48 Saatte kargoda",
        "✅ Yetkili distribütör faturalı",
        "📦 2-5 İş günü teslimat",
        "🔒 Güvenli ödeme sistemi",
        "📋 Şase No ile %100 tam uyum kontrolü",
        "✅ %100 Orijinal parça garantisi",
        "🔁 Kolay iade ve değişim garantisi",
        "🛡️ Yetkili distribütör güvencesiyle faturalı satış",
        "🚚 48 Saatte hızlı gönderim",
        "📋 Uzman ekipten şase no sorgulama desteği",
        "📦 Tahmini 2-5 iş günü içinde adrese teslimat",
        "✅ Orijinal kalite ve yüksek performans",
        "🔒 Güvenli ödeme altyapısı",
        "📋 Aracınıza özel parça teyidi",
        "🚚 48 Saatte kargoya teslim edilir",
        "✅ Sadece yetkili distribütör ürünleri",
        "📦 Şehir içi ve şehir dışı hızlı teslimat",
        "🔁 Koşulsuz iade garantisi",
        "📋 Yanlış parçaya son! Şase ile doğrulama yapıyoruz",
        "✅ Orijinal yedek parça ve faturalı gönderim",
        "🚚 Siparişiniz 48 saatte kargo firmasına verilir",
        "🔒 3D Secure güvenli ödeme seçeneği",
        "📦 2-5 İş günü sürecek profesyonel lojistik süreci",
        "✅ Filtre grubunda dünya markası kalitesi",
        "📋 Şase numaranız ile birebir uyumlu ürün tespiti",
        "🚚 Hızlı paketleme ve 48 saatte kargo çıkışı",
        "✅ Distribütör onaylı ve faturalı orijinal ürün",
        "🔁 14 Gün içinde kolay ve şeffaf iade süreci",
        "📋 Teknik destek ekibimizden şase no ile parça onayı",
    ]

    # Index'e göre seed belirle (her ürün için tutarlı olsun)
    random.seed(index)

    # Elementleri shuffle et
    shuffled = elements.copy()
    random.shuffle(shuffled)

    # %100 içeren ve içermeyen elementleri ayır
    elements_with_100 = [e for e in shuffled if "%100" in e]
    elements_without_100 = [e for e in shuffled if "%100" not in e]

    # KURAL: %100 maksimum 1 kez
    # 1. %100 içeren elementlerden 0 veya 1 tane seç
    has_100 = random.choice([True, False])

    if has_100 and elements_with_100:
        # 1 tane %100'lü element + 2-3 tane %100'süz element
        selected = [random.choice(elements_with_100)]
        num_more = 2 if len(f"MANN-FILTER {mann_code} {filter_type}") > 40 else 3
        selected.extend(random.sample(elements_without_100, min(num_more, len(elements_without_100))))
    else:
        # Sadece %100'süz elementler (3-4 tane)
        num_elements = 3 if len(f"MANN-FILTER {mann_code} {filter_type}") > 40 else 4
        selected = random.sample(elements_without_100, min(num_elements, len(elements_without_100)))

    # Meta oluştur
    base = f"MANN-FILTER {mann_code} {filter_type}."
    meta = f"{base} {' '.join(selected)}"

    # 160 karakter limiti kontrol
    if len(meta) > 160:
        # Son elementi kaldır
        if len(selected) > 3:
            selected = selected[:3]
            meta = f"{base} {' '.join(selected)}"

        # Hala uzunsa kırp
        if len(meta) > 160:
            truncated = meta[:157]
            last_space = truncated.rfind(' ')
            if last_space > 145:  # Min 145 karakter korunuyor
                meta = truncated[:last_space] + "..."
            else:
                meta = truncated + "..."

    # Minimum 145 karakter kontrolü
    if len(meta) < 145:
        # Bir element daha ekle (%100 kuralına uyarak)
        remaining = [e for e in elements_without_100 if e not in selected]

        # Eğer zaten %100 varsa, sadece %100'süz ekle
        has_100_already = any("%100" in e for e in selected)
        if has_100_already:
            remaining = [e for e in remaining if "%100" not in e]

        if remaining:
            extra = random.choice(remaining)
            test_meta = f"{base} {' '.join(selected)} {extra}"
            if len(test_meta) <= 160:
                meta = test_meta

    return meta


def build_tags_csv_mann(mann_code: str, filter_type: str, equivalents: List[Dict[str, str]]) -> str:
    """
    Tags - SADECE 6 önemli marka
    """
    tags = [mann_code.strip()]

    if filter_type:
        tags.append(filter_type.strip())

    tags.append("MANN-FILTER")

    important_brands = [
        ("HENGST", ["HENGST"]),
        ("BOSCH", ["BOSCH"]),
        ("MAHLE", ["MAHLE", "KNECHT-MAHLE", "KNECHT"]),
        ("FILTRON", ["FILTRON"]),
        ("PURFLUX", ["PURFLUX"]),
        ("UFI", ["UFI FILTERS", "UFI"]),
    ]

    for brand_name, brand_variants in important_brands:
        eq = None
        for variant in brand_variants:
            eq = next((e for e in equivalents if variant.upper() in e['brand'].upper()), None)
            if eq:
                break

        if eq:
            tags.append(f"{brand_name} {eq['code']}")

    seen = set()
    out = []
    for t in tags:
        t2 = t.strip()
        if not t2:
            continue
        k = t2.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t2)

    return ", ".join(out)


# =============================================================================
# HTML BUILDER (MAHLE MASTER TEMPLATE)
# =============================================================================

def build_equivalent_brands_html_table(equivalents: List[Dict[str, str]]) -> str:
    """Eşdeğer kodlar tablosu - SADECE 6 önemli marka"""
    if not equivalents:
        return ""

    important_brand_filters = [
        ("HENGST", ["HENGST"]),
        ("BOSCH", ["BOSCH"]),
        ("MAHLE", ["MAHLE", "KNECHT-MAHLE", "KNECHT"]),
        ("FILTRON", ["FILTRON"]),
        ("PURFLUX", ["PURFLUX"]),
        ("UFI FILTERS", ["UFI FILTERS", "UFI"]),
    ]

    important_equivalents = []
    seen_brands = set()

    for brand_name, brand_variants in important_brand_filters:
        if brand_name in seen_brands:
            continue

        for eq in equivalents:
            eq_brand_upper = eq['brand'].upper()

            for variant in brand_variants:
                if variant.upper() in eq_brand_upper:
                    important_equivalents.append({
                        'brand': brand_name,
                        'code': eq['code']
                    })
                    seen_brands.add(brand_name)
                    break

            if brand_name in seen_brands:
                break

    if not important_equivalents:
        return ""

    html = []
    html.append("<h3>🔄 Eşdeğer Filtre Kodları</h3>")
    html.append('<table style="width:100%;border-collapse:collapse;margin:10px 0;">')
    html.append('  <tr style="background:#f8f9fa;">')
    html.append('    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Marka</strong></td>')
    html.append('    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Kod</strong></td>')
    html.append('  </tr>')

    for eq in important_equivalents:
        html.append('  <tr>')
        html.append(f'    <td style="padding:8px;border:1px solid #dee2e6;">{eq["brand"]}</td>')
        html.append(f'    <td style="padding:8px;border:1px solid #dee2e6;"><strong>{eq["code"]}</strong></td>')
        html.append('  </tr>')

    html.append('</table>')

    return "\n".join(html)


def build_fitment_html_mahle_style(vehicles: Dict[str, List[str]]) -> str:
    """Araç uyumlulukları - MAHLE style (border-left div)"""
    if not vehicles:
        return ""

    html = []
    shown = 0

    for brand, models in vehicles.items():
        if shown >= BODY_MAX_TOTAL_MODELS:
            break

        brand_display = format_brand_title_case(brand)

        take = models[:BODY_MAX_MODELS_PER_BRAND]

        html.append(f'<div style="border-left: 4px solid #28a745; padding-left: 10px; margin: 10px 0;">')
        html.append(f'<p>✅ <strong>{brand_display}:</strong><br>')

        for m in take:
            html.append(f'  • {m}<br>')
            shown += 1
            if shown >= BODY_MAX_TOTAL_MODELS:
                break

        html.append('</p></div>')

    return "\n".join(html)


def build_body_html_mann_mahle_template(
    mann_code: str,
    filter_type: str,
    equivalents: List[Dict[str, str]],
    vehicles: Dict[str, List[str]],
    mann_url: str,
    top_brand: Optional[str]
) -> str:
    """
    MANN-FILTER için MAHLE MASTER TEMPLATE
    - Dış link: Sadece MANN-FILTER (3 link → 1 link)
    - Şase No ile Kontrol
    - Eşdeğer bölümü eklendi
    """
    code_disp = mann_code.strip()
    filter_disp = filter_type.strip() if filter_type else "Otomotiv Filtresi"
    top_brand_disp = top_brand or "Çeşitli markalar"

    total_models = sum(len(models) for models in vehicles.values())

    # Platform cümlesi
    platform_phrase = f"{top_brand_disp} platformlarında" if top_brand_disp != "Çeşitli markalar" else "seçili araç gruplarında"

    fl = filter_disp.lower()
    if "yağ" in fl:
        protection_text = "motor yağındaki metal parçacık, kurum ve kirleticileri filtreleyerek yağın temiz kalmasına yardımcı olur"
    elif "polen" in fl or "kabin" in fl:
        protection_text = "kabin havasını polen, toz ve zararlı partiküllerden arındırarak sağlıklı sürüş ortamı sunar"
    elif "yakıt" in fl:
        protection_text = "yakıt sistemindeki kirleticileri filtreler ve motor performansını korur"
    else:
        protection_text = "motorunuzu toz ve zararlı partiküllere karşı korumaya yardımcı olur"

    platform_p = f"<p>MANN-FILTER {code_disp} {filter_disp.lower()}, {platform_phrase} {protection_text}. Yüksek filtrasyon kapasitesi ile motor performansını destekler ve verim kaybı riskini azaltır.</p>"

    intro_p = f"<p>MANN-FILTER {code_disp} {filter_disp.lower()}, aracınızın iç mekanında temiz ve sağlıklı bir hava akışı sağlamak için tasarlandı. Yüksek kaliteli malzemelerden üretilen bu filtre, dışarıdan gelen toz, polen ve diğer zararlı partiküllerin içeri girmesini engelleyerek sürüş konforunuzu artırır.</p>"

    # Eşdeğer kod bilgisi
    # HENGST eşdeğerini bul (varsa)
    hengst_eq = next((eq for eq in equivalents if "HENGST" in eq['brand'].upper()), None)
    mann_line = f"HENGST {hengst_eq['code']}" if hengst_eq else "-"

    uyum_text = f"{top_brand_disp} (seçili {total_models} araç grubu)" if total_models else f"{top_brand_disp} (seçili 0 araç grubu)"

    vehicles_block = build_fitment_html_mahle_style(vehicles)

    # Eşdeğer kodlar bölümü
    equivalents_table = build_equivalent_brands_html_table(equivalents)

    safe_cta = "Hızlı kargo ve Güvenli alışverişle hemen sipariş verin."

    wa_text = f"Merhaba,%20MANN-FILTER%20{code_disp}%20%C3%BCr%C3%BCn%C3%BC%20hakk%C4%B1nda%20bilgi%20almak%20istiyorum"
    wa_url = f"https://wa.me/905363955525?text={wa_text}"

    # Dış link: SADECE MANN-FILTER
    mann_link_safe = mann_url or ""
    mann_anchor = f'<a href="{mann_link_safe}" target="_blank" rel="nofollow noopener">MANN-FILTER</a>' if mann_link_safe else "MANN-FILTER"

    return f"""<h2>MANN-FILTER {code_disp} {filter_disp}</h2>

<!-- Quick Info Bar (Above the Fold) -->
<div style="background:#f8f9fa;padding:15px;margin:15px 0;border-left:4px solid #28a745;">
<ul style="margin:0;padding-left:15px;list-style:none;">
  <li>✅ <strong>Uyumluluk:</strong> {uyum_text} – Şase No ile kontrol</li>
  <li>✅ <strong>Eşdeğer Kod:</strong> {mann_line}</li>
  <li>🚚 <strong>Hızlı Kargo</strong> – Aynı gün kargoya teslim</li>
  <li>🔁 <strong>Kolay İade</strong> – Faturalı satış</li>
</ul>
</div>

{platform_p}

{intro_p}

<h3>Neden MANN-FILTER {code_disp} Seçmelisiniz?</h3>
<ul>
  <li><strong>OEM Kalitesi:</strong> Orijinal ekipman standartlarında üretim</li>
  <li><strong>Yüksek Filtrasyon:</strong> Motorunuzu toz, kir ve partiküllerden korur</li>
  <li><strong>Hassas Uyum:</strong> {top_brand_disp} platformları için tasarlanmıştır</li>
  <li><strong>Dayanıklılık:</strong> Zorlu koşullarda bile stabil performans</li>
  <li><strong>Hızlı Kargo:</strong> Siparişleriniz özenle paketlenir ve hızla gönderilir</li>
  <li><strong>Güvenli Alışveriş:</strong> Güvenli ödeme altyapısı ile sorunsuz işlem</li>
</ul>

<h3>Teknik Özellikler – {code_disp}</h3>
<table style="width:100%;border-collapse:collapse;margin:10px 0;">
  <tr style="background:#f8f9fa;">
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Ürün Kodu</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;">MANN-FILTER {code_disp}</td>
  </tr>
  <tr>
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Filtre Tipi</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;">{filter_disp}</td>
  </tr>
  <tr style="background:#f8f9fa;">
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Marka</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;">MANN-FILTER</td>
  </tr>
  <tr>
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Eşdeğer (Muadil)</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>{mann_line}</strong></td>
  </tr>
  <tr style="background:#f8f9fa;">
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Uyumluluk</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;">Seçili {total_models} araç grubu (tam liste metafield'da)</td>
  </tr>
</table>

{equivalents_table}

<h3>Uyumlu Araç Modelleri</h3>
<p><strong>MANN-FILTER {code_disp}</strong> şu araçlarla uyumludur:</p>
{vehicles_block}

<p style="background:#fff3cd;padding:10px;border-left:4px solid #ffc107;margin:15px 0;">
<strong>📋 Not:</strong> Tam uyumluluk listesi ürün metafield'ında saklanır.
Şase No ile uyumluluğu teyit edebilirsiniz.
</p>

<h3>Bakım ve Değişim Önerisi</h3>
<p>
{filter_disp}nin düzenli olarak değiştirilmesi motorun sağlıklı çalışması için kritik öneme sahiptir.
Aracınızın kullanım kılavuzunda belirtilen bakım aralıklarına uyarak motorunuzun performansını koruyabilir
ve olası arızaların önüne geçebilirsiniz.
</p>

<h3>Sık Sorulan Sorular</h3>

<p><strong>❓ Bu ürün aracıma uyar mı?</strong><br>
Şase No ile kontrol önerilir. Uyumluluk listesi {total_models} araç grubu kapsar.</p>

<p><strong>❓ Muadil (eşdeğer) kodu nedir?</strong><br>
{mann_line} (katalog eşleştirmesi).</p>

<p><strong>❓ Ne zaman değiştirilmeli?</strong><br>
Aracınızın kullanım kılavuzuna göre; genelde 15.000-30.000 km aralığında kontrol önerilir.</p>

<p><strong>❓ Uyumluluk kaynağı nedir?</strong><br>
Uyumluluk verileri {'<a href="' + mann_link_safe + '" target="_blank" rel="nofollow noopener">MANN-FILTER</a>' if mann_link_safe else 'MANN-FILTER'} veritabanı ile doğrulanmıştır.</p>

<p><strong>❓ Kargo ve iade koşulları nedir?</strong><br>
Aynı gün kargo, güvenli paketleme. Kolay iade süreci ve faturalı satış garantisi.</p>

<div style="background:#d4edda;padding:15px;margin:20px 0;border:1px solid #c3e6cb;text-align:center;">
<p style="margin:0;font-size:16px;"><strong>🛒 {safe_cta}</strong></p>
<p style="margin:10px 0;font-size:14px;color:#155724;">
Uyumluluktan emin değilseniz şase no ile kontrol için bize yazabilirsiniz.
</p>
<a href="{wa_url}" target="_blank" rel="noopener" style="display:inline-block;background:#25D366;color:#fff;padding:12px 24px;text-decoration:none;border-radius:8px;font-weight:bold;margin-top:10px;">
💬 WhatsApp ile Uyumluluk Kontrolü
</a>
</div>

<hr style="margin:20px 0;">
<p style="font-size:12px;color:#6c757d;">
<strong>Kaynak bilgileri:</strong><br>
Uyumluluk Rehberi: {mann_anchor} veritabanı ile eşleştirilmiştir.<br>
Bilgi Erişimi: Kapsamlı uyumluluk tablosu, ürün ek veri alanlarında saklanmaktadır.
</p>"""



def _plain_text(value: str) -> str:
    """HTML veya düz metni JSON-LD için sade metne çevirir."""
    if not value:
        return ""
    return BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)


def _short_jsonld_description(value: str, fallback: str, max_length: int = 320) -> str:
    text = re.sub(r"\s+", " ", _plain_text(value or fallback)).strip()
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(" ", 1)[0].rstrip(" ,.;:-") + "."


def upsert_seo_structured_data(
    product_id: int,
    canonical_sku: str,
    external_code: str,
    filter_type_title: str,
    price: float,
    stock_qty: int,
    meta_desc: str = "",
    mann_display: Optional[str] = None,
    total_models: int = 0,
    equivalents: Optional[List[Dict[str, str]]] = None,
) -> bool:
    """MANN Product JSON-LD'sini custom.seo_structured_data metafield'ına yazar."""
    if not WRITE_SEO_STRUCTURED_METAFIELD:
        return True

    if DRY_RUN:
        log(
            f"[DRY_RUN] seo_structured_data -> pid={product_id} "
            f"sku={canonical_sku} price={price} stock={stock_qty}"
        )
        return True

    product_data = shopify_get(f"{BASE}/products/{product_id}.json", timeout=25)
    product = (product_data or {}).get("product") or {}
    handle = str(product.get("handle") or "").strip()
    if not handle:
        log(f"seo_structured_data: Shopify handle bulunamadı pid={product_id}", "ERROR")
        return False

    storefront_url = f"https://{STOREFRONT_DOMAIN}/products/{handle}"
    images = []
    for image in product.get("images") or []:
        src = str(image.get("src") or "").strip()
        if src and src not in images:
            images.append(src)

    fallback = (
        f"MANN-FILTER {external_code or canonical_sku} {filter_type_title}. "
        f"Uyumlu araç ve ürün bilgilerini kontrol ederek güvenli alışveriş yapın."
    )
    document = {
        "@context": "https://schema.org",
        "@type": "Product",
        "@id": f"{storefront_url}#product",
        "url": storefront_url,
        "name": str(product.get("title") or fallback).strip(),
        "image": images,
        "description": _short_jsonld_description(meta_desc, fallback),
        "sku": canonical_sku,
        "mpn": external_code or canonical_sku,
        "brand": {"@type": "Brand", "name": "MANN-FILTER"},
        "category": filter_type_title,
        "offers": {
            "@type": "Offer",
            "url": storefront_url,
            "priceCurrency": "TRY",
            "price": f"{float(price):.2f}",
            "availability": "https://schema.org/InStock" if int(stock_qty or 0) > 0 else "https://schema.org/OutOfStock",
            "itemCondition": "https://schema.org/NewCondition",
            "seller": {"@type": "Organization", "name": "FiltreOto"},
        },
    }
    properties = [
        {"@type": "PropertyValue", "name": "Filtre Türü", "value": filter_type_title},
        {"@type": "PropertyValue", "name": "MANN-FILTER Kodu", "value": mann_display or external_code or canonical_sku},
        {"@type": "PropertyValue", "name": "Uyumlu Araç Sayısı", "value": f"{int(total_models or 0)} Model"},
    ]
    for eq in equivalents or []:
        properties.append({
            "@type": "PropertyValue",
            "name": f"{eq.get('brand', '')} Eşdeğer Kodu",
            "value": str(eq.get("code") or ""),
        })
    document["additionalProperty"] = properties

    return upsert_metafield(
        product_id,
        "custom",
        "seo_structured_data",
        "json",
        json.dumps(document, ensure_ascii=False, separators=(",", ":")),
    )


def load_items_from_supabase(max_rows: int = 0) -> List[dict]:
    """IKILER_MANN tablosunu sayfalı okuyup SEO işlem kayıtlarına dönüştürür."""
    if not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_SECRET_KEY veya SUPABASE_KEY tanımlı değil")
    select = "sku,kod,marka,kategori,fiyat,depo_merkezi,toplam_stok,mann_url,img_url_1,img_url_2,img_url_3,guncelleme_tarihi"
    rows: List[dict] = []
    offset = 0
    while True:
        limit = SUPABASE_PAGE_SIZE if not max_rows else min(SUPABASE_PAGE_SIZE, max_rows - len(rows))
        if limit <= 0:
            break
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
            params={
                "select": select,
                "marka": "eq.MANN-FILTER",
                "order": "sku.asc",
                "limit": limit,
                "offset": offset,
            },
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Supabase GET {response.status_code}: {response.text[:300]}")
        batch = response.json()
        if not batch:
            break
        for row in batch:
            raw_sku = str(row.get("sku") or "").strip()
            external_code = str(row.get("kod") or raw_sku).strip()
            canonical = normalize_sku(raw_sku or external_code)
            if not canonical:
                continue
            try:
                price = round(float(row.get("fiyat") or 0) * PRICE_MULTIPLIER, 2)
            except (TypeError, ValueError):
                price = 0.0
            try:
                stock = int(row.get("toplam_stok") or 0)
            except (TypeError, ValueError):
                stock = 0
            image_urls = [str(row.get(f"img_url_{i}") or "").strip() for i in range(1, 4)]
            rows.append({
                "sku": canonical,
                "external_code": external_code,
                "filter_type": str(row.get("kategori") or "Hava Filtresi").strip(),
                "price": price,
                "stock": stock,
                "depo_merkezi": str(row.get("depo_merkezi") or "").strip(),
                "mann_url": str(row.get("mann_url") or "").strip(),
                "image_urls": [u for u in image_urls if u],
                "source_row": row,
            })
        offset += len(batch)
        log(f"Supabase MANN ürünleri: +{len(batch)} | toplam {len(rows)}")
        if len(batch) < limit or (max_rows and len(rows) >= max_rows):
            break
        time.sleep(0.1)
    unique: List[dict] = []
    seen = set()
    for item in rows:
        if item["sku"] not in seen:
            seen.add(item["sku"])
            unique.append(item)
    log(f"✅ Supabase kaynak ürünü: {len(unique)} benzersiz MANN SKU")
    return unique


def select_priority_equivalents(equivalents: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """En fazla üç eşdeğeri HENGST → BOSCH → MAHLE önceliğiyle seçer."""
    priorities = [
        ("HENGST", ["HENGST"]),
        ("BOSCH", ["BOSCH"]),
        ("MAHLE", ["MAHLE", "KNECHT-MAHLE", "KNECHT"]),
    ]
    selected: List[Dict[str, str]] = []
    for canonical_brand, aliases in priorities:
        for eq in equivalents:
            brand = str(eq.get("brand") or "").upper()
            if any(alias in brand for alias in aliases):
                selected.append({"brand": canonical_brand, "code": str(eq.get("code") or "").strip()})
                break
    return [eq for eq in selected if eq["code"]]


# =============================================================================
# MAIN
# =============================================================================

def main():
    log("=" * 80)
    log("🚀 MANN FILTER SEO ENRICHER - SUPABASE IKILER_MANN")
    log(f"Supabase table: {SUPABASE_TABLE} | vendor: {SHOPIFY_VENDOR}")
    log(
        f"DRY_RUN={DRY_RUN} | RESUME_EXISTING={RESUME_EXISTING} | "
        f"MAX_PRODUCTS={MAX_PRODUCTS or 'TÜMÜ'} | PRICE_MULTIPLIER={PRICE_MULTIPLIER}"
    )

    ufi_cross_ref = load_ufi_cross_reference()
    items = load_items_from_supabase(MAX_PRODUCTS)
    if not items:
        log("Supabase'ten işlenecek MANN ürünü bulunamadı.", "WARN")
        return

    products = load_all_products_since_id(SHOPIFY_VENDOR)
    sku_index = build_sku_index(products)
    location_id = get_primary_location_id()
    if not location_id:
        log("Shopify location bulunamadı.", "ERROR")
        return

    success = 0
    failed: List[dict] = []
    collections_map = load_all_collections()

    for idx, item in enumerate(items, start=1):
        sku = item["sku"]
        external_code = item["external_code"]
        filter_type = item["filter_type"]
        price = item["price"]
        raw_stock = item["stock"]
        stock_qty = 3 if raw_stock >= 4 else 2 if raw_stock in (2, 3) else 1 if raw_stock == 1 else 0
        equivalents = select_priority_equivalents(ufi_cross_ref.get(sku, []))
        product_url = item["mann_url"]
        images = item["image_urls"]

        try:
            log(f"[{idx}/{len(items)}] {external_code} | fiyat={price:.2f} | stok={raw_stock}->{stock_qty}")
            vehicles = mann_scrape_fitment_from_url(product_url) if product_url else {}
            top_vehicles = get_top_vehicles_for_title(vehicles, limit=3)
            top_brand = top_vehicles[0][0] if top_vehicles else None
            title = make_mann_title(external_code, filter_type, vehicles, TITLE_MAX_LEN)
            meta_desc = build_meta_description_mann(external_code, filter_type, vehicles, idx)
            tags_csv = build_tags_csv_mann(external_code, filter_type, equivalents)
            body_html = build_body_html_mann_mahle_template(
                external_code, filter_type, equivalents, vehicles, product_url, top_brand
            )
            total_models = sum(len(models) for models in vehicles.values())

            if sku in sku_index and not RESUME_EXISTING:
                data = sku_index[sku]
                product_id = data["product_id"]
                variant_id = data["variant_id"]
                if DRY_RUN:
                    log(f"[DRY_RUN] EXISTING sku={sku} price={price:.2f} stock={stock_qty}")
                    log(f"[DRY_RUN] seo_structured_data -> pid={product_id} sku={sku}")
                    success += 1
                    continue
                if not update_variant_price_sku(variant_id, sku, price):
                    raise RuntimeError("variant fiyat/SKU güncelleme başarısız")
                if not set_inventory_available(data.get("inventory_item_id"), location_id, stock_qty):
                    raise RuntimeError("stok güncelleme başarısız")
                category_payload = {
                    "product": {
                        "id": product_id,
                        "product_type": filter_type,
                        "tags": tags_csv,
                    }
                }
                ok, msg = shopify_put(f"{BASE}/products/{product_id}.json", category_payload)
                if not ok:
                    raise RuntimeError(f"kategori/tag güncelleme başarısız: {msg}")
                if not upsert_seo_structured_data(
                    product_id, sku, external_code, filter_type, price, stock_qty,
                    meta_desc, external_code, total_models, equivalents,
                ):
                    raise RuntimeError("JSON-LD metafield güncellenemedi")
                success += 1
                continue

            if sku in sku_index:
                data = sku_index[sku]
                product_id = data["product_id"]
                variant_id = data["variant_id"]
                inventory_item_id = data.get("inventory_item_id")
                created_now = False
            else:
                if DRY_RUN:
                    log(f"[DRY_RUN] CREATE sku={sku} title={title} price={price:.2f} stock={stock_qty}")
                    log(f"[DRY_RUN] seo_structured_data -> new product sku={sku}")
                    success += 1
                    continue
                created = create_product_mann(sku, title, filter_type, price, images)
                if not created or not created.get("product"):
                    raise RuntimeError("Shopify CREATE başarısız")
                product_id = int(created["product"]["id"])
                variant = created["product"]["variants"][0]
                variant_id = int(variant["id"])
                inventory_item_id = variant.get("inventory_item_id")
                created_now = True

            if DRY_RUN:
                log(f"[DRY_RUN] ENRICH sku={sku} title={title} eq={len(equivalents)}")
                log(f"[DRY_RUN] seo_structured_data -> pid={product_id} sku={sku}")
                success += 1
                continue

            payload = {
                "product": {
                    "id": product_id,
                    "vendor": SHOPIFY_VENDOR,
                    "product_type": filter_type,
                    "status": CREATE_STATUS,
                    "title": title,
                    "body_html": body_html,
                    "tags": tags_csv,
                }
            }
            ok, msg = shopify_put(f"{BASE}/products/{product_id}.json", payload)
            if not ok:
                raise RuntimeError(f"ürün PUT başarısız: {msg}")
            if not upsert_metafield(product_id, "global", "description_tag", "single_line_text_field", meta_desc[:160]):
                raise RuntimeError("description_tag yazılamadı")
            if not update_variant_price_sku(variant_id, sku, price):
                raise RuntimeError("variant fiyat/SKU güncellenemedi")
            if inventory_item_id and not set_inventory_available(int(inventory_item_id), location_id, stock_qty):
                raise RuntimeError("stok ayarlanamadı")
            upsert_metafield(product_id, "custom", "oem_brand", "single_line_text_field", "MANN")
            upsert_metafield(product_id, "custom", "oem_code", "single_line_text_field", external_code)
            upsert_metafield(product_id, "custom", "google_mpn", "single_line_text_field", sku)
            upsert_metafield(product_id, "custom", "equivalent_codes", "json", json.dumps(equivalents, ensure_ascii=False))
            if vehicles:
                upsert_metafield(product_id, "custom", "fitment_json", "json", json.dumps(vehicles, ensure_ascii=False))
            add_product_to_collections(product_id, filter_type, vehicles, collections_map)
            if created_now:
                set_product_handle_safe(product_id, title, sku)
            if not upsert_seo_structured_data(
                product_id, sku, external_code, filter_type, price, stock_qty,
                meta_desc, external_code, total_models, equivalents,
            ):
                raise RuntimeError("JSON-LD metafield yazılamadı")
            success += 1
            log(f"✅ {sku}: {'CREATE' if created_now else 'UPDATE'} tamamlandı")
        except Exception as exc:
            failed.append({"sku": sku, "external": external_code, "error": f"{type(exc).__name__}: {exc}"})
            log(f"{sku}: işlem başarısız: {type(exc).__name__}", "ERROR")

    log(f"ÖZET | başarılı={success} | başarısız={len(failed)}")
    if failed:
        with open(FAILED_FILE, "w", encoding="utf-8") as f:
            json.dump(failed, f, indent=2, ensure_ascii=False)
        log(f"Hatalar yazıldı: {FAILED_FILE}", "WARN")


if __name__ == "__main__":
    main()
