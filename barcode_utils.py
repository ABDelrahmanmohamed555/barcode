import os
from PIL import Image, ImageDraw, ImageFont, ImageOps

from prot.config import BASE_DIR, BARCODES_DIR, FONTS_DIR

# محاولة استيراد python-barcode
try:
    import barcode
    from barcode.writer import ImageWriter
    HAS_BARCODE = True
except Exception:
    HAS_BARCODE = False


#test

def _get_font(size=14, bold=False):
    # جرب عدة مسارات للخطوط لضمان وجود Tajawal/Cairo حتى لو FONTS_DIR غير دقيق
    candidates = []
    try:
        # المسار الأساسي
        candidates.append(os.path.join(FONTS_DIR, "Tajawal-Bold.ttf" if bold else "Tajawal-Regular.ttf"))
        candidates.append(os.path.join(FONTS_DIR, "Cairo.ttf"))
        # مسارات إضافية مباشرة
        for _cand_dir in [
            "/home/kali/Desktop/cashier/assets/fonts",
            "/home/kali/Desktop/cashier_2/assets/fonts",
            os.path.join(os.path.dirname(BASE_DIR), "cashier", "assets", "fonts"),
            os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "cashier", "assets", "fonts"),
            os.path.join(BASE_DIR, "assets", "fonts"),
        ]:
            if _cand_dir and os.path.exists(_cand_dir):
                candidates.append(os.path.join(_cand_dir, "Tajawal-Bold.ttf" if bold else "Tajawal-Regular.ttf"))
                candidates.append(os.path.join(_cand_dir, "Tajawal-Regular.ttf" if bold else "Tajawal-Bold.ttf"))
                candidates.append(os.path.join(_cand_dir, "Cairo.ttf"))
    except Exception:
        pass
    for path in candidates:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            continue
    # fallback أخير
    try:
        # حاول FONTS_DIR مرة أخرى بشكل مباشر
        path = os.path.join(FONTS_DIR, "Tajawal-Bold.ttf" if bold else "Tajawal-Regular.ttf")
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
        path2 = os.path.join(FONTS_DIR, "Cairo.ttf")
        if os.path.exists(path2):
            return ImageFont.truetype(path2, size)
    except Exception:
        pass
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

    # --- جملة الشركة أعلى الباركود مباشرة بمسافة قصيرة جدا (1-2px) ---
    company_text = "شركة النحال لقطع الغيار"
    # نحسب أبعاد نص الشركة أولاً بدون رسم، لنضعها مباشرة فوق الباركود (مكبر 25%+10%+5%≈19)
    try:
        font_company = _get_font(19, bold=True)  # 18*1.05≈19 (تكبير إضافي 5%)
        disp_company = company_text
        use_rtl = False
        # حاول استخدام Pillow Raqm (الحديث) مع النص الخام بدون تشكيل مسبق
        try:
            # اختبر هل Pillow يدعم direction rtl
            _test_bbox = draw.textbbox((0, 0), company_text, font=font_company, direction='rtl', language='ar')
            use_rtl = True
            disp_company = company_text
        except Exception:
            # fallback: استخدم reshape_arabic التقليدي
            try:
                for _cand in ["utils", "cashier.utils"]:
                    mod = __import__(_cand, fromlist=["reshape_arabic"])
                    reshape = getattr(mod, "reshape_arabic")
                    disp_company = reshape(company_text)
                    use_rtl = False
                    break
                else:
                    disp_company = company_text
                    use_rtl = False
            except Exception:
                disp_company = company_text
                use_rtl = False
        max_w_company = W - 10
        while True:
            try:
                if use_rtl:
                    bbox_c = draw.textbbox((0, 0), disp_company, font=font_company, direction='rtl', language='ar')
                else:
                    bbox_c = draw.textbbox((0, 0), disp_company, font=font_company)
                tw_c = bbox_c[2] - bbox_c[0]
            except Exception:
                tw_c = len(disp_company) * 7
            if tw_c <= max_w_company or getattr(font_company, "size", 16) <= 9:
                break
            try:
                font_company = ImageFont.truetype(font_company.path, font_company.size - 1)
            except Exception:
                break
        try:
            if use_rtl:
                bbox_c = draw.textbbox((0, 0), disp_company, font=font_company, direction='rtl', language='ar')
            else:
                bbox_c = draw.textbbox((0, 0), disp_company, font=font_company)
        except Exception:
            bbox_c = draw.textbbox((0, 0), disp_company, font=font_company)
        tw_c = bbox_c[2] - bbox_c[0]
        th_c = bbox_c[3] - bbox_c[1] if len(bbox_c) > 3 else 12
        x_c = (W - tw_c) // 2
        # لا نرسم الآن - سنرسم بعد حساب y للباركود ليكون مباشرة فوقه
        company_h = th_c + 1
        company_y_end = 2 + company_h
        # نحتفظ بـ use_rtl للرسم لاحقاً
    except Exception:
        font_company = _get_font(19, bold=True)
        disp_company = company_text
        tw_c = 100
        th_c = 15
        x_c = (W - tw_c)//2
        company_y_end = 2 + 15
        company_h = 15
        use_rtl = False

    # --- باركود وسط ---
    barcode_img = None
    try:
        if HAS_BARCODE:
            import barcode
            from barcode.writer import ImageWriter
            writer = ImageWriter()
            # لا تكتب الرقم داخل صورة الباركود — سنرسمه نحن تحت الباركود مباشرة بمسافة 1px
            # اختيار نوع الباركود بذكاء: EAN13 للـ 13 رقم (أكثر كثافة وأوضح للريدر)، Code128 لغيره
            barcode_val_clean = str(barcode_val).strip()
            use_ean = False
            bar = None
            opts = None
            # جرّب EAN13 لو 13 رقم صالح
            if len(barcode_val_clean) == 13 and barcode_val_clean.isdigit():
                try:
                    from barcode import EAN13
                    def _ean13_check(s12):
                        total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(s12[:12]))
                        return str((10 - total % 10) % 10)
                    if _ean13_check(barcode_val_clean) == barcode_val_clean[-1]:
                        use_ean = True
                        bar = EAN13(barcode_val_clean, writer=writer)
                        # زيادة العرض كمان 5% (العرض فقط): 0.357→0.375mm (~5%) مع quiet 2mm ليبقى ضمن W-4=316px
                        opts = {"module_width": 0.375, "module_height": 11, "font_size": 0, "text_distance": 0, "quiet_zone": 2, "background": "white", "foreground": "black", "write_text": False, "dpi": 203}
                except Exception:
                    use_ean = False
            if not use_ean:
                # Code128: استخدام module_width بعدد نقاط صحيح (0.25mm = 2 dots) مع quiet_zone واسع 4mm
                # بدون تصغير NEAREST المشوّه — نجرب تركيبات مرتبة وتختار أول واحدة تناسب العرض
                max_bw_px = W - 4
                # زيادة العرض كمان 5% (العرض فقط): نجرب 0.375mm و 0.289mm (+5%) مع quiet 2، لو لم يناسب نعود لـ 0.25
                candidates = [
                    (0.375, 2), # EAN +5% width مع quiet ضيق ليبقى ضمن 316px
                    (0.289, 2), # Code128 +5% width (≈0.275*1.05) مع quiet ضيق
                    (0.325, 4), # 30% wider السابق
                    (0.325, 2),
                    (0.25, 6),  # 2 dots, quiet 6mm واسع
                    (0.25, 4),  # 2 dots, quiet 4mm قياسي (الحالي)
                    (0.25, 2),  # 2 dots, quiet 2mm ضيق
                    (0.125, 4), # 1 dot fallback للباركود الطويل جداً
                    (0.125, 2),
                ]
                chosen_mw = 0.25
                chosen_qz = 4
                chosen_img = None
                for cand_mw, cand_qz in candidates:
                    try:
                        tmp_writer = ImageWriter()
                        tmp_bar = barcode.get_barcode_class('code128')(barcode_val_clean, writer=tmp_writer)
                        tmp_opts = {"module_width": cand_mw, "module_height": 12, "font_size": 0, "text_distance": 0, "quiet_zone": cand_qz, "background": "white", "foreground": "black", "write_text": False, "dpi": 203}
                        tmp_img = tmp_bar.render(writer_options=tmp_opts)
                        if tmp_img.size[0] <= max_bw_px:
                            chosen_mw = cand_mw
                            chosen_qz = cand_qz
                            chosen_img = tmp_img
                            break
                    except Exception:
                        continue
                if chosen_img is not None:
                    bar = barcode.get_barcode_class('code128')(barcode_val_clean, writer=writer)
                    opts = {"module_width": chosen_mw, "module_height": 12, "font_size": 0, "text_distance": 0, "quiet_zone": chosen_qz, "background": "white", "foreground": "black", "write_text": False, "dpi": 203}
                else:
                    # fallback أخير — أصغر حجم ممكن بدون تشويه
                    bar = barcode.get_barcode_class('code128')(barcode_val_clean, writer=writer)
                    opts = {"module_width": 0.125, "module_height": 12, "font_size": 0, "text_distance": 0, "quiet_zone": 2, "background": "white", "foreground": "black", "write_text": False, "dpi": 203}
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
            # مقاسات قصوى للباركود داخل الستيكر — تم الحفاظ عليها بدون تصغير مشوّه
            # كان التصغير بـ Image.NEAREST يشوّه نسب القضبان ويمنع الريدر من المسح
            # الآن نختار module_width بنقاط صحيحة (2 dots) مع quiet_zone واسع، فلا حاجة لأي resize
            max_bw = W - 4  # يسمح بـ 316px
            max_bh = int(H * 0.55)
            # حماية: لو لأي سبب تجاوز المقاس، لا نستخدم NEAREST (يشوّه) — نترك الصورة كما هي مع توسيط
            # الاختيار السابق للـ candidates يضمن عدم التجاوز أصلاً
            # زيادة بسيطة في الارتفاع قد تجعل bh يقترب من max_bh لكن لا يتجاوزه (9-10mm => 87-95px)
            # إضافة حد أبيض 1px حول الباركود لضمان quiet_zone نظيف للريدر (يحسّن المسح)
            # نسمح حتى W-2=318px (هامش 1px للحدود) وليس max_bw=316 فقط، لضمان قراءة الباركود العريض 316
            try:
                if barcode_img.mode != 'RGB':
                    barcode_img = barcode_img.convert('RGB')
                if bw + 2 <= W - 2 and bh + 2 <= H - 2:
                    barcode_img = ImageOps.expand(barcode_img, border=1, fill='white')
                    bw, bh = barcode_img.size
            except Exception:
                pass
            x = (W - bw) // 2
            # اسم الشركة فوق الباركود + نزول الباركود 60% لتحت حسب الطلب الجديد
            y = company_y_end + 1
            # تأكد أن الباركود + الرقم + الاسم يكفون داخل الستيكر
            try:
                f_tmp = _get_font(25)  # سيريال 24+5%≈25
                bbox_tmp = draw.textbbox((0, 0), barcode_val, font=f_tmp)
                th_tmp = bbox_tmp[3] - bbox_tmp[1] if len(bbox_tmp) > 3 else 18
            except Exception:
                th_tmp = 12
            try:
                font_tmp2 = _get_font(23, bold=True)  # اسم منتج مكبر 30%
                bbox_tmp2 = draw.textbbox((0, 0), name or "X", font=font_tmp2)
                th2_tmp = bbox_tmp2[3] - bbox_tmp2[1] if len(bbox_tmp2) > 3 else 18
            except Exception:
                th2_tmp = 18
            needed = bh + 2 + th_tmp + 2 + th2_tmp + 1
            # نزل الباركود لتحت بنسبة 60% من المساحة الفارغة (طلب جديد)
            try:
                slack = H - y - needed
                if slack > 4:
                    y += int(slack * 0.60)  # 60% نزول
            except Exception:
                pass
            # إذا المساحة لا تكفي، لا نصغّر الباركود بـ NEAREST (يشوّه القراءة)
            # بدلاً من ذلك نرفع موضع الباركود قليلاً ليكفي بدون تداخل، مع الحفاظ على نفس الحجم
            if y + needed > H:
                y = max(company_y_end + 1, H - needed - 1)
            if y < company_y_end + 1:
                y = company_y_end + 1
            # رسم اسم الشركة مباشرة فوق الباركود بمسافة قصيرة جدا 1px (خليه زي ما هو) - حجم مكبر 25%+10%≈18pt
            try:
                y_c = y - th_c - 1  # 1px فجوة قصيرة جدا
                if y_c < 1:
                    y_c = 1
                if 'use_rtl' in locals() and use_rtl:
                    draw.text((x_c, y_c), disp_company, fill="black", font=font_company, direction='rtl', language='ar')
                else:
                    draw.text((x_c, y_c), disp_company, fill="black", font=font_company)
                company_y_end = y_c + th_c + 1
            except Exception:
                try:
                    if 'use_rtl' in locals() and use_rtl:
                        draw.text((x_c, 2), disp_company, fill="black", font=font_company, direction='rtl', language='ar')
                    else:
                        draw.text((x_c, 2), disp_company, fill="black", font=font_company)
                except Exception:
                    pass
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

    # --- الرقم التسلسلي تحت الباركود مباشرة بمسافة 2px قصيرة (مكبر +5% إضافي ≈25 حسب الطلب) ---
    th = 18
    serial_y = (barcode_y + barcode_bh + 2) if barcode_y is not None else H - 40
    if barcode_val and barcode_y is not None:
        try:
            font_serial = _get_font(25)  # كان 24 → 25 (+5%)
            # تأكد أن الرقم يكفي عرضاً — صغّر لو لازم
            max_w_serial = W - 8
            # حاول تصغير لو الرقم طويل
            while True:
                try:
                    bbox_s = draw.textbbox((0, 0), barcode_val, font=font_serial)
                    tw_s = bbox_s[2] - bbox_s[0]
                    th_s = bbox_s[3] - bbox_s[1] if len(bbox_s) > 3 else 10
                except Exception:
                    tw_s = len(barcode_val) * 7
                    th_s = 10
                if tw_s <= max_w_serial or getattr(font_serial, "size", 10) <= 7:
                    break
                try:
                    font_serial = ImageFont.truetype(font_serial.path, font_serial.size - 1)
                except Exception:
                    break
            bbox_s = draw.textbbox((0, 0), barcode_val, font=font_serial)
            tw_s = bbox_s[2] - bbox_s[0]
            th_s = bbox_s[3] - bbox_s[1] if len(bbox_s) > 3 else 10
            x_s = (W - tw_s) // 2
            y_s = barcode_y + barcode_bh + 2  # مسافة 2px قصيرة جداً تحت الباركود مباشرة
            # لو سيتجاوز أسفل الستيكر، ارفعه
            if y_s + th_s > H - 2:
                y_s = max(barcode_y + barcode_bh + 1, H - th_s - 2 - 14)
            draw.text((x_s, y_s), barcode_val, fill="black", font=font_serial)
            serial_y = y_s
            th = th_s
        except Exception:
            # fallback حساب فقط
            try:
                bbox = draw.textbbox((0, 0), barcode_val, font=_get_font(25))
                th = bbox[3] - bbox[1] if len(bbox) > 3 else 18
            except Exception:
                th = 10
            serial_y = (barcode_y + barcode_bh + 2) if barcode_y is not None else H - 40

    # --- اسم المنتج تحت الرقم التسلسلي بخط 18*1.3≈23 (تكبير 30% حسب الطلب) ---
    if name:
        try:
            font_prod = _get_font(23, bold=True)  # كان 18 -> 23 (تكبير 30%)
            disp_name = name
            lay_p = {}
            use_reshape = False
            try:
                # حاول استيراد _layout و reshape_arabic مع دعم libraqm
                _layp = None
                _reshape = None
                for _cand in ["sticker", "cashier.sticker"]:
                    try:
                        mod = __import__(_cand, fromlist=["_layout"])
                        _layp = getattr(mod, "_layout", None)
                        if _layp:
                            tmp_lay = _layp(name)
                            # اختبر هل libraqm مدعوم
                            try:
                                draw.textbbox((0, 0), name, font=font_prod, **tmp_lay)
                                lay_p = tmp_lay
                                disp_name = name
                            except Exception:
                                # libraqm غير مدعوم — استخدم reshape
                                raise
                            break
                    except Exception:
                        continue
                else:
                    # لم ينجح _layout — جرب reshape
                    for _cand in ["utils", "cashier.utils"]:
                        try:
                            mod = __import__(_cand, fromlist=["reshape_arabic"])
                            _reshape = getattr(mod, "reshape_arabic")
                            disp_name = _reshape(name)
                            use_reshape = True
                            lay_p = {}
                            break
                        except Exception:
                            continue
            except Exception:
                lay_p = {}
                disp_name = name
            # لو لسه lay_p فيه direction وسيسبب خطأ، حول ل reshape
            if lay_p.get("direction") == "rtl":
                try:
                    draw.textbbox((0, 0), disp_name, font=font_prod, **lay_p)
                except Exception:
                    # fallback reshape
                    try:
                        for _cand in ["utils", "cashier.utils"]:
                            mod = __import__(_cand, fromlist=["reshape_arabic"])
                            disp_name = getattr(mod, "reshape_arabic")(name)
                            break
                    except Exception:
                        disp_name = name
                    lay_p = {}
            max_w = W - 12
            # تصغير لو طويل
            while True:
                try:
                    bbox = draw.textbbox((0, 0), disp_name, font=font_prod, **lay_p)
                    tw2 = bbox[2] - bbox[0]
                except Exception:
                    try:
                        bbox = draw.textbbox((0, 0), disp_name, font=font_prod)
                        tw2 = bbox[2] - bbox[0]
                        lay_p = {}
                    except Exception:
                        tw2 = len(disp_name) * 8
                if tw2 <= max_w or getattr(font_prod, "size", 18) <= 10:
                    break
                try:
                    # حاول تصغير الخط
                    if hasattr(font_prod, "path") and os.path.exists(getattr(font_prod, "path", "")):
                        font_prod = ImageFont.truetype(font_prod.path, font_prod.size - 1)
                    else:
                        # جرب تحميل بحجم أصغر مباشرة
                        font_prod = _get_font(font_prod.size - 1, bold=True)
                except Exception:
                    break
            try:
                bbox = draw.textbbox((0, 0), disp_name, font=font_prod, **lay_p)
            except Exception:
                bbox = draw.textbbox((0, 0), disp_name, font=font_prod)
                lay_p = {}
            tw2 = bbox[2] - bbox[0]
            th2 = bbox[3] - bbox[1] if len(bbox) > 3 else 16
            prod_y = H - th2 - 2
            # طلب جديد: نزول اسم المنتج لتحت بنسبة 10% (حوالي 2px لخط 22)
            prod_y += int(th2 * 0.10)  # 10% نزول
            if prod_y + th2 > H - 1:
                prod_y = H - th2 - 1  # أقصى نزول داخل الستيكر
            # تأكد لا يتداخل مع الرقم — مسافة 2px قصيرة فقط ليكفي الستيكر
            if prod_y < serial_y + th + 2:
                prod_y = serial_y + th + 2
                if prod_y + th2 > H - 1:
                    prod_y = H - th2 - 1
            # رسم الاسم في المنتصف
            try:
                draw.text(((W - tw2)//2, prod_y), disp_name, fill="black", font=font_prod, **lay_p)
            except Exception:
                draw.text(((W - tw2)//2, prod_y), disp_name, fill="black", font=font_prod)
        except Exception:
            pass

    return sticker
