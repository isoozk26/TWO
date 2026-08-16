# TWO

TWO, marka bazlı filtre otomasyonlarının tek ana reposudur.

## Proje klasörleri

| Klasör | İçerik | Durum |
|---|---|---|
| [`filtron/`](filtron/) | IKILER FILTRON Supabase, URL/görsel ve Shopify akışı | ✅ Aktif |
| [`mann-filter/`](mann-filter/) | MANN-FILTER dosyaları için ayrılmış alan | 🟠 Yakında |

Her marka kendi klasöründe tutulur. Bir markanın Python dosyaları, SQL şeması, HTML arayüzü, bağımlılıkları ve README dosyası diğer markanın dosyalarına karışmaz.

## FILTRON ile çalışma

```bash
cd filtron
python -m pip install -r requirements.txt
```

Gizli değerler `.env`, cookie, CSV, log ve çalışma çıktıları olarak yerel tutulur; GitHub'a gönderilmez.

## Gelecekte MANN-FILTER ekleme

MANN-FILTER dosyaları yalnızca `mann-filter/` altına eklenmelidir. Ana repo ortak belgeler ve klasör yönlendirmesi için kullanılır; marka kodları birbirine karıştırılmaz.
