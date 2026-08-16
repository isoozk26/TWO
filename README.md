# IKILER FILTRON

FILTRON marka ürünleri için Supabase kaynaklı fiyat/stok, URL-görsel ve Shopify SEO senkronizasyon araçları.

## Akış

1. `01_filtron_ikiler_supabase_fiyat_stok.py` — Supabase fiyat/stok güncelleme
2. `02_filtron_ikiler_supabase_url_gorsel.py` — URL ve görsel güncelleme
3. `03_filtron_supabase_shopify_seo.py` — Shopify SEO, fiyat ve stok senkronizasyonu

`IKILER_FILTRON_create.sql` Supabase tablo ve indekslerini oluşturur.

## Kurulum

```bash
python -m pip install -r requirements.txt
```

## Gizli değişkenler

Gizli değerleri `.env` veya işletim sistemi ortam değişkenlerinde tutun. `.env` Git'e dahil edilmez.

Gerekli değişkenler kullanılan araca göre değişir; tipik olarak:

- `SUPABASE_URL`
- `SUPABASE_KEY` veya `SUPABASE_SECRET_KEY`
- `SHOP_SUBDOMAIN`
- `SHOPIFY_TOKEN`
- `OPENAI_API_KEY`

Canlı Shopify işlemlerinden önce `DRY_RUN=1` ile kontrol edin.

## Not

Yerel çalışma çıktıları, CSV/veri dosyaları, loglar, cookie dosyaları ve yedek Python dosyaları güvenlik ve depo temizliği için GitHub'a gönderilmez.
