#!/usr/bin/env python3
# prot/supabase_sync.py — مزامنة لحظية بين prot (SQLite) و Supabase (Postgres)
# يعمل ثنائي الاتجاه: يرفع المنتجات المحلية إلى Supabase، ويسحب التغييرات من Supabase
# الإعداد: prot/assets/supabase_config.json {url, key}
# أنشئ جدول في Supabase:
#   CREATE TABLE products (
#     id BIGINT PRIMARY KEY,
#     name TEXT NOT NULL,
#     barcode TEXT UNIQUE NOT NULL,
#     category TEXT DEFAULT 'عام',
#     price REAL DEFAULT 0,
#     stock INTEGER DEFAULT 0,
#     description TEXT DEFAULT '',
#     image_path TEXT DEFAULT '',
#     barcode_path TEXT DEFAULT '',
#     created_at TEXT,
#     updated_at TEXT
#   );
#   -- فعّل Realtime: Database → Realtime → Enable for products

import json
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "assets", "supabase_config.json")
TABLE = "products"

DEFAULT_CONFIG = {"url": "", "key": ""}

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return {"url": str(d.get("url","")).strip().rstrip("/"), "key": str(d.get("key","")).strip()}
    except Exception:
        return dict(DEFAULT_CONFIG)

def save_config(url, key):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    data = {"url": str(url or "").strip().rstrip("/"), "key": str(key or "").strip()}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

def is_configured():
    cfg = load_config()
    return bool(cfg.get("url") and cfg.get("key"))

def _headers():
    cfg = load_config()
    if not cfg["url"] or not cfg["key"]:
        raise RuntimeError("Supabase غير مهيأ — أدخل URL و anon key من الإعدادات")
    return {
        "apikey": cfg["key"],
        "Authorization": f"Bearer {cfg['key']}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def get_products():
    import urllib.request, urllib.error
    cfg = load_config()
    if not cfg["url"] or not cfg["key"]:
        raise RuntimeError("Supabase غير مهيأ")
    url = f"{cfg['url']}/rest/v1/{TABLE}?select=*&order=id.desc"
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())
        return data if isinstance(data, list) else []

def push_product(prod, method="POST"):
    """يرفع منتج واحد إلى Supabase — يستخدم upsert بالـ barcode لمنع التكرار والرجوع"""
    import urllib.request
    cfg = load_config()
    if not cfg["url"]:
        return None
    # upsert بالـ barcode هو الأساس — يمنع تضارب id ويضمن عدم الرجوع
    if "barcode" in prod and prod.get("barcode"):
        try:
            headers = {**_headers(), "Prefer": "resolution=merge-duplicates,return=representation"}
            url = f"{cfg['url']}/rest/v1/{TABLE}?on_conflict=barcode"
            body = json.dumps(prod, ensure_ascii=False).encode()
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode())
                return data[0] if data else None
        except Exception as e:
            # لو فشل الـ upsert، جرب PATCH كـ fallback
            pass
    headers = _headers()
    if method == "PATCH" and "id" in prod:
        pid = prod["id"]
        url = f"{cfg['url']}/rest/v1/{TABLE}?id=eq.{pid}"
        body = json.dumps({k:v for k,v in prod.items() if k!="id"}, ensure_ascii=False).encode()
        req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
    else:
        url = f"{cfg['url']}/rest/v1/{TABLE}"
        body = json.dumps(prod, ensure_ascii=False).encode()
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            return data[0] if data else None
    except Exception as e:
        if "duplicate" in str(e).lower() or "409" in str(e):
            try:
                # جرب PATCH بالـ barcode بدل id
                if prod.get("barcode"):
                    url2 = f"{cfg['url']}/rest/v1/{TABLE}?barcode=eq.{prod['barcode']}"
                    prod2 = {k:v for k,v in prod.items() if k not in ("id",)}
                    req2 = urllib.request.Request(url2, data=json.dumps(prod2, ensure_ascii=False).encode(), headers=headers, method="PATCH")
                    with urllib.request.urlopen(req2, timeout=10) as r2:
                        data2 = json.loads(r2.read().decode())
                        return data2[0] if data2 else None
                # fallback بالـ id
                prod2 = {k:v for k,v in prod.items() if k!="id"}
                url2 = f"{cfg['url']}/rest/v1/{TABLE}?id=eq.{prod['id']}"
                req2 = urllib.request.Request(url2, data=json.dumps(prod2, ensure_ascii=False).encode(), headers=headers, method="PATCH")
                with urllib.request.urlopen(req2, timeout=10) as r2:
                    data2 = json.loads(r2.read().decode())
                    return data2[0] if data2 else None
            except Exception:
                pass
        raise

def upsert_products(products):
    """يرفع قائمة كاملة (upsert) — يحاول رفع كل منتج"""
    ok = 0
    for p in products:
        try:
            push_product(p, method="POST")
            ok += 1
        except Exception:
            try:
                # جرب PATCH
                pid = p.get("id")
                if pid:
                    patch = {k:v for k,v in p.items() if k not in ("id","created_at")}
                    push_product({"id": pid, **patch}, method="PATCH")
                    ok += 1
            except Exception:
                pass
    return ok

def delete_product_supabase(pid):
    import urllib.request
    cfg = load_config()
    if not cfg["url"]:
        return False
    url = f"{cfg['url']}/rest/v1/{TABLE}?id=eq.{pid}"
    req = urllib.request.Request(url, headers=_headers(), method="DELETE")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status in (200, 204)

def test_connection():
    try:
        data = get_products()
        return True, f"✓ متصل — {len(data)} منتج"
    except Exception as e:
        return False, f"✗ فشل: {e}"

if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser(description="مزامنة Supabase للمنتجات")
    ap.add_argument("--test", action="store_true", help="اختبار الاتصال")
    ap.add_argument("--pull", action="store_true", help="سحب المنتجات من Supabase")
    ap.add_argument("--push", action="store_true", help="رفع المنتجات المحلية إلى Supabase")
    ap.add_argument("--config", nargs=2, metavar=("URL","KEY"), help="حفظ إعدادات Supabase")
    args = ap.parse_args()
    if args.config:
        save_config(args.config[0], args.config[1])
        print(f"✓ تم حفظ إعدادات Supabase: {args.config[0]}")
        ok, msg = test_connection()
        print(msg)
        sys.exit(0 if ok else 1)
    if args.test:
        ok, msg = test_connection()
        print(msg)
        sys.exit(0 if ok else 1)
    if args.pull:
        data = get_products()
        print(f"products: {len(data)}")
        print(json.dumps(data[:1], ensure_ascii=False, indent=2) if data else "[]")
    if args.push:
        from db.database import get_all_products
        rows = get_all_products()
        ok = upsert_products(rows)
        print(f"push: {ok}/{len(rows)}")
