import sqlite3
import os
import random
from datetime import datetime

from prot.config import DB_PATH, ADMIN_USERNAME, ADMIN_PASSWORD, EMPLOYEE_USERNAME, EMPLOYEE_PASSWORD


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 3000")
    except Exception:
        pass
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # جدول المستخدمين الخاص بـ prot (منفصل تماماً)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            barcode TEXT UNIQUE NOT NULL,
            category TEXT DEFAULT 'عام',
            price REAL DEFAULT 0,
            stock INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            image_path TEXT DEFAULT '',
            barcode_path TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # فهرس للبحث السريع
    cur.execute("CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)")

    # جدول المبيعات
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            barcode TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            total REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sale_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total REAL NOT NULL,
            items_count INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # جدول الإعدادات (للتحكم في تخزين المبيعات وغيرها)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    # إعداد افتراضي: تخزين المبيعات مفعل + طباعة الفاتورة مفعلة + حجم خط السلة 1.0
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("sales_enabled", "1"))
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("invoice_enabled", "1"))
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("user_invoice_enabled", "1"))
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("cart_font_scale", "1.0"))

    # إنشاء المستخدم الافتراضي لـ prot لو غير موجود
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO users (name, username, password, role) VALUES (?, ?, ?, ?)",
                    ("admin", ADMIN_USERNAME, ADMIN_PASSWORD, "admin"))
        # مستخدم عادي اختياري
        try:
            cur.execute("INSERT INTO users (name, username, password, role) VALUES (?, ?, ?, ?)",
                        ("user", EMPLOYEE_USERNAME, EMPLOYEE_PASSWORD, "employee"))
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()


def get_setting(key, default=None):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        conn.close()
        if row:
            return row["value"]
        return default
    except Exception:
        return default


def set_setting(key, value):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


def is_sales_enabled():
    """هل تخزين المبيعات مفعل؟ (قائمة المبيعات)"""
    v = get_setting("sales_enabled", "1")
    return str(v) not in ("0", "false", "False", "no", "off")


def set_sales_enabled(enabled: bool):
    set_setting("sales_enabled", "1" if enabled else "0")


def is_invoice_enabled():
    """هل طباعة الفاتورة بعد الدفع مفعلة؟ (عام)"""
    v = get_setting("invoice_enabled", "1")
    return str(v) not in ("0", "false", "False", "no", "off")


def set_invoice_enabled(enabled: bool):
    set_setting("invoice_enabled", "1" if enabled else "0")


def is_user_invoice_enabled():
    """هل يُسمح للمستخدم العادي بطباعة الفاتورة؟"""
    v = get_setting("user_invoice_enabled", "1")
    return str(v) not in ("0", "false", "False", "no", "off")


def set_user_invoice_enabled(enabled: bool):
    set_setting("user_invoice_enabled", "1" if enabled else "0")


def get_cart_font_scale(default=1.0):
    try:
        v = get_setting("cart_font_scale", str(default))
        f = float(v)
        # clamp 1.0 - 5.0
        if f < 1.0:
            f = 1.0
        if f > 5.0:
            f = 5.0
        return f
    except Exception:
        return float(default)


def set_cart_font_scale(scale):
    try:
        f = float(scale)
        if f < 1.0:
            f = 1.0
        if f > 5.0:
            f = 5.0
        # round to 1 decimal for cleanliness
        f = round(f, 1)
        set_setting("cart_font_scale", str(f))
        return f
    except Exception:
        return None


def add_sale(product_id, product_name, barcode, price, quantity):
    conn = get_connection()
    cur = conn.cursor()
    total = float(price) * int(quantity)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT INTO sales (product_id, product_name, barcode, price, quantity, total, created_at) VALUES (?,?,?,?,?,?,?)",
                (product_id, product_name, barcode, float(price), int(quantity), total, now))
    # خصم المخزون
    cur.execute("UPDATE products SET stock = stock - ?, updated_at=? WHERE id=?", (int(quantity), now, product_id))
    conn.commit()
    conn.close()
    return total


def create_sale_group(total, items_count):
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT INTO sale_groups (total, items_count, created_at) VALUES (?,?,?)", (float(total), int(items_count), now))
    conn.commit()
    gid = cur.lastrowid
    conn.close()
    return gid


def authenticate(username, password):
    # مصادقة منفصلة خاصة بـ prot — تحقق من DB أولاً ثم من config كـ fallback
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, username, password, role FROM users WHERE username=? AND password=?", (username, password))
        row = cur.fetchone()
        conn.close()
        if row:
            return {"id": row["id"], "name": row["name"], "username": row["username"], "password": row["password"], "role": row["role"]}
    except Exception:
        pass
    # fallback: تحقق من config (للسماح بتغيير الباسوورد من الملف مباشرة)
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        return {"id": 1, "name": "admin", "username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "role": "admin"}
    if username == EMPLOYEE_USERNAME and password == EMPLOYEE_PASSWORD:
        return {"id": 2, "name": "user", "username": EMPLOYEE_USERNAME, "password": EMPLOYEE_PASSWORD, "role": "employee"}
    return None


def reset_admin(username, password):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET username=?, password=? WHERE role='admin'", (username, password))
    conn.commit()
    conn.close()


def generate_barcode_value(prefix="880"):
    """توليد باركود رقمي فريد 12-13 رقم (EAN13 style) مع prefix"""
    # 12 رقم ثم حساب رقم التحقق EAN13
    base = prefix + "".join(str(random.randint(0, 9)) for _ in range(9))
    base = base[:12]  # 12 رقم
    # حساب EAN13 checksum
    total = 0
    for i, ch in enumerate(base):
        digit = int(ch)
        total += digit * (3 if i % 2 == 1 else 1)
    check = (10 - (total % 10)) % 10
    return base + str(check)


def get_unique_barcode():
    conn = get_connection()
    cur = conn.cursor()
    for _ in range(20):
        code = generate_barcode_value()
        cur.execute("SELECT 1 FROM products WHERE barcode=?", (code,))
        if not cur.fetchone():
            conn.close()
            return code
    conn.close()
    # fallback
    return datetime.now().strftime("%Y%m%d%H%M%S") + str(random.randint(10, 99))


def add_product(name, category="عام", price=0, stock=0, description="", barcode=None, image_path="", barcode_path=""):
    if not barcode:
        barcode = get_unique_barcode()
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cur.execute("""
            INSERT INTO products (name, barcode, category, price, stock, description, image_path, barcode_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, barcode, category, float(price), int(stock), description, image_path, barcode_path, now, now))
        conn.commit()
        pid = cur.lastrowid
        conn.close()
        return pid, barcode
    except sqlite3.IntegrityError as e:
        conn.close()
        raise ValueError(f"الباركود موجود مسبقاً: {barcode}") from e


def get_all_products(search="", category=""):
    conn = get_connection()
    cur = conn.cursor()
    q = "SELECT * FROM products WHERE 1=1"
    params = []
    if search:
        if search.isdigit():
            # إذا البحث رقمي: ابحث بالاسم/الباركود/الوصف (LIKE) أو بالـ id مطابق تماماً
            q += " AND (name LIKE ? OR barcode LIKE ? OR description LIKE ? OR CAST(id AS TEXT) = ?)"
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%", search])
        else:
            q += " AND (name LIKE ? OR barcode LIKE ? OR description LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if category and category != "الكل":
        q += " AND category = ?"
        params.append(category)
    q += " ORDER BY created_at DESC"
    cur.execute(q, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_product_by_id(pid):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id=?", (pid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_product_by_barcode(barcode):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE barcode=?", (barcode,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_product(pid, name=None, category=None, price=None, stock=None, description=None, barcode=None, image_path=None, barcode_path=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id=?", (pid,))
    if not cur.fetchone():
        conn.close()
        return False
    fields = []
    params = []
    if name is not None:
        fields.append("name=?"); params.append(name)
    if category is not None:
        fields.append("category=?"); params.append(category)
    if price is not None:
        fields.append("price=?"); params.append(float(price))
    if stock is not None:
        fields.append("stock=?"); params.append(int(stock))
    if description is not None:
        fields.append("description=?"); params.append(description)
    if barcode is not None:
        fields.append("barcode=?"); params.append(barcode)
    if image_path is not None:
        fields.append("image_path=?"); params.append(image_path)
    if barcode_path is not None:
        fields.append("barcode_path=?"); params.append(barcode_path)
    if not fields:
        conn.close()
        return True
    fields.append("updated_at=?")
    params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    params.append(pid)
    try:
        cur.execute(f"UPDATE products SET {', '.join(fields)} WHERE id=?", params)
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def delete_product(pid):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # احذف المبيعات المرتبطة أولاً لتجنب قيد المفتاح الخارجي (للتوافق مع قواعد قديمة بدون CASCADE)
        cur.execute("DELETE FROM sales WHERE product_id=?", (pid,))
        cur.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
        ok = cur.rowcount > 0
    except sqlite3.IntegrityError as e:
        conn.rollback()
        ok = False
    except Exception:
        conn.rollback()
        ok = False
    finally:
        conn.close()
    return ok


def count_products():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM products")
    n = cur.fetchone()[0]
    conn.close()
    return n


# ---------- المبيعات (قائمة المبيعات) ----------

def get_all_sales(limit=200, search=""):
    """جلب قائمة المبيعات (sales) مرتبة بالأحدث"""
    conn = get_connection()
    cur = conn.cursor()
    q = "SELECT * FROM sales WHERE 1=1"
    params = []
    if search:
        q += " AND (product_name LIKE ? OR barcode LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    q += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(int(limit))
    cur.execute(q, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_sales_count():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sales")
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_sale_groups(limit=100):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sale_groups ORDER BY created_at DESC, id DESC LIMIT ?", (int(limit),))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def clear_all_sales():
    """حذف كل المبيعات (يستخدمه الأدمن)"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sales")
    cur.execute("DELETE FROM sale_groups")
    conn.commit()
    conn.close()
