#!/usr/bin/env python3
# prot/sync_api.py — مزامنة phone app <-> قاعدة بيانات prot (SQLite) عبر HTTP JSON
# يعمل على نفس الشبكة: شغل `python sync_api.py` ثم افتح phone app على http://DESKTOP_IP:5000
# phone app يطلب /api/products ويُحدّث الأسعار عبر PATCH

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PHONE_DIR = os.path.join(os.path.dirname(BASE_DIR), "phone app")
PHONE_JSON = os.path.join(PHONE_DIR, "products.json")
PHONE_VERSION_JSON = os.path.join(PHONE_DIR, "version.json")
# ضمان وجود مسارات المشروع حتى لو شُغّل من venv أو cron
for p in [os.path.dirname(BASE_DIR), BASE_DIR, "/home/kali/Desktop", "/home/kali/Desktop/cashier"]:
    if p not in sys.path:
        sys.path.insert(0, p)

def _export_local():
    # مزامنة محلية للبرمجة: يكتب DB إلى phone app/products.json (يعمل حتى بدون شبكة)
    try:
        rows = get_all_products()
        os.makedirs(os.path.dirname(PHONE_JSON), exist_ok=True)
        with open(PHONE_JSON, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

try:
    from prot.db.database import get_all_products, get_product_by_id, add_product, update_product
except ModuleNotFoundError:
    # fallback لو prot غير موجود كـ package (تشغيل من داخل prot)
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("prot.db.database", os.path.join(BASE_DIR, "db", "database.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    get_all_products = mod.get_all_products
    get_product_by_id = mod.get_product_by_id
    add_product = mod.add_product
    update_product = mod.update_product

HOST = "0.0.0.0"
PORT = 5000

def _cors_headers(handler):
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Max-Age", "86400")

def _mime_for(path):
    if path.endswith(".html"): return "text/html; charset=utf-8"
    if path.endswith(".js"): return "text/javascript; charset=utf-8"
    if path.endswith(".css"): return "text/css; charset=utf-8"
    if path.endswith(".json"): return "application/json; charset=utf-8"
    if path.endswith(".png"): return "image/png"
    if path.endswith(".jpg") or path.endswith(".jpeg"): return "image/jpeg"
    if path.endswith(".zip"): return "application/zip"
    if path.endswith(".apk"): return "application/vnd.android.package-archive"
    return "application/octet-stream"

def _serve_static(handler, filepath):
    if not os.path.isfile(filepath):
        handler._err("not found", 404)
        return True
    try:
        # منع directory traversal
        real_phone = os.path.realpath(PHONE_DIR)
        real_file = os.path.realpath(filepath)
        if not real_file.startswith(real_phone):
            handler._err("forbidden", 403)
            return True
        with open(filepath, "rb") as f:
            data = f.read()
        handler.send_response(200)
        _cors_headers(handler)
        handler.send_header("Content-Type", _mime_for(filepath))
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        handler.end_headers()
        handler.wfile.write(data)
        return True
    except Exception as e:
        handler._err(str(e), 500)
        return True

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stdout.write(f"[{self.client_address[0]}] {format%args}\n")

    def do_OPTIONS(self):
        self.send_response(204)
        _cors_headers(self)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/api/products":
            # ?price_zero=1 للمنتجات سعر 0 فقط (لتسعير)
            try:
                if qs.get("price_zero", ["0"])[0] in ("1","true","True"):
                    rows = [r for r in get_all_products() if not r["price"] or float(r["price"])==0]
                else:
                    rows = get_all_products()
                body = json.dumps(rows, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                _cors_headers(self)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self._err(str(e))
            return

        if path.startswith("/api/products/"):
            try:
                pid = int(path.split("/")[-1])
                prod = get_product_by_id(pid)
                if not prod:
                    self._err("غير موجود", 404)
                    return
                body = json.dumps(prod, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                _cors_headers(self)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self._err(str(e))
            return

        if path in ("/", "/api", "/api/"):
            body = json.dumps({"ok": True, "endpoints": ["/api/products", "/api/products?price_zero=1", "POST /api/products", "PATCH /api/products/<id>", "/api/app_version", "/version.json", "/app/<file>", "/api/bundle"]}, ensure_ascii=False).encode()
            self.send_response(200)
            _cors_headers(self)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return

        # --- OTA: نسخة التطبيق ---
        if path in ("/api/app_version", "/version.json"):
            fp = PHONE_VERSION_JSON
            if not os.path.exists(fp):
                # fallback بسيط
                body = json.dumps({"version":"1.0.0","build":1,"files":{}}, ensure_ascii=False).encode()
                self.send_response(200)
                _cors_headers(self)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            return _serve_static(self, fp)

        # --- OTA: ملفات التطبيق الثابتة /app/* و /updates/* ---
        if path.startswith("/app/") or path.startswith("/updates/"):
            # /app/app.js -> phone app/app.js
            rel = path.split("/", 2)[-1] if "/" in path[1:] else ""
            # منع .. 
            rel = rel.replace("..", "").lstrip("/")
            if not rel:
                rel = "index.html"
            fp = os.path.join(PHONE_DIR, rel)
            return _serve_static(self, fp)

        # خدمة مباشرة للملفات الجذرية (للتسهيل): /index.html /app.js /style.css /updater.js /version.json
        if path in ("/index.html","/app.js","/style.css","/updater.js","/manifest.json","/icon.png","/products.json"):
            fp = os.path.join(PHONE_DIR, path.lstrip("/"))
            return _serve_static(self, fp)

        # --- OTA: حزمة zip كاملة ---
        if path == "/api/bundle":
            # أنشئ zip مؤقت يحتوي phone app/www الملفات
            import tempfile, zipfile, io
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for fname in ["index.html","app.js","style.css","manifest.json","version.json","updater.js","icon.png"]:
                    fp = os.path.join(PHONE_DIR, fname)
                    if os.path.exists(fp):
                        z.write(fp, fname)
            data = buf.getvalue()
            self.send_response(200)
            _cors_headers(self)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", "attachment; filename=phone_app_update.zip")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self._err("not found", 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/products":
            self._err("not found", 404)
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except:
            data = {}
        # يسمح حتى لو price 0
        name = (data.get("name") or "").strip()
        if not name:
            self._err("name مطلوب", 400)
            return
        try:
            price = float(data.get("price", 0) or 0)
            stock = int(float(data.get("stock", 0) or 0))
            barcode = (data.get("barcode") or "").strip() or None
            category = (data.get("category") or "عام").strip() or "عام"
            desc = (data.get("description") or "").strip()
            pid, code = add_product(name, category, price, stock, desc, barcode)
            prod = get_product_by_id(pid)
            _export_local()
            body = json.dumps(prod, ensure_ascii=False).encode()
            self.send_response(201)
            _cors_headers(self)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self._err(str(e), 400)

    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith("/api/products/"):
            self._err("not found", 404)
            return
        try:
            pid = int(parsed.path.split("/")[-1])
        except:
            self._err("id غير صحيح", 400)
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except:
            data = {}
        # يسمح بتحديث أي حقل حتى price 0
        try:
            # price/stock قد تكون 0 فيجب عدم تجاهلها
            kwargs = {}
            if "name" in data:
                kwargs["name"] = data["name"]
            if "category" in data:
                kwargs["category"] = data["category"]
            if "price" in data:
                kwargs["price"] = float(data["price"] or 0)
            if "stock" in data:
                kwargs["stock"] = int(float(data["stock"] or 0))
            if "description" in data:
                kwargs["description"] = data["description"]
            if "barcode" in data:
                kwargs["barcode"] = data["barcode"]
            ok = update_product(pid, **kwargs)
            if not ok:
                self._err("فشل التحديث (باركود مكرر؟)", 400)
                return
            prod = get_product_by_id(pid)
            _export_local()
            body = json.dumps(prod, ensure_ascii=False).encode()
            self.send_response(200)
            _cors_headers(self)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self._err(str(e), 400)

    def _err(self, msg, code=500):
        body = json.dumps({"error": msg}, ensure_ascii=False).encode()
        self.send_response(code)
        _cors_headers(self)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def run(host=HOST, port=PORT):
    # اطبع IP المحلي لتسهيل فتحه على الموبايل
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "127.0.0.1"
    print(f"✓ Prot Sync API يعمل على http://{local_ip}:{port}")
    print(f"  - GET  http://{local_ip}:{port}/api/products")
    print(f"  - GET  http://{local_ip}:{port}/api/products?price_zero=1")
    print(f"  - GET  http://{local_ip}:{port}/api/app_version  (للتحديث OTA)")
    print(f"  - GET  http://{local_ip}:{port}/app/index.html  (ملفات التطبيق)")
    print(f"  - GET  http://{local_ip}:{port}/api/bundle  (حزمة zip)")
    print(f"  - افتح phone app عبر http://{local_ip}:8000  (python3 -m http.server 8000 في phone app)")
    print(f"  - أو عبر http://{local_ip}:{port}/app/index.html مباشرة (بدون سيرفر ثاني)")
    print("  اضغط Ctrl+C للإيقاف")
    server = ThreadedHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nتم الإيقاف")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Prot Sync API")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    run(args.host, args.port)
