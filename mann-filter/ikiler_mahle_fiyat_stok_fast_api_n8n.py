#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
===============================================================================
 İKİLER OTOMOTİV - ÇOKLU MARKA FİYAT & STOK SENKRONİZASYON SİSTEMİ
 FastAPI + N8N + Shopify + WhatsApp (Evolution API)
===============================================================================

GENEL AÇIKLAMA:
    Bu sistem, İkiler B2B tedarikçi platformundan (b4b.ikilerotomotiv.com)
    belirtilen markalar için ürün fiyatı ve stok bilgisi çeker, bu verileri
    işleyerek Shopify mağazasıyla senkronize eder. Tüm işlemler loglanır ve
    sonuçlar WhatsApp üzerinden raporlanır.

DESTEKLENEN MARKALAR:
    - MAHLE         : OX, OC, KL, KX, LX, LA kodlu filtreler
    - MANN-FILTER   : W, WK, C, CU, H, HU kodlu filtreler
    - PURFLUX       : L, LS, A, AN, CS, C kodlu filtreler
    - UFI FILTERS   : 23, 24, 25, 26, 27 ile başlayan kodlar
    - FILTORQ       : Marka özel kodlar
    - FILTRON       : OP, OE, PP, AP, AM, AR kodlu filtreler

KURULUM GEREKSİNİMLERİ:
    pip install fastapi uvicorn requests pandas python-dotenv colorama

ÇEVRE DEĞİŞKENLERİ (.env dosyası):
    COOKIE_STR          = İkiler B2B oturum cookie'si (zorunlu)
    SHOPIFY_STORE       = Shopify mağaza adresi (örn: magazam.myshopify.com)
    SHOPIFY_TOKEN       = Shopify Admin API erişim token'ı
    SHOPIFY_API_VERSION = API versiyonu (varsayılan: 2024-01)
    PRICE_MULTIPLIER    = Fiyat çarpanı (varsayılan: 1.75 = %75 kar)
    LOG_DIR             = Log dosyaları dizini (varsayılan: ./logs)
    REPORT_DIR          = Rapor dosyaları dizini (varsayılan: ./reports)

FASTAPI ENDPOINTLERİ:
    GET  /health                          → Sistem durumu kontrolü
    GET  /scrape/{marka}?limit=N          → Tek marka veri çek
    GET  /scrape/all?limit=N              → Tüm markalar veri çek
    POST /sync/{marka}/start?limit=N      → Tek marka Shopify sync başlat
    POST /sync/all/start?limit=N          → Tüm markalar Shopify sync başlat
    GET  /sync/status/{job_id}            → Job durumu sorgula
    GET  /sync/report/{job_id}            → WhatsApp raporu al
    GET  /sync/jobs                       → Tüm jobları listele
    GET  /logs?lines=50                   → Ana log dosyası
    GET  /stats?lines=100                 → İstatistik logları

N8N AKIŞ TASARIMI:
    Schedule (Her 3 günde bir)
        └─> HTTP POST /sync/{marka}/start?limit=500   (job başlat)
            └─> Set Node (job_id kaydet)
                └─> Wait 5sn
                    └─> HTTP GET /sync/status/{job_id} (durum kontrol)
                        └─> Code JS (WhatsApp mesajı hazırla)
                            └─> IF status == "completed"
                                ├─> TRUE: Evolution API (WhatsApp gönder)
                                └─> FALSE: Wait 30sn → tekrar kontrol

WHATSAPP ENTEGRASYONU:
    Evolution API kullanılır. N8N'deki "Enviar texto" node'unda:
    - instanceName : Evolution API'deki instance adı
    - remoteJid    : Alıcı telefon numarası (905XXXXXXXXX formatında)
    - messageText  : {{ $json.mesaj }}

FİYAT KURALI:
    Shopify fiyatı = İkiler fiyatı × PRICE_MULTIPLIER
    Örnek: 248.66 TL × 1.75 = 435.16 TL

STOK KURALI:
    İkiler stoku → Shopify stoku
    4 veya üzeri → 4 (maksimum 4 gösterilir)
    3             → 3
    2             → 2
    1             → 1
    0             → 0

YASAKLI ÜRÜNLER (otomatik filtrelenir):
    - SIVI CONTA
    - KOL YATAK STD
    - TEK STD
    - ACP*, CR*, AH* kodlu ürünler
    - KURUTUCU
    - SU FİLTRE

DOSYA YAPISI:
    /home/fast-api/ikiler/
    ├── .env
    ├── cookie.txt
    ├── ikiler_multi_marka_fast_api.py   ← bu dosya
    ├── logs/
    │   ├── sync_YYYYMMDD.log            ← ana log
    │   ├── stats_YYYYMMDD.log           ← istatistik log
    │   ├── updates_YYYYMMDD.csv         ← güncelleme kaydı
    │   └── errors_YYYYMMDD.csv          ← hata kaydı
    ├── reports/
    │   └── {marka}_data_YYYYMMDD.csv    ← çekilen veriler
    └── jobs/
        └── {job_id}.json                ← job durumu

VERSİYON GEÇMİŞİ:
    v1.0 - Sadece MAHLE, temel scraper
    v2.0 - FastAPI + async job sistemi
    v3.0 - successes/errors listeleri, WhatsApp raporu, gelişmiş loglar
    v4.0 - Çoklu marka desteği (MAHLE, MANN, PURFLUX, UFI, FILTORQ, FILTRON)
===============================================================================
"""

# ===========================================================================
# BÖLÜM 1: BAĞIMLILIKLAR VE .ENV YÜKLEME
# ===========================================================================

import os
from pathlib import Path

# .env dosyasını Python kütüphaneleri yüklenmeden ÖNCE yükle.
# Böylece tüm os.getenv() çağrıları doğru değerleri okur.
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        print(f"✅ .env yüklendi: {env_path}")
    else:
        print(f"⚠️  .env bulunamadı: {env_path}")
except ImportError:
    print("⚠️  python-dotenv yüklü değil, sistem env kullanılıyor.")
except Exception as e:
    print(f"⚠️  .env yükleme hatası: {e}")

import requests
import pandas as pd
import json
import time
import re
import csv
import threading
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict, field

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from colorama import Fore, Style, init

init(autoreset=True)


# ===========================================================================
# BÖLÜM 2: MARKA TANIMLARI
# ===========================================================================
# Her marka için İkiler API'ye gönderilecek tam isim ve
# Shopify'da "vendor" alanında görünecek isim tanımlanır.
# Yeni marka eklemek için buraya bir satır eklemek yeterlidir.
# ===========================================================================

MARKA_TANIM = {
    # anahtar  : (ikiler_api_adi,   shopify_vendor_adi)
    # ikiler_api_adi → İkiler B2B POST payload "manufacturer" değeri
    # shopify_vendor → Shopify'da vendor alanındaki EXACT değer
    "filtorq" : ("FILTORQ",       "FILTORQ"),
    "filtron" : ("FILTRON",       "FILTRON"),
    "hengst"  : ("HENGST",        "HENGST"),
    "knecht"  : ("KNECHT",        "KNECHT"),
    "mahle"   : ("MAHLE FILTRE",  "MAHLE"),
    "mann"    : ("MANN-FILTER",   "MANN"),
    "purflux" : ("PURFLUX",       "PURFLUX"),
    "ufi"     : ("UFI FILTRE",    "UFI FİLTRE"),
}

# N8N veya API çağrılarında kullanılacak geçerli marka anahtarları
GECERLI_MARKALAR = list(MARKA_TANIM.keys())

# MAHLE için UFI cross reference CSV dosyasının yolu
# Bu dosya olmadan MAHLE sync çalışmaz!
# Format: Brand, Part_Code sütunları içermeli, Brand="KNECHT-MAHLE" satırları kullanılır
UFI_CSV_PATH = os.getenv("UFI_CSV_PATH", "./ufi_cross_referans_STABLE.csv")

# Global UFI veritabanı (uygulama başladığında bir kez yüklenir)
_UFI_DB: Dict[str, Dict] = {}


# ===========================================================================
# BÖLÜM 3: LOG SİSTEMİ
# ===========================================================================
# Tüm işlemler merkezi LogSystem sınıfı üzerinden loglanır.
# Günlük olarak ayrı log dosyaları oluşturulur.
# ===========================================================================

class LogSystem:
    """
    Merkezi loglama sınıfı.

    Dosyalar:
        sync_YYYYMMDD.log    → Tüm işlemlerin ana logu
        stats_YYYYMMDD.log   → Job özet istatistikleri (insan tarafından okunabilir)
        updates_YYYYMMDD.csv → Başarılı Shopify güncellemeleri (tablo formatı)
        errors_YYYYMMDD.csv  → Hatalar (tablo formatı)
    """

    def __init__(self, log_dir: str = "./logs", report_dir: str = "./reports"):
        self.log_dir    = Path(log_dir)
        self.report_dir = Path(report_dir)
        self.log_dir.mkdir(exist_ok=True, parents=True)
        self.report_dir.mkdir(exist_ok=True, parents=True)

        today = datetime.now().strftime('%Y%m%d')
        self.main_log  = self.log_dir / f"sync_{today}.log"
        self.stats_log = self.log_dir / f"stats_{today}.log"
        self.sync_log  = self.log_dir / f"updates_{today}.csv"
        self.error_log = self.log_dir / f"errors_{today}.csv"

        self._init_csv_headers()

    def _init_csv_headers(self):
        """CSV dosyaları ilk kez oluşturuluyorsa başlık satırı ekle."""
        if not self.sync_log.exists():
            with open(self.sync_log, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow([
                    'Timestamp', 'Marka', 'Kod', 'SKU',
                    'Urun Tipi', 'Ikiler Fiyat', 'Shopify Fiyat',
                    'Ikiler Stok', 'Shopify Stok', 'Status', 'Mesaj'
                ])

        if not self.error_log.exists():
            with open(self.error_log, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['Timestamp', 'Marka', 'Kod', 'Hata Tipi', 'Hata Mesaji'])

    def log(self, message: str, level: str = "INFO"):
        """Ana log dosyasına yazar. ERROR ve WARN ayrıca konsola da yazdırılır."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg   = f"[{timestamp}] [{level:5s}] {message}"
        if level in ["ERROR", "WARN"]:
            print(log_msg)
        try:
            with open(self.main_log, "a", encoding="utf-8") as f:
                f.write(log_msg + "\n")
        except:
            pass

    def log_stats(self, message: str):
        """İstatistik logunu hem stats dosyasına hem ana loga yazar."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}"
        print(line)
        try:
            with open(self.stats_log, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            with open(self.main_log, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except:
            pass

    def log_update(self, marka: str, kod: str, sku: str, urun_tipi: str,
                   ikiler_fiyat: str, shopify_fiyat: str,
                   ikiler_stok: int, shopify_stok: int,
                   status: str, mesaj: str):
        """Shopify güncelleme kaydını CSV'ye ekler."""
        try:
            with open(self.sync_log, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow([
                    datetime.now().isoformat(), marka, kod, sku,
                    urun_tipi, ikiler_fiyat, shopify_fiyat,
                    ikiler_stok, shopify_stok, status, mesaj
                ])
        except:
            pass

    def log_error(self, marka: str, kod: str, hata_tipi: str, hata_mesaji: str):
        """Hata kaydını CSV'ye ekler."""
        try:
            with open(self.error_log, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow([
                    datetime.now().isoformat(), marka, kod, hata_tipi, hata_mesaji
                ])
        except:
            pass

    def write_job_summary(self, job_id: str, job_data: dict):
        """
        Job tamamlandığında hem konsola hem log dosyalarına
        okunabilir bir özet rapor yazar.

        Örnek çıktı:
        ────────────────────────────────────────────────────────────
          JOB RAPORU  |  2026-02-28 16:00:05  |  #aa94f225
        ────────────────────────────────────────────────────────────
          Marka      : MAHLE
          Durum      : COMPLETED
          Sure       : 0dk 10sn
          Toplam     : 10 urun
          Basarili   : 4 urun
          Basarisiz  : 6 urun
        ────────────────────────────────────────────────────────────
          GUNCELLENENLER (4 adet)
        ────────────────────────────────────────────────────────────
            1. OC47OF       Ikiler:   154,97 TL  Shopify:   271.20 TL  Stok: 10 -> 4
        ...
        """
        ts        = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        marka     = job_data.get('marka', '-')
        toplam    = job_data.get('total', 0)
        basarili  = job_data.get('updated', 0)
        basarisiz = job_data.get('failed', 0)
        durum     = job_data.get('status', '?').upper()

        sure_str = "-"
        try:
            baslangic = datetime.fromisoformat(job_data.get('started_at', ''))
            bitis     = datetime.fromisoformat(job_data.get('completed_at', '')) \
                        if job_data.get('completed_at') else datetime.now()
            sure_sn   = int((bitis - baslangic).total_seconds())
            sure_str  = f"{sure_sn // 60}dk {sure_sn % 60}sn"
        except:
            pass

        sep   = f"{'─' * 60}"
        lines = [
            "",
            sep,
            f"  JOB RAPORU  |  {ts}  |  #{job_id}",
            sep,
            f"  Marka      : {marka}",
            f"  Durum      : {durum}",
            f"  Sure       : {sure_str}",
            f"  Toplam     : {toplam} urun",
            f"  Basarili   : {basarili} urun",
            f"  Basarisiz  : {basarisiz} urun",
            sep,
        ]

        successes = job_data.get('successes', [])
        if successes:
            lines.append(f"  GUNCELLENENLER ({len(successes)} adet)")
            lines.append(sep)
            for i, s in enumerate(successes, 1):
                lines.append(
                    f"  {i:>3}. {s.get('sku',''):12s}  "
                    f"Ikiler: {s.get('ikiler_fiyat',''):>8s} TL  "
                    f"Shopify: {s.get('shopify_fiyat',''):>8s} TL  "
                    f"Stok: {s.get('ikiler_stok',0)} -> {s.get('shopify_stok',0)}"
                )
            lines.append(sep)

        errors = job_data.get('errors', [])
        if errors:
            lines.append(f"  BASARISIZLAR ({len(errors)} adet)")
            lines.append(sep)
            for i, e in enumerate(errors, 1):
                lines.append(
                    f"  {i:>3}. {e.get('sku', e.get('kod','?')):12s}  {e.get('error','')}"
                )
            lines.append(sep)

        lines.append("")
        summary_text = "\n".join(lines)
        print(summary_text)
        try:
            with open(self.main_log,  "a", encoding="utf-8") as f:
                f.write(summary_text + "\n")
            with open(self.stats_log, "a", encoding="utf-8") as f:
                f.write(summary_text + "\n")
        except:
            pass


# Global log nesnesi - tüm modül boyunca bu kullanılır
LOG = LogSystem(
    log_dir    = os.getenv("LOG_DIR",    "./logs"),
    report_dir = os.getenv("REPORT_DIR", "./reports")
)


# ===========================================================================
# BÖLÜM 4: SHOPIFY AYARLARI VE FİYAT/STOK KURALLARI
# ===========================================================================

SHOPIFY_STORE       = os.getenv("SHOPIFY_STORE",       "z42kyc-dt.myshopify.com")
SHOPIFY_TOKEN       = os.getenv("SHOPIFY_TOKEN",       "")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")
SHOPIFY_RATE_LIMIT  = 2   # saniyede maksimum istek sayısı (Shopify limiti)

PRICE_MULTIPLIER  = float(os.getenv("PRICE_MULTIPLIER", "1.63"))  # %75 kar marjı
MAX_STOCK_DISPLAY = 4     # Shopify'da gösterilecek maksimum stok


def calculate_shopify_price(ikiler_price: str) -> str:
    """
    İkiler fiyatını Shopify satış fiyatına dönüştürür.

    Kural: Shopify fiyatı = İkiler fiyatı × PRICE_MULTIPLIER

    Türkçe format desteği:
        "248,66"    → 248.66  (normal)
        "1.086,79"  → 1086.79 (binler ayracı nokta, ondalık virgül)
        "1,086.79"  → 1086.79 (İngilizce format)

    Returns:
        "435.16" formatında string fiyat (Shopify API formatı)
        Hata durumunda "0.00" döner
    """
    try:
        p = (ikiler_price or '').strip()
        # Türkçe format: 1.086,79 → nokta binler ayracı, virgül ondalık
        if ',' in p and '.' in p:
            # 1.086,79 formatı → virgülden önce nokta var = Türkçe
            if p.index('.') < p.index(','):
                p = p.replace('.', '').replace(',', '.')
            else:
                # 1,086.79 formatı → İngilizce, sadece virgülü sil
                p = p.replace(',', '')
        else:
            # Sadece virgül var: 248,66 → Türkçe ondalık
            p = p.replace(',', '.')
        price_float   = float(p)
        shopify_price = price_float * PRICE_MULTIPLIER
        return f"{shopify_price:.2f}"
    except:
        return "0.00"


def normalize_stock(stock: int) -> int:
    """
    İkiler stok miktarını Shopify'da gösterilecek değere dönüştürür.

    Kural: 4 veya üzeri stok → 4 olarak göster (stok fazlalığını gizle)
           4 altı stok       → olduğu gibi göster

    Args:
        stock: İkiler'den gelen gerçek stok miktarı

    Returns:
        Shopify'da gösterilecek normalleştirilmiş stok
    """
    if stock >= MAX_STOCK_DISPLAY:
        return MAX_STOCK_DISPLAY
    return stock


# ===========================================================================
# BÖLÜM 5: JOB SİSTEMİ
# ===========================================================================
# Her sync işlemi bir "Job" olarak takip edilir.
# Job durumu JSON dosyasına kaydedilir, N8N bu dosyayı okuyarak
# işlemin tamamlanıp tamamlanmadığını kontrol eder.
# ===========================================================================

JOBS_DIR = Path("./jobs")
JOBS_DIR.mkdir(exist_ok=True)


@dataclass
class SyncJob:
    """
    Shopify sync işleminin durumunu takip eden veri sınıfı.

    Alanlar:
        job_id       : 8 karakterlik benzersiz kimlik (örn: "aa94f225")
        status       : pending / running / completed / failed
        marka        : İşlenen marka adı (örn: "MAHLE")
        total        : Toplam ürün sayısı
        processed    : İşlenen ürün sayısı
        updated      : Başarıyla güncellenen ürün sayısı
        failed       : Başarısız güncelleme sayısı
        started_at   : Başlangıç zamanı (ISO format)
        completed_at : Bitiş zamanı (ISO format, None ise devam ediyor)
        errors       : Hatalı ürünlerin listesi [{sku, kod, error}, ...]
        successes    : Başarılı ürünlerin listesi [{sku, ikiler_fiyat, ...}, ...]
    """
    job_id      : str
    status      : str
    marka       : str
    total       : int
    processed   : int
    updated     : int
    failed      : int
    started_at  : str
    completed_at: Optional[str]       = None
    errors           : List[Dict]     = field(default_factory=list)
    successes        : List[Dict]     = field(default_factory=list)
    csv_ikiler_count : int            = 0   # İkiler VAR, Shopify YOK sayısı
    csv_stok0_count  : int            = 0   # Shopify VAR, İkiler YOK → stok 0 sayısı
    csv_ikiler_path  : str            = ""  # {marka}_ikiler_{tarih}.csv yolu
    csv_stok0_path   : str            = ""  # {marka}_stok0_{tarih}.csv yolu

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self):
        """Job durumunu JSON dosyasına kaydet. N8N bu dosyayı okur."""
        filepath = JOBS_DIR / f"{self.job_id}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, job_id: str) -> Optional['SyncJob']:
        """
        JSON dosyasından job durumunu yükle.

        Returns:
            SyncJob nesnesi veya dosya yoksa None
        """
        filepath = JOBS_DIR / f"{job_id}.json"
        if not filepath.exists():
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Eski format uyumluluğu için eksik alanları varsayılan değerle doldur
        data.setdefault("errors",            [])
        data.setdefault("successes",         [])
        data.setdefault("marka",             "BILINMIYOR")
        data.setdefault("started_at",        datetime.now().isoformat())
        data.setdefault("csv_ikiler_count",  0)
        data.setdefault("csv_stok0_count",   0)
        data.setdefault("csv_ikiler_path",   "")
        data.setdefault("csv_stok0_path",    "")
        return cls(**data)


# ===========================================================================
# BÖLÜM 6: SHOPIFY API İSTEMCİSİ
# ===========================================================================

class ShopifyAPI:
    """
    Shopify Admin REST API ile iletişim kurar.

    Temel işlevler:
        1. Tüm MAHLE/MANN/vb. ürünleri çek (pagination ile)
        2. SKU index'i oluştur (hızlı arama için)
        3. Variant fiyatını güncelle
        4. Inventory (stok) miktarını güncelle

    SKU Index Mantığı:
        Shopify'daki her ürünün SKU'su normalize edilir
        (boşluk, nokta, slash kaldırılır, büyük harfe çevrilir)
        ve bir sözlükte saklanır. Bu sayede her ürün için
        ayrı API çağrısı yapmak yerine O(1) hızında arama yapılır.

        Örnek: "OX 153D3 ECO" → "OX153D3ECO" → {variant_id, product_id, ...}
    """

    def __init__(self):
        if not SHOPIFY_TOKEN:
            raise ValueError("SHOPIFY_TOKEN .env dosyasında tanımlanmamış!")
        self.base_url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}"
        self.session  = requests.Session()
        self.session.headers.update({
            "X-Shopify-Access-Token": SHOPIFY_TOKEN,
            "Content-Type":           "application/json"
        })
        self.sku_index: Dict[str, Dict] = {}

    def load_all_products(self, vendor: str) -> List[Dict]:
        """
        Shopify'daki belirtilen vendor'a ait tüm ürünleri çeker.

        Shopify API'si sayfa başına maksimum 250 ürün döner.
        Bu nedenle since_id parametresi ile tüm ürünler çekilene
        kadar pagination yapılır.

        Args:
            vendor: Shopify'daki marka adı (örn: "MAHLE", "MANN-FILTER")

        Returns:
            Tüm ürünlerin listesi
        """
        all_products = []
        since_id     = 0
        LOG.log(f"Shopify {vendor} ürünleri yükleniyor...", "INFO")

        while True:
            url    = f"{self.base_url}/products.json"
            params = {
                "limit":    250,
                "since_id": since_id,
                "fields":   "id,title,vendor,variants",
                "vendor":   vendor
            }
            try:
                r = self.session.get(url, params=params, timeout=30)
                r.raise_for_status()
                products = r.json().get("products", [])
                if not products:
                    break
                all_products.extend(products)
                since_id = products[-1]["id"]
                LOG.log(f"  +{len(products)} urun | Toplam: {len(all_products)}", "INFO")
                print(f"     ✓ {len(all_products)} {vendor} ürünü...", end='\r')
                time.sleep(0.3)
            except Exception as e:
                LOG.log(f"Urun yukleme hatasi ({vendor}): {e}", "ERROR")
                break

        LOG.log(f"✅ {vendor}: {len(all_products)} urun yuklendi", "INFO")
        print(f"\n✅ Shopify {vendor}: {len(all_products)} ürün")
        return all_products

    def build_sku_index(self, products: List[Dict], vendor: str) -> Dict[str, Dict]:
        """
        Ürün listesinden hızlı arama için SKU index'i oluşturur.

        Normalizasyon kuralı:
            "OX 153D3 ECO" → "OX153D3ECO"
            "KL 100/2"     → "KL1002"
            "W.712/75"     → "W71275"

        Args:
            products: Shopify'dan çekilen ürün listesi
            vendor:   Sadece bu vendor'ın ürünleri index'e alınır

        Returns:
            {sku_normalized: {variant_id, product_id, inventory_item_id, ...}}
        """
        idx = {}
        for p in products:
            pid    = p.get("id")
            title  = p.get("title", "")
            pvend  = p.get("vendor", "")
            if pvend.upper() != vendor.upper():
                continue
            for v in p.get("variants", []):
                raw_sku  = v.get("sku") or ""
                sku_norm = raw_sku.replace(' ', '').replace('.', '') \
                                  .replace('/', '').upper()
                if sku_norm:
                    idx[sku_norm] = {
                        "product_id":        int(pid),
                        "variant_id":        int(v.get("id")),
                        "inventory_item_id": int(v["inventory_item_id"])
                                             if v.get("inventory_item_id") else None,
                        "title":             title,
                        "vendor":            pvend,
                        "raw_sku":           raw_sku,
                        "urun_tipi":         v.get("title", ""),
                        "current_price":     v.get("price"),
                        "current_inventory": v.get("inventory_quantity", 0)
                    }
        LOG.log(f"✅ {vendor} SKU index: {len(idx)} SKU", "INFO")
        return idx

    def init_sku_index(self, vendor: str) -> int:
        """
        SKU index'ini yükler (ilk çağrıda Shopify'dan çeker, sonraki çağrılarda cache'den döner).

        Returns:
            Index'teki toplam SKU sayısı
        """
        if not self.sku_index:
            products       = self.load_all_products(vendor)
            self.sku_index = self.build_sku_index(products, vendor)
        return len(self.sku_index)

    def find_by_sku(self, sku: str) -> Optional[Dict]:
        """
        Normalize edilmiş SKU ile index'te arama yapar.

        Args:
            sku: Herhangi formatta SKU (normalizasyon otomatik yapılır)

        Returns:
            Variant bilgileri dict'i veya bulunamazsa None
        """
        sku_norm = (sku or '').replace(' ', '').replace('.', '').replace('/', '').upper()
        return self.sku_index.get(sku_norm)

    def update_price(self, variant_id: int, price: str) -> bool:
        """
        Shopify variant fiyatını günceller.

        Args:
            variant_id: Shopify variant ID
            price:      "271.20" formatında yeni fiyat

        Returns:
            True: Başarılı, False: Hata
        """
        try:
            url     = f"{self.base_url}/variants/{variant_id}.json"
            payload = {"variant": {"id": variant_id, "price": price}}
            r = self.session.put(url, json=payload, timeout=30)
            r.raise_for_status()
            time.sleep(1 / SHOPIFY_RATE_LIMIT)
            return True
        except Exception as e:
            LOG.log(f"Fiyat guncelleme hatasi (variant {variant_id}): {e}", "ERROR")
            return False

    def update_stock(self, inventory_item_id: int, quantity: int, location_id: int) -> bool:
        """
        Shopify inventory (stok) miktarını günceller.

        Args:
            inventory_item_id: Shopify inventory item ID
            quantity:          Yeni stok miktarı
            location_id:       Shopify depo/lokasyon ID

        Returns:
            True: Başarılı, False: Hata
        """
        try:
            url     = f"{self.base_url}/inventory_levels/set.json"
            payload = {
                "location_id":       location_id,
                "inventory_item_id": inventory_item_id,
                "available":         quantity
            }
            r = self.session.post(url, json=payload, timeout=30)
            r.raise_for_status()
            time.sleep(1 / SHOPIFY_RATE_LIMIT)
            return True
        except Exception as e:
            LOG.log(f"Stok guncelleme hatasi ({inventory_item_id}): {e}", "ERROR")
            return False

    def get_first_location_id(self) -> Optional[int]:
        """
        Shopify mağazasındaki ilk lokasyonun ID'sini döner.
        Stok güncellemesi için location_id zorunludur.

        Returns:
            Lokasyon ID veya bulunamazsa None
        """
        try:
            r = self.session.get(f"{self.base_url}/locations.json", timeout=30)
            r.raise_for_status()
            locs = r.json().get('locations', [])
            return locs[0]['id'] if locs else None
        except:
            return None


# ===========================================================================
# BÖLÜM 7: SYNC WORKER (ARKA PLAN İŞLEMCİSİ)
# ===========================================================================
# Bu fonksiyon ayrı bir thread'de çalışır.
# N8N isteği beklerken bu thread arka planda Shopify güncellemelerini yapar.
# Job durumu JSON dosyasına yazılır, N8N bu dosyayı polling ile okur.
# ===========================================================================

def _save_ikiler_csv(marka_key: str, rows: List[Dict]) -> str:
    """
    İkiler'de VAR Shopify'da YOK ürünleri CSV'ye kaydeder.
    Kolonlar: Marka | Kod | SKU | Urun | Fiyat_Ikiler | Fiyat_Shopify | Stok | Depo | Mann_URL | img_url_1 | img_url_2 | img_url_3
    Döner: kayıt yolu (string)
    """
    if not rows:
        return ""
    today    = datetime.now().strftime('%Y%m%d')
    filename = LOG.report_dir / f"{marka_key}_ikiler_{today}.csv"
    headers  = ['Marka','Kod','Fiyat','DEPO MERKEZİ','Toplam Stok','Mann_URL','img_url_1','img_url_2','img_url_3','img_url_4','img_url_5']
    try:
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=';')
            writer.writeheader()
            for r in rows:
                writer.writerow({h: r.get(h, '') for h in headers})
        LOG.log(f"📋 {marka_key}_ikiler CSV: {len(rows)} satir -> {filename}", "INFO")
    except Exception as e:
        LOG.log(f"CSV yazma hatasi ({filename}): {e}", "ERROR")
    return str(filename)


def _save_stok0_csv(marka_key: str, rows: List[Dict]) -> str:
    """
    Shopify'da VAR İkiler'de YOK ürünleri (stok 0 yapılanlar) CSV'ye kaydeder.
    Kolonlar: Marka | SKU | Shopify_Title | Shopify_Product_ID | Onceki_Stok | Tarih
    Döner: kayıt yolu (string)
    """
    if not rows:
        return ""
    today    = datetime.now().strftime('%Y%m%d')
    filename = LOG.report_dir / f"{marka_key}_stok0_{today}.csv"
    headers  = ['Marka','Kod','SKU','Variant_ID','Product_ID','Inventory_Item_ID','Shopify_Title','Onceki_Stok','Tarih','Islem']
    try:
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=';')
            writer.writeheader()
            for r in rows:
                writer.writerow({h: r.get(h, '') for h in headers})
        LOG.log(f"⚠️  {marka_key}_stok0 CSV: {len(rows)} satir -> {filename}", "INFO")
    except Exception as e:
        LOG.log(f"CSV yazma hatasi ({filename}): {e}", "ERROR")
    return str(filename)


def sync_worker(job_id: str, marka_key: str, products: List[Dict], limit: Optional[int] = None):
    """
    Shopify sync işlemini arka planda yürüten ana worker fonksiyonu.

    Akış:
        1. Job durumunu "running" yap
        2. ShopifyAPI başlat, SKU index'i yükle
        3. Her ürün için:
           a. Fiyatı hesapla (×PRICE_MULTIPLIER)
           b. Stoku normalize et (max 4)
           c. SKU ile Shopify'da ara
           d. Shopify'da YOK → ikiler_csv listesine ekle
           e. Shopify'da VAR → Fiyat + stok güncelle
        4. Shopify'da VAR İkiler'de YOK → stok 0 yap → stok0_csv listesine ekle
        5. CSV'leri kaydet
        6. Job durumunu "completed" yap
        7. Özet logu yaz

    Args:
        job_id    : SyncJob ID (jobs/{job_id}.json dosyasını günceller)
        marka_key : Marka anahtarı (örn: "mahle", "mann")
        products  : İkiler'den çekilen ürün listesi
    """
    job = SyncJob.load(job_id)
    if not job:
        return

    # Shopify vendor adını al (örn: "MAHLE", "MANN")
    shopify_vendor = MARKA_TANIM.get(marka_key, (marka_key.upper(), marka_key.upper()))[1]

    job.status = "running"
    job.save()

    # CSV listeleri
    ikiler_csv_rows: List[Dict] = []   # İkiler VAR → Shopify YOK
    stok0_csv_rows:  List[Dict] = []   # Shopify VAR → İkiler YOK → stok 0

    # İkiler SKU seti (stok0 tespiti için)
    ikiler_sku_set: set = set()

    try:
        shopify     = ShopifyAPI()
        sku_count   = shopify.init_sku_index(shopify_vendor)
        location_id = shopify.get_first_location_id()

        LOG.log(f"Job {job_id} [{shopify_vendor}]: {sku_count} SKU, location_id={location_id}", "INFO")

        for product in products:
            sku          = product.get('SKU', '')
            fiyat_ikiler = product.get('Fiyat', '')
            stok_ikiler  = product.get('Toplam Stok', 0)
            urun_tipi    = product.get('Urun', '')
            marka_adi    = product.get('Marka', shopify_vendor)
            kod          = product.get('Kod', sku)
            depo         = product.get('Depo', '')

            # İkiler SKU setine ekle (stok0 tespiti için)
            if sku:
                sku_norm = (sku or '').replace(' ','').replace('.','').replace('/','').upper()
                ikiler_sku_set.add(sku_norm)

            # Fiyat ve stok hesapla
            fiyat_shopify = calculate_shopify_price(fiyat_ikiler)
            try:
                stok_shopify    = normalize_stock(int(stok_ikiler))
                ikiler_stok_int = int(stok_ikiler)
            except:
                stok_shopify    = 0
                ikiler_stok_int = 0

            # Fiyat bilgisi yoksa atla
            if not fiyat_ikiler or fiyat_shopify == "0.00":
                job.failed += 1
                job.errors.append({"sku": sku, "kod": kod, "error": "Fiyat bilgisi yok"})
                job.processed += 1
                job.save()
                LOG.log(f"⚠ {sku}: Fiyat yok, atlaniyor", "WARN")
                LOG.log_error(shopify_vendor, sku, "FIYAT_YOK", "Fiyat bilgisi yok")
                continue

            try:
                # SKU ile Shopify'da ara
                shopify_item = shopify.find_by_sku(sku)

                if not shopify_item:
                    # ── İKİLER VAR, SHOPIFY YOK → CSV listesine ekle ──
                    # Kolonlar: Marka | Kod | Fiyat | DEPO MERKEZİ | Toplam Stok | Mann_URL | img_url_1-5
                    # Mann_URL ve img_url sütunları şimdilik boş — img scraper eklenince dolacak
                    ikiler_csv_rows.append({
                        'Marka':        marka_adi,
                        'Kod':          kod,
                        'Fiyat':        fiyat_ikiler,
                        'DEPO MERKEZİ': depo,
                        'Toplam Stok':  ikiler_stok_int,
                        'Mann_URL':     '',
                        'img_url_1':    '',
                        'img_url_2':    '',
                        'img_url_3':    '',
                        'img_url_4':    '',
                        'img_url_5':    '',
                    })
                    job.failed += 1
                    job.errors.append({"sku": sku, "kod": kod, "error": "SKU Shopify'da bulunamadi"})
                    job.processed += 1
                    job.save()
                    LOG.log(f"📋 {sku}: Shopify'da yok → ikiler_csv eklendi", "WARN")
                    LOG.log_error(shopify_vendor, sku, "SKU_BULUNAMADI", "Shopify'da esleme yok")
                    continue

                # Fiyat güncelle
                price_ok = shopify.update_price(shopify_item['variant_id'], fiyat_shopify)

                # Stok güncelle
                stock_ok = True
                if location_id and shopify_item.get('inventory_item_id'):
                    stock_ok = shopify.update_stock(
                        shopify_item['inventory_item_id'],
                        stok_shopify,
                        location_id
                    )

                if price_ok and stock_ok:
                    job.updated += 1
                    job.successes.append({
                        "sku":               sku,
                        "kod":               kod,
                        "marka":             marka_adi,
                        "urun":              urun_tipi,
                        "ikiler_fiyat":      fiyat_ikiler,
                        "shopify_fiyat":     fiyat_shopify,
                        "ikiler_stok":       ikiler_stok_int,
                        "shopify_stok":      stok_shopify,
                        "product_id":        shopify_item["product_id"],
                        "variant_id":        shopify_item["variant_id"],
                        "inventory_item_id": shopify_item.get("inventory_item_id"),
                        "shopify_title":     shopify_item.get("title"),
                    })
                    LOG.log(
                        f"✅ {sku}: {fiyat_ikiler} TL -> {fiyat_shopify} TL | "
                        f"Stok: {stok_ikiler} -> {stok_shopify}",
                        "INFO"
                    )
                    LOG.log_update(
                        marka_adi, kod, sku, urun_tipi,
                        fiyat_ikiler, fiyat_shopify,
                        ikiler_stok_int, stok_shopify,
                        "GUNCELLENDI", "Basarili"
                    )
                else:
                    job.failed += 1
                    job.errors.append({"sku": sku, "kod": kod, "error": "Shopify guncelleme basarisiz"})
                    LOG.log_error(shopify_vendor, sku, "GUNCELLEME_HATASI",
                                  "Fiyat veya stok guncellenemedi")

                job.processed += 1
                job.save()

            except Exception as e:
                job.failed += 1
                job.errors.append({"sku": sku, "kod": kod, "error": str(e)})
                job.processed += 1
                job.save()
                LOG.log(f"✗ {sku}: Exception - {e}", "ERROR")
                LOG.log_error(shopify_vendor, sku, "EXCEPTION", str(e))

        # ── SHOPIFY VAR, İKİLER YOK → STOK 0 YAP ──────────────────────────
        # GÜVENLİK KURALI: limit verilmişse (kısmi sync) stok 0 işlemi YAPILMAZ.
        # Sadece limit=None (tüm ürünler çekildiğinde) aktif olur.
        # Kısmi sync'te sadece CSV raporlanır, Shopify'a dokunulmaz.
        # ── SHOPIFY VAR, İKİLER YOK → SADECE TAM SYNC'TE RAPOR ──────────────
        # limit verilmişse (kısmi/test sync) bu faz TAMAMEN ATLANIR.
        # Sadece limit=None (tüm ürünler) durumunda stok0 CSV raporu üretilir.
        # Shopify'a hiçbir zaman dokunulmaz — sen onayladıktan sonra manuel yapılır.
        if limit is not None:
            LOG.log(f"📋 Stok0 taramasi atlandi: limit={limit} (tam sync degil)", "INFO")
        else:
            tarih = datetime.now().strftime('%Y-%m-%d %H:%M')
            for shopify_sku_norm, shopify_info in shopify.sku_index.items():
                if shopify_sku_norm not in ikiler_sku_set:
                    onceki_stok = shopify_info.get('current_inventory', 0)
                    if onceki_stok == 0:
                        continue
                    stok0_csv_rows.append({
                        'Marka':              shopify_vendor,
                        'Kod':                shopify_info.get('raw_sku', shopify_sku_norm),
                        'SKU':                shopify_sku_norm,
                        'Variant_ID':         shopify_info.get('variant_id', ''),
                        'Product_ID':         shopify_info.get('product_id', ''),
                        'Inventory_Item_ID':  shopify_info.get('inventory_item_id', ''),
                        'Shopify_Title':      shopify_info.get('title', ''),
                        'Onceki_Stok':        onceki_stok,
                        'Tarih':              tarih,
                        'Islem':              'RAPOR_ONLY',
                    })
                    LOG.log(f"📋 {shopify_sku_norm}: Ikiler'de yok → stok0 CSV'ye eklendi (Shopify'a dokunulmadi)", "INFO")

        # ── CSV KAYDET ──────────────────────────────────────────────────────
        ikiler_csv_path = _save_ikiler_csv(marka_key, ikiler_csv_rows)
        stok0_csv_path  = _save_stok0_csv(marka_key, stok0_csv_rows)

        # Job'a CSV istatistiklerini ekle
        job.csv_ikiler_count = len(ikiler_csv_rows)
        job.csv_stok0_count  = len(stok0_csv_rows)
        job.csv_ikiler_path  = ikiler_csv_path
        job.csv_stok0_path   = stok0_csv_path

        job.status = "completed"

    except Exception as e:
        job.status = "failed"
        job.errors.append({"error": f"Worker crashed: {e}"})
        LOG.log(f"✗ Job {job_id} CRASHED: {e}", "ERROR")

    job.completed_at = datetime.now().isoformat()
    job.save()

    # Özet raporu log'a yaz
    LOG.write_job_summary(job_id, job.to_dict())
    LOG.log_stats(
        f"JOB TAMAMLANDI | #{job_id} | {shopify_vendor} | "
        f"Toplam: {job.total} | Basarili: {job.updated} | Basarisiz: {job.failed} | "
        f"Yeni(CSV): {len(ikiler_csv_rows)} | Stok0: {len(stok0_csv_rows)}"
    )


# ===========================================================================
# BÖLÜM 8: YARDIMCI FONKSİYONLAR
# ===========================================================================

def print_red(t):     print(f"{Fore.RED}{t}{Style.RESET_ALL}")
def print_green(t):   print(f"{Fore.GREEN}{t}{Style.RESET_ALL}")
def print_yellow(t):  print(f"{Fore.YELLOW}{t}{Style.RESET_ALL}")
def print_cyan(t):    print(f"{Fore.CYAN}{t}{Style.RESET_ALL}")
def print_magenta(t): print(f"{Fore.MAGENTA}{t}{Style.RESET_ALL}")


def clean_price(text: Optional[str]) -> str:
    """
    HTML içerebilen fiyat metnini temizler ve sadece sayıyı döner.

    Örnekler:
        "<span>248,66</span> TL" → "248,66"
        "248.66&nbsp;TL"          → "248.66"
        None                      → ""
    """
    if not text or not isinstance(text, str):
        return ""
    text  = re.sub(r'<[^>]+>', '', text).replace('&nbsp;', ' ').strip()
    match = re.search(r'[\d]+[.,\d]*', text)
    return match.group(0) if match else ""


def clean_code(code_str: Optional[str], marka_key: str = "mahle") -> str:
    """
    MAHLE: ikiler_mahle_marka_cekme.py'deki orijinal clean_code
    Diğer markalar: sonraki adımlarda ayrı ayrı eklenecek
    """
    if not code_str:
        return ""

    if marka_key == "mahle":
        # MAHLE orijinal — ikiler_mahle_marka_cekme.py'den
        cleaned = re.sub(r'^(YD\.|YP\.|Yl\.|YD\s|YP\s|Yl\s)?MAHLE[\.\ s]*', '', code_str, flags=re.IGNORECASE)
        return cleaned.strip()

    if marka_key == "purflux":
        # PURFLUX orijinal — ikiler_purflux_marka.py'den
        cleaned = re.sub(r'^(YD\.|YD\s)?PURFLUX[\.\s]*', '', code_str, flags=re.IGNORECASE)
        return cleaned.strip()

    if marka_key == "filtron":
        # FILTRON orijinal — ikiler_filtron_marka.py'den
        brand_escaped = re.escape('FILTRON')
        pattern = rf'^(YD\.|YD\s)?{brand_escaped}[\.\ s]*'
        cleaned = re.sub(pattern, '', code_str, flags=re.IGNORECASE)
        return cleaned.strip()

    if marka_key == "ufi":
        # UFI orijinal — ikiler_ufi_filter_marka_cekme.py'den
        # Adımlar: prefix temizle → noktasız kodu noktalıya çevir
        k = code_str.strip()
        k = re.sub(r'^UFI\.', '', k)
        k = re.sub(r'^[A-Za-z]{1,3}\.UFI\s*', '', k)
        k = re.sub(r'^YD\.', '', k)
        k = re.sub(r'^Yl\.', '', k)
        k = k.strip()
        # noktali_yap: 2503900 -> 25.039.00
        if '.' not in k:
            kn = k.replace(' ', '').upper()
            if len(kn) == 7 and re.match(r'^[\dA-Z]{7}$', kn):
                k = f'{kn[0:2]}.{kn[2:5]}.{kn[5:7]}'
            elif len(kn) == 8 and re.match(r'^[\dA-Z]{8}$', kn):
                k = f'{kn[0:2]}.{kn[2:5]}.{kn[5:8]}'
        return k.strip()

    if marka_key == "mann":
        # MANN orijinal — ikiler_mann_filter_marka_cekme.py'den
        # strip_m_prefix: "M. W719/30" -> "W719/30"
        # normalize_code_display: "H U 12345" -> "HU 12345", "W K 68" -> "WK 68"
        MANN_PREFIXES = ["CUK", "WDK", "WK", "CU", "HU", "PU", "TB", "W", "H", "C"]

        # M. / M: / M- prefix temizle
        k = re.sub(r'^\s*M\s*[\.\:\-]\s*', '', code_str.strip(), flags=re.IGNORECASE).strip()
        # Çoklu boşlukları tek yap
        k = re.sub(r'\s+', ' ', k).strip()

        # "H U 12345" -> "HU 12345", "W K 68" -> "WK 68", "C U K 5" -> "CUK 5"
        toks = k.split()
        if len(toks) >= 3 and toks[0].upper() == 'C' and toks[1].upper() == 'U' and toks[2].upper() == 'K':
            k = 'CUK ' + ' '.join(toks[3:]).strip()
        elif len(toks) >= 2 and toks[0].upper() == 'H' and toks[1].upper() == 'U':
            k = 'HU ' + ' '.join(toks[2:]).strip()
        elif len(toks) >= 2 and toks[0].upper() == 'W' and toks[1].upper() == 'K':
            k = 'WK ' + ' '.join(toks[2:]).strip()
        elif len(toks) >= 2 and toks[0].upper() == 'C' and toks[1].upper() == 'U':
            k = 'CU ' + ' '.join(toks[2:]).strip()
        else:
            # Prefix varsa normalize et: "W719/30" -> "W 719/30"
            up = k.upper()
            for p in MANN_PREFIXES:
                if up.startswith(p + ' ') or up == p or up.startswith(p):
                    rest = k[len(p):].strip()
                    rest = re.sub(r'\s+', ' ', rest).strip()
                    k = f'{p} {rest}'.strip() if rest else p
                    break
        return k.strip()

    # Diğer markalar buraya eklenecek
    return code_str.strip()


def get_warehouse_name(raw_name: str) -> str:
    """Depo ismini kısaltır."""
    if not raw_name:
        return "Bilinmiyor"
    mapping = {
        'Fabrika - Büro': 'FABRIKA',
        'Logistik':       'LOGISTIK',
        'İstanbul':       'ISTANBUL',
        'Ankara':         'ANKARA',
        'İzmir':          'IZMIR'
    }
    return mapping.get(raw_name, raw_name)


def is_banned(product_name: Optional[str], product_code: Optional[str]) -> tuple:
    """
    Ürünün yasaklı listede olup olmadığını kontrol eder.

    Yasaklı ürünler sistematik olarak atlanır.
    Yasaklama kriterleri:
        - Belirli kelimeler içeren ürün adları
        - Belirli prefix'lerle başlayan ürün kodları

    Returns:
        (True, sebep) veya (False, None)
    """
    if not product_name: product_name = ""
    if not product_code: product_code = ""

    text = (product_name + " " + product_code).upper()

    banned_phrases = ["SIVI CONTA", "KOL YATAK STD", "TEK STD"]
    for phrase in banned_phrases:
        if phrase in text:
            return True, phrase

    banned_prefixes = ['ACP', 'CR', 'AH']
    for prefix in banned_prefixes:
        if product_code.upper().startswith(prefix):
            return True, prefix

    return False, None


# ===========================================================================
# MAHLE'YE ÖZEL: UFI CROSS REFERENCE SİSTEMİ
# ===========================================================================
# MAHLE mantığı diğer markalardan tamamen farklıdır:
#   1. ufi_cross_referans_STABLE.csv dosyasından KNECHT-MAHLE kodları yüklenir
#   2. İkiler'den çekilen her MAHLE kodu bu listede aranır
#   3. UFI listesinde YOKSA → ürün ATLANIR (Shopify'a yazılmaz)
#   4. UFI listesinde VARSA → ürün tipi UFI'dan alınır
#   5. Kod formatlanır: KL913 → KL 913
#
# Bu sistem sadece gerçekten satılabilir MAHLE ürünlerini seçer.
# ===========================================================================

def load_ufi_db(csv_path: str) -> Dict[str, Dict]:
    """
    UFI cross reference CSV'den KNECHT-MAHLE kodlarını yükler.

    CSV formatı:
        Brand,Part_Code,...
        KNECHT-MAHLE,KL 100/2,...
        KNECHT-MAHLE,OC 47OF,...

    Her kod iki formatta index'e alınır:
        - Temiz: "KL1002"  (boşluk/nokta/slash kaldırılmış)
        - Orijinal: "KL 100/2"

    Returns:
        {kod: {'tip': 'Yakıt Filtresi', 'original': 'KL 100/2'}}
        Hata veya dosya yoksa boş dict döner.
    """
    global _UFI_DB
    if _UFI_DB:
        return _UFI_DB  # Zaten yüklenmiş, tekrar yükleme

    LOG.log(f"UFI DB yükleniyor: {csv_path}", "INFO")
    try:
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        mahle_df = df[df['Brand'].str.contains('KNECHT-MAHLE', case=False, na=False)]
        LOG.log(f"KNECHT-MAHLE kayıt sayısı: {len(mahle_df)}", "INFO")

        db = {}
        # KOD → FİLTRE TİPİ eşlemesi (MAHLE kod prefix kuralı)
        PREFIX_TIP = {
            'KL':  'Yakıt Filtresi',
            'KX':  'Yakıt Filtresi',
            'OC':  'Yağ Filtresi',
            'OX':  'Yağ Filtresi',
            'LX':  'Hava Filtresi',
            'LAK': 'Kabin Hava Filtresi',
            'LAO': 'Kabin Hava Filtresi',
            'LA':  'Kabin Hava Filtresi',
            'HX':  'Hidrolik Şanzıman Filtresi',
        }

        for _, row in mahle_df.iterrows():
            original = str(row['Part_Code']).strip()
            upper    = original.upper()
            clean    = upper.replace(' ', '').replace('.', '').replace('/', '')

            filtre_tipi = None
            # Uzundan kısaya sıralı kontrol (LAK, LAO → LA'dan önce)
            for prefix in ['LAK', 'LAO', 'LA', 'KL', 'KX', 'OC', 'OX', 'LX', 'HX']:
                if upper.startswith(prefix):
                    filtre_tipi = PREFIX_TIP[prefix]
                    break

            if filtre_tipi:
                entry = {'tip': filtre_tipi, 'original': original}
                db[clean] = entry   # "KL1002"
                db[upper] = entry   # "KL 100/2"

        LOG.log(f"UFI DB yüklendi: {len(db)} kod", "INFO")
        _UFI_DB = db
        return db

    except FileNotFoundError:
        LOG.log(f"UFI CSV bulunamadı: {csv_path}", "WARN")
        return {}
    except Exception as e:
        LOG.log(f"UFI DB yükleme hatası: {e}", "ERROR")
        return {}


def check_ufi_approved(product_code: str, ufi_db: Dict) -> Optional[Dict]:
    """
    MAHLE kodunun UFI onaylı listesinde olup olmadığını kontrol eder.

    Args:
        product_code: Temizlenmiş MAHLE kodu (örn: "KL 913" veya "KL913")
        ufi_db:       load_ufi_db() ile yüklenmiş veritabanı

    Returns:
        {'tip': 'Yakıt Filtresi', 'original': 'KL 100/2'} → onaylı
        None → listede yok, bu ürünü ATLA
    """
    if not product_code or not ufi_db:
        return None
    upper = product_code.upper()
    clean = upper.replace(' ', '').replace('.', '').replace('/', '')
    return ufi_db.get(clean) or ufi_db.get(upper)


def format_mahle_code(code_str: str) -> str:
    """
    MAHLE kodlarını standart formata getirir: KL913 → KL 913

    MAHLE kodu prefix + numara şeklindedir.
    İkiler bazen boşluksuz gönderir, Shopify'da boşluklu olması gerekir.

    Örnekler:
        "KL913"   → "KL 913"
        "OC47OF"  → "OC 47OF"
        "KL 913"  → "KL 913"  (zaten doğru)
    """
    if not code_str:
        return code_str
    upper = code_str.upper().strip()
    for prefix in ['LAK', 'LAO', 'LA', 'KL', 'KX', 'OC', 'OX', 'LX', 'HX']:
        if upper.startswith(prefix):
            rest = code_str[len(prefix):].strip()
            if rest and code_str[len(prefix):len(prefix)+1] != ' ':
                return f"{prefix} {rest}"
            return code_str  # Zaten boşluklu
    return code_str


# ===========================================================================
# GENEL: ÜRÜN TİPİ BELİRLEME (MAHLE hariç tüm markalar)
# ===========================================================================

# ===========================================================================
# UFI KATEGORİ KURAL TABLOSU — ikiler_ufi_filter_marka_cekme.py'den
# CSV gerektirmez, deterministik %100 doğru
# ===========================================================================
_UFI_XX_KAT: Dict[str, str] = {
    '24': 'Hava Filtresi',
    '27': 'Hava Filtresi',
    '30': 'Hava Filtresi',
    '31': 'Hava Filtresi',
    '55': 'Hava Filtresi',
    '80': 'Hava Filtresi',
    '25': 'Yağ Filtresi',
    '26': 'Yağ Filtresi',
    '00': 'Yağ Filtresi',
    '65': 'Yağ Filtresi',
    '34': 'Kabin Hava Filtresi',
    '53': 'Kabin Hava Filtresi',
    '54': 'Kabin Hava Filtresi',
    '22': 'Yakıt Filtresi',
    '60': 'Yakıt Filtresi',
}
_UFI_YAG_23: frozenset = frozenset({
    '101','237','244','248','264','274','303','313','476','488'
})

def ufi_kod_kategori(kod: str) -> str:
    """UFI kodundan deterministik kategori — XX kural tablosu"""
    k = str(kod).strip()
    parts = k.split('.')
    if len(parts) == 3:
        xx, yyy = parts[0], parts[1]
    else:
        kn = k.replace(' ', '').replace('-', '')
        if len(kn) < 2:
            return 'UFI FİLTRE Ürünü'
        xx  = kn[:2].upper()
        yyy = kn[2:5] if len(kn) >= 5 else ''
    xx = xx.upper()
    if xx == '23':
        return 'Yağ Filtresi' if yyy in _UFI_YAG_23 else 'Yakıt Filtresi'
    return _UFI_XX_KAT.get(xx, 'UFI FİLTRE Ürünü')


def detect_product_type(sku: str, marka_key: str) -> str:
    """
    SKU koduna ve markaya göre ürün tipini belirler.

    Args:
        sku:       Normalize edilmiş SKU kodu
        marka_key: Marka anahtarı

    Returns:
        Ürün tipi string'i
    """
    # UFI: kendi kural tablosunu kullan (noktalı format ile)
    if marka_key == "ufi":
        return ufi_kod_kategori(sku)

    sku_up = sku.upper()

    if sku_up.startswith(('OC', 'OX', 'W', 'HU')):
        return "Yağ Filtresi"
    elif sku_up.startswith(('KL', 'KX', 'WK', 'PP')):
        return "Yakıt Filtresi"
    elif sku_up.startswith(('LX', 'C', 'AP', 'AM', 'AR')):
        return "Hava Filtresi"
    elif sku_up.startswith(('LA', 'CU')):
        return "Kabin Hava Filtresi"
    else:
        return f"{marka_key.upper()} Ürünü"


# ===========================================================================
# BÖLÜM 9: İKİLER SCRAPER
# ===========================================================================

def run_scraper(cookie_str: str, marka_key: str,
                limit: Optional[int] = None) -> Dict[str, Any]:
    """
    İkiler B2B platformundan belirtilen marka için ürünleri çeker.

    İkiler API Bilgileri:
        URL:    https://b4b.ikilerotomotiv.com/Search/SearchProduct
        Method: POST
        Auth:   Cookie ile oturum

    Sayfalama:
        Her istekte dataCount arttırılır (0, 24, 48, ...)
        Batch < 24 geldiğinde son sayfa olduğu anlaşılır.

    Args:
        cookie_str: "key1=val1; key2=val2" formatında cookie string
        marka_key:  Marka anahtarı (örn: "mahle", "mann")
        limit:      Maksimum çekilecek ürün sayısı (None = tümü)

    Returns:
        {
            "status":        "ok" / "empty" / "error",
            "marka":         "MAHLE",
            "csv_file":      "mahle_data_20260228.csv",
            "total_records": 829,
            "added":         780,
            "skipped":       30,
            "banned":        19,
            "duration_seconds": 45.2,
            "rows":          [{...}, ...]  ← Shopify sync için kullanılır
        }
    """
    if marka_key not in MARKA_TANIM:
        return {"status": "error", "message": f"Bilinmeyen marka: {marka_key}. Gecerli: {GECERLI_MARKALAR}"}

    ikiler_marka, shopify_vendor = MARKA_TANIM[marka_key]

    LOG.log("=" * 60, "INFO")
    LOG.log(f"SCRAPER BASLADI: {ikiler_marka}", "INFO")
    LOG.log("=" * 60, "INFO")

    start_time = datetime.now()
    session    = requests.Session()

    # Cookie'yi parse et ve session'a yükle
    try:
        cookies_dict = {}
        for part in cookie_str.split(';'):
            part = part.strip()
            if '=' in part:
                k, v = part.split('=', 1)
                cookies_dict[k.strip()] = v.strip()
        session.cookies.update(cookies_dict)
        session.headers.update({
            'Accept':       'application/json, text/plain, */*',
            'Content-Type': 'application/json;charset=UTF-8',
            'User-Agent':   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        LOG.log("✅ Cookie yuklendi", "INFO")
    except Exception as e:
        LOG.log(f"Cookie hatasi: {e}", "ERROR")
        return {"status": "error", "message": str(e)}

    base_url     = "https://b4b.ikilerotomotiv.com/Search/SearchProduct"
    all_data     = []
    data_count   = 0
    batch_size   = 24
    added        = 0
    skipped      = 0
    banned_count = 0

    try:
        while True:
            payload = {
                "dataCount":        data_count,
                "manufacturer":     ikiler_marka,  # ← marka burada değişir
                "vehicleCategory":  None,
                "vehicleBrand":     None,
                "vehicleModel":     None,
                "productGroup1":    None,
                "productGroup2":    None,
                "productGroup3":    None,
                "campaign":         False,
                "newArrival":       False,
                "newProduct":       False,
                "comparsionProduct":False,
                "onQuantity":       False,
                "onWay":            False,
                "isOem":            0,
                "isTop50":          False,
                "isCode":           0
            }

            print_magenta(f"\n[{ikiler_marka}] Sayfa: {data_count // max(batch_size,1) + 1}")
            LOG.log(f"[{ikiler_marka}] Sayfa {data_count // max(batch_size,1) + 1}", "INFO")

            response = session.post(base_url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            items      = data.get('ProductList', [])
            batch_size = len(items)

            if not items:
                LOG.log(f"[{ikiler_marka}] Bos sayfa, son sayfa. Response: {str(data)[:200]}", "WARN")
                break

            for item in items:
                kod       = item.get('Code', '')
                temiz_kod = clean_code(kod, marka_key)

                if not temiz_kod:
                    skipped += 1
                    continue

                # Yasaklı ürün kontrolü
                banned, reason = is_banned(item.get('Name', ''), temiz_kod)
                if banned:
                    banned_count += 1
                    LOG.log_error(ikiler_marka, temiz_kod, "BANNED", f"Yasakli: {reason}")
                    continue

                name_up = item.get('Name', '').upper()
                if 'KURUTUCU' in name_up or ('SU' in name_up and 'FILTRE' in name_up):
                    skipped += 1
                    continue

                # ============================================================
                # MAHLE'YE ÖZEL MANTIĞI — DİĞER MARKALAR BU BLOĞA GİRMEZ
                # ============================================================
                # MAHLE'de ürün tipi UFI cross reference listesinden alınır.
                # UFI listesinde olmayan MAHLE kodları tamamen atlanır.
                # Diğer tüm markalarda bu kontrol yapılmaz, tüm ürünler alınır.
                # ============================================================
                # Ürün tipi SKU prefix'inden belirlenir (MAHLE dahil tüm markalar)
                # ikiler_mahle_marka_cekme.py orijinal mantığı
                sku_norm = temiz_kod.replace(' ', '').replace('.', '').replace('/', '').upper()

                if sku_norm.startswith(('KL', 'KX')):
                    urun_tipi = 'Yakıt Filtresi'
                elif sku_norm.startswith(('OC', 'OX')):
                    urun_tipi = 'Yağ Filtresi'
                elif sku_norm.startswith('LX'):
                    urun_tipi = 'Hava Filtresi'
                elif sku_norm.startswith(('LAK', 'LAO', 'LA')):
                    urun_tipi = 'Kabin Hava Filtresi'
                elif sku_norm.startswith('HX'):
                    urun_tipi = 'Hidrolik Şanzıman Filtresi'
                else:
                    urun_tipi = detect_product_type(sku_norm, marka_key)

                # Fiyat önceliği: Kampanya > Net > Liste
                raw_camp = clean_price(item.get('CampaignPriceCustomerStr', ''))
                raw_net  = clean_price(item.get('PriceNetCustomerStr', ''))
                raw_list = clean_price(item.get('PriceListStr', ''))

                if raw_camp and raw_camp not in ["0,00", "0"]:
                    son_fiyat = raw_camp
                elif raw_net and raw_net not in ["0,00", "0"]:
                    son_fiyat = raw_net
                else:
                    son_fiyat = raw_list

                # Stok ve depo bilgisi
                toplam_stok   = 0
                depo_isimleri = []
                for wh in item.get('WarehouseQuantity', []):
                    qty     = int(wh.get('Quantity', 0))
                    wh_name = wh.get('Warehouse', {}).get('Name', '')
                    toplam_stok += qty
                    if qty > 0:
                        cw = get_warehouse_name(wh_name)
                        if cw not in depo_isimleri:
                            depo_isimleri.append(cw)

                depo_str = " | ".join(depo_isimleri) if depo_isimleri else "Stok Yok"
                sku_norm = temiz_kod.replace(' ', '').replace('.', '').replace('/', '').upper()

                row = {
                    'Marka':       item.get('Manufacturer', ikiler_marka),
                    'Kod':         temiz_kod,
                    'SKU':         sku_norm,
                    'Urun':        urun_tipi,
                    'Fiyat':       son_fiyat,
                    'Toplam Stok': toplam_stok,
                    'Depo':        depo_str
                }
                all_data.append(row)
                added += 1

                LOG.log_update(
                    ikiler_marka, temiz_kod, sku_norm, urun_tipi,
                    son_fiyat, "-", toplam_stok, 0, "CEKILDI", "Ikiler'den alindi"
                )
                print_yellow(
                    f"  ✓ {temiz_kod:15s} | {urun_tipi:20s} | "
                    f"Stok: {int(toplam_stok):3d} | {son_fiyat:>8s} TL"
                )

                if limit and len(all_data) >= limit:
                    LOG.log(f"Limit ({limit}) ulasildi", "INFO")
                    break

            if limit and len(all_data) >= limit:
                break

            data_count += batch_size

            if batch_size < 24:
                LOG.log("Batch < 24, son sayfa", "INFO")
                break

            time.sleep(0.3)

    except Exception as e:
        LOG.log(f"Scraper hatasi [{ikiler_marka}]: {e}", "ERROR")
        raise

    # Sonuç
    sure = (datetime.now() - start_time).total_seconds()
    result = {
        "status":           "empty",
        "marka":            ikiler_marka,
        "csv_file":         None,
        "total_records":    0,
        "limit":            limit,
        "added":            added,
        "skipped":          skipped,
        "banned":           banned_count,
        "duration_seconds": sure,
        "timestamp":        start_time.isoformat(),
        "rows":             []
    }

    if all_data:
        df       = pd.DataFrame(all_data)
        ts       = time.strftime("%Y%m%d_%H%M%S")
        csv_name = f"{marka_key}_data_{ts}.csv"
        csv_path = LOG.report_dir / csv_name
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')

        print_green(f"\n✅ CSV: {csv_name} ({len(df)} ürün)")
        LOG.log_stats(
            f"SCRAPER TAMAMLANDI | {ikiler_marka} | "
            f"Toplam: {len(df)} | Eklenen: {added} | Atlanan: {skipped} | "
            f"Yasakli: {banned_count} | Sure: {sure:.1f}sn"
        )
        result.update({
            "status":        "ok",
            "csv_file":      csv_name,
            "total_records": int(len(df)),
            "rows":          all_data
        })
    else:
        LOG.log(f"[{ikiler_marka}] Hic veri cekilemedi!", "WARN")

    return result


# ===========================================================================
# BÖLÜM 10: WHATSAPP RAPOR OLUŞTURUCU
# ===========================================================================

def build_whatsapp_report(job: SyncJob) -> str:
    """
    N8N üzerinden Evolution API'ye gönderilecek WhatsApp mesajını oluşturur.

    Format (orta detay - SKU + fiyat):
        *MAHLE Shopify Sync*
        28.02.2026 16:00  |  Sure: 0dk 10sn

        Toplam: 10  |  Basarili: 4  |  Basarisiz: 6  |  Basari: %40

        *Guncellenenler (4)*
        OC47OF  154.97 TL -> 271.20 TL
        ...

        *Hatali Urunler (6)*
        Fiyat eksik (3):
          CLC262000S
          ...
        Shopify SKU yok (3):
          OX153D3ECO
          ...

        _MAHLE Otomasyon_

    Not: WhatsApp'ta *metin* kalın, _metin_ italik gösterir.
         Emoji kullanılmaz (bazı cihazlarda bozuk görünür).

    Args:
        job: Tamamlanmış SyncJob nesnesi

    Returns:
        WhatsApp'a gönderilmeye hazır mesaj metni
    """
    now = datetime.now().strftime('%d.%m.%Y %H:%M')

    sure_str = "-"
    try:
        bas   = datetime.fromisoformat(job.started_at)
        bit   = datetime.fromisoformat(job.completed_at) if job.completed_at else datetime.now()
        sn    = int((bit - bas).total_seconds())
        sure_str = f"{sn // 60}dk {sn % 60}sn"
    except:
        pass

    oran = int((job.updated / job.total * 100)) if job.total > 0 else 0

    lines = [
        f"*{job.marka} Shopify Sync*",
        f"{now}  |  Sure: {sure_str}",
        f"",
        f"Toplam: {job.total}  |  Basarili: {job.updated}  |  Basarisiz: {job.failed}  |  Basari: %{oran}",
    ]

    # Başarılı ürünler
    if job.successes:
        lines.append("")
        lines.append(f"*Guncellenenler ({len(job.successes)})*")
        for s in job.successes:
            ikiler  = s.get('ikiler_fiyat', '').replace(',', '.')
            shopify = s.get('shopify_fiyat', '')
            lines.append(f"{s.get('sku','')}  {ikiler} TL -> {shopify} TL")

    # Başarısız ürünler - türe göre gruplandır
    if job.errors:
        lines.append("")
        lines.append(f"*Hatali Urunler ({len(job.errors)})*")

        fiyat_yok      = [e for e in job.errors if "Fiyat" in e.get('error', '')]
        sku_bulunamadi = [e for e in job.errors if "bulunamadi" in e.get('error', '').lower()
                                                  or "bulunamadı" in e.get('error', '').lower()]
        diger          = [e for e in job.errors
                          if e not in fiyat_yok and e not in sku_bulunamadi]

        if fiyat_yok:
            lines.append(f"Fiyat eksik ({len(fiyat_yok)}):")
            for e in fiyat_yok:
                lines.append(f"  {e.get('sku', e.get('kod', '?'))}")

        if sku_bulunamadi:
            lines.append(f"Shopify SKU yok ({len(sku_bulunamadi)}):")
            for e in sku_bulunamadi:
                lines.append(f"  {e.get('sku', e.get('kod', '?'))}")

        if diger:
            lines.append(f"Diger ({len(diger)}):")
            for e in diger:
                lines.append(f"  {e.get('sku','?')}  {e.get('error','')}")

    lines.append("")
    lines.append("_MAHLE Otomasyon_")

    return "\n".join(lines)


# ===========================================================================
# BÖLÜM 11: FASTAPI UYGULAMASI
# ===========================================================================

app = FastAPI(
    title       = "İkiler Çoklu Marka Sync API",
    description = "İkiler B2B → Shopify senkronizasyon sistemi",
    version     = "4.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

LAST_SYNC_TIME = None


# --------------------------------------------------------------------------
# ENDPOINT: /health
# N8N'de sistem durumunu kontrol etmek için kullanılır.
# --------------------------------------------------------------------------
@app.get("/health", summary="Sistem durumu")
def health_check():
    """
    Servisin çalışıp çalışmadığını ve desteklenen markaları döner.

    N8N kullanımı: Her workflow başında çağrılabilir.
    """
    return {
        "status":             "ok",
        "version":            "4.1.0",
        "timestamp":          datetime.now().isoformat(),
        "last_sync":          LAST_SYNC_TIME,
        "desteklenen_markalar": GECERLI_MARKALAR
    }


# --------------------------------------------------------------------------
# ENDPOINT: /scrape/{marka}
# Tek bir marka için İkiler'den veri çeker.
# --------------------------------------------------------------------------
@app.get("/scrape/{marka}", summary="Tek marka veri çek")
def scrape_single(
    marka: str,
    limit: Optional[int] = Query(None, description="Max ürün sayısı", ge=1)
):
    """
    Belirtilen marka için İkiler'den fiyat/stok verisi çeker.

    Parametreler:
        marka : mahle | mann | purflux | ufi | filtorq | filtron
        limit : Kaç ürün çekileceği (boş = tümü)

    N8N kullanımı:
        GET http://VPS_IP:8888/scrape/mahle?limit=500

    Örnek yanıt:
        {
            "status": "ok",
            "marka": "MAHLE",
            "total_records": 500,
            "csv_file": "mahle_data_20260228.csv",
            "rows": [...]
        }
    """
    if marka not in MARKA_TANIM:
        return JSONResponse(
            status_code=400,
            content={"status": "error",
                     "message": f"Gecersiz marka: {marka}",
                     "gecerli": GECERLI_MARKALAR}
        )

    cookie_str = _get_cookie()
    if not cookie_str:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Cookie bulunamadi"})

    try:
        result = run_scraper(cookie_str, marka, limit=limit)
        return JSONResponse(content=result)
    except Exception as e:
        LOG.log(f"SCRAPE HATASI [{marka}]: {e}", "ERROR")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# --------------------------------------------------------------------------
# ENDPOINT: /scrape/all
# Tüm markalar için veri çeker.
# --------------------------------------------------------------------------
@app.get("/scrape/all", summary="Tüm markalar veri çek")
def scrape_all(
    limit: Optional[int] = Query(None, description="Her marka için max ürün", ge=1)
):
    """
    Tüm desteklenen markalar için sırayla İkiler'den veri çeker.

    Not: Her marka için ayrı CSV oluşturulur.

    N8N kullanımı:
        GET http://VPS_IP:8888/scrape/all?limit=200
    """
    cookie_str = _get_cookie()
    if not cookie_str:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Cookie bulunamadi"})

    results = {}
    for marka_key in GECERLI_MARKALAR:
        try:
            results[marka_key] = run_scraper(cookie_str, marka_key, limit=limit)
        except Exception as e:
            results[marka_key] = {"status": "error", "message": str(e)}

    return JSONResponse(content={"results": results, "toplam_marka": len(results)})


# --------------------------------------------------------------------------
# ENDPOINT: POST /sync/{marka}/start
# Tek marka için async Shopify sync job başlatır.
# --------------------------------------------------------------------------
@app.post("/sync/{marka}/start", summary="Tek marka sync başlat")
def start_sync_single(
    marka: str,
    limit: Optional[int] = Query(None, description="Max ürün sayısı", ge=1)
):
    """
    Belirtilen marka için Shopify sync job başlatır.

    Adımlar:
        1. İkiler'den veri çek
        2. Arka plan thread'i başlat
        3. Job ID döndür

    N8N kullanımı:
        POST http://VPS_IP:8888/sync/mahle/start?limit=500

    Dönen job_id ile durum takibi:
        GET http://VPS_IP:8888/sync/status/{job_id}

    Desteklenen markalar:
        mahle, mann, purflux, ufi, filtorq, filtron
    """
    if marka not in MARKA_TANIM:
        return JSONResponse(
            status_code=400,
            content={"status": "error",
                     "message": f"Gecersiz marka: {marka}",
                     "gecerli": GECERLI_MARKALAR}
        )

    cookie_str = _get_cookie()
    if not cookie_str:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Cookie bulunamadi"})

    if not SHOPIFY_TOKEN:
        return JSONResponse(status_code=400, content={"status": "error", "message": "SHOPIFY_TOKEN tanimli degil"})

    try:
        result = run_scraper(cookie_str, marka, limit=limit)

        if result['status'] != 'ok':
            return JSONResponse(status_code=500, content={"status": "error", "message": "Veri cekilemedi"})

        products = result.get('rows', [])
        if not products:
            return JSONResponse(content={"status": "ok", "message": "Sync edilecek urun yok", "total": 0})

        job_id = str(uuid.uuid4())[:8]
        job    = SyncJob(
            job_id      = job_id,
            status      = "pending",
            marka       = MARKA_TANIM[marka][1],
            total       = len(products),
            processed   = 0,
            updated     = 0,
            failed      = 0,
            started_at  = datetime.now().isoformat(),
            errors      = [],
            successes   = []
        )
        job.save()

        thread = threading.Thread(
            target = sync_worker,
            args   = (job_id, marka, products, limit),
            daemon = True
        )
        thread.start()

        LOG.log(f"Sync job basladi: #{job_id} [{MARKA_TANIM[marka][1]}] {len(products)} urun", "INFO")

        return JSONResponse(content={
            "status":  "started",
            "job_id":  job_id,
            "marka":   MARKA_TANIM[marka][1],
            "total":   len(products),
            "message": f"{len(products)} urun icin sync baslatildi"
        })

    except Exception as e:
        LOG.log(f"SYNC START HATASI [{marka}]: {e}", "ERROR")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# --------------------------------------------------------------------------
# ENDPOINT: POST /sync/all/start
# Tüm markalar için sırayla sync başlatır.
# --------------------------------------------------------------------------
@app.post("/sync/all/start", summary="Tüm markalar sync başlat")
def start_sync_all(
    limit: Optional[int] = Query(None, description="Her marka için max ürün", ge=1)
):
    """
    Tüm desteklenen markalar için ayrı ayrı sync job başlatır.

    Her marka için ayrı job_id döner.

    N8N kullanımı:
        POST http://VPS_IP:8888/sync/all/start?limit=500

    Dönen yanıt:
        {
            "jobs": {
                "mahle": {"job_id": "aa94f225", "total": 829},
                "mann":  {"job_id": "bb12c456", "total": 412},
                ...
            }
        }
    """
    cookie_str = _get_cookie()
    if not cookie_str:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Cookie bulunamadi"})

    if not SHOPIFY_TOKEN:
        return JSONResponse(status_code=400, content={"status": "error", "message": "SHOPIFY_TOKEN tanimli degil"})

    jobs = {}
    for marka_key in GECERLI_MARKALAR:
        try:
            result = run_scraper(cookie_str, marka_key, limit=limit)
            if result['status'] != 'ok' or not result.get('rows'):
                jobs[marka_key] = {"status": "skip", "reason": "Veri cekilemedi veya bos"}
                continue

            products = result['rows']
            job_id   = str(uuid.uuid4())[:8]
            job      = SyncJob(
                job_id     = job_id,
                status     = "pending",
                marka      = MARKA_TANIM[marka_key][1],
                total      = len(products),
                processed  = 0,
                updated    = 0,
                failed     = 0,
                started_at = datetime.now().isoformat(),
                errors     = [],
                successes  = []
            )
            job.save()

            thread = threading.Thread(
                target = sync_worker,
                args   = (job_id, marka_key, products, limit),
                daemon = True
            )
            thread.start()

            jobs[marka_key] = {
                "status": "started",
                "job_id": job_id,
                "total":  len(products)
            }
        except Exception as e:
            jobs[marka_key] = {"status": "error", "message": str(e)}

    return JSONResponse(content={"jobs": jobs, "toplam": len(jobs)})


# --------------------------------------------------------------------------
# ENDPOINT: GET /sync/status/{job_id}
# N8N bu endpoint'i polling ile çağırır.
# --------------------------------------------------------------------------
@app.get("/sync/status/{job_id}", summary="Job durumu sorgula")
def get_status(job_id: str):
    """
    Belirtilen job'ın anlık durumunu döner.

    N8N bu endpoint'i 30 saniyede bir çağırır.
    status == "completed" olduğunda WhatsApp mesajı gönderilir.

    Dönen alanlar:
        status      : pending / running / completed / failed
        progress    : "45/100"
        updated     : Başarıyla güncellenen sayı
        failed      : Başarısız sayı
        eta_seconds : Tahmini kalan süre (saniye)
        successes   : Başarılı ürün listesi
        errors      : Hatalı ürün listesi
    """
    job = SyncJob.load(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Job bulunamadi"})

    result             = job.to_dict()
    result['progress'] = f"{job.processed}/{job.total}"

    if job.status == "running" and job.processed > 0:
        try:
            elapsed          = (datetime.now() - datetime.fromisoformat(job.started_at)).total_seconds()
            avg_time         = elapsed / job.processed
            result['eta_seconds'] = int((job.total - job.processed) * avg_time)
        except:
            result['eta_seconds'] = None
    else:
        result['eta_seconds'] = None

    return JSONResponse(content=result)


# --------------------------------------------------------------------------
# ENDPOINT: GET /sync/report/{job_id}
# WhatsApp için hazır mesaj formatı döner.
# --------------------------------------------------------------------------
@app.get("/sync/report/{job_id}", summary="WhatsApp raporu al")
def get_report(job_id: str):
    """
    Tamamlanmış bir job için WhatsApp'a gönderilmeye hazır rapor üretir.

    N8N'de Enviar texto node'unun Mensagem alanına:
        {{ $json.mesaj }}

    yazılması yeterlidir.
    """
    job = SyncJob.load(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Job bulunamadi"})

    mesaj = build_whatsapp_report(job)

    return JSONResponse(content={
        "status":     "ok",
        "job_id":     job_id,
        "job_status": job.status,
        "marka":      job.marka,
        "updated":    job.updated,
        "failed":     job.failed,
        "total":      job.total,
        "mesaj":      mesaj,         # ← N8N: {{ $json.mesaj }}
        "successes":  job.successes,
        "errors":     job.errors
    })


# --------------------------------------------------------------------------
# ENDPOINT: GET /sync/jobs
# Tüm job'ları listeler.
# --------------------------------------------------------------------------
@app.get("/sync/jobs", summary="Tüm jobları listele")
def list_jobs():
    """Tüm geçmiş ve devam eden jobların özetini döner."""
    jobs = []
    try:
        for fp in JOBS_DIR.glob("*.json"):
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                d['success_count'] = len(d.get('successes', []))
                d['error_count']   = len(d.get('errors', []))
                jobs.append(d)
            except:
                pass
        jobs.sort(key=lambda x: x.get('started_at', ''), reverse=True)
        return JSONResponse(content={"jobs": jobs, "total": len(jobs)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# --------------------------------------------------------------------------
# ENDPOINT: GET /logs
# --------------------------------------------------------------------------
@app.get("/logs", summary="Log dosyasını görüntüle")
def get_logs(lines: int = Query(50, ge=1, le=500)):
    """Son N satır ana logu döner."""
    try:
        with open(LOG.main_log, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        return {"status": "ok", "lines": "".join(all_lines[-lines:])}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --------------------------------------------------------------------------
# ENDPOINT: GET /stats
# --------------------------------------------------------------------------
@app.get("/stats", summary="İstatistik logları")
def get_stats(lines: int = Query(100, ge=1, le=1000)):
    """Son N satır istatistik logu döner (job özetleri)."""
    try:
        with open(LOG.stats_log, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        return {"status": "ok", "lines": "".join(all_lines[-lines:])}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --------------------------------------------------------------------------
# Yardımcı: Cookie okuma
# --------------------------------------------------------------------------
def _get_cookie() -> str:
    """
    Cookie'yi şu sıraya göre arar:
        1. COOKIE_STR environment variable
        2. cookie.txt dosyası
    """
    cookie_str = os.getenv("COOKIE_STR", "")
    if not cookie_str:
        try:
            with open(Path(__file__).parent / "cookie.txt", 'r', encoding='utf-8') as f:
                cookie_str = f.read().strip()
        except FileNotFoundError:
            pass
    return cookie_str


# ===========================================================================
# BÖLÜM 12: CLI MODU
# ===========================================================================

if __name__ == "__main__":
    print_cyan("=" * 60)
    print_cyan("  İKİLER ÇOKLU MARKA SCRAPER - CLI MODU")
    print_cyan("=" * 60)

    cookie_str = _get_cookie()
    if not cookie_str:
        print_red("❌ COOKIE_STR veya cookie.txt bulunamadi!")
        exit(1)

    print_cyan(f"\nDesteklenen markalar: {', '.join(GECERLI_MARKALAR)}")
    marka_input = input("Marka (boş = mahle): ").strip().lower() or "mahle"

    if marka_input not in MARKA_TANIM:
        print_red(f"❌ Gecersiz marka. Secenekler: {GECERLI_MARKALAR}")
        exit(1)

    try:
        raw   = input("Limit (boş = tümü): ").strip()
        limit = int(raw) if raw else None
    except:
        limit = None

    summary = run_scraper(cookie_str, marka_input, limit=limit)

    print_magenta("\n" + "=" * 60)
    print_magenta("SONUC")
    print_magenta("=" * 60)
    print(json.dumps(
        {k: v for k, v in summary.items() if k != 'rows'},
        indent=2, ensure_ascii=False
    ))
    print_magenta("=" * 60)
