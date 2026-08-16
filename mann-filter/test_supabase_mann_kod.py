#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Supabase IKILER_MANN canlı kod/SKU teşhis aracı.

Kullanım (Git Bash):
  SUPABASE_SECRET_KEY='sb_secret_...' python test_supabase_mann_kod.py 1005619501

Secret kesinlikle bu dosyaya yazılmaz. SUPABASE_SECRET_KEY ortam değişkeninden okunur.
Bu araç yalnızca SELECT yapar; Supabase'e yazmaz.
"""

import argparse
import os
import sys
from typing import Any

import requests


SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://lrjphkajdkipwjizzxsc.supabase.co",
).rstrip("/")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "IKILER_MANN")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY", "")


COLUMNS = (
    "sku,kod,marka,kategori,fiyat,depo_merkezi,toplam_stok,"
    "mann_url,img_url_1,img_url_2,img_url_3,guncelleme_tarihi"
)


def fetch(params: dict[str, str]) -> tuple[int, Any]:
    if not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_SECRET_KEY veya SUPABASE_KEY ortam değişkeni eksik. "
            "Secret'i dosyaya yazmayın."
        )
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
        params=params,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
        timeout=30,
    )
    try:
        body = response.json()
    except ValueError:
        body = response.text[:500]
    return response.status_code, body


def show(label: str, rows: Any) -> None:
    print(f"\n[{label}]")
    if isinstance(rows, list) and rows:
        for row in rows:
            print(row)
    elif isinstance(rows, list):
        print("Kayıt yok")
    else:
        print(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="IKILER_MANN SKU/kod SELECT testi")
    parser.add_argument("code", nargs="?", default="1005619501")
    args = parser.parse_args()

    code = args.code.strip()
    if not code:
        print("Kod boş olamaz", file=sys.stderr)
        return 2

    common = {"select": COLUMNS, "limit": "20"}
    for label, field in (("SKU", "sku"), ("KOD", "kod")):
        status, body = fetch({**common, field: f"eq.{code}"})
        print(f"{label} STATUS={status}")
        if status != 200:
            print(body, file=sys.stderr)
            return 1
        show(label, body)

    print("\n[TEŞHİS]")
    print("02_ikiler_mann_filter_img_url_cekme.py katalog aramasına Supabase 'kod' alanını gönderir.")
    print(f"Bu testte gönderilecek katalog değeri: {code}")
    print("Bu araç SELECT-only'dir; Supabase'e INSERT/UPDATE/PATCH yapmaz.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
