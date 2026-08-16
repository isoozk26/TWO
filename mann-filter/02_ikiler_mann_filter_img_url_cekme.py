# -*- coding: utf-8 -*-
"""
MANN FILTER → SUPABASE IKILER_MANN URL / KATEGORİ / GÖRSEL AŞAMASI
===================================================================

KAYNAK : Supabase public."IKILER_MANN" (yalnızca stoklu MANN ürünleri)
HEDEF  : Aynı tablonun kategori, mann_url ve img_url_1..3 alanları

KURALLAR:
✅ MANN ürün sayfasından gerçek kategori okunur.
✅ Kategori formatı: Yağ Filtresi, Hava Filtresi, Yakıt Filtresi, Polen Filtresi.
✅ Scene7 URL'leri ürün kodu ile doğrulanır; en fazla 3 temiz URL yazılır.
✅ Tüm stoklu MANN kayıtları Selenium ile baştan doğrulanır; URL/görseller yenilenir.
✅ Fiyat, stok, SKU ve KOD alanlarına dokunulmaz.
"""

import os
import re
import csv
import time
import requests
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote, unquote

from colorama import init as colorama_init, Fore, Style
colorama_init(autoreset=True)

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from selenium.common.exceptions import (
    TimeoutException,
    ElementNotInteractableException,
    StaleElementReferenceException,
    WebDriverException
)

# ===================== CONFIG =====================
INPUT_CSV = "mannfilter_full.csv"
OUTPUT_CSV = "mann_output_img_.csv"
CATALOG_URL = "https://www.mann-filter.com/tr-tr/katalog.html"
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lrjphkajdkipwjizzxsc.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY", "")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "IKILER_MANN")
SHOPIFY_VENDOR = "MANN"

HEADLESS = False  # Tarayıcı görünür
MAX_IMG = 3  # Maksimum görsel sayısı

TYPE_DELAY = 0.04  # Yazma hızı
DROPDOWN_WAIT_SECONDS = 5.0  # Ürün dropdown'ı için zorunlu bekleme
PRODUCT_WAIT = 10.0  # Ürün sayfası yükleme

SLEEP_BETWEEN = 0.10  # İşlemler arası bekleme
LIMIT = 0  # 0 = sınırsız

BLOCK_HEAVY_ASSETS = True  # Görsel/font blok
ENABLE_CACHE = True  # Önbellekleme

SCENE7_PREFIX = "https://s7g10.scene7.com/is/image/mannhummel/"
MANN_PRODUCT_PREFIX = "https://www.mann-filter.com/tr-tr/katalog/arama-sonuclar%C4%B1/urun.html/"
OUTPUT_DELIMITER = ";"


# ===================== LOG =====================
def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(level: str, msg: str) -> None:
    cmap = {
        "INFO": Fore.CYAN,
        "OK": Fore.GREEN,
        "WARN": Fore.YELLOW,
        "ERROR": Fore.RED,
        "DBG": Fore.MAGENTA,
        "STEP": Fore.BLUE,
        "STAT": Fore.WHITE,
    }
    c = cmap.get(level, Fore.WHITE)
    print(f"{Style.DIM}[{ts()}]{Style.RESET_ALL} {c}[{level}]{Style.RESET_ALL} {msg}")

def stat_line(total: int, processed: int, ok: int, no: int, skip: int, imgs0: int, cached: int, last_code: str = "") -> None:
    msg = f"TOTAL={total} | DONE={processed} | OK={ok} | NO={no} | SKIP={skip} | IMGS0={imgs0} | CACHED={cached}"
    if last_code:
        msg += f" | LAST={last_code}"
    log("STAT", msg)


# ===================== CSV HELPERS =====================
def sniff_delimiter(path: str, default: str = ",") -> str:
    """CSV delimiter otomatik tespit (virgül, noktalı virgül vs.)"""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            sample = f.read(4096)
        if not sample.strip():
            return default
        sn = csv.Sniffer()
        dialect = sn.sniff(sample, delimiters=[",", ";", "\t", "|"])
        return dialect.delimiter
    except Exception:
        return default

def read_rows(path: str) -> Tuple[List[str], List[dict], str]:
    """CSV dosyasını oku (header + satırlar + delimiter)"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input bulunamadı: {path}")
    delim = sniff_delimiter(path, default=",")
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        dr = csv.DictReader(f, delimiter=delim)
        headers = dr.fieldnames or []
        rows = list(dr)
    return headers, rows, delim

def output_headers(input_headers: List[str]) -> List[str]:
    """
    Output header'ı oluştur:
    Marka | Kod | Kategori | ... | Mann_URL | img_url_1 | img_url_2 | img_url_3
    """
    extra_tail = ["Mann_URL", "img_url_1", "img_url_2", "img_url_3"]

    h0 = input_headers[0] if len(input_headers) >= 1 else "col_1"
    h1 = input_headers[1] if len(input_headers) >= 2 else "col_2"
    rest = input_headers[2:] if len(input_headers) > 2 else []

    out = [h0, h1, "Kategori"]  # ✅ "Mann_Kategori" → "Kategori"

    # Eski kolonları dışla (Mann_Kategori, img_url_4/5)
    rest2 = [h for h in rest if h not in ("Kategori", "Mann_Kategori", "Mann_Kategori_Raw", "img_url_4", "img_url_5")]
    out.extend(rest2)

    for h in extra_tail:
        if h not in out:
            out.append(h)
    return out

def _looks_like_header(first_row: List[str], expected_headers: List[str]) -> bool:
    """İlk satır header mı yoksa veri mi kontrol et"""
    if not first_row:
        return False
    s = [c.strip().lower() for c in first_row]
    need = 0
    for k in ("kod", "mann_url", "img_url_1"):
        if k in s:
            need += 1
    if need >= 2:
        return True
    eh = [c.strip().lower() for c in expected_headers]
    common = len(set(s) & set(eh))
    return common >= max(3, min(6, len(eh) // 3))

def repair_output_if_header_missing(expected_headers: List[str]) -> None:
    """Output CSV'de header yoksa veya yanlışsa düzelt"""
    if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) < 5:
        return

    delim_old = sniff_delimiter(OUTPUT_CSV, default=OUTPUT_DELIMITER)

    try:
        with open(OUTPUT_CSV, "r", encoding="utf-8-sig", newline="") as f:
            rd = csv.reader(f, delimiter=delim_old)
            first = next(rd, None)
            if first is None:
                return

        # Header yoksa ekle
        if not _looks_like_header(first, expected_headers):
            with open(OUTPUT_CSV, "r", encoding="utf-8-sig", newline="") as f:
                rd = csv.reader(f, delimiter=delim_old)
                rows = list(rd)
            _rewrite_output_with_expected(expected_headers, rows, has_header=False, delim_old=delim_old)
            log("INFO", f"OUTPUT header FIX: header yoktu → eklendi")
            return

        # Header var ama farklıysa güncelle
        old_headers = [c.strip() for c in first]
        if old_headers == expected_headers:
            return

        with open(OUTPUT_CSV, "r", encoding="utf-8-sig", newline="") as f:
            dr = csv.DictReader(f, delimiter=delim_old)
            data_rows = list(dr)

        _rewrite_output_dictrows(expected_headers, data_rows)
        log("INFO", f"OUTPUT header UPDATE: eski kolonlar düşürüldü")
        return

    except Exception as e:
        log("WARN", f"Output header kontrol/onarım başarısız: {e}")
        return


def _rewrite_output_with_expected(expected_headers: List[str], rows: List[List[str]], has_header: bool, delim_old: str) -> None:
    """Output dosyasını yeniden yaz (header + veri)"""
    tmp = OUTPUT_CSV + ".tmp"
    bak = OUTPUT_CSV + ".bak"
    try:
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            wr = csv.writer(f, delimiter=OUTPUT_DELIMITER, quoting=csv.QUOTE_MINIMAL)
            wr.writerow(expected_headers)

            start_idx = 1 if has_header else 0
            for r in rows[start_idx:]:
                out = [(r[i] if i < len(r) else "") for i in range(len(expected_headers))]
                wr.writerow(out)

        try:
            if os.path.exists(bak):
                os.remove(bak)
        except Exception:
            pass
        os.replace(OUTPUT_CSV, bak)
        os.replace(tmp, OUTPUT_CSV)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        raise


def _rewrite_output_dictrows(expected_headers: List[str], data_rows: List[dict]) -> None:
    """Output dosyasını dict formatında yeniden yaz"""
    tmp = OUTPUT_CSV + ".tmp"
    bak = OUTPUT_CSV + ".bak"
    try:
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            wr = csv.DictWriter(
                f,
                fieldnames=expected_headers,
                delimiter=OUTPUT_DELIMITER,
                quoting=csv.QUOTE_MINIMAL
            )
            wr.writeheader()
            for r in data_rows:
                wr.writerow({h: (r.get(h, "") if r else "") for h in expected_headers})

        try:
            if os.path.exists(bak):
                os.remove(bak)
        except Exception:
            pass
        os.replace(OUTPUT_CSV, bak)
        os.replace(tmp, OUTPUT_CSV)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        raise


def ensure_output_header(headers: List[str]) -> None:
    """Output dosyasını başlat (header yaz)"""
    repair_output_if_header_missing(headers)
    if os.path.exists(OUTPUT_CSV) and os.path.getsize(OUTPUT_CSV) > 5:
        return
    with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f, delimiter=OUTPUT_DELIMITER, quoting=csv.QUOTE_MINIMAL)
        wr.writerow(headers)

def append_output_row(headers: List[str], row: dict) -> None:
    """Output dosyasına satır ekle"""
    with open(OUTPUT_CSV, "a", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(
            f,
            fieldnames=headers,
            delimiter=OUTPUT_DELIMITER,
            quoting=csv.QUOTE_MINIMAL
        )
        wr.writerow({h: row.get(h, "") for h in headers})

def load_done_codes_from_output() -> set:
    """Output'ta zaten işlenmiş kodları yükle (resume için)"""
    if not os.path.exists(OUTPUT_CSV):
        return set()
    done = set()
    try:
        delim = sniff_delimiter(OUTPUT_CSV, default=OUTPUT_DELIMITER)
        with open(OUTPUT_CSV, "r", encoding="utf-8-sig", newline="") as f:
            dr = csv.DictReader(f, delimiter=delim)
            for r in dr:
                k = (r.get("Kod") or "").strip()
                if k:
                    done.add(k.upper())
    except Exception:
        pass
    return done


# ===================== CODE NORMALIZE =====================
# Bilinen prefix'ler (uzundan kısaya sıralı - CF önce gelmeli)
PREFIXES = ["CUK", "WDK", "CF", "BF", "CU", "HU", "PU", "TB", "WD", "WK", "W", "H", "C", "P"]

def strip_m_prefix(s: str) -> str:
    """'M.' veya 'M:' prefix'ini sil (örn: M.HU 718 → HU 718)"""
    if not s:
        return ""
    t = str(s).strip()
    return re.sub(r"^\s*M\s*[\.\:\-]\s*", "", t, flags=re.IGNORECASE).strip()

def normalize_code_display(code: str) -> str:
    """
    Kod formatını düzelt:
    - "HU718/1k" → "HU 718/1 k"
    - "WDK11102/28" → "WDK 11102/28"
    """
    if not code:
        return ""
    c = strip_m_prefix(code)
    c = re.sub(r"\s+", " ", c).strip()

    # İki harfli prefixler (HU, WK, CU)
    toks = c.split()
    if len(toks) >= 2:
        if len(toks) >= 3 and toks[0].upper() == "C" and toks[1].upper() == "U" and toks[2].upper() == "K":
            return "CUK " + " ".join(toks[3:]).strip()
        if toks[0].upper() == "H" and toks[1].upper() == "U":
            return "HU " + " ".join(toks[2:]).strip()
        if toks[0].upper() == "W" and toks[1].upper() == "K":
            return "WK " + " ".join(toks[2:]).strip()
        if toks[0].upper() == "C" and toks[1].upper() == "U":
            return "CU " + " ".join(toks[2:]).strip()

    # Tek harfli prefixler (H, W, C, TB, WD vs.)
    up = c.upper()
    pref = ""
    for p in PREFIXES:
        if up.startswith(p + " ") or up == p or up.startswith(p):
            pref = p
            break
    if not pref:
        return c

    rest = c[len(pref):].strip()
    rest = re.sub(r"\s+", " ", rest).strip()
    return f"{pref} {rest}".strip() if rest else pref

def code_scene7_tokens(code: str) -> List[str]:
    """
    Kod için Scene7 URL'de bulunması gereken token'lar
    Örn: "HU 718/1 k" → ["HU_718.1_k", "718.1_k", "HU_718_1_k"]
    """
    c = normalize_code_display(code or "").strip()
    if not c:
        return []
    up = c.upper()
    parts = up.split(" ", 1)
    pref = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""

    # "/" → "." ve space → "_"
    rest = rest.replace("/", ".")
    rest = re.sub(r"\s+", "_", rest)
    rest = re.sub(r"_+", "_", rest).strip("_")

    tokens = []
    if rest:
        tokens.append(f"{pref}_{rest}")
        tokens.append(rest)
        if "." in rest:
            tokens.append(f"{pref}_{rest.replace('.', '_')}")
    else:
        tokens.append(pref)

    # Tekrar eden token'ları sil
    out, seen = [], set()
    for t in tokens:
        k = t.upper()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out


# ===================== IMAGE URL TEMİZLEME =====================
def clean_scene7_url(url: str) -> str:
    """
    Scene7 URL'den gereksiz parametreleri temizle

    ÖNCE: https://s7g10.scene7.com/.../HU_718.1_k?qlt=82&amp;ts=...&quot;,&quot;is3D...
    SONRA: https://s7g10.scene7.com/.../HU_718.1_k
    """
    if not url:
        return ""

    url = str(url).strip()

    # HTML entities → normal karakter
    url = url.replace("&amp;", "&")
    url = url.replace("&quot;", '"')
    url = url.replace("&lt;", "<")
    url = url.replace("&gt;", ">")
    url = url.replace("&#39;", "'")

    # JSON parçalarını kes
    if '","' in url:
        url = url.split('","')[0]
    if '",' in url:
        url = url.split('",')[0]
    if '"' in url and not url.startswith('"'):
        parts = url.split('"')
        url = parts[0]

    # Query parametrelerini sil (?qlt=82&ts=... kısmı)
    url = url.split("?")[0]

    # Sondaki gereksiz karakterler
    url = url.rstrip('",;\\/')

    return url.strip()


# ===================== SELENIUM =====================
def make_driver() -> webdriver.Chrome:
    """Chrome driver oluştur"""
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")

    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1500,950")
    opts.add_argument("--lang=tr-TR")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--log-level=3")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    opts.page_load_strategy = "none"

    service = Service(ChromeDriverManager().install())
    d = webdriver.Chrome(service=service, options=opts)
    d.set_page_load_timeout(35)
    return d

def enable_fast_blocking(d: webdriver.Chrome) -> None:
    """Görsel/font/video blok (hız için)"""
    if not BLOCK_HEAVY_ASSETS:
        return
    try:
        d.execute_cdp_cmd("Network.enable", {})
        d.execute_cdp_cmd("Network.setBlockedURLs", {
            "urls": [
                "*.jpg*", "*.jpeg*", "*.png*", "*.gif*", "*.webp*",
                "*.mp4*", "*.webm*", "*.avi*", "*.mov*",
                "*.woff*", "*.woff2*", "*.ttf*", "*.otf*",
            ]
        })
        log("INFO", "CDP block aktif (hız optimizasyonu)")
    except Exception as e:
        log("WARN", f"CDP block açılamadı: {e}")

def wait_dom_interactive(d: webdriver.Chrome, timeout: float = 14.0) -> None:
    """DOM yüklenene kadar bekle"""
    end = time.time() + timeout
    while time.time() < end:
        try:
            rs = d.execute_script("return document.readyState")
            if rs in ("interactive", "complete"):
                return
        except Exception:
            pass
        time.sleep(0.06)

def safe_click(d, el) -> bool:
    """Element'e güvenli tıkla (3 farklı yöntem dene)"""
    try:
        d.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.05)
        el.click()
        return True
    except Exception:
        try:
            ActionChains(d).move_to_element(el).pause(0.03).click(el).perform()
            return True
        except Exception:
            try:
                d.execute_script("arguments[0].click();", el)
                return True
            except Exception:
                return False

def hard_kill_onetrust(d) -> None:
    """OneTrust cookie popup'ı kaldır"""
    try:
        d.execute_script("""
            const ids = ['onetrust-consent-sdk', 'onetrust-banner-sdk', 'onetrust-pc-sdk'];
            ids.forEach(id=>{
              const el = document.getElementById(id);
              if(el) el.remove();
            });
            document.querySelectorAll('.onetrust-consent-sdk, .onetrust-pc-dark-filter, .ot-sdk-container, .ot-sdk-row')
              .forEach(e=>e.remove());
        """)
    except Exception:
        pass

def dismiss_overlays(d) -> None:
    """Popup'ları kapat (cookie, kabul et vs.)"""
    xps = [
        "//button[contains(., 'Tümüne İzin Ver') or contains(., 'Tümüne izin ver')]",
        "//button[contains(., 'Tümünü Kabul Et') or contains(., 'Tümünü kabul et')]",
        "//button[contains(translate(., 'ACCEPT', 'accept'), 'accept')]",
        "//button[contains(translate(., 'KABUL', 'kabul'), 'kabul')]",
        "//button[contains(., 'Seçimlerimi Onayla') or contains(., 'Seçimlerimi onayla')]",
        "//button[contains(translate(., 'CONFIRM', 'confirm'), 'confirm')]",
        "//button[contains(translate(@aria-label, 'KAPATCLOSE', 'kapatclose'), 'kapat') or contains(translate(@aria-label, 'KAPATCLOSE', 'kapatclose'), 'close')]",
    ]
    for xp in xps:
        try:
            els = d.find_elements(By.XPATH, xp)
            for el in els[:3]:
                if el.is_displayed():
                    safe_click(d, el)
                    time.sleep(0.15)
        except Exception:
            pass
    hard_kill_onetrust(d)

def force_focus_and_set_value(d, el, value: str) -> None:
    """Input'a zorla değer yaz (JavaScript ile)"""
    d.execute_script(
        """
        const el = arguments[0];
        const val = arguments[1];
        el.scrollIntoView({block:'center'});
        el.focus();
        el.value = val;
        el.dispatchEvent(new Event('input', {bubbles:true}));
        el.dispatchEvent(new Event('change', {bubbles:true}));
        """,
        el, value
    )

def clear_and_type_robust(d, el, text: str) -> None:
    """Input'u temizle ve yavaş yavaş yaz"""
    dismiss_overlays(d)
    try:
        d.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.05)
        el.click()
        el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.DELETE)
        for ch in text:
            el.send_keys(ch)
            time.sleep(TYPE_DELAY)
        return
    except Exception:
        pass
    force_focus_and_set_value(d, el, text)


# ===================== ML KATEGORİ TAHMİNİ =====================
# 6905 üründen öğrenilmiş + manuel düzeltilmiş pattern tablosu
CATEGORY_PATTERNS = {
    # Yağ filtreleri (92 ürün)
    "HU": "Yağ Filtresi",      # 48 ürün, %97.9 doğruluk
    "W": "Yağ Filtresi",       # 47 ürün, %87.2 doğruluk
    "ZR": "Yağ Filtresi",      # 2 ürün, %100.0 doğruluk
    "LB": "Yağ Filtresi",      # 1 ürün, %100.0 doğruluk
    "WP": "Yağ Filtresi",      # W P prefix

    # Yakıt filtreleri (63 ürün)
    "WK": "Yakıt Filtresi",    # 36 ürün, %100.0 doğruluk
    "PU": "Yakıt Filtresi",    # 14 ürün, %100.0 doğruluk
    "PL": "Yakıt Filtresi",    # 3 ürün, %100.0 doğruluk
    "WDK": "Yakıt Filtresi",   # 2 ürün, %100.0 doğruluk
    "P": "Yakıt Filtresi",     # 2 ürün, %100.0 doğruluk

    # Hava filtreleri (57 ürün)
    "C": "Hava Filtresi",      # 36 ürün, %97.2 doğruluk
    "TB": "Hava Filtresi",     # 5 ürün, %100.0 doğruluk (hava kurutucu kartuşu)
    "CF": "Hava Filtresi",     # 5 ürün, %80.0 doğruluk

    # Kabin Hava Filtreleri ✅ MANUEL DÜZELTİLDİ
    "CU": "Kabin Hava Filtresi",   # 9 ürün, %100 DOĞRU ✅
    "CUK": "Kabin Hava Filtresi",  # 7 ürün, %100 DOĞRU ✅
    "FP": "Kabin Hava Filtresi",   # %100 DOĞRU ✅

    # NOT: H prefix çok belirsiz (Hidrolik Direksiyon/Şanzıman/Yağ vs.)
    # Web scraping kategoriden otomatik algılanacak
    # HD prefix varsa eklenebilir
}

def predict_category_from_code(code: str) -> str:
    """
    ML: Kod prefix'ine göre kategori tahmin et
    6905 üründen öğrenilmiş + manuel düzeltilmiş pattern'ler

    Örnek:
    - HU 718/1 k → HU → Yağ filtresi
    - TB 1374/13 X → TB → Hava filtresi
    - CF 16 002 → CF → Hava filtresi
    - CU 2101 → CU → Kabin Hava Filtresi ✅
    - CUK 3037 → CUK → Kabin Hava Filtresi ✅
    - FP 123 → FP → Kabin Hava Filtresi ✅
    - H 601/4 → Web scraping → Hidrolik Direksiyon Filtresi ✅
    """
    if not code:
        return ""

    normalized = normalize_code_display(code)
    parts = normalized.split(" ", 1)
    prefix = parts[0].upper() if parts else ""

    # Pattern tablosunda ara
    return CATEGORY_PATTERNS.get(prefix, "")


# ===================== KATEGORİ (H1 ÜSTÜ HEADİNG) =====================
def normalize_filter_category_text(cat_txt: str) -> str:
    """Kategori metnini normalize et → Yağ/Hava/Yakıt/Kabin Hava/Hidrolik filtresi"""
    up = (cat_txt or "").strip().upper()
    if not up:
        return ""

    # Hidrolik kategorileri (önce spesifikten başla)
    if "HIDROLIK" in up or "HYDRAULIC" in up:
        if "DIREKSIYON" in up or "STEERING" in up or "DIREKTION" in up:
            return "Hidrolik Direksiyon Filtresi"
        elif "ŞANZIMAN" in up or "SANZIMAN" in up or "TRANSMISSION" in up:
            return "Hidrolik Şanzıman Filtresi"
        else:
            return "Hidrolik"

    # Kabin hava filtresi
    if "KABIN" in up or "CABIN" in up:
        return "Kabin Hava Filtresi"

    # "Hava kurutucu kartuşu" → "Hava filtresi"
    if "KURUTUCU" in up or "DRYER" in up:
        return "Hava Filtresi"

    if "YAKIT" in up or "FUEL" in up:
        return "Yakıt Filtresi"
    if "YAĞ" in up or "YAG" in up or "OIL" in up:
        return "Yağ Filtresi"
    if "HAVA" in up or "AIR" in up:
        return "Hava Filtresi"

    return ""

def get_category_from_product_page(d, code: str) -> str:
    """
    Ürün sayfasında kategoriyi al:
    1) Web scraping dene (.cmp-product__title-family vs.)
    2) Başarısız olursa ML ile kod prefix'inden tahmin et
    """
    # 1) WEB SCRAPING DENE
    try:
        # 1a) Önce direkt class'tan dene
        try:
            cat_el = d.find_element(By.CSS_SELECTOR, ".cmp-product__title-family")
            cat_text = (cat_el.text or "").strip()
            if cat_text:
                normalized = normalize_filter_category_text(cat_text)
                if normalized:
                    return normalized
        except Exception:
            pass

        # 1b) Alternatif: "filtre" içeren tüm başlıklar
        try:
            headings = d.find_elements(By.CSS_SELECTOR, "h2, h3, h4, .cmp-product__title-family, [class*='title'], [class*='category']")
            for h in headings[:15]:
                try:
                    txt = (h.text or "").strip()
                    if txt and ("filtre" in txt.lower() or "filter" in txt.lower() or "kurutucu" in txt.lower()):
                        normalized = normalize_filter_category_text(txt)
                        if normalized:
                            return normalized
                except Exception:
                    continue
        except Exception:
            pass

        # 1c) Son çare: H1 üstündeki heading
        try:
            h1 = d.find_element(By.CSS_SELECTOR, "h1")
            category_text = d.execute_script("""
                let h1 = arguments[0];
                let allHeadings = document.querySelectorAll('h2, h3');
                let closestHeading = null;
                let minDistance = Infinity;
                let h1Rect = h1.getBoundingClientRect();

                for(let heading of allHeadings) {
                    let headingRect = heading.getBoundingClientRect();
                    if(headingRect.top < h1Rect.top) {
                        let distance = h1Rect.top - headingRect.top;
                        if(distance < minDistance) {
                            minDistance = distance;
                            closestHeading = heading;
                        }
                    }
                }
                return closestHeading ? closestHeading.textContent.trim() : '';
            """, h1)

            if category_text:
                normalized = normalize_filter_category_text(category_text)
                if normalized:
                    return normalized
        except Exception:
            pass

    except Exception as e:
        log("WARN", f"Web scraping başarısız: {e}")

    # 2) ML TAHMİNİ (scraping başarısızsa)
    ml_prediction = predict_category_from_code(code)
    if ml_prediction:
        log("DBG", f"ML tahmin: {code} → {ml_prediction}")
        return ml_prediction

    return ""


# ===================== SCENE7 GÖRSEL TOPLAMA =====================
def is_scene7(url: str) -> bool:
    """URL Scene7 URL'si mi?"""
    return (url or "").strip().startswith(SCENE7_PREFIX)

def scene7_asset_name(url: str) -> str:
    """Scene7 URL'den asset ismini al (mannhummel/ sonrası)"""
    u = (url or "").strip().replace("\\/", "/")
    u = u.split("?", 1)[0]
    if not u.startswith(SCENE7_PREFIX):
        return ""
    return u[len(SCENE7_PREFIX):].strip()

def url_has_code(url: str, code: str) -> bool:
    """URL içinde ürün kodu var mı? (HU_718.1_k gibi)"""
    if not is_scene7(url):
        return False
    asset = scene7_asset_name(url)
    if not asset:
        return False
    asset_up = asset.upper()
    for tok in code_scene7_tokens(code):
        if tok.upper() in asset_up:
            return True
    return False

def extract_scene7_from_html(html: str) -> List[str]:
    """HTML source'dan tüm Scene7 URL'leri regex ile çek"""
    if not html:
        return []
    html2 = html.replace("\\/", "/")
    pat = r"https://s7g10\.scene7\.com/is/image/mannhummel/[A-Za-z0-9_\-./]+(?:\?[^\s\"']+)?"
    return re.findall(pat, html2, flags=re.I) or []

def _meta_content(d, prop_names: List[str]) -> List[str]:
    """Meta tag'lerden görsel URL'leri al (og:image vs.)"""
    out = []
    for p in prop_names:
        try:
            els = d.find_elements(By.CSS_SELECTOR, f"meta[property='{p}'], meta[name='{p}']")
            for el in els:
                v = (el.get_attribute("content") or "").strip()
                if v:
                    out.append(v)
        except Exception:
            pass
    return out

def collect_scene7_images_only_for_code(d, code: str) -> List[str]:
    """
    Scene7 görselleri topla:
    - Sadece ürün kodu içeren
    - Max 3 adet
    - Temiz URL (query params yok)
    """
    urls = []

    # 1) HTML source
    try:
        urls.extend(extract_scene7_from_html(d.page_source or ""))
    except Exception:
        pass

    # 2) Meta tags
    try:
        urls.extend(_meta_content(d, ["og:image", "twitter:image"]))
    except Exception:
        pass

    # 3) <img> elementleri
    try:
        imgs = d.find_elements(By.CSS_SELECTOR, "img")
        for img in imgs[:900]:
            for attr in ["src", "data-src", "data-original", "data-lazy", "data-zoom-image", "data-large-image"]:
                v = (img.get_attribute(attr) or "").strip()
                if v:
                    urls.append(v)
    except Exception:
        pass

    # Filtrele + temizle
    seen = set()
    out = []
    for u in urls:
        u = (u or "").strip()
        if not u:
            continue
        if not is_scene7(u):
            continue
        if not url_has_code(u, code):  # Kod içermeyen skip
            continue

        # URL temizle
        clean_u = clean_scene7_url(u)

        k = clean_u.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(clean_u)

        if len(out) >= MAX_IMG:
            break

    return out


def wait_for_scene7_code(d, code: str, timeout: float = PRODUCT_WAIT) -> bool:
    """Ürün sayfasındaki JS/HTML Scene7 verisinin gelmesini bekle."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            html = d.page_source or ""
            for raw_url in extract_scene7_from_html(html):
                if url_has_code(clean_scene7_url(raw_url), code):
                    return True
            imgs = d.find_elements(By.CSS_SELECTOR, "img")
            for img in imgs[:300]:
                for attr in ("src", "data-src", "data-original", "data-lazy", "data-zoom-image", "data-large-image"):
                    value = (img.get_attribute(attr) or "").strip()
                    if value and url_has_code(clean_scene7_url(value), code):
                        return True
        except Exception:
            pass
        time.sleep(0.20)
    return False


# ===================== DROPDOWN ARAMA =====================
def find_search_input(d):
    """Arama input'unu bul"""
    dismiss_overlays(d)
    try:
        return WebDriverWait(d, 4).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "input[placeholder*='Arama terimi']"))
        )
    except Exception:
        pass
    for sel in ["input[type='search']", "input[role='combobox']", "input[type='text']", "input:not([type])"]:
        try:
            els = d.find_elements(By.CSS_SELECTOR, sel)
            for e in els:
                if e.is_displayed() and e.size.get("width", 0) >= 250:
                    return e
        except Exception:
            continue
    return None

def _get_listbox_from_input(d, search_input):
    """Input'un aria-controls ile bağlı listbox'ı bul"""
    if not search_input:
        return None
    for attr in ("aria-controls", "aria-owns"):
        try:
            lb_id = (search_input.get_attribute(attr) or "").strip()
            if lb_id:
                try:
                    el = d.find_element(By.ID, lb_id)
                    if el and el.is_displayed():
                        return el
                except Exception:
                    pass
        except Exception:
            pass
    try:
        wrapper = d.execute_script(
            """
            const inp = arguments[0];
            let cur = inp;
            for(let i=0;i<6 && cur; i++){
              const cand = cur.querySelector && cur.querySelector("[role='listbox']");
              if(cand) return cand;
              cur = cur.parentElement;
            }
            return null;
            """,
            search_input
        )
        return wrapper
    except Exception:
        return None

def _dropdown_candidates_under_input(search_input):
    """Input altındaki dropdown item'ları bul (XPath)"""
    if not search_input:
        return []
    xps = [
        ".//following::ul[1]//li//*[self::a or self::li or @role='option']",
        ".//following::div[1]//ul//li//*[self::a or self::li or @role='option']",
        ".//following::div[contains(@class,'autocomplete') or contains(@class,'suggest') or contains(@class,'typeahead')][1]//*[self::a or self::li or @role='option']",
    ]
    for xp in xps:
        try:
            els = search_input.find_elements(By.XPATH, xp)
            out = []
            for e in els[:80]:
                try:
                    if e.is_displayed():
                        out.append(e)
                except Exception:
                    continue
            if out:
                return out
        except Exception:
            continue
    return []

def _best_dropdown_item(cands: List, code: str):
    """Dropdown item'ları skorla, en iyisini seç"""
    if not cands:
        return None
    code_up = normalize_code_display(code or "").upper()
    code_compact = re.sub(r"[^A-Z0-9]", "", code_up)
    bad_words = ("KATALOG", "CATALOG", "KATAL", "GÜNCEL", "DÜZENLİ OLARAK")

    scored = []
    order = 0
    for e in cands:
        order += 1
        try:
            if not e.is_displayed():
                continue
        except Exception:
            continue

        try:
            tx = (e.text or "").strip()
        except Exception:
            tx = ""
        up = (tx or "").upper()
        # Sadece kullanıcının istediği MANN-FILTER sonucu kabul edilir.
        # Aynı kod için PURFLUX/SAKURA gibi diğer marka sonuçlarına tıklanmaz.
        if not re.search(r"\bMANN[\s-]*FILTER\b", up):
            continue
        if up and any(w in up for w in bad_words):
            continue

        href = ""
        try:
            if (e.tag_name or "").lower() == "a":
                href = (e.get_attribute("href") or "").strip()
            else:
                try:
                    a = e.find_element(By.CSS_SELECTOR, "a[href]")
                    href = (a.get_attribute("href") or "").strip()
                except Exception:
                    href = ""
        except Exception:
            href = ""

        up_compact = re.sub(r"[^A-Z0-9]", "", up)
        href_compact = re.sub(r"[^A-Z0-9]", "", (href or "").upper())
        score = 0
        if code_compact and (code_compact in up_compact or code_compact in href_compact):
            # MANN dropdown ürünleri bazen href="#" ile gelir;
            # gerçek /urun.html/ adresi tıklama sonrası JavaScript ile oluşur.
            score += 1200 if "/urun.html/" in (href or "") else 1000
        else:
            continue
        if "MANN" in up:
            score += 10

        if score > 0:
            scored.append((score, -order, e))

    if scored:
        scored.sort(reverse=True)
        return scored[0][2]

    # Güvenli davranış: ürün linki doğrulanmadıysa hiçbir öğeyi seçme.
    return None

def find_first_dropdown_item(d, search_input, code: str):
    """Dropdown'daki en iyi ürün item'ını bul"""
    dismiss_overlays(d)
    listbox = _get_listbox_from_input(d, search_input)
    cands = []
    if listbox:
        try:
            cands = listbox.find_elements(By.CSS_SELECTOR, "a, li, [role='option']")[:80]
        except Exception:
            cands = []
    if not cands:
        cands = _dropdown_candidates_under_input(search_input)
    if not cands:
        try:
            cands = d.find_elements(By.CSS_SELECTOR, "[role='listbox'] [role='option'], ul li a, ul li")[:120]
        except Exception:
            cands = []
    return _best_dropdown_item(cands, code)

def dropdown_wait_and_click(d, search_input, code: str) -> Optional[str]:
    """Dropdown bekle → ilk ürüne tıkla → URL döndür"""
    log("STEP", f"WAIT {DROPDOWN_WAIT_SECONDS:.0f}sn (dropdown)")
    time.sleep(DROPDOWN_WAIT_SECONDS)

    item = None
    item_wait_end = time.time() + 12.0
    while time.time() < item_wait_end:
        item = find_first_dropdown_item(d, search_input, code)
        if item:
            break
        time.sleep(0.25)
    if not item:
        return None

    href = ""
    try:
        if item.tag_name.lower() == "a":
            href = (item.get_attribute("href") or "").strip()
        else:
            try:
                a = item.find_element(By.CSS_SELECTOR, "a[href]")
                href = (a.get_attribute("href") or "").strip()
            except Exception:
                href = ""
    except Exception:
        href = ""

    log("STEP", f"CLICK → '{(item.text or '').strip()[:60]}'")
    safe_click(d, item)
    time.sleep(0.25)
    wait_dom_interactive(d, 14.0)
    dismiss_overlays(d)

    # href="#" olan JS dropdown öğesinde gerçek URL'nin oluşmasını bekle.
    end = time.time() + PRODUCT_WAIT
    while time.time() < end:
        cur = (d.current_url or "").strip()
        if "/urun.html/" in cur:
            return cur
        time.sleep(0.15)

    cur = (d.current_url or "").strip()
    if "/urun.html/" in cur:
        return cur
    if "/urun.html/" in href:
        return href

    return None


# ===================== SESSION YÖNETİMİ =====================
class MannCatalogSession:
    """MANN katalog session - tab yönetimi"""
    def __init__(self, driver: webdriver.Chrome):
        self.d = driver
        self.wait = WebDriverWait(driver, 20)
        self.catalog_tab = None
        self.search_input = None

    def start(self) -> None:
        """Katalog sayfasını aç"""
        log("STEP", f"OPEN → {CATALOG_URL}")
        self.d.get(CATALOG_URL)
        wait_dom_interactive(self.d, 14.0)
        time.sleep(0.40)
        dismiss_overlays(self.d)

        self.catalog_tab = self.d.current_window_handle
        self.search_input = find_search_input(self.d)
        if not self.search_input:
            raise RuntimeError("Arama kutusu bulunamadı!")
        log("INFO", "Katalog hazır")

    def reset(self) -> None:
        """Katalog tab'ına geri dön"""
        try:
            self.d.switch_to.window(self.catalog_tab)
        except Exception:
            pass

        cur = (self.d.current_url or "")
        if "/urun.html/" in cur or "arama-sonuclari" in cur:
            log("STEP", "BACK → katalog")
            try:
                self.d.get(CATALOG_URL)
                wait_dom_interactive(self.d, 14.0)
                time.sleep(0.35)
            except Exception:
                pass

        dismiss_overlays(self.d)
        self.search_input = find_search_input(self.d)

    def search_open_product_tab(self, code: str) -> Optional[str]:
        """Supabase kodunu arama çubuğuna yaz → 5 sn bekle → MANN satırına tıkla."""
        self.reset()

        if not self.search_input:
            self.search_input = find_search_input(self.d)
        if not self.search_input:
            raise RuntimeError("Search input yok!")

        log("STEP", f"TYPE → '{code}'")
        clear_and_type_robust(self.d, self.search_input, code)

        product_url = dropdown_wait_and_click(self.d, self.search_input, code)
        if not product_url:
            return None

        # Yeni tab aç
        self.d.switch_to.window(self.catalog_tab)
        self.d.execute_script("window.open(arguments[0], '_blank');", product_url)
        time.sleep(0.12)

        handle = self.d.window_handles[-1]
        self.d.switch_to.window(handle)
        wait_dom_interactive(self.d, 14.0)
        time.sleep(0.25)
        dismiss_overlays(self.d)

        return product_url

    def open_product_tab(self, product_url: str) -> Optional[str]:
        """Supabase'te kayıtlı ürün URL'sini arama yapmadan yeni tab'da aç."""
        if not product_url or "/urun.html/" not in product_url:
            return None
        self.d.switch_to.window(self.catalog_tab)
        self.d.execute_script("window.open(arguments[0], '_blank');", product_url)
        time.sleep(0.12)
        handle = self.d.window_handles[-1]
        self.d.switch_to.window(handle)
        wait_dom_interactive(self.d, 14.0)
        time.sleep(0.25)
        dismiss_overlays(self.d)
        return product_url

    def close_product_tab(self) -> None:
        """Ürün tab'ını kapat, katalog'a dön"""
        try:
            if self.d.current_window_handle != self.catalog_tab:
                self.d.close()
        except Exception:
            pass
        try:
            self.d.switch_to.window(self.catalog_tab)
        except Exception:
            pass


# ===================== SUPABASE =====================
def supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def load_supabase_rows(session: requests.Session) -> List[dict]:
    """IKILER_MANN tablosundan stoklu MANN kayıtlarını sayfalı oku."""
    if not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_SECRET_KEY veya SUPABASE_KEY tanımlı değil")

    rows: List[dict] = []
    offset = 0
    page_size = 500
    while True:
        resp = session.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
            params={
                "select": "sku,kod,marka,kategori,toplam_stok,mann_url,img_url_1,img_url_2,img_url_3",
                "marka": "eq.MANN-FILTER",
                "toplam_stok": "gt.0",
                "limit": page_size,
                "offset": offset,
                "order": "sku.asc",
            },
            headers=supabase_headers(),
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Supabase SELECT hata {resp.status_code}: {resp.text[:300]}")
        batch = resp.json()
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += len(batch)
    return rows


def clean_db_code(raw: str) -> str:
    """Supabase kodunu MANN katalog arama formatına getir."""
    value = (raw or "").strip()
    value = re.sub(r"^\s*(?:YD[.\s-]*)?(?:MANN[-\s]?FILTER|MANN)\s*", "", value, flags=re.IGNORECASE)
    return normalize_code_display(value)


def is_valid_mann_catalog_code(code: str) -> bool:
    """Dahili/numerik stok kodunu MANN katalog kodundan ayır."""
    normalized = clean_db_code(code)
    return bool(re.match(r"^[A-Z]{1,4}\s*[0-9]", normalized, flags=re.IGNORECASE))


def code_from_product_url(product_url: str) -> str:
    """Mevcut MANN ürün URL'sinden görsel doğrulama için ürün kodu çıkar."""
    if not product_url:
        return ""
    # Ürün slug'ında slash ürün kodunun parçasıdır: bf1018/1_mann-filter.html.
    m = re.search(r"/urun\.html/([^?#]+)", unquote(product_url), flags=re.IGNORECASE)
    if not m:
        return ""
    slug = re.sub(r"_mann-filter.*$", "", m.group(1), flags=re.IGNORECASE)
    slug = slug.replace("_", " ")
    return normalize_code_display(slug)


def build_mann_product_url(code: str) -> str:
    """MANN kodundan doğrudan ürün URL'si üret."""
    normalized = clean_db_code(code)
    compact = normalized.replace(" ", "").lower()
    if not compact:
        return ""
    slug = quote(f"{compact}_mann-filter.html", safe="/._-")
    return f"{MANN_PRODUCT_PREFIX}{slug}"


def resolve_mann_product_url(code: str) -> Optional[str]:
    """Doğrudan MANN URL'sini HTTP ile doğrula; bulunamazsa boş dön."""
    url = build_mann_product_url(code)
    if not url:
        return None
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "tr-TR,tr;q=0.9"},
            timeout=15,
            allow_redirects=True,
        )
        if resp.status_code == 200 and "/urun.html/" in (resp.url or "") and "<h1" in resp.text.lower():
            return resp.url
    except requests.RequestException as exc:
        log("DBG", f"Direkt MANN URL kontrolü başarısız: {code} → {type(exc).__name__}")
    return None


def patch_supabase_row(session: requests.Session, row: dict, category: str, product_url: str, images: List[str]) -> bool:
    """Tam yenilemede doğrulanan kategori, URL ve üç görsel alanını güncelle."""
    payload = {}
    if category:
        payload["kategori"] = category
    if product_url:
        current_url = (row.get("mann_url") or "").strip()
        if product_url.strip() != current_url:
            payload["mann_url"] = product_url
    for i in range(1, MAX_IMG + 1):
        key = f"img_url_{i}"
        new_image = images[i - 1] if i <= len(images) else ""
        if new_image != (row.get(key) or "").strip():
            payload[key] = new_image
    if not payload:
        return True

    sku = (row.get("sku") or "").strip()
    if not sku:
        log("WARN", "SKU boş olduğu için Supabase PATCH atlandı")
        return False
    resp = session.patch(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
        params={"sku": f"eq.{sku}"},
        json=payload,
        headers={**supabase_headers(), "Prefer": "return=minimal"},
        timeout=30,
    )
    if resp.status_code not in (200, 204):
        log("ERROR", f"Supabase PATCH hata {resp.status_code} | SKU={sku} | {resp.text[:200]}")
        return False
    return True


# ===================== MAIN =====================
def main():
    supa = requests.Session()
    rows = load_supabase_rows(supa)
    # Kullanıcı talebi: mevcut URL/görsel dolu olsa bile tüm stoklu kayıtlar
    # Supabase kodu ile Selenium aramasından baştan geçirilir.
    candidates = list(rows)

    if LIMIT:
        candidates = candidates[:LIMIT]

    total = len(candidates)
    log("INFO", f"SUPABASE FULL REFRESH START | stoklu MANN kayıtları={len(rows)} | yeniden kontrol={total}")
    if not candidates:
        log("OK", "İşlenecek eksik URL/görsel kaydı yok")
        return

    d = make_driver()
    enable_fast_blocking(d)
    sess = MannCatalogSession(d)
    ok = no = fail = 0
    cache: Dict[str, Tuple[str, str, List[str]]] = {}

    try:
        sess.start()
        for idx, row in enumerate(candidates, start=1):
            kod = clean_db_code(row.get("kod") or "")
            if not kod:
                fail += 1
                log("WARN", f"[{idx}/{total}] Boş/geçersiz kod | SKU={row.get('sku', '')}")
                continue
            if not is_valid_mann_catalog_code(kod):
                fail += 1
                log("WARN", f"[{idx}/{total}] MANN kodu değil, katalog araması atlandı: {kod} | SKU={row.get('sku', '')}")
                continue

            # Her aday için kaynak Supabase kodu arama çubuğuna yazılır.
            search_code = kod
            cache_key = search_code
            if cache_key in cache:
                product_url, category, images = cache[cache_key]
            else:
                product_url = None
                error = None
                for attempt in range(1, 4):
                    try:
                        product_url = sess.search_open_product_tab(search_code)
                        error = None
                        break
                    except (ElementNotInteractableException, StaleElementReferenceException, TimeoutException, WebDriverException) as exc:
                        error = exc
                        log("WARN", f"Retry({attempt}) {search_code} → {type(exc).__name__}")
                        try:
                            sess.reset()
                        except Exception:
                            pass
                        time.sleep(0.45)

                if error or not product_url:
                    no += 1
                    log("WARN", f"[{idx}/{total}] MANN ürün bulunamadı: {search_code}")
                    continue

                try:
                    try:
                        WebDriverWait(d, PRODUCT_WAIT).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
                    except Exception:
                        pass
                    has_scene7 = wait_for_scene7_code(d, search_code, PRODUCT_WAIT)
                    if not has_scene7:
                        log("DBG", f"Scene7 bekleme zaman aşımı veya ürün görseli yok: {search_code}")
                    category = get_category_from_product_page(d, search_code)
                    images = collect_scene7_images_only_for_code(d, search_code)
                finally:
                    sess.close_product_tab()
                cache[cache_key] = (product_url, category, images)

            if patch_supabase_row(supa, row, category, product_url, images):
                ok += 1
                log("OK", f"[{idx}/{total}] {search_code} | kategori={category or '-'} | görsel={len(images)}")
            else:
                fail += 1
            time.sleep(SLEEP_BETWEEN)
    finally:
        try:
            d.quit()
        except Exception:
            pass

    log("STAT", f"DONE | OK={ok} | NO={no} | FAIL={fail} | TOTAL={total}")


if __name__ == "__main__":
    main()
