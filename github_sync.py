#!/usr/bin/env python3
# github_sync.py — مزامنة products.json عبر GitHub Contents API (حل جذري)
# يعمل حتى لو اللابتوب مطفي بالنسبة للقراءة، والكتابة تحتاج token
import base64, json, os, pathlib

REPO = "ABDelrahmanmohamed555/barcode_phoneapp"
PATH_IN_REPO = "products.json"
API_URL = f"https://api.github.com/repos/{REPO}/contents/{PATH_IN_REPO}"
RAW_URL = f"https://raw.githubusercontent.com/{REPO}/main/{PATH_IN_REPO}"

def get_token():
    # يبحث عن token في env أو ملف
    for k in ["GITHUB_TOKEN","GH_TOKEN","GITHUB_PAT"]:
        if os.environ.get(k):
            return os.environ[k].strip()
    # ملف محلي prot/assets/github_token.txt
    for p in [pathlib.Path(__file__).parent / "assets" / "github_token.txt",
              pathlib.Path.home() / ".github_token",
              pathlib.Path("/home/kali/.github_token")]:
        if p.exists():
            try:
                t = p.read_text().strip()
                if t:
                    return t
            except:
                pass
    return None

def get_products_from_github(token=None):
    import urllib.request, ssl
    headers = {"Accept":"application/vnd.github.v3+json", "User-Agent":"prot-sync"}
    if token:
        headers["Authorization"] = f"token {token}"
    # حاول API أولاً (أحدث)
    try:
        req = urllib.request.Request(API_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            j = json.loads(r.read().decode())
            # j['content'] is base64
            import base64
            content = base64.b64decode(j["content"]).decode("utf-8")
            data = json.loads(content)
            return data, j.get("sha")
    except Exception as e:
        pass
    # fallback Raw
    try:
        import urllib.request
        with urllib.request.urlopen(RAW_URL + f"?_t={__import__('time').time()}", timeout=10) as r:
            data = json.loads(r.read().decode())
            return data, None
    except Exception as e:
        return None, None

def push_products_to_github(products, message="auto sync products", token=None):
    token = token or get_token()
    if not token:
        return False, "no token"
    import urllib.request, json, base64
    # احصل على sha الحالي
    sha = None
    try:
        headers = {"Accept":"application/vnd.github.v3+json", "Authorization": f"token {token}", "User-Agent":"prot-sync"}
        req = urllib.request.Request(API_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            j = json.loads(r.read().decode())
            sha = j.get("sha")
    except Exception as e:
        # لو 404 يعني ملف جديد
        sha = None
    content = base64.b64encode(json.dumps(products, ensure_ascii=False, indent=2).encode()).decode()
    body = {"message": message, "content": content}
    if sha:
        body["sha"] = sha
    try:
        headers = {"Accept":"application/vnd.github.v3+json", "Authorization": f"token {token}", "User-Agent":"prot-sync", "Content-Type":"application/json"}
        data = json.dumps(body).encode()
        req = urllib.request.Request(API_URL, data=data, headers=headers, method="PUT")
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read().decode())
            return True, j.get("content",{}).get("sha","")
    except Exception as e:
        return False, str(e)

if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser(description="مزامنة GitHub للمنتجات")
    ap.add_argument("--push", action="store_true", help="رفع products.json المحلي إلى GitHub")
    ap.add_argument("--pull", action="store_true", help="جلب من GitHub")
    ap.add_argument("--token", help="GitHub token")
    args = ap.parse_args()
    if args.pull:
        data, sha = get_products_from_github(args.token or get_token())
        print(f"products: {len(data) if data else 0} sha:{sha[:7] if sha else 'none'}")
        if data:
            print(json.dumps(data[:1], ensure_ascii=False, indent=2))
    if args.push:
        # اقرأ products.json المحلي
        p = pathlib.Path(__file__).parent.parent / "phone app" / "products.json"
        if not p.exists():
            p = pathlib.Path("/home/kali/Desktop/phone app/products.json")
        data = json.loads(p.read_text(encoding="utf-8"))
        ok, msg = push_products_to_github(data, token=args.token or get_token())
        print(f"push: {ok} {msg}")
