import os
from PIL import Image, ImageDraw, ImageFont

from prot.config import BASE_DIR, BARCODES_DIR, FONTS_DIR

# محاولة استيراد python-barcode
try:
    import barcode
    from barcode.writer import ImageWriter
    HAS_BARCODE = True
except Exception:
    HAS_BARCODE = False


def _get_font(size=14, bold=False):
    try:
        path = os.path.join(FONTS_DIR, "Tajawal-Bold.ttf" if bold else "Tajawal-Regular.ttf")
        if not os.path.exists(path):
            path = os.path.join(FONTS_DIR, "Cairo.ttf")
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def generate_barcode_image(barcode_value, product_name="", out_path=None):
    """إنشاء صورة باركود Code128 مع اسم المنتج أسفله.
    يرجع مسار الصورة.
    """
    os.makedirs(BARCODES_DIR, exist_ok=True)
    if not out_path:
        # تنظيف القيمة للاسم
        safe = "".join(c if c.isalnum() else "_" for c in str(barcode_value))[:30]
        out_path = os.path.join(BARCODES_DIR, f"{safe}.png")

    # لو python-barcode متوفر استخدمه
    if HAS_BARCODE:
        try:
            writer = ImageWriter()
            # تخصيص الكتابة
            writer_options = {
                "module_width": 0.3,
                "module_height": 12,
                "font_size": 10,
                "text_distance": 4,
                "quiet_zone": 4,
                "background": "white",
                "foreground": "black",
            }
            code128 = barcode.get_barcode_class('code128')
            # code128 يتطلب نص ascii - الباركود رقمي فقط
            bar = code128(str(barcode_value), writer=writer)
            # حفظ مؤقت بدون امتداد لأن المكتبة تضيف .png
            tmp_base = out_path.replace(".png", "")
            saved = bar.save(tmp_base, options=writer_options)
            # saved هو المسار مع .png
            # الآن أضف اسم المنتج أسفل الصورة لو موجود
            if product_name:
                try:
                    img = Image.open(saved).convert("RGB")
                    font = _get_font(16, bold=True)
                    # حساب ارتفاع إضافي للنص
                    dummy = ImageDraw.Draw(img)
                    try:
                        bbox = dummy.textbbox((0, 0), product_name, font=font)
                        text_h = bbox[3] - bbox[1] + 16
                    except Exception:
                        text_h = 28
                    new_h = img.height + text_h
                    new_img = Image.new("RGB", (img.width, new_h), "white")
                    new_img.paste(img, (0, 0))
                    draw = ImageDraw.Draw(new_img)
                    # رسم الاسم في المنتصف
                    try:
                        # محاولة دعم عربي بسيط — يدعم داخل cashier أو sibling
                        disp = product_name
                        for _cand in ["utils", "cashier.utils"]:
                            try:
                                mod = __import__(_cand, fromlist=["reshape_arabic"])
                                disp = getattr(mod, "reshape_arabic")(product_name)
                                break
                            except Exception:
                                continue
                    except Exception:
                        disp = product_name
                    # حساب عرض النص
                    try:
                        bbox = draw.textbbox((0, 0), disp, font=font)
                        tw = bbox[2] - bbox[0]
                    except Exception:
                        tw = len(disp) * 8
                    x = (new_img.width - tw) // 2
                    y = img.height + 4
                    draw.text((x, y), disp, fill="black", font=font)
                    new_img.save(saved)
                except Exception:
                    pass
            return saved
        except Exception as e:
            print(f"barcode fallback due to: {e}")

    # Fallback: رسم باركود بسيط وهمي + qrcode لو متاح
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(str(barcode_value))
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        # أضف نص
        W, H = qr_img.size
        font = _get_font(14)
        extra = 40
        out = Image.new("RGB", (W, H + extra), "white")
        out.paste(qr_img, (0, 0))
        draw = ImageDraw.Draw(out)
        txt = f"{product_name} - {barcode_value}" if product_name else str(barcode_value)
        try:
            bbox = draw.textbbox((0, 0), txt, font=font)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(txt) * 7
        draw.text(((W - tw)//2, H + 8), txt, fill="black", font=font)
        out.save(out_path)
        return out_path
    except Exception:
        pass

    # أبسط fallback: صورة نصية فقط
    img = Image.new("RGB", (400, 180), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([2, 2, 398, 178], outline="black", width=2)
    font = _get_font(18, bold=True)
    font_small = _get_font(14)
    try:
        draw.text((20, 20), str(product_name)[:30], fill="black", font=font)
        draw.text((20, 70), str(barcode_value), fill="black", font=font_small)
        draw.text((20, 120), "BARCODE", fill="gray", font=font_small)
    except Exception:
        pass
    img.save(out_path)
    return out_path


def generate_barcode_for_product(product):
    """اختصار: product dict يحتوي barcode و name"""
    code = product.get("barcode") or product.get("id")
    name = product.get("name", "")
    return generate_barcode_image(str(code), name)


def open_barcode_image(path):
    try:
        return Image.open(path)
    except Exception:
        return None


def generate_product_sticker(product, copies=1):
    """إنشاء صورة ستيكر منتج متناسبة تماماً مع مقاس الستيكر في sticker_config.json
    تحتوي: اسم المنتج أعلى + باركود وسط + سعر أسفل. الحجم النهائي = مقاس الستيكر."""
    try:
        # حمّل مقاس الستيكر من الإعدادات الأساسية — يدعم داخل أو sibling
        import json
        MAIN_BASE = None
        for _cand in ["config", "cashier.config"]:
            try:
                mod = __import__(_cand, fromlist=["BASE_DIR"])
                MAIN_BASE = getattr(mod, "BASE_DIR")
                break
            except Exception:
                continue
        if MAIN_BASE is None:
            # fallback: حاول إيجاد cashier كـ sibling
            for _cand_path in [os.path.join(os.path.dirname(BASE_DIR), "cashier"), os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "cashier")]:
                if os.path.exists(os.path.join(_cand_path, "assets", "sticker_config.json")):
                    MAIN_BASE = _cand_path
                    break
        if MAIN_BASE is None:
            raise FileNotFoundError("sticker_config not found")
        cfg_path = os.path.join(MAIN_BASE, "assets", "sticker_config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        dpi = float(cfg.get("dpi", 203))
        ppm = dpi / 25.4
        scale = float(cfg.get("scale", 1.0))
        w_mm = float(cfg["sticker_width_mm"]) * scale
        h_mm = float(cfg["sticker_height_mm"]) * scale
        W = max(1, int(round(w_mm * ppm)))
        H = max(1, int(round(h_mm * ppm)))
    except Exception:
        W, H = 320, 235  # fallback 40x29.4mm @203dpi
        dpi = 203
        ppm = dpi / 25.4

    # صورة بيضاء بحجم الستيكر
    sticker = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(sticker)

    # حدود خفيفة (اختيارية)
    try:
        draw.rounded_rectangle([1, 1, W-2, H-2], radius=4, outline="#cccccc", width=1)
    except Exception:
        draw.rectangle([0, 0, W-1, H-1], outline="#cccccc")

    name = str(product.get("name", "") or "").strip()
    barcode_val = str(product.get("barcode", "") or "").strip()
    price = product.get("price", "")
    try:
        price_text = f"{float(price):.2f} جنيه" if str(price).strip() != "" else ""
    except Exception:
        price_text = str(price)
    _ = price_text  # لإسكات pyflakes - السعر ملغى حسب الطلب `prot/barcode_utils.py:259`

    barcode_y = None
    barcode_bh = 0
    # سيُرسم اسم المنتج أسفل الرقم التسلسلي بخط 16 (بعد الباركود)

    # --- باركود وسط ---
    barcode_img = None
    try:
        if HAS_BARCODE:
            import barcode
            from barcode.writer import ImageWriter
            writer = ImageWriter()
            opts = {"module_width": 0.26, "module_height": 10, "font_size": 8, "text_distance": 6, "quiet_zone": 2, "background": "white", "foreground": "black"}
            code128 = barcode.get_barcode_class('code128')
            bar = code128(barcode_val, writer=writer)
            # render to PIL without saving
            barcode_img = bar.render(writer_options=opts)
        else:
            raise Exception("no barcode")
    except Exception:
        # fallback: حاول توليد عبر الملف ثم افتحه
        try:
            tmp_path = generate_barcode_image(barcode_val, "")
            barcode_img = Image.open(tmp_path).convert("RGB")
            # اقتطع جزء الباركود فقط (بدون النص الإضافي)
            # barcode_img قد تحتوي نص أسفلها، نحتفظ بها كما هي
        except Exception:
            barcode_img = None

    if barcode_img is not None:
        try:
            bw, bh = barcode_img.size
            max_bw = int(W * 0.92)
            max_bh = int(H * 0.55)
            ratio = min(max_bw / bw, max_bh / bh, 1.0)
            if ratio < 1.0:
                barcode_img = barcode_img.resize((int(bw * ratio), int(bh * ratio)), Image.LANCZOS)
            # تكبير إضافي 10% + 10% إضافية = 21% إجمالي
            bw, bh = barcode_img.size
            barcode_img = barcode_img.resize((int(bw * 1.21), int(bh * 1.21)), Image.LANCZOS)
            bw, bh = barcode_img.size
            # حد أقصى بعد التكبير
            if bw > int(W * 0.99):
                ratio2 = (W * 0.99) / bw
                barcode_img = barcode_img.resize((int(bw * ratio2), int(bh * ratio2)), Image.LANCZOS)
                bw, bh = barcode_img.size
            if bh > int(H * 0.68):
                ratio2 = (H * 0.68) / bh
                barcode_img = barcode_img.resize((int(bw * ratio2), int(bh * ratio2)), Image.LANCZOS)
                bw, bh = barcode_img.size
            x = (W - bw) // 2
            y = (H - bh) // 2 - 8
            if y < 6:
                y = 6
            sticker.paste(barcode_img, (x, y))
            barcode_y = y
            barcode_bh = bh
        except Exception:
            barcode_y = None
            barcode_bh = 0
    else:
        try:
            f = _get_font(14)
            draw.text(((W - len(barcode_val)*7)//2, H//2), barcode_val, fill="black", font=f)
        except Exception:
            pass
        barcode_y = H // 2
        barcode_bh = 20

    # تم إلغاء طباعة السعر على الستيكر حسب الطلب

    # تم إلغاء النص التسلسلي المنفصل فوق اسم المنتج (كان غير واضح) — يبقى فقط رقم الباركود داخل صورة الباركود نفسها
    try:
        f_small = _get_font(11)
        bbox = draw.textbbox((0, 0), barcode_val, font=f_small)
        th = bbox[3] - bbox[1] if len(bbox) > 3 else 10
    except Exception:
        th = 10
    serial_y = (barcode_y + barcode_bh + 8) if barcode_y is not None else H - 40

    # --- اسم المنتج تحت الرقم التسلسلي بخط 16 +20% → 19 ---
    if name:
        try:
            font_prod = _get_font(27, bold=True)
            try:
                # حاول استيراد _layout من cashier سواء كان prot داخل cashier أو sibling
                _layp = None
                for _cand in ["sticker", "cashier.sticker"]:
                    try:
                        mod = __import__(_cand, fromlist=["_layout"])
                        _layp = getattr(mod, "_layout", None)
                        if _layp:
                            lay_p = _layp(name)
                            break
                    except Exception:
                        continue
                else:
                    lay_p = {}
            except Exception:
                lay_p = {}
            max_w = W - 12
            # تصغير لو طويل
            while True:
                try:
                    bbox = draw.textbbox((0, 0), name, font=font_prod, **lay_p)
                    tw2 = bbox[2] - bbox[0]
                except Exception:
                    tw2 = len(name) * 8
                if tw2 <= max_w or font_prod.size <= 10:
                    break
                try:
                    font_prod = ImageFont.truetype(font_prod.path, font_prod.size - 1)
                except Exception:
                    break
            bbox = draw.textbbox((0, 0), name, font=font_prod, **lay_p)
            tw2 = bbox[2] - bbox[0]
            th2 = bbox[3] - bbox[1] if len(bbox) > 3 else 16
            prod_y = H - th2 - 4
            # تأكد لا يتداخل مع الرقم
            if prod_y < serial_y + th + 4:
                prod_y = serial_y + th + 4
                if prod_y + th2 > H - 2:
                    prod_y = H - th2 - 2
            draw.text(((W - tw2)//2, prod_y), name, fill="black", font=font_prod, **lay_p)
        except Exception:
            pass

    return sticker
