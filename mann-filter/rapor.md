# 📊 MANN-FILTER Entegrasyon ve Kod Analiz Raporu

**Tarih:** 16 Ağustos 2026
**İncelenen Dosyalar:**
1. [`01_ikiler_mann_supabase_fiyat_stok.py`](file:///c:/VPS/IKILER_V_2/MANN/01_ikiler_mann_supabase_fiyat_stok.py) *(1. Aşama: Fiyat & Stok)*
2. [`02_ikiler_mann_filter_img_url_cekme.py`](file:///c:/VPS/IKILER_V_2/MANN/02_ikiler_mann_filter_img_url_cekme.py) *(2. Aşama: URL, Kategori & Görsel)*
**Hedef Tablo:** Supabase `public."IKILER_MANN"`

---

## 1. 🎯 Soru & Doğrulama: Kod Tam Olarak Böyle mi Çalışıyor?

> **Soru:** *"İşlem için ilk önce Supabase'e giderek `IKILER_MANN` tablosundan kod bilgisini alarak MANN'da arama yapacak; kod gerçekten böyle mi çalışıyor?"*

### ✅ **EVET, KOD TAM OLARAK BU ŞEKİLDE ÇALIŞMAKTADIR.**

`02_ikiler_mann_filter_img_url_cekme.py` dosyasının çalışma mimarisi adım adım şu şekildedir:

1. **Supabase'den Stoklu Kayıtları Çekme:**
   [`load_supabase_rows()`](file:///c:/VPS/IKILER_V_2/MANN/02_ikiler_mann_filter_img_url_cekme.py#L1144-L1171) fonksiyonu, Supabase REST API üzerinden `IKILER_MANN` tablosuna bağlanır ve yalnızca `marka = 'MANN-FILTER'` ve `toplam_stok > 0` olan satırları 500'lük sayfalar halinde çeker.
2. **Eksik URL ve Görsel Tespiti:**
   Çekilen kayıtlardan `mann_url` alanı boş olan veya 3 görseli (`img_url_1`, `img_url_2`, `img_url_3`) eksik olan satırlar **aday (candidate)** listesine alınır.
3. **Kod Bilgisini Çıkarma & Temizleme:**
   [`clean_db_code()`](file:///c:/VPS/IKILER_V_2/MANN/02_ikiler_mann_filter_img_url_cekme.py#L1174-L1179) ve [`normalize_code_display()`](file:///c:/VPS/IKILER_V_2/MANN/02_ikiler_mann_filter_img_url_cekme.py#L190-L225) ile tablodaki `kod` alanı temizlenir (örn: `YD.MANN HU 718/1k` → `HU 718/1 k`).
4. **MANN Kataloğunda Otomatik Arama (Selenium):**
   - Eğer ürüne ait geçerli bir `mann_url` henüz yoksa, `https://www.mann-filter.com/tr-tr/katalog.html` arama çubuğuna temizlenen kod yazılır.
   - Çıkan autocomplete / dropdown listesinden en yüksek skora sahip ürün linki (`/urun.html/...`) seçilerek yeni sekmede açılır.
   - Eğer ürünün `mann_url`'i zaten varsa, arama yapmadan doğrudan ilgili ürün sayfasına gidilir.
5. **Kategori ve Scene7 Görsellerinin Çekilmesi:**
   - Sayfa başlığından (`.cmp-product__title-family`) veya ML destekli prefix kurallarından ürünün **gerçek kategorisi** (`Yağ Filtresi`, `Hava Filtresi`, `Yakıt Filtresi`, `Kabin Hava Filtresi` vb.) okunur.
   - Sayfadaki Scene7 görsel havuzundan ürün kodunu doğrulayan en fazla 3 adet temiz görsel URL'si (`clean_scene7_url`) toplanır.
6. **Supabase'e Noktasal Güncelleme (`PATCH`):**
   [`patch_supabase_row()`](file:///c:/VPS/IKILER_V_2/MANN/02_ikiler_mann_filter_img_url_cekme.py#L1199-L1228) fonksiyonu, `sku` bazında ilgili satıra `PATCH` isteği atar. Yalnızca eksik olan `kategori`, `mann_url` ve `img_url_1..3` alanlarını doldurur. **Fiyat, stok, depo ve kod alanlarına asla dokunmaz.**

---

## 2. 🔄 2 Aşamalı Genel Sistem Mimarisi

```mermaid
flowchart TD
    subgraph AŞAMA 1: Fiyat ve Stok Entegrasyonu
        A1[İkiler B2B API] -->|Marka: MANN-FILTER| B1[01_ikiler_mann_supabase_fiyat_stok.py]
        B1 -->|Temizle & Filtrele| C1[Fiyat, Stok, Depo, SKU]
        C1 -->|UPSERT: merge-duplicates| D1[(Supabase: IKILER_MANN)]
    end

    subgraph AŞAMA 2: Zenginleştirme (URL, Kategori & Görsel)
        D1 -->|1. SELECT: stok > 0 & eksik URL/Görsel| A2[02_ikiler_mann_filter_img_url_cekme.py]
        A2 -->|2. Kod Temizleme: HU 718/1 k| B2[Selenium Headless Chrome]
        B2 -->|3. Arama & Seçim| C2[MANN Online Katalog]
        C2 -->|4. Gerçek Kategori & Scene7 Görselleri| A2
        A2 -->|5. PATCH: Yalnızca Kategori & Görseller| D1
    end
```

---

## 3. 🗄️ Supabase Tablo Yapısı ve Alan Dağılımı

Tablo Şeması: `public."IKILER_MANN"`

```sql
create table if not exists public."IKILER_MANN" (
  sku text not null,
  kod text null,
  marka text not null default 'MANN-FILTER'::text,
  kategori text null,
  fiyat numeric(12, 2) null,
  depo_merkezi text null,
  toplam_stok integer not null default 0,
  mann_url text null,
  img_url_1 text null,
  img_url_2 text null,
  img_url_3 text null,
  guncelleme_tarihi timestamp with time zone null,
  constraint IKILER_MANN_pkey primary key (sku)
);

create index if not exists ikiler_mann_marka_idx on public."IKILER_MANN" (marka);
create index if not exists ikiler_mann_stok_idx on public."IKILER_MANN" (toplam_stok);
```

### 📋 Hangi Script Hangi Kolonları Yönetir?

| Kolon | Tip | Yöneten Script | Açıklama |
| :--- | :--- | :--- | :--- |
| `sku` | `text (PK)` | **Aşama 1** | Boşluksuz ve standartlaştırılmış tekil anahtar (Örn: `HU7181K`) |
| `kod` | `text` | **Aşama 1** | Formatlanmış ürün kodu (Örn: `HU 718/1 k`) |
| `marka` | `text` | **Aşama 1** | `MANN-FILTER` |
| `fiyat` | `numeric(12,2)`| **Aşama 1** | Kampanya > Net > Liste fiyatı önceliğine göre hesaplanan tutar |
| `depo_merkezi`| `text` | **Aşama 1** | Stoğun bulunduğu depolar (`DENİZLİ MERKEZ \| DENİZLİ ÇARDAK`) |
| `toplam_stok` | `integer` | **Aşama 1** | Depolardaki toplam adet (yalnızca `> 0` olanlar aktarılır) |
| `guncelleme_tarihi`| `timestamptz`| **Aşama 1** | Fiyat/stok senkronizasyon zamanı |
| `kategori` | `text` | **Aşama 1 & 2**| Aşama 1 tahmini atar; **Aşama 2 MANN web sayfasından doğrular** |
| `mann_url` | `text` | **Aşama 2** | MANN kataloğundaki doğrudan ürün sayfası bağlantısı |
| `img_url_1` | `text` | **Aşama 2** | Ürün kodunu içeren 1. doğrulanmış Scene7 görseli |
| `img_url_2` | `text` | **Aşama 2** | Ürün kodunu içeren 2. doğrulanmış Scene7 görseli |
| `img_url_3` | `text` | **Aşama 2** | Ürün kodunu içeren 3. doğrulanmış Scene7 görseli |

---

## 4. 🔬 02 Numaralı Scriptin Detaylı İşleyiş Mekanizması

### 4.1. Kod Normalizasyonu ve Önek Ayıklama
- `clean_db_code()`: Veritabanında `YD.MANN HU 718/1k` veya `MANN-FILTER CUK 2939` gibi yer alan isimleri temizler.
- `normalize_code_display()`: `CUK`, `HU`, `WK`, `CU`, `WDK`, `CF`, `TB` gibi MANN filtre kodlarını doğru boşluklu hale getirir (Örn: `HU 718/1 k`).
- `is_valid_mann_catalog_code()`: Kodun MANN formatında olup olmadığını (`^[A-Z]{1,4}\s*[0-9]`) kontrol eder; dahili yedek parça numaralarını aramaya sokmaz.

### 4.2. Akıllı Arama ve Dropdown Seçimi
- Arama kutusuna kod yazıldıktan sonra `dropdown_wait_and_click()` tetiklenir.
- Açılan dropdown listesindeki öğeler taranır:
  - `KATALOG`, `GÜNCEL` gibi genel bağlantılar filtrelenir.
  - `/urun.html/` içeren ve ürün kodunu tam eşleştiren en yüksek skorlu eleman seçilir.
- Yeni bir sekmede (`_blank`) ürün detayı açılarak katalog sekmesinin durumu bozulmadan korunur.

### 4.3. Kategori Tespiti (Web Scraping + Fallback)
- **1. Tercih:** `.cmp-product__title-family` CSS sınıfı üzerinden doğrudan kategori okunur (`Yağ Filtresi`, `Hava Filtresi` vb.).
- **2. Tercih:** Sayfa içindeki `h2`, `h3` başlıkları taranır.
- **3. Tercih (ML / Kural Tabanlı Fallback):** Sayfadan okunamadıysa `predict_category_from_code()` fonksiyonu devreye girer (Örn: `HU` → Yağ, `CUK/CU/FP` → Kabin Hava, `WK/PU` → Yakıt).

### 4.4. Scene7 Görsel Doğrulama ve Temizleme
- Scene7 CDN URL'leri (`https://s7g10.scene7.com/is/image/mannhummel/...`) taranır.
- `url_has_code()` kontrolü ile URL'nin gerçekten o ürüne ait olduğu teyit edilir (alakasız banner/logo görselleri elenir).
- `clean_scene7_url()` ile URL arkasındaki query parametreleri (`?qlt=82...`) ve JSON/HTML kaçış karakterleri temizlenerek saf görsel linki elde edilir.
- En fazla 3 görsel seçilir.

---

## 5. 🛠️ Kodda Tespit Edilen Durumlar ve Optimizasyonlar

1. **Eski CSV Kod Artıkları (Legacy Code):**
   - Scriptin üst kısmında CSV okuma/yazma yardımcı fonksiyonları (`sniff_delimiter`, `read_rows`, `output_headers`, `repair_output_if_header_missing`) bulunmaktadır.
   - Bu fonksiyonlar scriptin ilk versiyonlarından kalmadır; ancak `main()` akışında doğrudan Supabase kullanıldığı için bu CSV fonksiyonları çalışmayı engellemez, sadece ölü kod (dead code) niteliğindedir.
2. **Kayıtlı URL Avantajı (Fast-Path):**
   - Eğer ürünün `mann_url`'i daha önce kaydedilmişse ancak görselleri eksikse, script gereksiz katalog araması yapmaz; doğrudan ilgili sayfayı açarak görselleri çeker.
3. **Session & Bellek Önbelleği (`cache`):**
   - Aynı kod veya URL birden fazla satırda geçiyorsa, Selenium tekrar çalıştırılmaz; hafızadaki `cache` üzerinden anında Supabase'e PATCH atılır.

---

## 6. 📌 Sonuç ve Uygulama Sırası

1. **Önce:** [`01_ikiler_mann_supabase_fiyat_stok.py`](file:///c:/VPS/IKILER_V_2/MANN/01_ikiler_mann_supabase_fiyat_stok.py) çalıştırılır. İkiler B2B'deki güncel fiyat, stoklu MANN ürünleri ve depolar Supabase'e yazılır.
2. **Sonra:** [`02_ikiler_mann_filter_img_url_cekme.py`](file:///c:/VPS/IKILER_V_2/MANN/02_ikiler_mann_filter_img_url_cekme.py) çalıştırılır. Supabase'deki stoklu MANN ürünlerinden URL'si veya görseli eksik olanlar tespit edilir, MANN kataloğundan çekilerek Supabase tablosu zenginleştirilir.
