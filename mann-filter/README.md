# MANN-FILTER

İkiler B2B → Supabase `IKILER_MANN` → MANN-FILTER URL/görsel/kategori akışı.

## Ana dosyalar

- `01_ikiler_mann_supabase_fiyat_stok.py` — fiyat/stok kaynağı
- `02_ikiler_mann_filter_img_url_cekme.py` — MANN ürün URL/kategori/görselleri
- `test_supabase_mann_kod.py` — yalnız-okuma Supabase teşhis testi
- `IKILER_MANN_create.sql` — tablo şeması
- `mann_ikiler.html` — yerel PowerShell komut üreticisi

## Güvenlik

Secret, cookie, CSV çıktı, log ve Python cache dosyaları depoya alınmaz.
Supabase/Shopify/OpenAI değerlerini yerel ortam değişkenleri veya yerel HTML alanları üzerinden girin.
