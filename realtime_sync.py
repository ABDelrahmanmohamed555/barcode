#!/usr/bin/env python3
# prot/realtime_sync.py — خدمة مزامنة لحظية ثنائية الاتجاه
# تعمل في الخلفية داخل prot/main.py (ثريد منفصل)
# تزامن بين: SQLite (المحلي) <-> Supabase (السحابي) <-> GitHub (احتياطي)
# المنطق:
#  - كل 3 ثواني: اسحب من Supabase/GitHub، ادمج في DB المحلي
#  - عند أي تغيير محلي (add/update/delete): ارفع فوراً إلى Supabase و GitHub

import os
import sys
import time
import json
import threading
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.dirname(BASE_DIR))

try:
    from prot.db.database import get_all_products, get_product_by_id, get_product_by_barcode, add_product, update_product, delete_product, upsert_product_from_remote
except ImportError:
    import importlib.util
    spec = importlib.util.spec_from_file_location("db.database", os.path.join(BASE_DIR, "db", "database.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    get_all_products = mod.get_all_products
    get_product_by_id = mod.get_product_by_id
    get_product_by_barcode = mod.get_product_by_barcode
    add_product = mod.add_product
    update_product = mod.update_product
    delete_product = mod.delete_product
    upsert_product_from_remote = getattr(mod, 'upsert_product_from_remote', None)

# حالة الخدمة
_running = False
_thread = None
_last_pull = []
_last_push_hash = None

def _hash_products(products):
    import hashlib
    s = json.dumps(sorted(products, key=lambda x: x.get("id",0)), ensure_ascii=False, sort_keys=True)
    return hashlib.md5(s.encode()).hexdigest()

def _merge_remote_to_local(remote_products):
    """دمج المنتجات القادمة من Supabase/GitHub إلى DB المحلي"""
    if not remote_products:
        return 0
    # فهرس محلي بالباركود والـ id
    local_all = get_all_products()
    by_barcode = {p["barcode"]: p for p in local_all}
    by_id = {p["id"]: p for p in local_all}
    merged = 0
    for rp in remote_products:
        # تطبيع
        try:
            name = (rp.get("name") or "").strip()
            if not name:
                continue
            barcode = (rp.get("barcode") or "").strip()
            if not barcode:
                continue
            category = (rp.get("category") or "عام").strip() or "عام"
            price = float(rp.get("price", 0) or 0)
            stock = int(float(rp.get("stock", 0) or 0))
            desc = (rp.get("description") or rp.get("desc") or "").strip()
            rid = int(rp.get("id")) if rp.get("id") else None
            # ابحث محلياً
            local = by_barcode.get(barcode) or (by_id.get(rid) if rid else None)
            if not local:
                # منتج جديد من السحابة — استخدم upsert مع الحفاظ على id
                try:
                    if upsert_product_from_remote:
                        ok = upsert_product_from_remote(rp)
                        if ok: merged += 1
                    else:
                        add_product(name, category, price, stock, desc, barcode)
                        merged += 1
                except Exception as e:
                    # لو باركود مكرر بسبب سباق، جرب تحديث
                    if "موجود" in str(e) or "UNIQUE" in str(e):
                        existing = get_product_by_barcode(barcode)
                        if existing:
                            upd = {}
                            if existing["name"] != name: upd["name"]=name
                            if float(existing["price"]) != price: upd["price"]=price
                            if int(existing["stock"]) != stock: upd["stock"]=stock
                            if existing["category"] != category: upd["category"]=category
                            if upd:
                                update_product(existing["id"], **upd)
                                merged += 1
            else:
                # موجود -> قارن updated_at — لو المحلي أحدث احتفظ به ولا ترجع لقديم
                r_updated = rp.get("updated_at") or rp.get("created_at") or ""
                l_updated = local.get("updated_at") or local.get("created_at") or ""
                # لو المحلي أحدث من السحابي — تجاهل السحابي القديم (يمنع الرجوع بعد حفظ)
                if l_updated and r_updated and l_updated > r_updated:
                    continue
                need = False
                if r_updated and l_updated and r_updated > l_updated:
                    need = True
                elif r_updated == l_updated and (price != float(local["price"]) or stock != int(local["stock"]) or name != local["name"] or category != local["category"]):
                    need = True
                elif not r_updated or not l_updated:
                    if price != float(local["price"]) or stock != int(local["stock"]) or name != local["name"]:
                        need = True
                if need:
                    upd = {}
                    if name != local["name"]: upd["name"]=name
                    if category != local["category"]: upd["category"]=category
                    if price != float(local["price"]): upd["price"]=price
                    if stock != int(local["stock"]): upd["stock"]=stock
                    if desc != (local.get("description") or ""): upd["description"]=desc
                    if upd:
                        update_product(local["id"], **upd)
                        merged += 1
        except Exception as e:
            # تجاهل منتج واحد فاسد
            continue
    return merged

def _pull_once():
    """سحب واحد من السحابة ودمجه"""
    merged_total = 0
    # 1) Supabase أولاً
    try:
        import prot.supabase_sync as supa
        if supa.is_configured():
            try:
                remote = supa.get_products()
                if remote:
                    m = _merge_remote_to_local(remote)
                    if m>0:
                        print(f"[Realtime] Supabase pull: {m} منتج مدمج")
                    merged_total += m
                    return merged_total  # لو Supabase نجح، لا حاجة لـ GitHub
            except Exception as e:
                print(f"[Realtime] Supabase pull fail: {e}")
    except ImportError:
        # fallback مباشر
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("supabase_sync", os.path.join(BASE_DIR, "supabase_sync.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if mod.is_configured():
                remote = mod.get_products()
                if remote:
                    m = _merge_remote_to_local(remote)
                    if m>0:
                        print(f"[Realtime] Supabase pull: {m}")
                    return m
        except Exception:
            pass
    # 2) GitHub fallback (للقراءة بدون سيرفر)
    try:
        import prot.github_sync as gh
        # استخدم get_products_from_github حتى بدون token (يقرأ raw)
        try:
            token = gh.get_token()
        except Exception:
            token = None
        data, sha = gh.get_products_from_github(token)
        if data and isinstance(data, list):
            m = _merge_remote_to_local(data)
            if m>0:
                print(f"[Realtime] GitHub pull: {m} منتج مدمج")
            merged_total += m
    except Exception as e:
        # github_sync قد لا يكون موجوداً
        pass
    return merged_total

def _push_once(local_products):
    """رفع محلي إلى السحابة"""
    # Supabase
    try:
        import prot.supabase_sync as supa
        if supa.is_configured():
            # upsert كل المنتجات
            try:
                # جرب رفع الفرق فقط
                cnt = supa.upsert_products(local_products)
                if cnt>0:
                    print(f"[Realtime] Supabase push: {cnt}")
            except Exception as e:
                print(f"[Realtime] Supabase push fail: {e}")
    except Exception:
        pass
    # GitHub
    try:
        import prot.github_sync as gh
        token = gh.get_token()
        if token:
            ok, msg = gh.push_products_to_github(local_products, message="auto sync products realtime")
            if ok:
                print(f"[Realtime] GitHub push ✓ {msg[:7] if msg else ''}")
            else:
                if "no token" not in str(msg):
                    print(f"[Realtime] GitHub push fail: {msg}")
    except Exception as e:
        print(f"[Realtime] GitHub push err: {e}")

def sync_loop(interval=3):
    global _running
    print(f"[Realtime] بدء خدمة المزامنة اللحظية كل {interval}s")
    while _running:
        try:
            _pull_once()
        except Exception as e:
            print(f"[Realtime] loop pull err: {e}")
        # ادخر push للاستدعاء من _notify_local_change لتقليل الحمل
        time.sleep(interval)

def start(interval=3):
    global _running, _thread
    if _running:
        return
    _running = True
    _thread = threading.Thread(target=sync_loop, args=(interval,), daemon=True, name="realtime_sync")
    _thread.start()
    return _thread

def stop():
    global _running
    _running = False

def notify_local_change():
    """يُستدعى بعد أي add/update/delete محلي لرفع فوري — يسحب أولاً لتجنب الكتابة فوق تعديل أحدث من التليفون"""
    def _bg():
        try:
            time.sleep(0.6)  # انتظر كتابة DB
            # اسحب أولاً وادمج أي تعديل أحدث من السحابة قبل الرفع
            try:
                _pull_once()
            except Exception:
                pass
            time.sleep(0.2)
            rows = get_all_products()
            # تجنب الرفع المكرر لنفس البيانات
            global _last_push_hash
            h = _hash_products(rows)
            if h == _last_push_hash:
                return
            _last_push_hash = h
            _push_once(rows)
            # أيضاً اكتب لـ phone app/products.json
            try:
                import json, os
                for cand in [os.path.join(os.path.dirname(BASE_DIR), "phone app", "products.json"),
                             "/home/kali/Desktop/phone app/products.json"]:
                    try:
                        os.makedirs(os.path.dirname(cand), exist_ok=True)
                        with open(cand, "w", encoding="utf-8") as f:
                            json.dump(rows, f, ensure_ascii=False, indent=2)
                        break
                    except Exception:
                        continue
            except Exception:
                pass
        except Exception as e:
            print(f"[Realtime] notify err: {e}")
    threading.Thread(target=_bg, daemon=True).start()

def force_push():
    """دفع فوري للتجربة"""
    rows = get_all_products()
    _push_once(rows)
    return len(rows)

def force_pull():
    return _pull_once()

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="خدمة المزامنة اللحظية")
    ap.add_argument("--push", action="store_true", help="رفع فوري")
    ap.add_argument("--pull", action="store_true", help="سحب فوري")
    ap.add_argument("--loop", action="store_true", help="حلقة مستمرة")
    args = ap.parse_args()
    if args.push:
        n = force_push()
        print(f"pushed {n}")
    if args.pull:
        n = force_pull()
        print(f"pulled merged {n}")
    if args.loop:
        start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop()
