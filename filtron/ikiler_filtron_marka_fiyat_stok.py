import requests
import pandas as pd
import json
import os
import time
import re

def clean_price(text):
    """
    Fiyat metnini temizler. HTML, harf, boşluk siler.
    Sadece '630,83' gibi sayıyı döndürür.
    """
    if not text or not isinstance(text, str):
        return ""
    
    # HTML tagleri sil
    text = re.sub(r'<[^>]+>', '', text)
    # &nbsp; sil
    text = text.replace('&nbsp;', ' ').strip()
    
    # Sayı yakala
    match = re.search(r'[\d]+[.,\d]*', text)
    if match:
        return match.group(0)
    return ""

def clean_code(code_str, brand_name):
    """
    Kodun başındaki 'YD.FILTRON', 'FILTRON.' gibi ekleri siler.
    Örn: 'YD.FILTRON OE648/7' -> 'OE648/7'
    """
    if not code_str:
        return ""
    
    # Markayı regex için escape et
    brand_escaped = re.escape(brand_name)
    
    # Örn: 'YD.FILTRON ', 'YD FILTRON ', 'FILTRON.', 'FILTRON ' vs.
    pattern = rf'^(YD\.|YD\s)?{brand_escaped}[\.\s]*'
    
    cleaned = re.sub(pattern, '', code_str, flags=re.IGNORECASE)
    return cleaned.strip()

def parse_filter_type(product_name):
    """Ürün isminden tipi bulur"""
    name_upper = product_name.upper()
    
    # İSTENMEYENLER (Main döngüde atlanacak)
    if 'KURUTUCU' in name_upper:
        return 'KURUTUCU FİLTRE'
    if 'SU' in name_upper:
        return 'SU FİLTRESİ'
    
    # İSTENENLER
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

def get_clean_warehouse_name(raw_name):
    """
    Depo adlarını istenen formata çevirir.
    Y.PARÇA -> DENİZLİ MERKEZ
    DENİZLİ -> DENİZLİ ÇARDAK
    """
    if not raw_name:
        return ""
    upper_name = raw_name.upper()
    
    # Y.PARÇA ise DENİZLİ MERKEZ yap
    if "Y.PARÇA" in upper_name or "Y.PARCA" in upper_name:
        return "DENİZLİ MERKEZ"
    
    # DENİZLİ ise DENİZLİ ÇARDAK yap
    if "DENİZLİ" in upper_name or "DENIZLI" in upper_name:
        return "DENİZLİ ÇARDAK"
        
    return raw_name

def main():
    print("--- İkiler Otomotiv: FILTRON TAM LİSTE (CSV MODU) ---")
    
    cookie_file = 'cookie.txt'
    if not os.path.exists(cookie_file):
        print("HATA: 'cookie.txt' dosyası bulunamadı! Lütfen oluşturun.")
        return

    with open(cookie_file, 'r', encoding='utf-8') as f:
        cookie_value = f.read().strip()

    url = "https://b4b.ikilerotomotiv.com/Search/SearchProduct"
    
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json;charset=UTF-8',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
        'Cookie': cookie_value
    }

    # 🔧 BURASI ARTIK SADECE FILTRON
    target_brand = 'FILTRON'
    
    all_data = []
    data_count = 0
    is_finished = False
    
    print(f"\n🚀 '{target_brand}' için tüm veriler çekiliyor (Sınır Yok)...")

    while not is_finished:
        payload = {
            "dataCount": data_count, 
            "manufacturer": target_brand,
            "vehicleCategory": None,
            "vehicleBrand": None,
            "vehicleModel": None, 
            "productGroup1": None,
            "productGroup2": None,
            "productGroup3": None, 
            "campaign": False,
            "newArrival": False,
            "newProduct": False, 
            "comparsionProduct": False,
            "onQuantity": False,
            "onWay": False, 
            "isOem": 0,
            "isTop50": False,
            "isCode": 0
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            # Debug istersen burada açabilirsin:
            # print(response.status_code, response.text[:300])

            if response.status_code == 200:
                try:
                    data = response.json()
                    products = data.get('ProductList', [])
                    
                    batch_size = len(products)
                    
                    # Eğer hiç veri gelmediyse bitmiştir
                    if batch_size == 0:
                        print("   -> Veri sonu.")
                        is_finished = True
                        break
                    
                    for item in products:
                        # Marka Filtresi (API bazen karıştırabilir)
                        manufacturer = item.get('Manufacturer', '')
                        if target_brand not in manufacturer.upper():
                            continue

                        # ÜRÜN TİPİ ve FİLTRELEME
                        urun_tipi = parse_filter_type(item.get('Name', ''))
                        
                        # Su ve Kurutucu filtreleri ALMA
                        if urun_tipi in ['SU FİLTRESİ', 'KURUTUCU FİLTRE']:
                            continue

                        # KOD TEMİZLİĞİ (FILTRON ön ekini kaldır)
                        temiz_kod = clean_code(item.get('Code', ''), target_brand)
                        
                        # FİYAT MANTIĞI (Öncelik: Kampanya -> Net -> Liste)
                        raw_campaign = clean_price(item.get('CampaignPriceCustomerStr', ''))
                        raw_net = clean_price(item.get('PriceNetCustomerStr', ''))
                        raw_list = clean_price(item.get('PriceListStr', ''))

                        son_fiyat = ""
                        if raw_campaign and raw_campaign not in ["0,00", "0"]:
                            son_fiyat = raw_campaign
                        elif raw_net and raw_net not in ["0,00", "0"]:
                            son_fiyat = raw_net
                        else:
                            son_fiyat = raw_list

                        # STOK VE DEPO (İSİM DÜZELTME)
                        toplam_stok = 0
                        depo_isimleri = []
                        
                        if item.get('WarehouseQuantity'):
                            for wh in item['WarehouseQuantity']:
                                qty = wh.get('Quantity', 0)
                                raw_wh_name = wh.get('Warehouse', {}).get('Name', '')
                                
                                toplam_stok += qty
                                
                                if qty > 0:
                                    yeni_isim = get_clean_warehouse_name(raw_wh_name)
                                    if yeni_isim not in depo_isimleri:
                                        depo_isimleri.append(yeni_isim)
                        
                        depo_string = " | ".join(depo_isimleri)

                        # CSV İÇİN SATIR
                        row = {
                            'Marka': manufacturer,     # Burada da FILTRON gelecek
                            'Kod': temiz_kod,
                            'Ürün': urun_tipi,
                            'Fiyat': son_fiyat,
                            'DEPO MERKEZİ': depo_string,
                            'Toplam Stok': toplam_stok
                        }
                        
                        all_data.append(row)
                    
                    print(f"   -> Toplam {len(all_data)} ürün toplandı... (Son paket: {batch_size})")
                    
                    # Sonraki sayfa için sayacı artır
                    data_count += batch_size
                    
                    # Eryaz sisteminde 24'ten az geliyorsa son sayfadır
                    if batch_size < 24:
                        print("   -> Liste sonuna ulaşıldı.")
                        is_finished = True
                        
                except json.JSONDecodeError:
                    print("⚠️ HATA: JSON çözülemedi (Cookie bitmiş olabilir).")
                    is_finished = True
            else:
                print(f"❌ Sunucu Hatası: {response.status_code}")
                is_finished = True

        except Exception as e:
            print(f"❌ Bağlantı hatası: {e}")
            is_finished = True
        
        # IP ban yememek için bekleme
        time.sleep(0.2)

    # CSV KAYDETME
    if all_data:
        df = pd.DataFrame(all_data)
        csv_name = 'filtron_data.csv'
        
        # Türkçe karakter sorunu olmaması için 'utf-8-sig' ve ayırıcı olarak ';' kullanıyoruz
        df.to_csv(csv_name, index=False, sep=';', encoding='utf-8-sig')
        
        print(f"\n✅ BAŞARILI! Tüm veriler kaydedildi: {csv_name}")
        print(f"Toplam Satır: {len(df)}")
        print("Örnek Veri:")
        print(df.head())
    else:
        print("\n❌ Hiçbir veri çekilemedi.")

if __name__ == "__main__":
    main()
