create table if not exists public."IKILER_FILTRON" (
    sku text primary key,
    kod text,
    marka text not null default 'FILTRON',
    kategori text,
    fiyat numeric(12,2),
    depo_merkezi text,
    toplam_stok integer not null default 0,
    mann_url text,
    img_url_1 text,
    img_url_2 text,
    img_url_3 text,
    guncelleme_tarihi timestamptz
);

create index if not exists ikiler_filtron_marka_idx
    on public."IKILER_FILTRON" (marka);

create index if not exists ikiler_filtron_stok_idx
    on public."IKILER_FILTRON" (toplam_stok);
