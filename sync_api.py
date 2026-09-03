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
# ضمان وجود مسارات المشروع حتى لو شُغّل من venv أو cron
for p in [os.path.dirname(BASE_DIR), BASE_DIR, "/home/kali/Desktop", "/home/kali/Desktop/cashier"]:
    if p not in sys.path:
        sys.path.insert(0, p)

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
            body = json.dumps({"ok": True, "endpoints": ["/api/products", "/api/products?price_zero=1", "POST /api/products", "PATCH /api/products/<id>"]}, ensure_ascii=False).encode()
            self.send_response(200)
            _cors_headers(self)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
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
    print(f"  - افتح phone app عبر http://{local_ip}:8000  (python3 -m http.server 8000 في phone app)")
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
