# -*- coding: utf-8 -*-

r"""
================================================================================
FILTRON SEO ENRICHER [V17 - SUPABASE SKU INDEX + CANLI İSTATİSTİK]
================================================================================

NE YAPAR?
─────────
Filtron filtre ürünlerini Shopify mağazasına otomatik olarak ekler veya
fiyat/stok bilgilerini günceller. Her ürün için:
  1. CSV'deki KOD kolonundan SKU index oluşturur
  2. Shopify'dan tüm ürünleri çekip SKU index ile karşılaştırır
  3. SKU Shopify'da VARSA  → sadece fiyat + stok günceller (hızlı yol)
  4. SKU Shopify'da YOKSA  → yeni ürün açar + Mann crossref + fitment
     scraping + OpenAI SEO metni + metafield + koleksiyon ataması yapar
  5. Terminal'e canlı ilerleme istatistiği basar

AKIŞ DİYAGRAMI
──────────────
CSV oku → Supabase SKU index
       ↓
Shopify ürünleri çek → Shopify SKU index
       ↓
Karşılaştır (ön rapor)
       ↓
Her SKU için:
  ┌─ Shopify'da VAR?
  │    EVET → fiyat+stok güncelle → continue
  │    HAYIR → yeni ürün aç
  │              ↓
  │           Mann crossref API
  │              ↓
  │           Mann fitment scrape
  │              ↓
  │           OpenAI SEO metni
  │              ↓
  │           Shopify product PUT (başlık, body, tags)
  │              ↓
  │           Metafield yaz (oem_brand, oem_code, mann_code, fitment_json)
  │              ↓
  │           Marka koleksiyonları ata
  └─ LiveStats güncelle

BAŞLARKEN
─────────
  Windows:
    set SHOPIFY_TOKEN=shpat_xxxxx
    set OPENAI_API_KEY=sk-xxxxx
    python filtron_17.py

  Linux/Mac:
    export SHOPIFY_TOKEN=shpat_xxxxx
    export OPENAI_API_KEY=sk-xxxxx
    python3 filtron_17.py

================================================================================
ENV DEĞİŞKENLERİ (Tüm Ayarlar)
================================================================================

  ┌─────────────────────────────┬──────────────┬──────────────────────────────┐
  │ Değişken                    │ Varsayılan   │ Açıklama                     │
  ├─────────────────────────────┼──────────────┼──────────────────────────────┤
  │ SHOPIFY_TOKEN               │ (zorunlu)    │ Shopify Admin API token      │
  │ SHOP_SUBDOMAIN              │ z42kyc-dt    │ Mağaza subdomain'i           │
  │ SHOPIFY_API_VERSION         │ 2024-01      │ Shopify API versiyonu        │
  ├─────────────────────────────┼──────────────┼──────────────────────────────┤
  │ OPENAI_API_KEY              │ (zorunlu)    │ OpenAI API anahtarı          │
  │ OPENAI_MODEL                │ gpt-4o-mini  │ Kullanılacak model           │
  ├─────────────────────────────┼──────────────┼──────────────────────────────┤
  │ SUPABASE_TABLE               │ IKILER_FILTRON  │ Supabase tablo adı           │
  ├─────────────────────────────┼──────────────┼──────────────────────────────┤
  │ MAX_ROWS                    │ 5            │ İşlenecek maks. satır sayısı │
  │                             │              │ 0 = TÜMÜNÜ işle              │
  │                             │              │ Örnek: set MAX_ROWS=100      │
  │                             │              │ Tümü: set MAX_ROWS=0         │
  ├─────────────────────────────┼──────────────┼──────────────────────────────┤
  │                             │              │ Supabase fiyatı = Shopify  │
  │                             │              │ Supabase fiyatı Shopify'a yazılır │
  ├─────────────────────────────┼──────────────┼──────────────────────────────┤
  │ DRY_RUN                     │ 0            │ 1 = Shopify'a yazmaz,        │
  │                             │              │ sadece loglar (test modu)    │
  │ CREATE_STATUS               │ active       │ Yeni ürün durumu: active/draft│
  │ stock_qty             │ 3            │ Stok miktarı (tüm ürünler)  │
  ├─────────────────────────────┼──────────────┼──────────────────────────────┤
  │ UPDATE_TAGS                 │ 1            │ 1 = tag'leri güncelle        │
  │ HANDLE_MODE                 │ create_only  │ Sadece yeni ürünlere handle  │
  ├─────────────────────────────┼──────────────┼──────────────────────────────┤
  │ BODY_MAX_TOTAL_MODELS       │ 160          │ Body HTML'de max araç sayısı │
  │ BODY_MAX_MODELS_PER_BRAND   │ 25           │ Marka başına max model       │
  │ TITLE_MAX_LEN               │ 150          │ Ürün başlığı max karakter    │
  ├─────────────────────────────┼──────────────┼──────────────────────────────┤
  │ SHOPIFY_SLEEP               │ 0.6          │ Shopify API çağrıları arası  │
  │                             │              │ bekleme süresi (saniye)      │
  │ MANN_SLEEP                  │ 0.2          │ Mann API bekleme süresi      │
  │ OPENAI_SLEEP                │ 0.2          │ OpenAI çağrıları arası bekleme│
  ├─────────────────────────────┼──────────────┼──────────────────────────────┤
  │ LOG_FILE                    │ filtron_seo_debug.log    │ Log dosyası      │
  │ FAILED_FILE                 │ filtron_failed.json      │ Hatalı SKU'lar   │
  │ PROGRESS_FILE               │ filtron_debug_progress.jsonl │ Adım logları │
  │ PRINT_PARSE_DEBUG           │ 0            │ 1 = fitment parse debug      │
  ├─────────────────────────────┼──────────────┼──────────────────────────────┤
  │ PROCESS_ONLY_FAILED         │ 0            │ 1 = sadece failed.json'daki  │
  │                             │              │ SKU'ları tekrar işle         │
  └─────────────────────────────┴──────────────┴──────────────────────────────┘

ÖRNEK KULLANIM SENARYOLARI
──────────────────────────
  # İlk test: 5 Supabase satırı, Shopify'a yazma
    set MAX_ROWS=5 && set DRY_RUN=1 && python 03_filtron_supabase_shopify_seo.py

  # Tüm CSV'yi işle
    set MAX_ROWS=0 && python filtron_17.py

  # Sadece 50 satır, daha yüksek çarpan
    set MAX_ROWS=50 && python 03_filtron_supabase_shopify_seo.py

  # Önceki çalışmada hata veren SKU'ları tekrar dene
    set PROCESS_ONLY_FAILED=1 && python filtron_17.py

  # Ürünleri draft olarak aç
    set CREATE_STATUS=draft && python filtron_17.py

================================================================================
ÇIKTI DOSYALARI
================================================================================
  filtron_seo_debug.log          → Tüm log satırları (her çalışmaya eklenir)
  filtron_failed.json            → Hata veren SKU'lar (bir sonraki çalışmada
                                   PROCESS_ONLY_FAILED=1 ile tekrar dene)
  filtron_debug_progress.jsonl   → Her adımın JSON kaydı (her çalışmada sıfırlanır)

================================================================================
"""

import os
import sys
import json
import re
import time
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from openai import OpenAI


# =============================================================================
# .ENV DOSYASI OTOMATİK YÜKLE
# =============================================================================
# Script ile aynı klasördeki ".env" dosyasını okur.
# Her satır KEY=VALUE formatında olmalı. # ile başlayan satırlar yorum sayılır.
# Sistem env'de zaten varsa üzerine yazmaz (öncelik: sistem env > .env dosyası).

def _load_dotenv(env_path: str = ".env") -> None:
    """Script klasöründeki .env dosyasını okuyup os.environ'a yükler."""
    # Script'in bulunduğu klasörde ara
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        env_path,                                    # çalışma dizini
        os.path.join(script_dir, env_path),          # script klasörü
        os.path.join(script_dir, "_env"),            # _env (uzantısız)
        os.path.join(os.getcwd(), "_env"),           # _env çalışma dizini
    ]

    loaded_from = None
    for path in candidates:
        if os.path.exists(path):
            loaded_from = path
            break

    if not loaded_from:
        return  # .env yok, sistem env kullanılacak

    count = 0
    with open(loaded_from, "r", encoding="utf-8-sig", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key   = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:   # sistem env öncelikli
                os.environ[key] = value
                count += 1

    print(f"[.env] {loaded_from} dosyasından {count} değişken yüklendi.", flush=True)


_load_dotenv()


# =============================================================================
# CONFIG (ENV)
# =============================================================================

# Shopify bağlantı bilgileri
SHOP_SUBDOMAIN = os.getenv("SHOP_SUBDOMAIN", "z42kyc-dt")
STOREFRONT_DOMAIN = os.getenv("STOREFRONT_DOMAIN", "filtreoto.com").strip().rstrip("/")
SHOPIFY_TOKEN  = os.getenv("SHOPIFY_TOKEN", "")
API_VERSION    = os.getenv("SHOPIFY_API_VERSION", "2024-01")

# Supabase ürün kaynağı
SUPABASE_URL   = os.getenv("SUPABASE_URL", "https://lrjphkajdkipwjizzxsc.supabase.co").rstrip("/")
SUPABASE_KEY   = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY", "")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "IKILER_FILTRON")
SUPABASE_PAGE_SIZE = int(os.getenv("SUPABASE_PAGE_SIZE", "1000"))
PRICE_MULTIPLIER = float(os.getenv("PRICE_MULTIPLIER", "1.60"))

# İşlenecek maksimum Supabase satırı — 0 = tümü
MAX_ROWS = int(os.getenv("MAX_ROWS", "5"))

# OpenAI ayarları
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Davranış ayarları
DRY_RUN         = (os.getenv("DRY_RUN",         "0") == "1")  # 1=test modu, Shopify'a yazmaz
CREATE_STATUS   = os.getenv("CREATE_STATUS",   "active")       # active veya draft

# Hangi alanlar yazılacak
WRITE_PRODUCT_TITLE     = True   # Shopify ürün başlığı
WRITE_BODY_HTML         = True   # Ürün açıklaması (SEO body)
WRITE_META              = True   # Meta description
WRITE_FITMENT_METAFIELD = True   # Fitment JSON metafield
WRITE_SEO_STRUCTURED_METAFIELD = (os.getenv("WRITE_SEO_STRUCTURED_METAFIELD", "1") == "1")
UPDATE_PRICE            = True   # Variant fiyat
UPDATE_SKU_ON_SHOPIFY   = True   # Variant SKU normalize
UPDATE_TAGS             = (os.getenv("UPDATE_TAGS", "1") == "1")  # Tag'ler

# URL handle davranışı: "create_only" = sadece yeni ürünlerde handle yaz
HANDLE_MODE = os.getenv("HANDLE_MODE", "create_only").lower().strip()

# SEO body HTML limitleri
BODY_MAX_TOTAL_MODELS     = int(os.getenv("BODY_MAX_TOTAL_MODELS",     "160"))
BODY_MAX_MODELS_PER_BRAND = int(os.getenv("BODY_MAX_MODELS_PER_BRAND",  "25"))
TITLE_MAX_LEN             = int(os.getenv("TITLE_MAX_LEN",             "150"))

# API hız limitleri (saniye cinsinden bekleme süreleri)
SHOPIFY_SLEEP = float(os.getenv("SHOPIFY_SLEEP", "0.6"))  # Shopify rate limit
MANN_SLEEP    = float(os.getenv("MANN_SLEEP",    "0.2"))  # Mann-Filter API
OPENAI_SLEEP  = float(os.getenv("OPENAI_SLEEP",  "0.2"))  # OpenAI API

# Çıktı ve log dosyaları
LOG_FILE          = os.getenv("LOG_FILE",          "filtron_seo_debug.log")
FAILED_FILE       = os.getenv("FAILED_FILE",       "filtron_failed.json")
PROGRESS_FILE     = os.getenv("PROGRESS_FILE",     "filtron_debug_progress.jsonl")
PRINT_PARSE_DEBUG = (os.getenv("PRINT_PARSE_DEBUG", "0") == "1")

# 1 = sadece önceki çalışmada hata veren SKU'ları işle (filtron_failed.json'dan okur)
PROCESS_ONLY_FAILED = (os.getenv("PROCESS_ONLY_FAILED", "0") == "1")
RESUME_EXISTING = (os.getenv("RESUME_EXISTING", "0") == "1")


# =============================================================================
# SABİT ARAÇ MARKALARI (KOLEKSİYON BEYAZ LİSTE)
# =============================================================================

ALLOWED_VEHICLE_BRANDS: set = {
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
# ENV CHECK & LOGGING
# =============================================================================

def log(msg: str, level: str = "INFO") -> None:
    """Terminale ve log dosyasına zaman damgalı mesaj yazar. level: INFO/WARN/ERROR"""
    line = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except Exception:
        pass


if not SHOPIFY_TOKEN:
    log("❌ SHOPIFY_TOKEN boş. Windows: set SHOPIFY_TOKEN=shpat_...", "ERROR")
    raise SystemExit(1)

if not OPENAI_API_KEY:
    log("❌ OPENAI_API_KEY boş. Windows: set OPENAI_API_KEY=sk-...", "ERROR")
    raise SystemExit(1)

if not SUPABASE_KEY:
    log("❌ SUPABASE_SECRET_KEY veya SUPABASE_KEY boş.", "ERROR")
    raise SystemExit(1)

BASE = f"https://{SHOP_SUBDOMAIN}.myshopify.com/admin/api/{API_VERSION}"
HEADERS = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

UA_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept": "*/*",
}

client = OpenAI(api_key=OPENAI_API_KEY)

MANN_GQL = "https://www.mann-filter.com/api/graphql/catalog-prod"

MANN_QUERY_CROSSREF = r"""
query($search:String!,$currentPage:Int!,$pageSize:Int!,$filterBy:TYPE_OF_FILTER){
  catalogSearch:search_crossreference_no(search:$search currentPage:$currentPage pageSize:$pageSize filterBy:$filterBy){
    items{
      product{
        name
        sku
        urlKey:url_key
        attributes:attributes_value{key value adminValue:admin_value __typename}
        __typename
      }
      externalNumber:external_number
      externalProductName:ext_product_name
      manufacturer:ext_brand_name
      __typename
    }
  }
}
""".strip()


# =============================================================================
# DEBUG STEP
# =============================================================================

def debug_step(**kwargs) -> None:
    """Her işlem adımını JSON satırı olarak PROGRESS_FILE dosyasına yazar. Hata ayıklama için."""
    data = {
        "time": datetime.now().isoformat(timespec="seconds"),
        **kwargs,
    }
    line = json.dumps(data, ensure_ascii=False)
    try:
        with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except Exception:
        pass


# =============================================================================
# NORMALIZE / PARSE
# =============================================================================

def normalize_sku(x: str) -> str:
    """SKU normalize: boşluksuz, sadece A-Z0-9 (örn: AK381)"""
    return re.sub(r"[^A-Z0-9]", "", (x or "").upper().strip())


def parse_price(s: str) -> float:
    """
    129,74 veya 1.250,50 gibi formatları float'a çevirir.
    """
    if not s:
        return 0.0
    t = str(s).strip().replace(" ", "")
    t = t.replace(".", "").replace(",", ".")
    t = re.sub(r"[^0-9.]", "", t)
    if not t:
        return 0.0
    try:
        return float(t)
    except Exception:
        return 0.0


def to_shopify_money(v: float) -> str:
    """Float fiyatı Shopify'ın beklediği "129.74" string formatına çevirir."""
    try:
        return f"{float(v):.2f}"
    except Exception:
        return "0.00"


def detect_filter_type_from_csv_desc(desc: str) -> str:
    """CSV açıklama metninden filtre tipini tespit eder. Polen/Yakıt/Yağ/Hava/Hidrolik."""
    up = (desc or "").upper()

    if "POLEN" in up or "KABIN" in up or "KABİN" in up:
        return "Kabin Hava Filtresi"
    if "YAKIT" in up:
        return "Yakıt Filtresi"
    if "YAG" in up or "YAĞ" in up:
        return "Yağ Filtresi"
    if "HIDROLIK" in up or "HİDROLİK" in up or "SANZIMAN" in up or "ŞANZIMAN" in up:
        return "Hidrolik Şanzıman Filtresi"
    if "HAVA" in up:
        return "Hava Filtresi"

    return "Hava Filtresi"


def normalize_filter_type(value: str) -> str:
    """FILTRON ürün türünü tek standarda çevirir."""
    raw = " ".join(str(value or "").strip().split())
    key = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii").casefold()
    aliases = {
        "hava filtresi": "Hava Filtresi",
        "yag filtresi": "Yağ Filtresi",
        "yakit filtresi": "Yakıt Filtresi",
        "polen filtresi": "Polen Filtresi",
        "kabin hava filtresi": "Polen Filtresi",
        "hidrolik filtre": "Hidrolik Filtre",
        "hidrolik şanzıman filtresi": "Hidrolik Şanzıman Filtresi",
        "hidrolik sanziman filtresi": "Hidrolik Şanzıman Filtresi",
    }
    return aliases.get(key, raw.title() if raw else "Hava Filtresi")


def filter_type_for_title(filter_type_raw: str) -> str:
    """Ürün türünü başlık ve Shopify alanları için standartlaştırır."""
    return normalize_filter_type(filter_type_raw)


def scrape_filtron_catalog_images(sku: str) -> List[str]:
    """
    FILTRON katalog sayfasından görselleri scrape eder.
    URL: https://filtron.eu/tr/filtreyi-bul/arama-sonuclar%C4%B1/urun.html/{sku}_filtron.html
    
    Önemli: Görseller scene7.com CDN'inden geliyor (örn: s7g10.scene7.com)
    Görseller JavaScript ile yüklenebilir veya lazy-load attribute'larında olabilir.
    
    Returns: Liste of image URLs
    """
    # Orijinal SKU'yu al (external_code değil, sku parametresi)
    # Bu fonksiyona external_code gönderilmeli
    original = (sku or "").strip()
    
    # URL için: sadece boşlukları kaldır, / ve diğer karakterleri koru
    # AP 157/6 -> ap157/6
    url_code = re.sub(r'\s+', '', original).lower()
    
    url = f"https://filtron.eu/tr/filtreyi-bul/arama-sonuclar%C4%B1/urun.html/{url_code}_filtron.html"
    
    log(f"Scraping images from: {url}")
    
    try:
        r = requests.get(url, headers=UA_HEADERS, timeout=20)
        if r.status_code != 200:
            log(f"FILTRON catalog HTTP {r.status_code} for {sku}", "WARN")
            return []
        
        soup = BeautifulSoup(r.text, "html.parser")
        images = []
        
        # 1. ÖNCELİK: img tag'lerindeki tüm olası attribute'ları kontrol et
        img_attributes = ['src', 'data-src', 'data-lazy-src', 'data-original', 'data-image', 'data-url']
        
        for img in soup.find_all("img"):
            for attr in img_attributes:
                src = img.get(attr, "").strip()
                if not src:
                    continue
                
                # Relative URL'leri absolute yap
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = "https://filtron.eu" + src
                
                # scene7.com görselleri en yüksek öncelik
                if "scene7.com" in src.lower():
                    if src not in images:
                        images.append(src)
                        log(f"  ✓ Found scene7 image (attr={attr}): {src[:80]}...")
        
        # 2. JavaScript içinde scene7 URL'lerini ara
        if not images:
            log(f"  ⚠ No scene7 images in img tags, searching in scripts...")
            for script in soup.find_all("script"):
                script_text = script.string or ""
                # scene7.com içeren URL'leri regex ile bul
                matches = re.findall(r'https?://[^"\s]*scene7\.com[^"\s]*', script_text)
                for match in matches:
                    # Query parametrelerini temizle (? işaretinden sonrası opsiyonel)
                    clean_url = match.split('"')[0].split("'")[0]
                    if clean_url not in images:
                        images.append(clean_url)
                        log(f"  ✓ Found scene7 image in script: {clean_url[:80]}...")
        
        # 3. HTML içinde herhangi bir yerde scene7 URL'lerini ara
        if not images:
            log(f"  ⚠ No scene7 in scripts, searching in full HTML...")
            matches = re.findall(r'https?://[^"\s]*scene7\.com[^"\s]*', r.text)
            for match in matches:
                clean_url = match.split('"')[0].split("'")[0].split(')')[0].split(',')[0]
                if clean_url not in images:
                    images.append(clean_url)
                    log(f"  ✓ Found scene7 image in HTML: {clean_url[:80]}...")
        
        # 4. Eğer scene7 bulunamazsa, diğer kaynaklara bak
        if not images:
            log(f"  ⚠ No scene7 images found, trying fallback sources...")
            for img in soup.find_all("img"):
                for attr in img_attributes:
                    src = img.get(attr, "").strip()
                    if not src:
                        continue
                    
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = "https://filtron.eu" + src
                    
                    # Filtron ürün görseli olabilecek URL'leri filtrele
                    if any(x in src.lower() for x in ["/assets/", "/uploads/", "product", "photo", "filter"]):
                        if src not in images:
                            images.append(src)
                            log(f"  ✓ Found fallback image: {src[:80]}...")
        
        log(f"✅ Total {len(images)} images found for {sku} ({url_code})")
        return images[:10]  # Max 10 görsel
        
    except Exception as e:
        log(f"FILTRON catalog scrape error for {sku}: {type(e).__name__}: {e}", "WARN")
        return []


def build_filtron_image_urls(external_code: str, sku: str) -> List[str]:
    """
    FILTRON katalog sayfasından görselleri çeker.
    
    Args:
        external_code: Boşluklu format (AP 157/6)
        sku: Normalize edilmiş (AP1576)
    
    Eğer scraping başarısız olursa fallback olarak:
    1. Scene7 CDN pattern'i ile deneme yapar
    2. Static URLs (eski yöntem)
    """
    # external_code ile scrape et (AP 157/6 -> ap157/6_filtron.html)
    images = scrape_filtron_catalog_images(external_code)
    
    if images:
        return images
    
    # Fallback 1: Scene7 CDN pattern'i ile deneme
    # AP 157/6 -> AP_157.6 formatına çevir
    scene7_code = external_code.replace(" ", "_").replace("/", ".")
    
    scene7_url = f"https://s7g10.scene7.com/is/image/mannhummel/{scene7_code}-filter-with-box?qlt=82&dpr=off"
    
    log(f"Using scene7 pattern URL for {external_code}: {scene7_url}", "INFO")
    
    # Scene7 pattern'i ile deneme
    try:
        r = requests.head(scene7_url, headers=UA_HEADERS, timeout=10)
        if r.status_code == 200:
            log(f"  ✓ Scene7 pattern URL verified: {scene7_url}", "INFO")
            return [scene7_url]
    except Exception:
        pass
    
    # Fallback 2: Static URLs (eski yöntem)
    code_norm = normalize_sku(sku)
    base = "https://filtron.eu/assets/Uploads/Product-Photos"
    log(f"Using fallback static URLs for {external_code}", "WARN")
    return [
        f"{base}/{code_norm}.jpg",
        f"{base}/{code_norm}_1.jpg"
    ]


def slugify_tr(s: str) -> str:
    """Türkçe metni URL-safe handle'a çevirir. Türkçe karakterleri latinize eder, boşlukları tire yapar."""
    if not s:
        return ""
    x = s.strip().lower()
    tr_map = {
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
        "Ç": "c", "Ğ": "g", "İ": "i", "I": "i", "Ö": "o", "Ş": "s", "Ü": "u"
    }
    x = "".join(tr_map.get(ch, ch) for ch in x)
    x = re.sub(r"[^\w\s-]", " ", x, flags=re.UNICODE)
    x = re.sub(r"[\s_-]+", "-", x).strip("-")
    x = re.sub(r"-{2,}", "-", x)
    return x[:250]


# =============================================================================
# SUPABASE LOADER
# =============================================================================

def load_items_from_supabase(max_rows: int = 0) -> List[dict]:
    """IKILER_FILTRON tablosunu sayfalı okuyup Shopify işlem kayıtlarına dönüştürür."""
    if not SUPABASE_KEY:
        log("SUPABASE_SECRET_KEY tanımlı değil.", "ERROR")
        return []

    select = "sku,kod,marka,kategori,fiyat,depo_merkezi,toplam_stok,mann_url,img_url_1,img_url_2,img_url_3,guncelleme_tarihi"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    rows: List[dict] = []
    offset = 0

    while True:
        limit = SUPABASE_PAGE_SIZE
        if max_rows and len(rows) + limit > max_rows:
            limit = max_rows - len(rows)
        if limit <= 0:
            break

        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
                params={
                    "select": select,
                    "marka": "eq.FILTRON",
                    "order": "sku.asc",
                    "limit": limit,
                    "offset": offset,
                },
                headers=headers,
                timeout=30,
            )
            if r.status_code != 200:
                log(f"Supabase GET {r.status_code}: {r.text[:300]}", "ERROR")
                return []
            batch = r.json()
        except Exception as e:
            log(f"Supabase okuma hatası: {type(e).__name__}: {e}", "ERROR")
            return []

        if not batch:
            break

        for row in batch:
            raw_sku = str(row.get("sku") or "").strip()
            external_code = str(row.get("kod") or raw_sku).strip()
            canonical = normalize_sku(raw_sku or external_code)
            if not canonical:
                continue

            raw_price = row.get("fiyat")
            try:
                price_value = float(raw_price or 0)
            except (TypeError, ValueError):
                price_value = 0.0

            try:
                stock_qty = int(row.get("toplam_stok") or 0)
            except (TypeError, ValueError):
                stock_qty = 0

            image_urls = [
                str(row.get("img_url_1") or "").strip(),
                str(row.get("img_url_2") or "").strip(),
                str(row.get("img_url_3") or "").strip(),
            ]
            image_urls = [u for u in image_urls if u]

            rows.append({
                "sku": canonical,
                "external_code": external_code,
                "csv_sku_raw": external_code,
                "filter_type_raw": str(row.get("kategori") or "Hava Filtresi"),
                "price": to_shopify_money(price_value * PRICE_MULTIPLIER),
                "stock_qty": stock_qty,
                "depo_merkezi": str(row.get("depo_merkezi") or ""),
                "mann_url": str(row.get("mann_url") or "").strip(),
                "image_urls": image_urls,
                "source_row": row,
            })

        offset += len(batch)
        log(f"Supabase ürünleri: +{len(batch)} | toplam {len(rows)}")
        if len(batch) < limit or (max_rows and len(rows) >= max_rows):
            break
        time.sleep(0.1)

    # Aynı SKU birden fazla gelirse ilk kayıt korunur.
    seen = set()
    unique: List[dict] = []
    for item in rows:
        if item["sku"] in seen:
            continue
        seen.add(item["sku"])
        unique.append(item)

    log(f"✅ Supabase kaynak ürünü: {len(unique)} benzersiz SKU")
    return unique

def load_failed_allowlist(path: str) -> List[dict]:
    """filtron_failed.json dosyasını okur. PROCESS_ONLY_FAILED modu için hatalı SKU listesi döner."""
    if not os.path.exists(path):
        log(f"FAILED_FILE bulunamadı: {path} (allowlist boş geçilecek)", "WARN")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        log("FAILED_FILE JSON formatı liste değil, allowlist boş geçiliyor.", "WARN")
        return []
    except Exception as e:
        log(f"FAILED_FILE okunamadı: {e}", "ERROR")
        return []


# =============================================================================
# SHOPIFY HELPERS
# =============================================================================

def shopify_get(url: str, params: Optional[dict] = None, timeout: int = 25) -> Optional[dict]:
    """Shopify Admin API'ye GET isteği atar. Hata durumunda None döner, log yazar."""
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
        if r.status_code != 200:
            log(f"Shopify GET {r.status_code} | {url} | {r.text[:200]}", "ERROR")
            return None
        return r.json()
    except Exception as e:
        log(f"Shopify GET exception: {type(e).__name__}: {e} | {url}", "ERROR")
        return None


def shopify_put(url: str, payload: dict, timeout: int = 25) -> Tuple[bool, str]:
    """Shopify Admin API'ye PUT isteği atar. (ok, mesaj) tuple döner."""
    try:
        r = requests.put(url, headers=HEADERS, data=json.dumps(payload), timeout=timeout)
        if r.status_code == 200:
            return True, "200 OK"
        return False, f"{r.status_code} {r.text[:250]}"
    except Exception as e:
        return False, f"EXC {type(e).__name__}: {e}"


def shopify_post(url: str, payload: dict, timeout: int = 25) -> Tuple[bool, str, Optional[dict]]:
    """Shopify Admin API'ye POST isteği atar. (ok, mesaj, response_dict) tuple döner."""
    try:
        r = requests.post(url, headers=HEADERS, data=json.dumps(payload), timeout=timeout)
        if r.status_code in (200, 201):
            return True, f"{r.status_code} OK", r.json()
        return False, f"{r.status_code} {r.text[:250]}", None
    except Exception as e:
        return False, f"EXC {type(e).__name__}: {e}", None


def load_all_products_since_id() -> List[dict]:
    """Shopify'daki tüm ürünleri since_id pagination ile çeker. 250'şer sayfalarda okur."""
    all_products: List[dict] = []
    since_id = 0
    log("Shopify ürünleri yükleniyor (since_id pagination) ...")
    while True:
        url = f"{BASE}/products.json"
        params = {"limit": 250, "since_id": since_id}
        data = shopify_get(url, params=params, timeout=30)
        if not data:
            break
        products = data.get("products", [])
        if not products:
            break
        all_products.extend(products)
        since_id = products[-1]["id"]
        log(f"  ✓ Çekilen: +{len(products)} | Toplam: {len(all_products)} | since_id: {since_id}")
        time.sleep(0.35)
    log(f"✅ Toplam {len(all_products)} ürün yüklendi")
    return all_products


def build_sku_index(products: List[dict]) -> Dict[str, dict]:
    """Shopify ürün listesinden normalize SKU → {product_id, variant_id, inventory_item_id} index'i oluşturur."""
    idx: Dict[str, dict] = {}
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
                    "shopify_sku_raw": raw_sku,
                }
    log(f"✅ SKU index oluşturuldu: {len(idx)} SKU")
    return idx


# =============================================================================
# SUPABASE SKU INDEX
# =============================================================================

def build_source_sku_index(items: List[dict]) -> Dict[str, dict]:
    """
    CSV item listesinden normalize SKU → item eşlemesi oluşturur.
    Shopify SKU index ile karşılaştırmada kullanılır.
    """
    idx: Dict[str, dict] = {}
    for it in items:
        idx[it["sku"]] = it
    log(f"📋 Supabase SKU index oluşturuldu: {len(idx)} benzersiz SKU")
    return idx


def print_source_index_preview(csv_sku_index: Dict[str, dict], limit: int = 10) -> None:
    """CSV index'inden ilk N satırı terminale bas."""
    print()
    print("─" * 65)
    print(f"  SUPABASE SKU INDEX — İlk {limit} kayıt")
    print("─" * 65)
    for i, (sku, it) in enumerate(list(csv_sku_index.items())[:limit]):
        print(f"  {i+1:3d}. norm={sku:<12}  external={it['external_code']:<16}"
              f"  fiyat={it['price']:<10}  tip={it['filter_type_raw']}")
    if len(csv_sku_index) > limit:
        print(f"  ... ve {len(csv_sku_index) - limit} kayıt daha")
    print("─" * 65)
    print()


def print_comparison_preview(csv_sku_index: Dict[str, dict],
                              sku_index: Dict[str, dict],
                              limit: int = 15) -> None:
    """CSV vs Shopify karşılaştırmasını terminale bas."""
    match_count = sum(1 for s in csv_sku_index if s in sku_index)
    new_count   = sum(1 for s in csv_sku_index if s not in sku_index)

    print()
    print("=" * 70)
    print("  SUPABASE ↔ SHOPİFY SKU KARŞILAŞTIRMA")
    print("=" * 70)
    print(f"  Supabase'te toplam benzersiz SKU  : {len(csv_sku_index)}")
    print(f"  Shopify'da toplam SKU        : {len(sku_index)}")
    print(f"  ✅ EŞLEŞİYOR (güncelleme)    : {match_count}")
    print(f"  🆕 YENİ (ürün açılacak)       : {new_count}")
    print()
    print(f"  İlk {limit} Supabase SKU için durum:")
    print("  " + "─" * 65)
    for i, (sku, it) in enumerate(list(csv_sku_index.items())[:limit]):
        if sku in sku_index:
            status    = "✅ VAR  → fiyat+stok güncelle"
            shp_raw   = sku_index[sku].get("shopify_sku_raw", sku_index[sku].get("title", "-"))
        else:
            status  = "🆕 YOK  → yeni ürün aç"
            shp_raw = "-"
        print(f"  {i+1:3d}. CSV={it['external_code']:<16} norm={sku:<12} | {status}")
    if len(csv_sku_index) > limit:
        print(f"  ... ve {len(csv_sku_index) - limit} kayıt daha")
    print("=" * 70)
    print()


# =============================================================================
# CANLI İSTATİSTİK
# =============================================================================

class LiveStats:
    """Terminal'e \r ile üst üste yazan canlı istatistik."""

    def __init__(self, total: int):
        """LiveStats sayaçlarını sıfırlar ve zamanlayıcıyı başlatır."""
        self.total     = total
        self.processed = 0
        self.updated   = 0
        self.created   = 0
        self.failed    = 0
        self.skipped   = 0
        self._start    = time.time()
        self._sku      = ""
        self._step     = ""

    def set_current(self, sku: str, step: str):
        """Şu an işlenen SKU ve adımı günceller, ekranı yeniler."""
        self._sku  = sku
        self._step = step
        self._print()

    def mark_updated(self, sku: str):
        """Bir SKU başarıyla güncellendi (fiyat+stok). Sayaçları artırır."""
        self.processed += 1; self.updated += 1
        self._sku = sku; self._step = "✅ GÜNCELLENDI"
        self._print()

    def mark_created(self, sku: str):
        """Bir SKU için yeni ürün başarıyla oluşturuldu. Sayaçları artırır."""
        self.processed += 1; self.created += 1
        self._sku = sku; self._step = "🆕 OLUŞTURULDU"
        self._print()

    def mark_failed(self, sku: str, reason: str = ""):
        """Bir SKU hata verdi. Hata sayacını artırır, sebebi ekranda gösterir."""
        self.processed += 1; self.failed += 1
        self._sku = sku; self._step = f"❌ HATA: {reason}"
        self._print()

    def mark_skipped(self, sku: str, reason: str = ""):
        """Bir SKU atlandı. Atlanan sayacını artırır."""
        self.processed += 1; self.skipped += 1
        self._sku = sku; self._step = f"⏭ ATLANDI: {reason}"
        self._print()

    def _elapsed(self) -> str:
        """Başlangıçtan bu yana geçen süreyi MM:SS formatında döner."""
        s = int(time.time() - self._start); m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}"

    def _eta(self) -> str:
        """Kalan süreyi (tahmini) MM:SS formatında hesaplar. İşlem hızına göre dinamiktir."""
        if self.processed == 0:
            return "--:--"
        rate   = self.processed / (time.time() - self._start)
        remain = self.total - self.processed
        if rate == 0:
            return "--:--"
        s = int(remain / rate); m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}"

    def _print(self):
        """Canlı istatistik satırını \r ile terminal'e yazar (üst üste günceller)."""
        pct  = (self.processed / self.total * 100) if self.total else 0
        line = (
            f"\r[{self._elapsed()} / ETA {self._eta()}] "
            f"{self.processed}/{self.total} ({pct:.1f}%) | "
            f"🔄 Güncelleme:{self.updated} "
            f"🆕 Yeni:{self.created} "
            f"❌ Hata:{self.failed} "
            f"| SKU={self._sku} → {self._step}"
        )
        try:
            width = os.get_terminal_size().columns
        except Exception:
            width = 160
        import sys
        sys.stdout.write(line[:width].ljust(width))
        sys.stdout.flush()

    def print_summary(self):
        """İşlem bitince özet tabloyu terminal'e basar: toplam/güncellenen/yeni/hatalı/süre."""
        elapsed = int(time.time() - self._start)
        m, s    = divmod(elapsed, 60)
        print()
        print()
        print("=" * 70)
        print("  FILTRON SEO ENRICHER — ÖZET RAPOR")
        print("=" * 70)
        print(f"  Toplam Supabase SKU            : {self.total}")
        print(f"  İşlenen                   : {self.processed}")
        print(f"  ✅ Fiyat+Stok Güncelleme  : {self.updated}")
        print(f"  🆕 Yeni Ürün Oluşturma    : {self.created}")
        print(f"  ❌ Hatalı                 : {self.failed}")
        print(f"  ⏭  Atlanan                : {self.skipped}")
        print(f"  Geçen süre                : {m:02d}:{s:02d}")
        print("=" * 70)
        print()


def get_primary_location_id() -> Optional[int]:
    """Shopify mağazasının aktif location ID'sini döner. Stok güncellemesi için gerekli."""
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
    """Belirli bir ürün için stok miktarını ayarlar. DRY_RUN=1 ise gerçek istek atmaz."""
    url = f"{BASE}/inventory_levels/set.json"
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": int(available),
    }
    if DRY_RUN:
        log(f"[DRY_RUN] inventory set -> inventory_item_id={inventory_item_id} "
            f"loc={location_id} avail={available}")
        return True
    ok, msg, _ = shopify_post(url, payload, timeout=25)
    if not ok:
        log(f"Inventory set failed: {msg}", "ERROR")
    return ok


def create_product_for_csv_item(item: dict) -> Optional[dict]:
    """
    Yeni ürün oluşturur.
    - SKU: Normalize edilmiş (AK381)
    - Barcode: BOŞ (None)
    - Title: Boşluklu kod ile (FILTRON AK 381 ...)
    - Images: Katalog sayfasından scrape edilir
    """
    sku = item["sku"]  # AK381
    external_code = item["external_code"]  # AK 381
    filter_type_raw = item["filter_type_raw"]
    filter_type_title = filter_type_for_title(filter_type_raw)
    price = item["price"]
    
    # Öncelik: Supabase'teki URL'ler. Yoksa FILTRON sayfasından fallback scrape.
    image_urls = list(item.get("image_urls") or [])
    if not image_urls:
        image_urls = build_filtron_image_urls(external_code, sku)
    images_payload = [{"src": url} for url in image_urls if url]

    # Başlıkta boşluklu kod kullan
    title_code = external_code  # AK 381

    url = f"{BASE}/products.json"
    payload = {
        "product": {
            "title": f"FILTRON {title_code} {filter_type_title}".strip(),
            "vendor": "FILTRON",
            "product_type": filter_type_title,
            "tags": ", ".join([x for x in [external_code, filter_type_title, "FILTRON"] if x]),
            "status": CREATE_STATUS,
            "published": True,
            "images": images_payload,
            "variants": [{
                "sku": sku,  # AK381 (normalize)
                "barcode": None,  # BOŞ
                "price": price,
                "inventory_management": "shopify",
                "inventory_policy": "deny",
                "fulfillment_service": "manual",
                "requires_shipping": True,
            }],
        }
    }

    if DRY_RUN:
        log(f"[DRY_RUN] CREATE product -> sku={sku} external={external_code} price={price}")
        return {
            "product": {
                "id": 0,
                "variants": [{"id": 0, "sku": sku, "inventory_item_id": 0}],
            }
        }

    ok, msg, data = shopify_post(url, payload, timeout=30)
    if not ok or not data or "product" not in data:
        log(f"CREATE failed for {sku} -> {msg}", "ERROR")
        return None
    log(f"✅ CREATED: {sku} | pid={data['product'].get('id')}")
    return data


def update_variant_price_and_sku(variant_id: int, price: str, sku_normalized: str) -> bool:
    """
    Variant günceller:
    - Price
    - SKU: Normalize edilmiş (AK381)
    - Barcode: None (boş)
    """
    url = f"{BASE}/variants/{variant_id}.json"
    payload = {"variant": {"id": int(variant_id)}}
    
    if UPDATE_PRICE:
        payload["variant"]["price"] = str(price)
    
    if UPDATE_SKU_ON_SHOPIFY:
        payload["variant"]["sku"] = sku_normalized  # AK381
        payload["variant"]["barcode"] = None  # BOŞ

    if DRY_RUN:
        log(f"[DRY_RUN] variant update -> vid={variant_id} price={price} sku={sku_normalized} barcode=None")
        return True

    ok, msg = shopify_put(url, payload, timeout=25)
    if not ok:
        log(f"Variant update failed -> {msg}", "ERROR")
    return ok


def upsert_metafield(product_id: int, namespace: str, key: str, mtype: str, value: str) -> bool:
    """Ürün metafield'ını oluşturur veya günceller (namespace.key bazlı). PUT veya POST seçer."""
    url_list = f"{BASE}/products/{product_id}/metafields.json"
    data = shopify_get(url_list, timeout=25)
    if not data:
        return False

    metafields = data.get("metafields", []) or []
    existing_id = None
    for m in metafields:
        if m.get("namespace") == namespace and m.get("key") == key:
            existing_id = m.get("id")
            break

    payload = {
        "metafield": {
            "namespace": namespace,
            "key": key,
            "type": mtype,
            "value": value,
        }
    }

    if existing_id:
        url_put = f"{BASE}/metafields/{existing_id}.json"
        ok, msg = shopify_put(url_put, payload, timeout=25)
        if not ok:
            log(f"Metafield UPDATE failed: {namespace}.{key} -> {msg}", "ERROR")
        return ok

    ok, msg, _ = shopify_post(url_list, payload, timeout=25)
    if not ok:
        log(f"Metafield CREATE failed: {namespace}.{key} -> {msg}", "ERROR")
    return ok


def _plain_text(value: str) -> str:
    """HTML veya düz metni JSON-LD için güvenli plain text'e çevirir."""
    if not value:
        return ""
    return BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)


def upsert_seo_structured_data(
    product_id: int,
    canonical_sku: str,
    external_code: str,
    filter_type_title: str,
    price: str,
    stock_qty: int,
    meta_desc: str = "",
    mann_display: Optional[str] = None,
    total_models: int = 0,
) -> bool:
    """Ürün Product JSON-LD'sini custom.seo_structured_data metafield'ına yazar."""
    if not WRITE_SEO_STRUCTURED_METAFIELD:
        return True

    if DRY_RUN:
        log(
            f"[DRY_RUN] seo_structured_data -> pid={product_id} "
            f"sku={canonical_sku} type={filter_type_title} stock={stock_qty}"
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

    description = _plain_text(meta_desc) or _plain_text(product.get("body_html") or product.get("title") or "")
    document = {
        "@context": "https://schema.org",
        "@type": "Product",
        "@id": f"{storefront_url}#product",
        "url": storefront_url,
        "name": str(product.get("title") or f"FILTRON {external_code or canonical_sku} {filter_type_title}").strip(),
        "image": images,
        "description": description,
        "sku": canonical_sku,
        "mpn": external_code or canonical_sku,
        "brand": {"@type": "Brand", "name": "FILTRON"},
        "category": filter_type_title,
        "offers": {
            "@type": "Offer",
            "url": storefront_url,
            "priceCurrency": "TRY",
            "price": str(price),
            "availability": "https://schema.org/InStock" if int(stock_qty or 0) > 0 else "https://schema.org/OutOfStock",
            "itemCondition": "https://schema.org/NewCondition",
            "seller": {"@type": "Organization", "name": "FiltreOto"},
        },
    }
    properties = [
        {"@type": "PropertyValue", "name": "Filtre Türü", "value": filter_type_title},
        {"@type": "PropertyValue", "name": "OEM / Ürün Kodu", "value": external_code or canonical_sku},
    ]
    if mann_display:
        properties.append({"@type": "PropertyValue", "name": "MANN-FILTER Kodu", "value": mann_display})
    if total_models:
        properties.append({"@type": "PropertyValue", "name": "Uyumlu Araç Sayısı", "value": f"{int(total_models)} Model"})
    document["additionalProperty"] = properties

    return upsert_metafield(
        product_id,
        "custom",
        "seo_structured_data",
        "json",
        json.dumps(document, ensure_ascii=False, separators=(",", ":")),
    )


def normalize_brand_key(name: str) -> str:
    """Marka ismini karşılaştırma için büyük harfe ve strip'e getirir."""
    return (name or "").strip().upper()


def pretty_brand_title_from_upper(upper_name: str) -> str:
    """Büyük harfli marka ismini Title Case'e çevirir. 3 harf ve altı kısaltmalar büyük kalır."""
    parts = upper_name.split()
    pretty_parts: List[str] = []
    for p in parts:
        if len(p) <= 3 and p.isalpha():
            pretty_parts.append(p)
        else:
            pretty_parts.append(p.title())
    return " ".join(pretty_parts)


def get_or_create_brand_collection_id(brand_title: str) -> Optional[int]:
    """Shopify'da marka koleksiyonunu bulur, yoksa oluşturur. Koleksiyon ID döner."""
    title = (brand_title or "").strip()
    if not title:
        return None

    params = {"title": title}
    data = shopify_get(f"{BASE}/custom_collections.json", params=params, timeout=25)
    if data and data.get("custom_collections"):
        try:
            return int(data["custom_collections"][0]["id"])
        except Exception:
            pass

    if DRY_RUN:
        log(f"[DRY_RUN] custom collection create -> '{title}'", "INFO")
        return None

    payload = {"custom_collection": {"title": title, "published": True}}
    ok, msg, resp = shopify_post(
        f"{BASE}/custom_collections.json",
        payload,
        timeout=25,
    )
    if not ok or not resp or "custom_collection" not in resp:
        log(f"Custom collection create failed '{title}': {msg}", "ERROR")
        return None

    cid = int(resp["custom_collection"]["id"])
    log(f"✅ Custom collection: {title} | id={cid}")
    return cid


def ensure_product_in_collection(product_id: int, collection_id: int) -> bool:
    """Ürünü koleksiyona ekler. Zaten ekliyse tekrar eklemez."""
    if DRY_RUN:
        log(f"[DRY_RUN] collect create -> pid={product_id}, cid={collection_id}", "INFO")
        return True

    params = {"product_id": product_id, "collection_id": collection_id}
    data = shopify_get(f"{BASE}/collects.json", params=params, timeout=25)
    if data and data.get("collects"):
        return True

    payload = {"collect": {"product_id": int(product_id), "collection_id": int(collection_id)}}
    ok, msg, _ = shopify_post(f"{BASE}/collects.json", payload, timeout=25)
    if not ok:
        log(f"Collect create failed pid={product_id}, cid={collection_id}: {msg}", "ERROR")
        return False

    log(f"✅ Collect: pid={product_id} -> cid={collection_id}")
    return True


def ensure_brand_collections_for_product(product_id: int, vehicles: Dict[str, List[str]]) -> None:
    """Ürünün uyumlu araç markalarına göre koleksiyonlar oluşturur ve ürünü atar."""
    if not vehicles:
        return

    for brand in vehicles.keys():
        brand_upper = normalize_brand_key(brand)
        if brand_upper not in ALLOWED_VEHICLE_BRANDS:
            log(f"Brand '{brand}' beyaz listede değil, koleksiyon atlanıyor.", "INFO")
            continue

        pretty_title = pretty_brand_title_from_upper(brand_upper)
        cid = get_or_create_brand_collection_id(pretty_title)
        if cid:
            ensure_product_in_collection(product_id, cid)
            time.sleep(0.2)


def update_product_type_and_category_tag(product_id: int, filter_type_title: str) -> bool:
    """Mevcut FILTRON ürününde product_type ve kategori etiketini standardize eder."""
    standard = normalize_filter_type(filter_type_title)
    if DRY_RUN:
        log(f"[DRY_RUN] product_type/tag update -> pid={product_id} type={standard}")
        return True

    data = shopify_get(f"{BASE}/products/{product_id}.json", timeout=25)
    product = (data or {}).get("product") or {}
    if not product:
        log(f"Ürün GET başarısız; tag/type PUT yapılmayacak pid={product_id}", "ERROR")
        return False
    existing_tags = [x.strip() for x in str(product.get("tags") or "").split(",") if x.strip()]
    category_aliases = {
        "hava filtresi", "hava filtresi", "yag filtresi", "yağ filtresi",
        "yakit filtresi", "yakıt filtresi", "polen filtresi", "kabin hava filtresi",
    }
    kept = [tag for tag in existing_tags if normalize_filter_type(tag).casefold() not in category_aliases]
    if not any(tag.casefold() == standard.casefold() for tag in kept):
        kept.append(standard)

    payload = {"product": {
        "id": int(product_id),
        "product_type": standard,
    }}
    if UPDATE_TAGS:
        payload["product"]["tags"] = ", ".join(kept)
    ok, msg = shopify_put(f"{BASE}/products/{product_id}.json", payload, timeout=25)
    if not ok:
        log(f"Ürün türü/etiket güncelleme başarısız pid={product_id}: {msg}", "ERROR")
    return ok


def set_product_handle_safe(product_id: int, desired_handle: str, sku: str) -> bool:
    """Ürün URL handle'ını yazar. Çakışma varsa SKU suffix ekleyerek tekrar dener."""
    if DRY_RUN:
        log(f"[DRY_RUN] handle set -> pid={product_id} handle={desired_handle}")
        return True

    base = slugify_tr(desired_handle)
    sku_suf = normalize_sku(sku).lower()

    candidates = [base, f"{base}-{sku_suf}", f"{base}-{sku_suf}-2", f"{base}-{sku_suf}-3"]

    for h in candidates:
        payload = {"product": {"id": int(product_id), "handle": h}}
        ok, msg = shopify_put(f"{BASE}/products/{product_id}.json", payload, timeout=25)
        if ok:
            log(f"✅ Handle set: pid={product_id} -> {h}")
            return True

        low = (msg or "").lower()
        if "handle" in low and ("taken" in low or "already been" in low):
            log(f"⚠️ Handle taken, retry: {h} -> {msg}", "WARN")
            continue

        log(f"⚠️ Handle skipped (non-taken error): pid={product_id} msg={msg}", "WARN")
        return False

    log(f"⚠️ Handle skipped (all candidates taken): pid={product_id} base={base}", "WARN")
    return False


# =============================================================================
# TITLE / META / TAGS
# =============================================================================

def make_filtron_title(
    sku: str,
    external_code: Optional[str],
    filter_type_title: str,
    mann_display: Optional[str],
    top_brands: Optional[List[str]] = None,
) -> str:
    """
    Başlık formatı (MAX 70 karakter):
    FILTRON AP 157/6 Hava Filtresi | Eşdeğer: MANN C 4312/1 | Mercedes-Benz
    
    AKILLI MARKA SİSTEMİ:
    1. Önce 1 marka ekle → sığıyorsa ✅
    2. 2 marka dene → sığıyorsa ✅
    3. 3 marka dene → sığıyorsa ✅
    4. Sığmıyorsa bir önceki sığanı kullan
    
    Öncelik:
    - Her zaman "Eşdeğer: MANN" formatı
    - Filtre tipi gerekirse kısalt
    - Mümkün olduğunca çok marka ekle
    """
    TITLE_LIMIT = 70
    
    code = external_code or sku
    
    # Filtre tipi kısaltmaları
    type_short_map = {
        "Hava Filtresi": "Hava Filt.",
        "Yağ Filtresi": "Yağ Filt.",
        "Polen Filtresi": "Polen Filt.",
        "Yakıt Filtresi": "Yakıt Filt.",
        "Hidrolik Şanzıman Filtresi": "Hidrolik Filt.",
        "Kabin Hava Filtresi": "Kabin Filt.",
    }
    
    type_full = filter_type_title
    type_short = type_short_map.get(filter_type_title, filter_type_title[:10] + ".")
    
    # MANN kodu
    mann = mann_display if mann_display else ""
    
    # Marka yoksa basit başlık
    if not top_brands or len(top_brands) == 0:
        if mann:
            base = f"FILTRON {code} {type_full} | Eşdeğer: MANN {mann}"
            if len(base) <= TITLE_LIMIT:
                return base
            base_short = f"FILTRON {code} {type_short} | Eşdeğer: MANN {mann}"
            return base_short[:TITLE_LIMIT].rstrip(" -|/")
        else:
            return f"FILTRON {code} {type_full}"[:TITLE_LIMIT].rstrip(" -|/")
    
    # AKILLI MARKA EKLEME FONKSİYONU
    def try_add_brands(base_title, brands_list, max_brands=3):
        """
        Markaları teker teker ekleyerek en fazla sığanı bulur.
        Returns: (best_title, brands_used_count)
        """
        best_title = base_title
        brands_used = 0
        
        for count in range(1, min(len(brands_list) + 1, max_brands + 1)):
            # count kadar marka ekle
            brand_part = " / ".join(brands_list[:count])
            attempt = f"{base_title} | {brand_part}"
            
            if len(attempt) <= TITLE_LIMIT:
                best_title = attempt
                brands_used = count
            else:
                # Sığmadı, önceki en iyisini dön
                break
        
        return best_title, brands_used
    
    # STRATEJI 1: FULL TİP + EŞDEĞER + MARKALAR
    if mann:
        base = f"FILTRON {code} {type_full} | Eşdeğer: MANN {mann}"
        if len(base) <= TITLE_LIMIT:
            # Base sığdı, marka eklemeyi dene
            result, count = try_add_brands(base, top_brands, max_brands=3)
            if count > 0:
                return result
            # Hiç marka sığmadı ama base sığıyor
            return base
    
    # STRATEJI 2: KISA TİP + EŞDEĞER + MARKALAR
    if mann:
        base = f"FILTRON {code} {type_short} | Eşdeğer: MANN {mann}"
        if len(base) <= TITLE_LIMIT:
            result, count = try_add_brands(base, top_brands, max_brands=3)
            if count > 0:
                return result
            return base
    
    # STRATEJI 3: MANN YOKSA - FULL TİP + MARKALAR
    base = f"FILTRON {code} {type_full}"
    if len(base) <= TITLE_LIMIT:
        result, count = try_add_brands(base, top_brands, max_brands=3)
        if count > 0:
            return result
        return base
    
    # STRATEJI 4: MANN YOKSA - KISA TİP + MARKALAR
    base = f"FILTRON {code} {type_short}"
    result, count = try_add_brands(base, top_brands, max_brands=3)
    if count > 0:
        return result
    
    # Son çare
    return base[:TITLE_LIMIT].rstrip(" -|/")


def format_brand_title_case(brand: str) -> str:
    """
    Marka ismini Title Case'e çevirir.
    MERCEDES-BENZ → Mercedes-Benz
    VW → VW (kısaltmalar olduğu gibi kalır)
    EVOBUS (MERCEDES-BENZ/SETRA) → Evobus
    """
    brand = brand.strip()
    
    # Parantez içini temizle
    if "(" in brand:
        brand = brand.split("(")[0].strip()
    
    # Tire ile ayrılmış kelimeler (Mercedes-Benz)
    if "-" in brand:
        parts = brand.split("-")
        return "-".join(p.title() for p in parts)
    
    # Boşlukla ayrılmış (Land Rover)
    if " " in brand:
        return " ".join(p.title() for p in brand.split())
    
    # Tek kelime
    # Kısaltmalar büyük kalır (BMW, VW, VDL)
    if len(brand) <= 3 and brand.isupper():
        return brand
    
    return brand.title()


def build_meta_description_rotating(
    sku: str,
    external_code: str,
    filter_type_raw: str,
    mann_display: Optional[str],
    top_brands: List[str],
    index: int
) -> str:
    """
    9 farklı meta description template'inden birini seçer (rotating system).
    Her ürün farklı bir varyasyon alır, 10. üründe başa döner.
    
    Args:
        sku: Normalize SKU (AP1576)
        external_code: Boşluklu kod (AP 157/6)
        filter_type_raw: Filtre tipi (Hava Filtresi)
        mann_display: MANN kodu (C 4312/1)
        top_brands: Marka listesi (Mercedes-Benz, Volkswagen)
        index: CSV satır numarası veya ürün indeksi (döngü için)
    
    Returns:
        Max 160 karakterlik meta description
    """
    # Template seçimi (0-8 arası döngü)
    template_index = index % 9
    
    # Parametreler hazırla
    code = external_code or sku
    
    # Filtre tipi kısaltması (bazı template'ler için)
    type_short = filter_type_raw.replace(" Filtresi", "")
    
    # MANN kodu
    mann = mann_display if mann_display else "katalog eşdeğeri"
    
    # Platform metni oluştur (kısa ve öz)
    if top_brands and len(top_brands) > 0:
        if len(top_brands) == 1:
            platform = top_brands[0]
        else:
            # İki marka varsa kısalt
            # "Mercedes-Benz & Volkswagen" → "Mercedes & VW"
            brand1 = top_brands[0]
            if "-" in brand1:
                brand1 = brand1.split("-")[0]  # Mercedes-Benz → Mercedes
            
            brand2 = top_brands[1]
            # Uzun markayı kısalt
            if len(brand2) > 10:
                brand2 = brand2[:3]  # Volkswagen → Vol
            
            platform = f"{brand1} & {brand2}"
    else:
        platform = "Çeşitli araçlar"
    
    # Platform detaylı (bazı template'ler için model bilgili)
    platform_detail = platform  # Şimdilik aynı, gerekirse genişletilebilir
    
    # 9 FARKLI TEMPLATE
    templates = [
        # V1: Ürün + Eşdeğer + Platform (Standart)
        f"✅ FILTRON {code} {filter_type_raw} | MANN {mann} eşdeğeri. {platform} uyumlu. 🚚 Hızlı kargo 🔒 Güvenli alışveriş",
        
        # V2: Muadil vurgusu + Şase kontrolü
        f"FILTRON {code} {filter_type_raw} - MANN {mann} muadili. {platform} uyumlu. 🚚 Aynı gün kargo 📋 Şase ile kontrol",
        
        # V3: Kısa format + 3 emoji
        f"✅ {code} {filter_type_raw} | MANN {mann} eşdeğer. {platform} için. 🚚 Hızlı kargo 🔁 Kolay iade 🔒 Güvenli ödeme",
        
        # V4: MANN-FILTER onay vurgusu
        f"FILTRON {code} - MANN {mann} muadil. {platform} uyumlu. 📋 MANN-FILTER onaylı 🚚 Aynı gün kargo 🔒 Faturalı satış",
        
        # V5: Platform önce (ters sıralama)
        f"✅ {platform} için {code} {filter_type_raw} | MANN {mann} eşdeğer. 🚚 Hızlı teslimat 🔁 Kolay iade garantisi",
        
        # V6: Şase kontrolü vurgusu
        f"FILTRON {code} | MANN {mann} eşdeğer {type_short}. {platform} için. 📋 Şase kontrolü 🚚 Hızlı kargo 🔒 Güvenli ödeme",
        
        # V7: Aksiyon CTA (ateş emojisi)
        f"🔥 FILTRON {code} {filter_type_raw} | MANN {mann} muadil. {platform} uyumlu. ✅ Aynı gün kargo ✅ Kolay iade. Al!",
        
        # V8: Üçlü bilgi (kod | muadil | platform)
        f"✅ {code} | MANN {mann} eşdeğer | {platform}. 🚚 Hızlı kargo 🔁 Kolay iade 🔒 Güvenli alışveriş. Şase kontrol!",
        
        # V9: Platform ünlem + kısa CTA
        f"FILTRON {code} {filter_type_raw} - {platform} uyumlu! MANN {mann} muadil. 🚚 Aynı gün kargo 📋 MANN onaylı 🔒 Al!"
    ]
    
    # Seçili template'i al
    meta = templates[template_index]
    
    # 160 karakter limiti - kelime ortadan bölmeden kırp
    if len(meta) > 160:
        # Son tam kelimeyi bul
        truncated = meta[:157]
        last_space = truncated.rfind(' ')
        if last_space > 140:  # Çok kısa olmasın
            meta = truncated[:last_space] + "..."
        else:
            meta = truncated + "..."
    
    return meta


def build_meta_description(
    sku: str,
    external_code: str,
    filter_type_raw: str,
    mann_display: Optional[str],
) -> str:
    """
    DEPRECATED: Eski tek varyasyon fonksiyonu.
    Geriye dönük uyumluluk için korunuyor.
    Yeni kod build_meta_description_rotating() kullanmalı.
    """
    code = external_code or sku
    if mann_display:
        txt = (
            f"✅ FILTRON {code} {filter_type_raw} | {mann_display} eşdeğeri. "
            f"🚚 Hızlı kargo ve 🔒 güvenli alışverişle hemen satın alın!"
        )
    else:
        txt = (
            f"✅ FILTRON {code} {filter_type_raw}. "
            f"🚚 Hızlı kargo ve 🔒 güvenli alışverişle hemen satın alın!"
        )
    return txt[:160]


def build_tags_csv(external_code: str, filter_type_raw: str, mann_display: Optional[str]) -> str:
    """
    Etiketler:
    - Boşluklu external code (AK 381)
    - Filter type
    - FILTRON
    - MANN kod (varsa)
    
    NOT: Normalize edilmiş SKU (AK381) ETİKETLERE EKLENMİYOR
    """
    tags: List[str] = []
    
    # Boşluklu kod (AK 381)
    if external_code:
        tags.append(external_code.strip())

    # Filter type
    ft = normalize_filter_type(filter_type_raw)
    if ft:
        tags.append(ft)
    
    # Marka
    tags.append("FILTRON")

    # MANN kod
    if mann_display:
        tags.append(mann_display.strip())

    # Deduplicate
    seen = set()
    out = []
    for t in tags:
        t2 = (t or "").strip()
        if not t2:
            continue
        k = t2.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t2)

    return ", ".join(out)


# =============================================================================
# MANN
# =============================================================================

def build_mann_headers(referer: str) -> dict:
    """Mann-Filter API için gerekli HTTP header'larını oluşturur."""
    return {
        **UA_HEADERS,
        "Content-Type": "application/json",
        "Referer": referer,
        "Store": "pcat_mf_tr_store_tr",
    }


def format_mann_display_from_raw(mann_raw: str) -> str:
    """Ham Mann SKU'sunu okunabilir formata çevirir. Örn: C43121 → C 4312/1"""
    raw = (mann_raw or "").upper().replace("_MANN-FILTER", "").strip()
    raw = raw.replace("-", "").replace("_", "").replace("／", "/")
    raw_compact = raw.replace(" ", "")

    m = re.match(r"^(CUK|CU)(\d{5})$", raw_compact)
    if m:
        prefix = m.group(1)
        digits = m.group(2)
        return f"{prefix} {digits[:4]}/{digits[4]}"

    m2 = re.match(r"^([A-Z]+)(\d{5})$", raw_compact)
    if m2:
        prefix = m2.group(1)
        digits = m2.group(2)
        return f"{prefix} {digits[:2]} {digits[2:]}"

    m4 = re.match(r"^([A-Z]+)(\d{4})$", raw_compact)
    if m4:
        return f"{m4.group(1)} {m4.group(2)}"

    return raw.strip()


def mann_crossref_lookup_filtron(filtron_sku: str, external_code: Optional[str] = None) -> Optional[dict]:
    """Mann-Filter GraphQL API'sinde Filtron SKU karşılığını arar. Mann kodu ve ürün URL'ini döner."""
    def n(x: str) -> str:
        """Arama terimi için normalize yardımcı fonksiyon."""
        return normalize_sku(x).upper()

    candidates = []
    if external_code:
        candidates.append(external_code)
    candidates.append(filtron_sku)

    for search_term in candidates:
        search_norm = n(search_term)
        if not search_norm:
            continue

        referer = (
            "https://www.mann-filter.com/tr-tr/katalog/arama-sonuclar%C4%B1.html"
            f"?mode=crossReference&displayView=Grid&crossReference={search_norm}"
        )
        params = {
            "query": MANN_QUERY_CROSSREF,
            "variables": json.dumps(
                {
                    "search": search_norm,
                    "currentPage": 1,
                    "pageSize": 25,
                    "filterBy": "ALL_FILTER",
                },
                ensure_ascii=False,
            ),
        }

        try:
            r = requests.get(MANN_GQL, params=params, headers=build_mann_headers(referer), timeout=20)
        except Exception as e:
            log(f"MANN GraphQL exception: {type(e).__name__}: {e}", "WARN")
            continue

        if r.status_code != 200:
            log(f"MANN GraphQL HTTP {r.status_code} | {r.text[:200]}", "WARN")
            continue

        try:
            data = r.json()
        except Exception:
            log("MANN GraphQL: JSON parse failed", "WARN")
            continue

        items = data.get("data", {}).get("catalogSearch", {}).get("items", []) or []
        if not items:
            continue

        filtron_rows = []
        for it in items:
            if n(it.get("manufacturer") or "") != "FILTRON":
                continue
            ext = n(it.get("externalNumber") or it.get("externalProductName") or "")
            if not ext:
                continue

            if search_norm in ext or ext in search_norm:
                filtron_rows.append(it)

        if not filtron_rows:
            continue

        row = filtron_rows[0]
        product = row.get("product") or {}
        url_key = (product.get("urlKey") or "").strip()
        if not url_key:
            continue

        mann_sales = None
        for a in (product.get("attributes") or []):
            if (a.get("key") or "").lower() == "sales_designation":
                mann_sales = (a.get("value") or a.get("adminValue") or "").strip()
                if mann_sales:
                    break

        mann_raw = (product.get("sku") or "").replace("_MANN-FILTER", "").strip()
        mann_display = mann_sales if mann_sales else format_mann_display_from_raw(mann_raw)

        product_url = (
            "https://www.mann-filter.com/tr-tr/katalog/arama-sonuclar%C4%B1/urun.html/"
            f"{url_key}.html"
        )
        return {
            "mann_display": mann_display,
            "mann_raw": mann_raw,
            "url_key": url_key,
            "product_url": product_url,
            "referer": referer,
        }

    return None


# =============================================================================
# FITMENT (HEADING ONLY)
# =============================================================================

def mann_scrape_fitment_from_product_url(product_url: str, referer: str) -> Optional[dict]:
    """Mann-Filter ürün sayfasını scrape eder. "Araçlar / Uygulamalar" bölümünden marka/model listesi çıkarır."""
    log(f"MANN product scrape -> {product_url}")
    try:
        r = requests.get(product_url, headers=build_mann_headers(referer), timeout=25)
        log(f"MANN HTTP {r.status_code} | {product_url}")
        if r.status_code != 200 or not r.text or len(r.text) < 800:
            return None
        html = r.text
    except Exception as e:
        log(f"MANN request exception: {type(e).__name__}: {e}", "WARN")
        return None

    soup = BeautifulSoup(html, "html.parser")

    def clean(s: str) -> str:
        """HTML parse sırasında whitespace temizleme yardımcısı."""
        return re.sub(r"\s+", " ", (s or "").strip())

    apps_head = None
    for tag in soup.find_all(["h2", "h3", "h4"]):
        t = clean(tag.get_text(" ", strip=True))
        if "Araçlar / Uygulamalar" in t:
            apps_head = tag
            break

    if not apps_head:
        log("MANN: 'Araçlar / Uygulamalar' heading bulunamadı", "WARN")
        return None

    stop_markers = ("OE Numaraları", "İndirilebilir Dosyalar", "Hukuki Bilgiler")

    # Brand headings: only accept real vehicle brands (whitelist based)
    def normalize_brand_heading(txt: str) -> Optional[str]:
        """Heading metnini marka adıyla beyaz listeye göre eşleştirir. Eşleşmezse None döner."""
        s = clean(txt)
        if not s:
            return None
        up = s.upper()

        # normalize common "BRAND (DETAIL)" formats
        base = up.split("(")[0].strip() if "(" in up else up

        # exact / base match against whitelist
        if up in ALLOWED_VEHICLE_BRANDS:
            return up
        if base in ALLOWED_VEHICLE_BRANDS:
            return base

        # common catalog variants
        if "VOLKSWAGEN" in up and "VW" in ALLOWED_VEHICLE_BRANDS:
            return "VW"
        if up.startswith("VW") and "VW" in ALLOWED_VEHICLE_BRANDS:
            return "VW"
        if up == "VOLVO" and "VOLVO CARS" in ALLOWED_VEHICLE_BRANDS:
            return "VOLVO CARS"

        return None

    applications: List[dict] = []
    current_brand: Optional[str] = None
    seen = set()

    for tag in apps_head.find_all_next(["h2", "h3", "h4", "h5"]):
        t = clean(tag.get_text(" ", strip=True))
        if not t:
            continue
        if any(m in t for m in stop_markers):
            break
        if "Araçlar / Uygulamalar" in t:
            continue

        norm_brand = normalize_brand_heading(t)
        if norm_brand:
            current_brand = norm_brand
            continue

        if current_brand:
            model = t.strip()
            key = (current_brand.lower(), model.lower())
            if key in seen:
                continue
            seen.add(key)
            applications.append({"brand": current_brand, "model": model})

    if PRINT_PARSE_DEBUG:
        log(f"DEBUG heading applications sample: {applications[:50]}")

    if not applications:
        log("MANN: fitment boş (applications=0)", "WARN")
        return None

    time.sleep(MANN_SLEEP)
    return {"applications": applications, "source_url": product_url}


def parse_vehicles(app_data: dict) -> Dict[str, List[str]]:
    """Fitment app_data sözlüğünü {marka: [model listesi]} yapısına dönüştürür."""
    vehicles: Dict[str, List[str]] = {}
    if not app_data:
        return vehicles
    for app in app_data.get("applications", []):
        brand = (app.get("brand") or "").strip()
        model = (app.get("model") or "").strip()
        if not brand or not model:
            continue
        vehicles.setdefault(brand, [])
        if model not in vehicles[brand]:
            vehicles[brand].append(model)
    return vehicles


def vehicles_stats(vehicles: Dict[str, List[str]]) -> Tuple[int, List[Tuple[str, int]]]:
    """Araç uyumluluk istatistiği üretir: toplam model sayısı ve marka başına model sayısı ranking'i."""
    total = sum(len(m) for m in vehicles.values())
    ranked = sorted(
        ((b, len(m)) for b, m in vehicles.items()),
        key=lambda x: x[1],
        reverse=True,
    )
    return total, ranked


def build_fitment_html_longtail(vehicles: Dict[str, List[str]]) -> str:
    """Uzun format araç listesi HTML'i üretir. Long-tail SEO için marka + model listesi içerir."""
    if not vehicles:
        return ""
    total_models, ranked = vehicles_stats(vehicles)
    shown = 0
    parts: List[str] = []

    for brand, _cnt in ranked:
        models = vehicles.get(brand, [])
        if not models:
            continue

        take = models[:BODY_MAX_MODELS_PER_BRAND]
        if not take:
            continue

        chunk = [f"<strong>{brand}:</strong><br>"]
        for m in take:
            chunk.append(f"&nbsp;&nbsp;- {m}<br>")
            shown += 1
            if shown >= BODY_MAX_TOTAL_MODELS:
                break

        if len(models) > len(take):
            remain = len(models) - len(take)
            chunk.append(f"&nbsp;&nbsp;<em>... (ve {remain} model daha)</em><br>")

        parts.append("".join(chunk).rstrip("<br>"))
        if shown >= BODY_MAX_TOTAL_MODELS:
            break

    if total_models > shown:
        parts.append(
            f"<p><em>Not: Toplam {total_models} model uyumluluğu vardır. "
            f"Tam liste ürün metafield'ında saklanır.</em></p>"
        )

    return "<br>".join(parts)


# =============================================================================
# HTML (BODY) - ENHANCED SEO TEMPLATE
# =============================================================================

def build_filtron_catalog_url(code: str) -> str:
    """
    FILTRON katalog URL'i oluşturur.
    Önemli: AP 157/6 gibi kodlar için URL: ap157/6_filtron.html (slash korunur)
    """
    # Orijinal kodu al, sadece boşlukları kaldır, slash ve rakamları koru
    url_code = re.sub(r'\s+', '', (code or "").strip()).lower()
    return f"https://filtron.eu/tr/filtreyi-bul/arama-sonuclar%C4%B1/urun.html/{url_code}_filtron.html"


def inject_platform_to_intro(intro_html: str, top_brands: List[str], external_code: str, filter_type_raw: str) -> str:
    """
    OpenAI'den gelen intro_html'in ilk paragrafını platformla değiştirir.
    
    ÖNEMLİ:
    - Yağ filtresi → "motor yağındaki kirleticileri filtreler"
    - Hava filtresi → "toz ve zararlı partiküllere karşı korur"
    - Polen filtresi → "kabin havasını temizler"
    - 2 PARAGRAF MAX (3. paragrafı kaldır - çok uzun)
    """
    if not intro_html or not top_brands:
        return intro_html
    
    # Platform metni oluştur - MARKA bazlı
    platform_names = " / ".join(top_brands[:3]) if len(top_brands) > 1 else top_brands[0]
    
    # Filtre tipine göre doğru açıklama
    filter_lower = filter_type_raw.lower()
    
    if "yağ" in filter_lower:
        protection_text = (
            f"{platform_names} araçlarında motor yağındaki metal parçacık, kurum ve "
            f"kirleticileri filtreleyerek yağın temiz kalmasına yardımcı olur"
        )
    elif "polen" in filter_lower or "kabin" in filter_lower:
        protection_text = (
            f"{platform_names} araçlarında kabin havasını polen, toz ve "
            f"zararlı partiküllerden arındırarak sağlıklı sürüş ortamı sunar"
        )
    else:  # Hava filtresi veya diğer
        protection_text = (
            f"{platform_names} platformlarında motorunuzu toz ve zararlı "
            f"partiküllere karşı korumaya yardımcı olur"
        )
    
    # Yeni kısa paragraf (tek paragraf)
    new_first_p = (
        f"<p>FILTRON {external_code} {filter_type_raw.lower()}, "
        f"{protection_text}. Yüksek filtrasyon kapasitesi ile motor performansını "
        f"destekler ve verim kaybı riskini azaltır.</p>"
    )
    
    # Tüm <p> tag'lerini bul
    paragraphs = re.findall(r'<p>.*?</p>', intro_html, re.DOTALL)
    
    if len(paragraphs) == 0:
        return new_first_p
    
    # İlk paragrafı değiştir, 2. paragrafı koru, 3.+ paragrafları SİL
    if len(paragraphs) >= 2:
        # 2 paragraf: 1. değiştir, 2. koru
        updated_html = new_first_p + "\n\n" + paragraphs[1]
    else:
        # 1 paragraf: sadece değiştir
        updated_html = new_first_p
    
    return updated_html


def get_top_brands_from_vehicles(vehicles: Dict[str, List[str]], limit: int = 3) -> List[str]:
    """
    Araç markalarından en popüler olanları döndürür - TITLE CASE
    
    Returns brands in Title Case format:
    - Mercedes-Benz (not MERCEDES-BENZ)
    - Volkswagen (not VW)
    - BMW (kısaltmalar büyük kalır)
    """
    if not vehicles:
        return []
    
    # Marka normalizasyonu - TITLE CASE formatında
    brand_map = {
        "VW (VOLKSWAGEN)": "Volkswagen",
        "VW": "Volkswagen",
        "VOLKSWAGEN": "Volkswagen",
        "CC (358)": "Volkswagen",  # CC modeli Volkswagen markasıdır
        "MERCEDES-BENZ": "Mercedes-Benz",
        "EVOBUS (MERCEDES-BENZ/SETRA)": "Evobus",
        "EVOBUS": "Evobus",
        "VDL BUS + COACH": "VDL",
        "VDL": "VDL",
        "BMW": "BMW",
        "AUDI": "Audi",
        "A1 (8X)": "Audi",  # A1 modeli Audi markasıdır
        "FORD": "Ford",
        "VOLVO CARS": "Volvo",
        "VOLVO": "Volvo",
        "OPEL": "Opel",
        "RENAULT": "Renault",
        "PEUGEOT": "Peugeot",
        "CITROEN": "Citroën",
        "FIAT": "Fiat",
        "TOYOTA": "Toyota",
        "NISSAN": "Nissan",
        "HONDA": "Honda",
        "MAZDA": "Mazda",
        "HYUNDAI": "Hyundai",
        "KIA MOTORS": "Kia",
        "KIA": "Kia",
        "JEEP": "Jeep",
        "CHRYSLER": "Chrysler",
        "DODGE": "Dodge",
        "CHEVROLET": "Chevrolet",
        "ALFA ROMEO": "Alfa Romeo",
        "LANCIA": "Lancia",
        "SEAT": "Seat",
        "SKODA": "Škoda",
        "ŠKODA": "Škoda",
        "DACIA": "Dacia",
        "LAND ROVER": "Land Rover",
        "LANDROVER": "Land Rover",
        "JAGUAR": "Jaguar",
        "MINI": "Mini",
        "SMART": "Smart",
        "PORSCHE": "Porsche",
        "SUBARU": "Subaru",
        "SUZUKI": "Suzuki",
        "MITSUBISHI": "Mitsubishi",
        "SSANGYONG": "SsangYong",
        "ISUZU": "Isuzu",
    }
    
    brands = []
    for brand, models in vehicles.items():
        # Önce map'ten kontrol et
        if brand in brand_map:
            normalized = brand_map[brand]
        else:
            # Map'te yoksa format_brand_title_case kullan
            normalized = format_brand_title_case(brand)
        
        # Skip utility/commercial brands
        if normalized not in ["Bomag", "Morgan"] and normalized not in brands:
            brands.append(normalized)
    
    return brands[:limit]


def build_body_html_full_seo(
    sku: str,
    external_code: Optional[str],
    filter_type_raw: str,
    mann_display: str,
    vehicles: Dict[str, List[str]],
    intro_html: str,
    cta_text: str,
    source_url: str,
) -> str:
    """
    ENHANCED SEO Template - Satış Odaklı (UPDATED v2)
    
    Updates:
    - Full brand names (Mercedes-Benz, Volkswagen)
    - "5 model" → "seçili 5 araç grubu"
    - FAQ: removed quality claims, added "katalog eşleştirmesi"
    - Turkish grammar fixes
    - Platform injection to intro
    """
    code = external_code or sku
    filtron_url = build_filtron_catalog_url(code)
    
    # Top brands for SEO context - FULL NAMES
    top_brands = get_top_brands_from_vehicles(vehicles)
    brands_text = " / ".join(top_brands) if top_brands else "Çeşitli Markalar"
    
    # Vehicle stats
    total_models, ranked = vehicles_stats(vehicles)
    
    # Inject platform to intro HTML
    intro_with_platform = inject_platform_to_intro(intro_html, top_brands, code, filter_type_raw)
    safe_intro = (intro_with_platform or "").strip()
    safe_cta = (cta_text or "").strip() or "Hızlı kargo ve güvenli alışverişle hemen sipariş verin."
    
    # TÜM MARKALARI VE MODELLERİ GÖSTER (limit yok)
    shown_html = build_fitment_html_limited_seo(vehicles)
    
    # Turkish grammar fix for filter type
    filter_lower = filter_type_raw.lower()
    if filter_lower.endswith("filtresi"):
        filter_genitive = filter_lower[:-1] + "nin"  # filtresi -> filtresinin (küçük harf)
    else:
        filter_genitive = filter_lower + "nin"
    
    # Model sayısı ifadesi: "5 araç grubu" veya "5 model"
    # Tutarlılık için "araç grubu" kullanıyoruz
    model_count_text = f"{total_models} araç grubu"
    
    return f"""
<h2>FILTRON {code} {filter_type_raw}</h2>

<!-- Quick Info Bar (Above the Fold) -->
<div style="background:#f8f9fa;padding:15px;margin:15px 0;border-left:4px solid #28a745;">
<ul style="margin:0;padding-left:15px;list-style:none;">
  <li>✅ <strong>Uyumluluk:</strong> {brands_text} (seçili {model_count_text}) – Şase No/Marka-Model ile kontrol</li>
  <li>✅ <strong>Eşdeğer Kod:</strong> MANN {mann_display}</li>
  <li>🚚 <strong>Hızlı Kargo</strong> – Aynı gün kargoya teslim</li>
  <li>🔁 <strong>Kolay İade</strong> – Faturalı satış</li>
</ul>
</div>

{safe_intro}

<h3>Neden FILTRON {code} Seçmelisiniz?</h3>
<ul>
  <li><strong>OEM Kalitesi:</strong> Orijinal ekipman standartlarında üretim</li>
  <li><strong>Yüksek Filtrasyon:</strong> Motorunuzu toz, kir ve partiküllerden korur</li>
  <li><strong>Hassas Uyum:</strong> {brands_text} platformları için tasarlanmıştır</li>
  <li><strong>Dayanıklılık:</strong> Zorlu koşullarda bile stabil performans</li>
  <li><strong>Hızlı Kargo:</strong> Siparişleriniz özenle paketlenir ve hızla gönderilir</li>
  <li><strong>Güvenli Alışveriş:</strong> Güvenli ödeme altyapısı ile sorunsuz işlem</li>
</ul>

<h3>Teknik Özellikler – {code}</h3>
<table style="width:100%;border-collapse:collapse;margin:10px 0;">
  <tr style="background:#f8f9fa;">
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Ürün Kodu</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;">FILTRON {code}</td>
  </tr>
  <tr>
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Filtre Tipi</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;">{filter_type_raw}</td>
  </tr>
  <tr style="background:#f8f9fa;">
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Marka</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;">FILTRON</td>
  </tr>
  <tr>
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Eşdeğer (Muadil)</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>MANN {mann_display}</strong></td>
  </tr>
  <tr style="background:#f8f9fa;">
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Uyumluluk</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;">Seçili {model_count_text} (tam liste metafield'da)</td>
  </tr>
</table>

<h3>Uyumlu Araç Modelleri</h3>
<p><strong>FILTRON {code}</strong> şu araçlarla uyumludur:</p>
{shown_html}

<p style="background:#fff3cd;padding:10px;border-left:4px solid #ffc107;margin:15px 0;">
<strong>📋 Not:</strong> Tam uyumluluk listesi ürün metafield'ında saklanır. 
Şase No/Marka-Model bilgisi ile uyumluluğu teyit edebilirsiniz.
</p>

<h3>Bakım ve Değişim Önerisi</h3>
<p>
{filter_genitive.capitalize()} düzenli olarak değiştirilmesi motorun sağlıklı çalışması için kritik öneme sahiptir. 
Aracınızın kullanım kılavuzunda belirtilen bakım aralıklarına uyarak motorunuzun performansını koruyabilir 
ve olası arızaların önüne geçebilirsiniz.
</p>

<h3>Sık Sorulan Sorular</h3>

<p><strong>❓ Bu ürün aracıma uyar mı?</strong><br>
Şase No/Marka-Model bilginiz ile kontrol önerilir. Uyumluluk listesi {model_count_text} kapsar.</p>

<p><strong>❓ Muadil (eşdeğer) kodu nedir?</strong><br>
MANN {mann_display} (katalog eşleştirmesi).</p>

<p><strong>❓ Ne zaman değiştirilmeli?</strong><br>
Aracınızın kullanım kılavuzuna göre; genelde 15.000-30.000 km aralığında kontrol önerilir.</p>

<p><strong>❓ Uyumluluk kaynağı nedir?</strong><br>
Uyumluluk verileri <strong>MANN-FILTER</strong> eşleştirmesi ile doğrulanmıştır. 
Ek kontrol için <a href="{filtron_url}" target="_blank" rel="nofollow noopener">FILTRON katalog sayfası</a>.</p>

<p><strong>❓ Kargo ve iade koşulları nedir?</strong><br>
Aynı gün kargo, güvenli paketleme. Kolay iade süreci ve faturalı satış garantisi.</p>

<div style="background:#d4edda;padding:15px;margin:20px 0;border:1px solid #c3e6cb;text-align:center;">
<p style="margin:0;font-size:16px;"><strong>🛒 {safe_cta}</strong></p>
<p style="margin:10px 0;font-size:14px;color:#155724;">
Uyumluluktan emin değilseniz şase no/marka-model bilginiz ile kontrol için bize yazabilirsiniz.
</p>
<a href="https://wa.me/905363955525?text=Merhaba,%20FILTRON%20{code}%20ürünü%20hakkında%20bilgi%20almak%20istiyorum" 
   target="_blank" rel="noopener" 
   style="display:inline-block;background:#25D366;color:#fff;padding:12px 24px;text-decoration:none;border-radius:8px;font-weight:bold;margin-top:10px;">
💬 WhatsApp ile Uyumluluk Kontrolü
</a>
</div>

<hr style="margin:20px 0;">
<p style="font-size:12px;color:#6c757d;">
<strong>Kaynak bilgileri:</strong><br>
• Uyumluluk: <a href="{source_url}" target="_blank" rel="nofollow noopener">MANN-FILTER</a><br>
• Ürün bilgisi: <a href="{filtron_url}" target="_blank" rel="nofollow noopener">FILTRON katalog</a><br>
• Tam uyumluluk listesi ürün metafield'ında saklanır.
</p>
""".strip()


def build_body_html_light_seo(
    sku: str,
    external_code: Optional[str],
    filter_type_raw: str,
    mann_display: Optional[str],
    intro_html: str,
    cta_text: str,
) -> str:
    """
    LIGHT SEO Template - MANN verisi yok ama yine de SEO güçlü
    """
    safe_intro = (intro_html or "").strip()
    safe_cta = (cta_text or "").strip() or "Hızlı kargo ve güvenli alışverişle hemen sipariş verin."
    
    code = external_code or sku
    filtron_url = build_filtron_catalog_url(code)
    
    muadil_row = ""
    if mann_display:
        muadil_row = f"""  <tr>
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Eşdeğer (Muadil)</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>{mann_display}</strong></td>
  </tr>"""
    
    muadil_bullet = ""
    if mann_display:
        muadil_bullet = f"  <li>✅ <strong>Eşdeğer Kod:</strong> MANN {mann_display}</li>\n"
    
    # Turkish grammar fix for filter type
    filter_lower = filter_type_raw.lower()
    if filter_lower.endswith("filtresi"):
        filter_genitive = filter_lower[:-1] + "nin"  # filtresi -> filtresinin
    else:
        filter_genitive = filter_lower + "nin"
    
    muadil_faq = ""
    if mann_display:
        muadil_faq = f"""
<p><strong>❓ Muadil (eşdeğer) kodu nedir?</strong><br>
MANN {mann_display} (katalog eşleştirmesi).</p>
"""
    
    return f"""
<h2>FILTRON {code} {filter_type_raw}</h2>

<!-- Quick Info Bar -->
<div style="background:#f8f9fa;padding:15px;margin:15px 0;border-left:4px solid #28a745;">
<ul style="margin:0;padding-left:20px;list-style:none;">
{muadil_bullet}  <li>🚚 <strong>Hızlı Kargo</strong> – Aynı gün kargoya teslim</li>
  <li>🔁 <strong>Kolay İade</strong> – Faturalı satış</li>
  <li>📋 <strong>Uyumluluk:</strong> Şase No/Marka-Model ile kontrol</li>
</ul>
</div>

{safe_intro}

<h3>Neden FILTRON {code} Seçmelisiniz?</h3>
<ul>
  <li><strong>OEM Kalitesi:</strong> Orijinal ekipman üreticisi standartlarına uygundur</li>
  <li><strong>Güvenilir Koruma:</strong> Motorunuzu zararlı partiküllerden arındırır</li>
  <li><strong>Uzun Ömür:</strong> Kaliteli malzemeler ile uzun servis ömrü sunar</li>
  <li><strong>Kolay Montaj:</strong> Belirtilen araçlara tam uyum sağlar</li>
  <li><strong>Hızlı kargo ve güvenli alışveriş:</strong> Siparişten teslimata kadar destek</li>
</ul>

<h3>Teknik Özellikler – {code}</h3>
<table style="width:100%;border-collapse:collapse;margin:10px 0;">
  <tr style="background:#f8f9fa;">
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Ürün Kodu</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;">FILTRON {code}</td>
  </tr>
  <tr>
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Filtre Tipi</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;">{filter_type_raw}</td>
  </tr>
  <tr style="background:#f8f9fa;">
    <td style="padding:8px;border:1px solid #dee2e6;"><strong>Marka</strong></td>
    <td style="padding:8px;border:1px solid #dee2e6;">FILTRON</td>
  </tr>
{muadil_row}
</table>

<h3>Uyumluluk Bilgisi</h3>
<p>
Bu ürün, FILTRON üretici kataloğundaki ilgili araç uygulamalarına göre kullanılmalıdır.
Aracınız ile uyumluluğu kontrol etmek için aşağıdaki FILTRON katalog bağlantısını inceleyebilirsiniz.
</p>
<p>
<a href="{filtron_url}" target="_blank" rel="nofollow noopener" 
   style="display:inline-block;background:#007bff;color:#fff;padding:10px 20px;text-decoration:none;border-radius:4px;">
📖 FILTRON katalog sayfasını görüntüle
</a>
</p>

<h3>Bakım ve Değişim Önerisi</h3>
<p>
{filter_type_raw}nin düzenli olarak değiştirilmesi motorun sağlıklı çalışması için kritik öneme sahiptir. 
Aracınızın kullanım kılavuzunda belirtilen bakım aralıklarına uyarak motorunuzun performansını koruyabilirsiniz.
</p>

<h3>Sık Sorulan Sorular</h3>

<p><strong>❓ Bu ürün aracıma uyar mı?</strong><br>
FILTRON katalog sayfasından kontrol edebilirsiniz. Şase No/Marka-Model bilgisi ile kesin sonuç alabilirsiniz.</p>
{muadil_faq}
<p><strong>❓ Ne zaman değiştirilmeli?</strong><br>
Aracınızın kullanım kılavuzuna göre; genelde 15.000-30.000 km aralığında kontrol önerilir.</p>

<p><strong>❓ Orijinal ürün müdür?</strong><br>
Evet, FILTRON orijinal üretici markasıdır. Tüm ürünlerimiz faturalı ve garantilidir.</p>

<p><strong>❓ Kargo ve iade koşulları nedir?</strong><br>
Aynı gün kargo, güvenli paketleme. Kolay iade süreci ve faturalı satış garantisi.</p>

<div style="background:#d4edda;padding:15px;margin:20px 0;border:1px solid #c3e6cb;text-align:center;">
<p style="margin:0;font-size:16px;"><strong>🛒 {safe_cta}</strong></p>
<p style="margin:10px 0;font-size:14px;color:#155724;">
Uyumluluktan emin değilseniz şase no/marka-model bilginiz ile bize yazabilirsiniz.
</p>
<a href="https://wa.me/905363955525?text=Merhaba,%20FILTRON%20{code}%20ürünü%20hakkında%20bilgi%20almak%20istiyorum" 
   target="_blank" rel="noopener" 
   style="display:inline-block;background:#25D366;color:#fff;padding:12px 24px;text-decoration:none;border-radius:8px;font-weight:bold;margin-top:10px;">
💬 WhatsApp ile Uyumluluk Kontrolü
</a>
</div>

<hr style="margin:20px 0;">
<p style="font-size:12px;color:#6c757d;">
<strong>Kaynak bilgiler:</strong><br>
• Ürün detay: <a href="{filtron_url}" target="_blank" rel="nofollow noopener">FILTRON katalog</a><br>
• Uyumluluk için her zaman şasi numarası (VIN) ve üretici kataloğu referans alınmalıdır.
</p>
""".strip()


def build_fitment_html_limited_seo(
    vehicles: Dict[str, List[str]], 
    max_brands: int = 999,  # TÜM MARKALARI GÖSTER (limit yok)
    max_models_per_brand: int = 999  # TÜM MODELLERİ GÖSTER
) -> str:
    """
    SEO için optimize edilmiş araç listesi - YENİ VERSİYON
    
    DEĞİŞİKLİKLER:
    - TÜM markaları göster ("..." yok)
    - Her marka başına ✅ emoji
    - Yeşil dikey çizgi (border-left) her marka bloğunda
    - Shopify Quick Info Bar ile aynı stil
    """
    if not vehicles:
        return ""
    
    total_models, ranked = vehicles_stats(vehicles)
    parts: List[str] = []
    
    for brand, _cnt in ranked:
        models = vehicles.get(brand, [])
        if not models:
            continue
        
        # TÜM modelleri al (limit yok)
        take = models[:max_models_per_brand]
        if not take:
            continue
        
        # Yeşil çizgi + ✅ emoji ile marka bloğu
        chunk = [
            '<div style="border-left: 4px solid #28a745; padding-left: 10px; margin: 10px 0;">',
            f'<p>✅ <strong>{brand}:</strong><br>'
        ]
        
        for m in take:
            chunk.append(f"&nbsp;&nbsp;• {m}<br>")
        
        chunk.append("</p>")
        chunk.append("</div>")
        
        parts.append("".join(chunk))
    
    # "... ve X marka daha" KALDIRIDI - TÜM MARKALAR GÖSTERİLİYOR
    
    return "\n".join(parts)


# =============================================================================
# OPENAI
# =============================================================================

def build_openai_prompt(
    sku: str,
    external_code: Optional[str],
    filter_type_raw: str,
    top_brands: List[str],
) -> str:
    """OpenAI'ya gönderilecek SEO metin üretme promptunu oluşturur."""
    code = external_code or sku
    brands_str = ", ".join(top_brands[:4]) if top_brands else ""
    return f"""
Türkçe yazan profesyonel e-ticaret metin yazarı gibi yaz.

ÜRÜN:
- Marka: FILTRON
- Kod: {code}
- Filtre tipi: {filter_type_raw}
- Hedef marka örnekleri: {brands_str}

KURALLAR:
1) ASLA araç modeli uydurma.
2) "MANN" kelimesini kullanma (eşdeğer satırı HTML'de zaten var).
3) Emoji body içinde kullanma.
4) Sadece JSON üret.
5) intro_html 3 paragraf olsun: (2 paragraf ürün/marka kalitesi) + (1 paragraf bakım/değişim)

JSON:
{{
  "intro_html": "<p>...</p><p>...</p><p>...</p>",
  "cta_text": "Tek paragraf: Hızlı kargo ve Güvenli alışverişle hemen sipariş verin."
}}
""".strip()


def openai_generate_json(prompt: str) -> Optional[dict]:
    """OpenAI API'yi çağırır, JSON modunda intro_html ve cta_text döndürmesini ister. Fallback dener."""
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
            timeout=90,
        )
        return json.loads(resp.choices[0].message.content.strip())
    except Exception as e:
        log(f"OpenAI JSON-mode error (dev info): {type(e).__name__}", "WARN")

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            timeout=90,
        )
        content = resp.choices[0].message.content.strip()
        content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(content)
    except Exception as e:
        log(f"OpenAI fallback error (dev info): {type(e).__name__}", "WARN")
        return None


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Ana akış: Supabase oku → Shopify index → karşılaştır → işlem yap."""
    print()
    print("=" * 70)
    print("  FILTRON SEO ENRICHER [V17 - SUPABASE SKU INDEX + CANLI İSTATİSTİK]")
    print("=" * 70)
    log(f"SUPABASE_TABLE={SUPABASE_TABLE} | HANDLE_MODE={HANDLE_MODE}")
    log(f"LOG_FILE={LOG_FILE} | FAILED_FILE={FAILED_FILE} | PROGRESS_FILE={PROGRESS_FILE}")
    log(f"PROCESS_ONLY_FAILED={PROCESS_ONLY_FAILED} | RESUME_EXISTING={RESUME_EXISTING} | MAX_ROWS={MAX_ROWS or 'TÜMÜ'} | DRY_RUN={DRY_RUN}")

    try:
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
    except Exception:
        pass

    # ── 1. CSV YÜKLEme → SUPABASE SKU INDEX ───────────────────────────────────────
    print("\n📂 Supabase okunuyor ve SKU index oluşturuluyor...")
    items_all = load_items_from_supabase(max_rows=MAX_ROWS)
    if not items_all:
        log("CSV'den item bulunamadı.", "ERROR")
        return

    log(f"Supabase item adedi: {len(items_all)}")

    # Supabase SKU index: normalize SKU → item
    csv_sku_index = build_source_sku_index(items_all)
    print_source_index_preview(csv_sku_index, limit=10)

    items = items_all

    if PROCESS_ONLY_FAILED:
        failed_list = load_failed_allowlist(FAILED_FILE)
        if failed_list:
            failed_sku_set = set()
            failed_ext_set = set()
            for fe in failed_list:
                s = normalize_sku(fe.get("sku") or "")
                e = normalize_sku(fe.get("external") or "")
                if s:
                    failed_sku_set.add(s)
                if e:
                    failed_ext_set.add(e)

            filtered: List[dict] = []
            for it in items_all:
                sku_norm = normalize_sku(it["sku"])
                ext_norm = normalize_sku(it.get("external_code") or "")
                if sku_norm in failed_sku_set or ext_norm in failed_ext_set:
                    filtered.append(it)

            items = filtered
            log(f"FAILED allowlist yüklendi: {len(failed_list)} adet SKU / external")
            log(
                f"PROCESS_ONLY_FAILED=1 -> CSV {len(items_all)} üründen "
                f"{len(items)} adedi filtrelendi (failed.json allowlist)."
            )
        else:
            log("PROCESS_ONLY_FAILED=1 ama failed.json boş/bulunamadı, tüm CSV işlenecek.", "WARN")

    # ── 2. SHOPİFY SKU INDEX ─────────────────────────────────────────────────
    print("🛒 Shopify ürünleri ve SKU index yükleniyor...")
    products  = load_all_products_since_id()
    sku_index = build_sku_index(products)

    # ── 3. KARŞILAŞTIRMA ÖN RAPORU ───────────────────────────────────────────
    print_comparison_preview(csv_sku_index, sku_index, limit=15)

    location_id = get_primary_location_id()
    if not location_id:
        log("❌ Shopify location bulunamadı (stok set edilemez).", "ERROR")
        return
    log(f"✅ Location ID: {location_id}")

    failed: List[dict] = []
    success = 0

    # ── 4. CANLI İSTATİSTİK ───────────────────────────────────────────────────
    stats = LiveStats(total=len(items))
    print(f"\n🚀 İşlem başlıyor: {len(items)} SKU\n")

    pbar = tqdm(items, desc="SEO Enrich", dynamic_ncols=True)

    for csv_index, it in enumerate(pbar):
        canonical_sku = normalize_sku(it["sku"])  # AK381
        external_code = it.get("external_code")  # AK 381
        filter_type_raw = normalize_filter_type(it["filter_type_raw"])
        filter_type_title = filter_type_for_title(filter_type_raw)
        price = it["price"]
        raw_stock = int(it.get("stock_qty") or 0)
        stock_qty = min(max(raw_stock, 0), 3)
        if raw_stock < 0:
            log(f"{canonical_sku}: negatif stok {raw_stock} -> 0", "WARN")
        csv_sku_raw = it.get("csv_sku_raw")
        
        try:
            debug_step(
                sku=canonical_sku,
                external=external_code,
                step="csv_loaded",
                status="ok",
                csv_index=csv_index,
                filter_type_raw=filter_type_raw,
                price=price,
            )

            pbar.set_postfix_str(f"SKU={canonical_sku} | CREATE/UPDATE")
            created_now = False

            # ==================================================================
            #  SKU VAR MI? CSV normalize ↔ Shopify normalize karşılaştırma
            #   VAR  → sadece fiyat + stok güncelle, döngüye devam et
            #   YOK  → yeni ürün aç, tam SEO/Mann/OpenAI/metafield akışı
            # ==================================================================

            if canonical_sku in sku_index and not RESUME_EXISTING:
                # ── MEVCUT ÜRÜN: FİYAT + STOK + KATEGORİ STANDARDI ───────────
                product_id = int(sku_index[canonical_sku]["product_id"])
                variant_id = int(sku_index[canonical_sku]["variant_id"])

                stats.set_current(canonical_sku, "fiyat+stok güncelleniyor")
                log(f"{canonical_sku}: Shopify'da VAR → sadece fiyat+stok "
                    f"| pid={product_id} price={price} stock={stock_qty}")

                debug_step(
                    sku=canonical_sku, external=external_code,
                    step="shopify_existing", status="ok",
                    product_id=product_id, variant_id=variant_id,
                )

                # Fiyat güncelle
                if not update_variant_price_and_sku(
                    variant_id=variant_id, price=price, sku_normalized=canonical_sku
                ):
                    reason = "variant fiyat güncelleme başarısız"
                    failed.append({
                        "sku": canonical_sku, "external": external_code,
                        "step": "variant_price_update",
                        "product_id": product_id, "error": reason,
                    })
                    stats.mark_failed(canonical_sku, reason)
                    continue

                # Stok güncelle
                inv_item_id = sku_index[canonical_sku].get("inventory_item_id")
                if not inv_item_id:
                    vdata = shopify_get(f"{BASE}/variants/{variant_id}.json", timeout=25)
                    if vdata and vdata.get("variant") and vdata["variant"].get("inventory_item_id"):
                        inv_item_id = int(vdata["variant"]["inventory_item_id"])
                        sku_index[canonical_sku]["inventory_item_id"] = inv_item_id

                if not inv_item_id:
                    reason = "inventory_item_id bulunamadı"
                    failed.append({
                        "sku": canonical_sku, "external": external_code,
                        "step": "inventory_item_id",
                        "product_id": product_id, "error": reason,
                    })
                    stats.mark_failed(canonical_sku, reason)
                    continue

                if not set_inventory_available(int(inv_item_id), int(location_id), stock_qty):
                    reason = "stock set başarısız"
                    failed.append({
                        "sku": canonical_sku, "external": external_code,
                        "step": "stock_set", "product_id": product_id,
                        "inventory_item_id": inv_item_id, "error": reason,
                    })
                    stats.mark_failed(canonical_sku, reason)
                    continue

                if not update_product_type_and_category_tag(product_id, filter_type_title):
                    reason = "ürün türü/etiket güncelleme başarısız"
                    failed.append({
                        "sku": canonical_sku, "external": external_code,
                        "step": "product_type_tag_update", "product_id": product_id,
                        "error": reason,
                    })
                    stats.mark_failed(canonical_sku, reason)
                    continue

                if not upsert_seo_structured_data(
                    product_id=product_id,
                    canonical_sku=canonical_sku,
                    external_code=external_code,
                    filter_type_title=filter_type_title,
                    price=price,
                    stock_qty=stock_qty,
                ):
                    reason = "seo_structured_data güncelleme başarısız"
                    failed.append({
                        "sku": canonical_sku, "external": external_code,
                        "step": "seo_structured_data", "product_id": product_id,
                        "error": reason,
                    })
                    stats.mark_failed(canonical_sku, reason)
                    continue

                success += 1
                debug_step(
                    sku=canonical_sku, external=external_code,
                    step="done_update_only", status="ok",
                    product_id=product_id, price=price, stock=stock_qty,
                )
                stats.mark_updated(canonical_sku)
                time.sleep(SHOPIFY_SLEEP)
                continue  # ← güncelleme bitti, sonraki SKU'ya geç

            # ── YENİ ÜRÜN veya KISMI ÜRÜNÜ TAMAMLAMA ───────────────────────────
            stats.set_current(canonical_sku, "ürün akışı hazırlanıyor")
            created_now = False
            if canonical_sku in sku_index and RESUME_EXISTING:
                existing = sku_index[canonical_sku]
                created = {"product": {"id": int(existing["product_id"]), "title": existing.get("title", ""), "variants": [{"id": int(existing["variant_id"]), "sku": canonical_sku, "inventory_item_id": existing.get("inventory_item_id")} ]}}
                log(f"RESUME_EXISTING: mevcut ürün tam zenginleştirme -> {canonical_sku}")
            else:
                stats.set_current(canonical_sku, "yeni ürün oluşturuluyor")
                created = create_product_for_csv_item(it)
                if not created or "product" not in created:
                    reason = "Shopify CREATE başarısız"
                    failed.append({
                        "sku": canonical_sku, "external": external_code,
                        "step": "shopify_create", "error": reason,
                    })
                    stats.mark_failed(canonical_sku, reason)
                    continue
                if DRY_RUN:
                    tags_preview = build_tags_csv(external_code, filter_type_title, None)
                    log(f"[DRY_RUN PLAN] CREATE sku={canonical_sku} type={filter_type_title} tags={tags_preview}")
                    success += 1
                    stats.mark_created(canonical_sku)
                    debug_step(sku=canonical_sku, external=external_code, step="dry_run_plan", status="ok", simulated=True)
                    continue
                created_now = True
            product_id = int(created["product"]["id"])
            variant = created["product"]["variants"][0]
            variant_id = int(variant["id"])
            inv_item_id = int(variant.get("inventory_item_id") or 0)

            sku_index[canonical_sku] = {
                "product_id": product_id,
                "variant_id": variant_id,
                "inventory_item_id": inv_item_id if inv_item_id else None,
                "title": created["product"].get("title", ""),
                "shopify_sku_raw": canonical_sku,
            }

            debug_step(
                sku=canonical_sku, external=external_code,
                step="shopify_product", status="ok",
                product_id=product_id, variant_id=variant_id, created_now=created_now,
            )

            # Variant SKU normalize + barcode boş
            stats.set_current(canonical_sku, "variant SKU yazılıyor")
            if not update_variant_price_and_sku(variant_id=variant_id, price=price, sku_normalized=canonical_sku):
                reason = "variant update failed"
                failed.append({
                    "sku": canonical_sku, "external": external_code,
                    "step": "variant_update", "product_id": product_id, "error": reason,
                })
                stats.mark_failed(canonical_sku, reason)
                continue

            inv_item_id = sku_index[canonical_sku].get("inventory_item_id")
            if not inv_item_id:
                vdata = shopify_get(f"{BASE}/variants/{variant_id}.json", timeout=25)
                if vdata and vdata.get("variant") and vdata["variant"].get("inventory_item_id"):
                    inv_item_id = int(vdata["variant"]["inventory_item_id"])
                    sku_index[canonical_sku]["inventory_item_id"] = inv_item_id

            if not inv_item_id:
                reason = "inventory_item_id bulunamadı"
                failed.append({
                    "sku": canonical_sku, "external": external_code,
                    "step": "inventory_item_id", "product_id": product_id, "error": reason,
                })
                stats.mark_failed(canonical_sku, reason)
                continue

            debug_step(
                sku=canonical_sku, external=external_code,
                step="inventory_item_id", status="ok",
                product_id=product_id, variant_id=variant_id, inventory_item_id=inv_item_id,
            )

            stats.set_current(canonical_sku, "stok ayarlanıyor")
            if not set_inventory_available(int(inv_item_id), int(location_id), stock_qty):
                reason = "stock set failed"
                failed.append({
                    "sku": canonical_sku, "external": external_code,
                    "step": "stock_set", "product_id": product_id,
                    "inventory_item_id": inv_item_id, "error": reason,
                })
                stats.mark_failed(canonical_sku, reason)
                continue

            debug_step(
                sku=canonical_sku, external=external_code,
                step="stock_set", status="ok",
                product_id=product_id, inventory_item_id=inv_item_id, stock=stock_qty,
            )

            # MANN crossref
            pbar.set_postfix_str(f"SKU={canonical_sku} | MANN")
            mann = mann_crossref_lookup_filtron(canonical_sku, external_code=external_code)

            mann_display: Optional[str] = None
            mann_url_key: Optional[str] = None
            mann_product_url: Optional[str] = None
            vehicles: Dict[str, List[str]] = {}
            total_models = 0
            ranked_brands: List[str] = []
            app_data: Optional[dict] = None

            if mann:
                mann_display = mann["mann_display"]
                mann_url_key = mann.get("url_key")
                mann_product_url = mann.get("product_url")
                debug_step(
                    sku=canonical_sku,
                    external=external_code,
                    step="mann_crossref",
                    status="ok",
                    product_id=product_id,
                    mann_display=mann_display,
                    mann_product_url=mann_product_url,
                )

                pbar.set_postfix_str(f"SKU={canonical_sku} | FITMENT")
                app_data = mann_scrape_fitment_from_product_url(
                    mann["product_url"],
                    mann["referer"],
                )
                if app_data:
                    vehicles = parse_vehicles(app_data)
                    total_models, ranked = vehicles_stats(vehicles)
                    if total_models > 0:
                        ranked_brands = [b for b, _ in ranked]
                        debug_step(
                            sku=canonical_sku,
                            external=external_code,
                            step="fitment_ok",
                            status="ok",
                            product_id=product_id,
                            total_models=total_models,
                            brand_count=len(vehicles),
                        )
                    else:
                        vehicles = {}
                        total_models = 0
                        ranked_brands = []
                        debug_step(
                            sku=canonical_sku,
                            external=external_code,
                            step="fitment_empty",
                            status="no_models",
                            product_id=product_id,
                        )
                else:
                    debug_step(
                        sku=canonical_sku,
                        external=external_code,
                        step="mann_fitment",
                        status="not_found",
                        product_id=product_id,
                    )
            else:
                debug_step(
                    sku=canonical_sku,
                    external=external_code,
                    step="mann_crossref",
                    status="not_found",
                    product_id=product_id,
                )

            # OpenAI SEO text
            pbar.set_postfix_str(f"SKU={canonical_sku} | AI")
            seo_json = openai_generate_json(
                build_openai_prompt(
                    canonical_sku,
                    external_code,
                    filter_type_raw,
                    ranked_brands[:6] if ranked_brands else [],
                )
            ) or {}

            intro_html = (seo_json.get("intro_html") or "").strip()
            cta_text = (seo_json.get("cta_text") or "").strip()
            if not intro_html:
                intro_html = (
                    f"<p>FILTRON {external_code or canonical_sku} {filter_type_raw}, "
                    f"motorunuzun verimli ve sağlıklı çalışmasına yardımcı olmak için "
                    f"tasarlanmış kaliteli bir filtre çözümüdür.</p>"
                    f"<p>Üretici standartlarına uygun yapısı, güvenilir filtrasyon performansı ve "
                    f"dayanıklı malzemeleriyle uzun süreli kullanım sunar.</p>"
                    f"<p>Aracınızın bakım aralıklarını aksatmamak, hem motor ömrünü uzatır hem de "
                    f"yakıt tüketimini optimize etmeye yardımcı olur.</p>"
                )
            if not cta_text:
                cta_text = "Hızlı kargo ve Güvenli alışverişle hemen sipariş verin."

            debug_step(
                sku=canonical_sku,
                external=external_code,
                step="ai_body_built",
                status="ok",
                product_id=product_id,
            )

            # FULL vs LIGHT body
            if vehicles and total_models > 0 and mann_display and app_data:
                # FULL SEO Template
                body_html = build_body_html_full_seo(
                    sku=canonical_sku,
                    external_code=external_code,
                    filter_type_raw=filter_type_raw,
                    mann_display=mann_display,
                    vehicles=vehicles,
                    intro_html=intro_html,
                    cta_text=cta_text,
                    source_url=app_data.get("source_url", ""),
                )
            else:
                # LIGHT SEO Template
                body_html = build_body_html_light_seo(
                    sku=canonical_sku,
                    external_code=external_code,
                    filter_type_raw=filter_type_raw,
                    mann_display=mann_display,
                    intro_html=intro_html,
                    cta_text=cta_text,
                )

            filtron_title = make_filtron_title(
                canonical_sku,
                external_code,
                filter_type_title,
                mann_display,
                top_brands=ranked_brands[:2] if ranked_brands else None,
            )
            
            # Meta description - Rotating 9 variants
            meta_desc = build_meta_description_rotating(
                canonical_sku,
                external_code,
                filter_type_raw,
                mann_display,
                ranked_brands[:2] if ranked_brands else [],
                csv_index  # Döngü için index
            )
            
            # Tags: Boşluklu kod (AK 381)
            tags_csv = build_tags_csv(external_code, filter_type_title, mann_display)

            pbar.set_postfix_str(f"SKU={canonical_sku} | WRITE")

            if DRY_RUN:
                log(
                    f"[DRY_RUN] {canonical_sku} pid={product_id} created_now={created_now} "
                    f"title='{filtron_title}' tags='{tags_csv}' mann='{mann_display}' "
                    f"models={total_models} type_raw='{filter_type_raw}' "
                    f"type_title='{filter_type_title}' external='{external_code}' csv_sku='{csv_sku_raw}'"
                )
                success += 1
                debug_step(
                    sku=canonical_sku,
                    external=external_code,
                    step="done",
                    status="ok",
                    product_id=product_id,
                    total_models=total_models,
                )
                stats.mark_created(canonical_sku)
                continue

            # Product update
            payload = {"product": {"id": product_id}}
            if created_now:
                payload["product"]["status"] = CREATE_STATUS
            if WRITE_PRODUCT_TITLE:
                payload["product"]["title"] = filtron_title
            if WRITE_BODY_HTML:
                payload["product"]["body_html"] = body_html
            if UPDATE_TAGS:
                payload["product"]["tags"] = tags_csv

            ok, msg = shopify_put(f"{BASE}/products/{product_id}.json", payload)
            if not ok:
                failed.append({
                    "sku": canonical_sku,
                    "external": external_code,
                    "step": "shopify_product_put",
                    "product_id": product_id,
                    "error": msg,
                })
                stats.mark_failed(canonical_sku, f"shopify_put: {msg[:40]}")
                continue

            debug_step(
                sku=canonical_sku,
                external=external_code,
                step="shopify_product_put",
                status="ok",
                product_id=product_id,
            )

            # Handle
            if HANDLE_MODE == "create_only" and created_now:
                desired_handle = slugify_tr(filtron_title)
                set_product_handle_safe(
                    product_id=product_id,
                    desired_handle=desired_handle,
                    sku=canonical_sku,
                )

            # Meta description
            if WRITE_META and meta_desc:
                upsert_metafield(
                    product_id,
                    "global",
                    "description_tag",
                    "single_line_text_field",
                    meta_desc[:160],
                )

            # Metafields
            upsert_metafield(
                product_id,
                "custom",
                "oem_brand",
                "single_line_text_field",
                "FILTRON",
            )
            upsert_metafield(
                product_id,
                "custom",
                "oem_code",
                "single_line_text_field",
                external_code or canonical_sku,
            )
            if mann_display:
                upsert_metafield(
                    product_id,
                    "custom",
                    "mann_code",
                    "single_line_text_field",
                    mann_display,
                )

            # Fitment JSON
            if WRITE_FITMENT_METAFIELD:
                fitment_json = {
                    "sku": canonical_sku,  # AK381
                    "external_code": external_code,  # AK 381
                    "filter_type_raw": filter_type_raw,
                    "filter_type_title": filter_type_title,
                    "price": price,
                    "price_source": "supabase.fiyat",
                    "stock_forced": stock_qty,
                    "oem_brand": "FILTRON",
                    "oem_code": external_code or canonical_sku,
                    "mann_code": mann_display,
                    "filtron_title": filtron_title,
                    "shopify_tags": tags_csv,
                    "created_now": created_now,
                    "handle_mode": HANDLE_MODE,
                    "mann_url_key": mann_url_key,
                    "mann_product_url": mann_product_url,
                    "supabase_mann_url": it.get("mann_url", ""),
                    "depo_merkezi": it.get("depo_merkezi", ""),
                    "total_models": total_models,
                    "brands": vehicles,
                    "source": "mann-filter" if mann_display else "filtron-only",
                    "source_url": app_data.get("source_url") if app_data else None,
                    "filtron_catalog_url": build_filtron_catalog_url(external_code or canonical_sku),
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "csv_sku_raw": csv_sku_raw,
                }
                upsert_metafield(
                    product_id,
                    "custom",
                    "fitment_json",
                    "json",
                    json.dumps(fitment_json, ensure_ascii=False),
                )

            if not upsert_seo_structured_data(
                product_id=product_id,
                canonical_sku=canonical_sku,
                external_code=external_code,
                filter_type_title=filter_type_title,
                price=price,
                stock_qty=stock_qty,
                meta_desc=meta_desc,
                mann_display=mann_display,
                total_models=total_models,
            ):
                reason = "seo_structured_data güncelleme başarısız"
                failed.append({
                    "sku": canonical_sku, "external": external_code,
                    "step": "seo_structured_data", "product_id": product_id,
                    "error": reason,
                })
                stats.mark_failed(canonical_sku, reason)
                continue

            # Smart koleksiyon, standart kategori etiketi üzerinden otomatik eşleştirir.
            stats.set_current(canonical_sku, "marka koleksiyonları")
            ensure_brand_collections_for_product(product_id, vehicles)

            success += 1
            log(
                f"{canonical_sku}: ✅ YENİ ÜRÜN OLUŞTURULDU | pid={product_id} "
                f"| price={price} | stock={stock_qty} | mann={mann_display} "
                f"| models={total_models} | type_raw='{filter_type_raw}' "
                f"| type_title='{filter_type_title}' | tags={tags_csv} "
                f"| external='{external_code}' | csv_sku='{csv_sku_raw}'"
            )

            debug_step(
                sku=canonical_sku,
                external=external_code,
                step="done",
                status="ok",
                product_id=product_id,
                total_models=total_models,
            )

            stats.mark_created(canonical_sku)
            time.sleep(SHOPIFY_SLEEP)
            time.sleep(OPENAI_SLEEP)

        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            log(f"{canonical_sku}: ❌ Unhandled -> {msg}", "ERROR")
            failed.append({
                "sku": canonical_sku,
                "external": external_code,
                "step": "unhandled",
                "error": msg,
            })
            stats.mark_failed(canonical_sku, msg[:60])

    # ── ÖZET RAPOR ────────────────────────────────────────────────────────────
    stats.print_summary()
    log(f"✅ Success: {success} | ❌ Failed: {len(failed)}")

    if failed:
        try:
            with open(FAILED_FILE, "w", encoding="utf-8") as f:
                json.dump(failed, f, indent=2, ensure_ascii=False)
            log(f"Hatalar yazıldı: {FAILED_FILE}", "WARN")
        except Exception as e:
            log(f"failed.json yazılamadı: {e}", "ERROR")


if __name__ == "__main__":
    main()