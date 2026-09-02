# prot/main.py — نظام المنتجات والباركود بنفس ستايل المشروع الأساسي
import os
import sys
import threading
from datetime import datetime

# تأكد أن المجلد الأب في المسار لاستيراد المشروع الأساسي
BASE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_PARENT not in sys.path:
    sys.path.insert(0, BASE_PARENT)

import customtkinter as ctk
from customtkinter import CTkImage
from PIL import Image

from prot.config import COLORS, FONT_ARABIC, FONT_ARABIC_BOLD, FONT_HEADER, FONT_BODY, FONT_BODY_BOLD, FONT_SMALL, APP_NAME, CATEGORIES, BASE_DIR
from prot.db.database import init_db, add_product, get_all_products, update_product, delete_product, get_product_by_id, get_product_by_barcode, add_sale, create_sale_group, is_sales_enabled, set_sales_enabled, get_all_sales, get_sales_count, is_invoice_enabled, set_invoice_enabled, is_user_invoice_enabled, set_user_invoice_enabled, get_cart_font_scale, set_cart_font_scale
from prot.barcode_utils import generate_barcode_image, generate_product_sticker
from arabic_entry import ArabicEntry
from config import BASE_DIR as MAIN_BASE
from utils import reshape_arabic, save_window_state, restore_or_center, apply_gold_cursor, make_undecorated, enable_resize, make_optionmenu_values
from dropdown import AnimatedOptionMenu
from titlebar import TitleBar


class ProtWindow(ctk.CTk):
    def __init__(self, user=None):
        super().__init__()
        make_undecorated(self)
        self.user = user or {"name": "admin", "role": "admin"}
        self.title(APP_NAME)
        self.geometry("1150x760")
        self.minsize(1000, 650)
        enable_resize(self, 1000, 650)
        self.configure(fg_color=COLORS["bg_dark"])
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._clock_timer = None
        self._editing_id = None
        self._barcode_preview = None
        # POS للمستخدم العادي (employee)
        self._cart = []
        self._selected_product = None
        self._pos_inited = False
        self._scan_buffer = ""

        init_db()
        restore_or_center(self, "prot_window", 1150, 760)
        self.after(150, lambda: apply_gold_cursor(self))
        self._build_ui()
        if self.user.get("role") != "admin":
                # وضع المستخدم: فعل السكان مباشرة
            if hasattr(self, '_refresh_pos_cart'):
                self._refresh_pos_cart()
        else:
            self._refresh_table()
        self.bind("<Escape>", lambda e: self._logout())
        self.protocol("WM_DELETE_WINDOW", self._logout)

    def _build_ui(self):
        self._build_header()
        self._build_content()

    def _build_header(self):
        _logo_path = os.path.join(MAIN_BASE, "icon.png")
        logo_img = None
        if os.path.exists(_logo_path):
            try:
                logo_img = CTkImage(light_image=Image.open(_logo_path), dark_image=Image.open(_logo_path), size=(32, 32))
            except Exception:
                logo_img = None
        TitleBar(self, APP_NAME, self._logout, logo_image=logo_img).pack(fill="x")

        toolbar = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], height=44, corner_radius=0)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        right_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        right_frame.pack(side="right", padx=20, fill="y")

        self.time_label = ctk.CTkLabel(right_frame, text="", font=FONT_BODY, text_color=COLORS["text_light"])
        self.time_label.pack(side="right", padx=(0, 10), pady=10)
        self._update_clock()

        ctk.CTkLabel(toolbar, text=datetime.now().strftime("%d / %m / %Y"), font=FONT_BODY, text_color=COLORS["text_light"]).place(relx=0.5, rely=0.5, anchor="center")

        left_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        left_frame.pack(side="left", padx=20, fill="y")

        ctk.CTkLabel(left_frame, text=reshape_arabic(f"المستخدم: {self.user.get('name','admin')}"), font=FONT_BODY, text_color=COLORS["text_light"]).pack(side="left", pady=11)

        # زر البحث — للأدمن فقط (المستخدم العادي ليس له وظيفة)
        if self.user.get("role") == "admin":
            ctk.CTkButton(left_frame, text=reshape_arabic("بحث"), font=FONT_SMALL, width=70, height=30, corner_radius=6,
                          fg_color="transparent", border_width=1, border_color=COLORS["border"], hover_color=COLORS["bg_hover"], text_color=COLORS["text_light"],
                          command=self._open_search).pack(side="left", padx=(12, 0))

        # زر ترس الإعدادات — يظهر للأدمن والمستخدم (صلاحيات المستخدم تحتوي على حجم الخط)
        ctk.CTkButton(left_frame, text="⚙", font=(FONT_ARABIC_BOLD, 18), width=36, height=30, corner_radius=6,
                      fg_color="transparent", border_width=1, border_color=COLORS["border"], hover_color=COLORS["bg_hover"], text_color=COLORS["text_light"],
                      command=self._open_settings).pack(side="left", padx=(10, 0))

        ctk.CTkButton(left_frame, text=reshape_arabic("خروج"), font=FONT_SMALL, width=80, height=30, corner_radius=6,
                      fg_color="transparent", border_width=1, border_color=COLORS["border"], hover_color=COLORS["bg_hover"], text_color=COLORS["text_light"],
                      command=self._logout).pack(side="left", padx=(10, 0))

    def _update_clock(self):
        self.time_label.configure(text=datetime.now().strftime("%I:%M:%S %p"))
        self._clock_timer = self.after(1000, self._update_clock)

    def destroy(self):
        save_window_state("prot_window", self.geometry())
        if self._clock_timer:
            try:
                self.after_cancel(self._clock_timer)
            except Exception:
                pass
        super().destroy()

    def _logout(self):
        # رجوع لنافذة تسجيل الدخول الخاصة بـ prot (نفس ربط المشروع الأساسي)
        try:
            self.destroy()
        except Exception:
            pass
        try:
            from prot.login import ProtLoginWindow
            app = ProtLoginWindow()
            app.mainloop()
        except Exception:
            # fallback: إغلاق فقط
            pass

    # ---------- helpers لحجم خط السلة ----------
    def _get_cart_scale(self):
        try:
            return float(get_cart_font_scale())
        except Exception:
            return 1.0

    def _scaled_font(self, base_font, scale=None):
        try:
            s = float(scale) if scale is not None else self._get_cart_scale()
        except Exception:
            s = 1.0
        try:
            if isinstance(base_font, tuple):
                if len(base_font) == 2:
                    fam, sz = base_font
                    return (fam, max(8, int(round(sz * s))))
                elif len(base_font) >= 3:
                    fam, sz, *rest = base_font
                    return (fam, max(8, int(round(sz * s))), *rest)
        except Exception:
            pass
        return base_font

    def _scaled_width(self, base, scale=None):
        try:
            s = float(scale) if scale is not None else self._get_cart_scale()
            return max(10, int(round(base * s)))
        except Exception:
            return base

    def _scaled_height(self, base, scale=None):
        try:
            s = float(scale) if scale is not None else self._get_cart_scale()
            return max(12, int(round(base * s)))
        except Exception:
            return base

    def _rebuild_pos_ui(self):
        """إعادة بناء واجهة السلة والتفاصيل بعد تغيير حجم الخط — مع ضبط العرض تلقائياً"""
        try:
            if not hasattr(self, '_pos_left_parent') or not hasattr(self, '_pos_right_parent'):
                return
            # حفظ السلة مؤقتاً
            # إعادة ضبط عرض لوحة التفاصيل حسب الحجم الجديد
            det_w = self._scaled_width(380)
            try:
                max_w = int(self.winfo_width() * 0.48) if self.winfo_width() > 200 else 520
                if det_w > max_w and max_w > 380:
                    det_w = max_w
                # عند 5x قد يصبح كبير جداً، نحدّه بـ 650
                if det_w > 650:
                    det_w = 650
            except Exception:
                pass
            try:
                self._pos_right_parent.configure(width=det_w)
            except Exception:
                pass
            # إعادة بناء
            self._pos_inited = False
            self._build_pos_cart(self._pos_left_parent)
            self._build_pos_details(self._pos_right_parent)
            # تحديث السلة الحالية
            self._refresh_pos_cart()
            if self._selected_product:
                self._refresh_pos_details(self._selected_product)
        except Exception:
            pass

    # ---------- المحتوى ----------
    def _build_content(self):
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=15)

        is_admin = self.user.get("role") == "admin"
        if is_admin:
                # يمين: قائمة المنتجات - يسار: فورم إضافة (أدمن فقط)
            left_panel = ctk.CTkFrame(content, fg_color="transparent", width=420)
            left_panel.pack(side="right", fill="y", padx=(10, 0))
            left_panel.pack_propagate(False)
            right_panel = ctk.CTkFrame(content, fg_color="transparent")
            right_panel.pack(side="left", fill="both", expand=True)
            self._build_form(left_panel)
            self._build_table(right_panel)
        else:
            # مستخدم عادي: POS سكان + سلة يسار وتفاصيل يمين (نفس طلب الكاشير)
            ctk.CTkLabel(content, text=reshape_arabic("وضع المستخدم: سكان وبيع — الإضافة والتعديل للأدمن"), font=FONT_SMALL, text_color=COLORS["text_light"]).pack(side="bottom", pady=(6, 0))
            det_w = self._scaled_width(380)
            # حد أقصى حتى لا يتجاوز نصف النافذة عند تكبير 5x
            try:
                max_w = int(self.winfo_width() * 0.48) if self.winfo_width() > 100 else 520
                if det_w > max_w and max_w > 380:
                    det_w = max_w
            except Exception:
                pass
            right_details = ctk.CTkFrame(content, fg_color="transparent", width=det_w)
            right_details.pack(side="right", fill="y", padx=(10, 0))
            right_details.pack_propagate(False)
            left_cart = ctk.CTkFrame(content, fg_color="transparent")
            left_cart.pack(side="left", fill="both", expand=True)
            # حفظ المراجع لإعادة البناء عند تغيير حجم الخط
            self._pos_left_parent = left_cart
            self._pos_right_parent = right_details
            self._pos_content = content
            self._build_pos_cart(left_cart)
            self._build_pos_details(right_details)

    def _build_form(self, parent):
        form_frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=10)
        form_frame.pack(fill="both", expand=True)

        header = ctk.CTkFrame(form_frame, fg_color=COLORS["accent_dim"], height=48, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        self.form_title = ctk.CTkLabel(header, text=reshape_arabic("إضافة منتج"), font=FONT_HEADER, text_color=COLORS["text_white"])
        self.form_title.pack(expand=True)

        body = ctk.CTkFrame(form_frame, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=15)

        # اسم المنتج
        self._create_field(body, "اسم المنتج", 0)
        self.name_entry = ArabicEntry(body, placeholder=reshape_arabic(" "), font=FONT_BODY, height=42, corner_radius=6,
                                  fg_color=COLORS["bg_input"], text_color=COLORS["text_white"], border_color=COLORS["border"])
        self.name_entry.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.name_entry._frame.bind("<KeyRelease>", lambda e: self._auto_update_barcode_name(), add=True)

        # الباركود + زر توليد
        self._create_field(body, "الباركود (يُنشأ تلقائياً)", 2)
        barcode_row = ctk.CTkFrame(body, fg_color="transparent")
        barcode_row.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        barcode_row.columnconfigure(0, weight=1)
        self.barcode_entry = ctk.CTkEntry(barcode_row, font=FONT_BODY, height=42, corner_radius=6,
                                      fg_color=COLORS["bg_input"], text_color=COLORS["text_white"], border_color=COLORS["border"], justify="center",
                                      placeholder_text="auto")
        self.barcode_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(barcode_row, text="↻", font=("DejaVu Sans", 14, "bold"), width=42, height=42, corner_radius=6,
                  fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="white",
                  command=self._generate_new_barcode).grid(row=0, column=1)

        # الفئة
        self._create_field(body, "الفئة", 4)
        disp, self.cat_map = make_optionmenu_values(CATEGORIES)
        self.cat_menu = AnimatedOptionMenu(body, values=disp, font=FONT_BODY, dropdown_font=FONT_BODY, height=42, corner_radius=6,
                                       fg_color=COLORS["bg_input"], button_color=COLORS["accent"], button_hover_color=COLORS["accent_hover"], text_color=COLORS["text_white"])
        self.cat_menu.set(disp[0])
        self.cat_menu.grid(row=5, column=0, sticky="ew", pady=(0, 10))

        # السعر + المخزون في صف واحد
        price_stock = ctk.CTkFrame(body, fg_color="transparent")
        price_stock.grid(row=6, column=0, sticky="ew", pady=(0, 10))
        price_stock.columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(price_stock, text=reshape_arabic("السعر"), font=FONT_SMALL, text_color=COLORS["text_light"], anchor="e").grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkLabel(price_stock, text=reshape_arabic("المخزون"), font=FONT_SMALL, text_color=COLORS["text_light"], anchor="e").grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.price_entry = ctk.CTkEntry(price_stock, font=FONT_BODY, height=42, corner_radius=6,
                                     fg_color=COLORS["bg_input"], text_color=COLORS["text_white"], border_color=COLORS["border"], justify="center",
                                     placeholder_text="0.00")
        self.price_entry.grid(row=1, column=0, sticky="ew", padx=(0, 4))
        self.price_entry.bind("<KeyRelease>", self._filter_price)

        self.stock_entry = ctk.CTkEntry(price_stock, font=FONT_BODY, height=42, corner_radius=6,
                                     fg_color=COLORS["bg_input"], text_color=COLORS["text_white"], border_color=COLORS["border"], justify="center",
                                     placeholder_text="0")
        self.stock_entry.grid(row=1, column=1, sticky="ew", padx=(4, 0))
        self.stock_entry.bind("<KeyRelease>", self._filter_int)

        # الوصف
        self._create_field(body, "الوصف (اختياري)", 7)
        self.desc_entry = ArabicEntry(body, placeholder=reshape_arabic(" "), font=FONT_BODY, height=42, corner_radius=6,
                                  fg_color=COLORS["bg_input"], text_color=COLORS["text_white"], border_color=COLORS["border"])
        self.desc_entry.grid(row=8, column=0, sticky="ew", pady=(0, 10))

        # معاينة باركود
        self.barcode_preview_frame = ctk.CTkFrame(body, fg_color=COLORS["bg_input"], corner_radius=8, border_width=1, border_color=COLORS["border"])
        self.barcode_preview_frame.grid(row=9, column=0, sticky="ew", pady=(6, 8))
        self.barcode_preview_frame.grid_propagate(False)
        self.barcode_preview_frame.configure(height=90)
        self.barcode_preview_label = ctk.CTkLabel(self.barcode_preview_frame, text=reshape_arabic("معاينة الباركود"), font=FONT_SMALL, text_color=COLORS["text_light"])
        self.barcode_preview_label.pack(expand=True)

        body.columnconfigure(0, weight=1)

        # أزرار
        self.save_btn = ctk.CTkButton(form_frame, text=reshape_arabic("حفظ المنتج + باركود"), font=FONT_BODY_BOLD, height=46, corner_radius=8,
                                  fg_color=COLORS["success"], hover_color=COLORS["success_hover"], text_color="white", command=self._save_product)
        self.save_btn.pack(fill="x", padx=20, pady=(0, 8))

        self.edit_btns = ctk.CTkFrame(form_frame, fg_color="transparent")
        # مخفي حتى وضع التعديل
        self.update_btn = ctk.CTkButton(self.edit_btns, text=reshape_arabic("حفظ التعديل"), font=FONT_BODY_BOLD, height=44, corner_radius=8,
                                    fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="white", command=self._update_product)
        self.update_btn.pack(fill="x", pady=(0, 6))
        ctk.CTkButton(self.edit_btns, text=reshape_arabic("إلغاء التعديل"), font=FONT_BODY, height=38, corner_radius=8,
                  fg_color="transparent", border_width=1, border_color=COLORS["border"], hover_color=COLORS["bg_hover"], text_color=COLORS["text_light"],
                  command=self._cancel_edit).pack(fill="x")

        btn_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 15))
        ctk.CTkButton(btn_row, text=reshape_arabic("مسح"), font=FONT_BODY, width=100, height=42, corner_radius=8,
                  fg_color="transparent", border_width=1, border_color=COLORS["border"], hover_color=COLORS["bg_hover"], text_color=COLORS["text_light"],
                  command=self._clear_form).pack(side="right")

        # توليد باركود مبدئي
        self.after(300, self._generate_new_barcode)

    def _create_field(self, parent, text, row):
        ctk.CTkLabel(parent, text=reshape_arabic(text), font=FONT_SMALL, text_color=COLORS["text_light"], anchor="e").grid(row=row, column=0, sticky="e", pady=(0, 4))

    # ---------- جدول المنتجات ----------
    def _build_table(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=10)
        frame.pack(fill="both", expand=True)

        header = ctk.CTkFrame(frame, fg_color=COLORS["accent_dim"], height=48, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text=reshape_arabic("قائمة المنتجات"), font=FONT_HEADER, text_color=COLORS["text_white"]).pack(side="right", padx=15)
        ctk.CTkButton(header, text=reshape_arabic("تحديث"), font=FONT_SMALL, width=80, height=30, corner_radius=6,
                  fg_color="transparent", border_width=1, border_color=COLORS["border_light"], hover_color=COLORS["bg_hover"], text_color="white",
                  command=self._refresh_table).pack(side="left", padx=15)

        # بحث — يدعم الاسم/الباركود/الرقم
        search_row = ctk.CTkFrame(frame, fg_color="transparent")
        search_row.pack(fill="x", padx=10, pady=(8, 0))
        self.search_entry = ctk.CTkEntry(search_row, font=FONT_SMALL, height=34, corner_radius=6,
                                      fg_color=COLORS["bg_input"], text_color="white", border_color=COLORS["border"], justify="right",
                                      placeholder_text=reshape_arabic("بحث بالاسم أو الباركود أو الرقم"))
        self.search_entry.pack(side="right", fill="x", expand=True, padx=(0, 6))
        self.search_entry.bind("<KeyRelease>", lambda e: self._refresh_table())
        ctk.CTkButton(search_row, text="⌕", font=("DejaVu Sans", 14), width=40, height=34, corner_radius=6,
                  fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="white",
                  command=self._refresh_table).pack(side="right")

        cols = ctk.CTkFrame(frame, fg_color=COLORS["bg_input"], corner_radius=0)
        cols.pack(fill="x", padx=10, pady=(8, 0))
        headers = [(reshape_arabic("الرقم"), 45), (reshape_arabic("المتاح"), 70), (reshape_arabic("السعر"), 80), (reshape_arabic("الفئة"), 90), (reshape_arabic("الباركود"), 130), (reshape_arabic("الاسم"), 160), (reshape_arabic("تحكم"), 185)]
        for txt, w in headers:
            ctk.CTkLabel(cols, text=txt, font=FONT_BODY_BOLD, text_color=COLORS["accent"], width=w).pack(side="right", padx=6, pady=8)

        self.scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=10, pady=(6, 10))

    def _refresh_table(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        search = self.search_entry.get().strip() if hasattr(self, 'search_entry') else ""
        # الترقيم الثابت 1..n حسب الترتيب الكلي (created_at DESC)
        all_rows = get_all_products(search="")
        id_to_seq = {ap["id"]: str(idx + 1) for idx, ap in enumerate(all_rows)}
        # جلب المنتجات المطابقة للبحث (الاسم/الباركود/الـ id)
        rows = get_all_products(search=search)
        # إذا البحث رقمي، أضف المنتج ذا الرقم التسلسلي المطابق إن لم يكن موجوداً
        if search and search.isdigit():
            try:
                target_num = int(search)
                if 1 <= target_num <= len(all_rows):
                    seq_prod = all_rows[target_num - 1]
                    if seq_prod["id"] not in [r["id"] for r in rows]:
                        rows = [seq_prod] + rows
            except Exception:
                pass
        if not rows:
            ctk.CTkLabel(self.scroll, text=reshape_arabic("لا توجد منتجات"), font=FONT_BODY, text_color=COLORS["text_light"]).pack(pady=40)
            return
        for i, p in enumerate(rows):
            bg = COLORS["bg_hover"] if i % 2 == 0 else COLORS["bg_card"]
            row = ctk.CTkFrame(self.scroll, fg_color=bg, corner_radius=6)
            row.pack(fill="x", pady=2)
            # الرقم التسلسلي الثابت (لا يتغير بالبحث)
            seq_num = id_to_seq.get(p["id"], str(i + 1))
            ctk.CTkLabel(row, text=seq_num, font=FONT_BODY_BOLD, text_color=COLORS["accent"], width=45).pack(side="right", padx=6, pady=8)

            # أزرار التحكم يسار — أدمن: كل شيء، مستخدم: عرض وطباعة فقط
            act = ctk.CTkFrame(row, fg_color="transparent")
            act.pack(side="left", padx=6, pady=6)
            is_admin = self.user.get("role") == "admin"
            ctk.CTkButton(act, text="↻", font=("DejaVu Sans", 11, "bold"), width=32, height=28, corner_radius=4,
                          fg_color=COLORS["success"], hover_color=COLORS["success_hover"], text_color="white",
                          command=lambda pid=p["id"]: self._show_barcode(pid)).pack(side="left", padx=1)
            ctk.CTkButton(act, text="🖨", font=("DejaVu Sans", 11), width=32, height=28, corner_radius=4,
                          fg_color=COLORS["info"], hover_color=COLORS["info_hover"], text_color="white",
                          command=lambda pid=p["id"]: self._print_barcode(pid)).pack(side="left", padx=1)
            if is_admin:
                ctk.CTkButton(act, text="✏", font=("DejaVu Sans", 11, "bold"), width=32, height=28, corner_radius=4,
                              fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="white",
                              command=lambda prod=p: self._start_edit(prod)).pack(side="left", padx=1)
                ctk.CTkButton(act, text="✕", font=("DejaVu Sans", 11, "bold"), width=32, height=28, corner_radius=4,
                              fg_color=COLORS["danger"], hover_color="#d94a4a", text_color="white",
                              command=lambda pid=p["id"]: self._delete_confirm(pid)).pack(side="left", padx=1)

            ctk.CTkLabel(row, text=str(p["stock"]), font=FONT_BODY, text_color=COLORS["text_white"], width=70).pack(side="right", padx=6, pady=8)
            ctk.CTkLabel(row, text=f"{float(p['price']):.2f}", font=FONT_BODY, text_color=COLORS["success"], width=80).pack(side="right", padx=6, pady=8)
            ctk.CTkLabel(row, text=reshape_arabic(p["category"] or ""), font=FONT_BODY, text_color=COLORS["text_light"], width=90).pack(side="right", padx=6, pady=8)
            ctk.CTkLabel(row, text=p["barcode"], font=FONT_BODY, text_color=COLORS["text_light"], width=130).pack(side="right", padx=6, pady=8)
            ctk.CTkLabel(row, text=reshape_arabic(p["name"]), font=FONT_BODY, text_color=COLORS["text_white"], width=160).pack(side="right", padx=6, pady=8)

    # ---------- منطق ----------
    def _generate_new_barcode(self):
        from prot.db.database import get_unique_barcode
        code = get_unique_barcode()
        self.barcode_entry.delete(0, "end")
        self.barcode_entry.insert(0, code)
        self._update_barcode_preview()

    def _update_barcode_preview(self):
        code = self.barcode_entry.get().strip()
        name = self.name_entry.get().strip()
        if not code:
            return
        try:
            path = generate_barcode_image(code, name)
            img = Image.open(path)
            # تصغير للمعاينة
            w, h = img.size
            max_w = 360
            if w > max_w:
                    ratio = max_w / w
            img = img.resize((max_w, int(h * ratio)), Image.LANCZOS)
            ctk_img = CTkImage(light_image=img, dark_image=img, size=img.size)
            self.barcode_preview_label.configure(text="", image=ctk_img)
            self.barcode_preview_label.image = ctk_img
        except Exception as e:
            self.barcode_preview_label.configure(text=f"خطأ: {e}", image=None)

    def _auto_update_barcode_name(self):
        # تحديث المعاينة تلقائياً عند كتابة الاسم
        if hasattr(self, '_preview_job') and self._preview_job:
            try:
                self.after_cancel(self._preview_job)
            except Exception:
                pass
        self._preview_job = self.after(400, self._update_barcode_preview)

    def _filter_price(self, *_):
        txt = self.price_entry.get()
        allowed = "".join(c for c in txt if c.isdigit() or c in ".,")
        allowed = allowed.replace(",", ".")
        if allowed.count(".") > 1:
            parts = allowed.split(".")
        allowed = parts[0] + "." + "".join(parts[1:])
        if allowed != txt:
            self.price_entry.delete(0, "end")
        self.price_entry.insert(0, allowed)

    def _filter_int(self, *_):
        txt = self.stock_entry.get()
        filt = "".join(c for c in txt if c.isdigit())
        if filt != txt:
            self.stock_entry.delete(0, "end")
        self.stock_entry.insert(0, filt)

    def _save_product(self):
        name = self.name_entry.get().strip()
        barcode = self.barcode_entry.get().strip()
        cat_disp = self.cat_menu.get()
        category = self.cat_map.get(cat_disp, cat_disp)
        price = self.price_entry.get().strip() or "0"
        stock = self.stock_entry.get().strip() or "0"
        desc = self.desc_entry.get().strip()

        if not name:
            self._toast(reshape_arabic("ادخل اسم المنتج"), COLORS["danger"])
        return
        if not barcode:
            from prot.db.database import get_unique_barcode
        barcode = get_unique_barcode()
        try:
            price_f = float(price)
            stock_i = int(stock)
        except ValueError:
            self._toast(reshape_arabic("السعر/المخزون غير صحيح"), COLORS["danger"])
        return
        try:
            path = generate_barcode_image(barcode, name)
        except Exception:
            path = ""
        try:
            pid, code = add_product(name, category, price_f, stock_i, desc, barcode, barcode_path=path)
            self._toast(reshape_arabic(f"تم حفظ {name}"), COLORS["success"])
            self._clear_form()
            self._refresh_table()
        except ValueError as e:
            self._toast(reshape_arabic(str(e)), COLORS["danger"])
        except Exception as e:
            self._toast(reshape_arabic(f"خطأ: {e}"), COLORS["danger"])

    def _start_edit(self, prod):
        self._editing_id = prod["id"]
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, prod["name"])
        self.barcode_entry.delete(0, "end")
        self.barcode_entry.insert(0, prod["barcode"])
        # فئة
        try:
            # عكس الخريطة للعرض
            disp = None
            for k, v in self.cat_map.items():
                if v == prod["category"]:
                    disp = k
                    break
            if disp:
                self.cat_menu.set(disp)
        except Exception:
            pass
        self.price_entry.delete(0, "end")
        self.price_entry.insert(0, str(prod["price"]))
        self.stock_entry.delete(0, "end")
        self.stock_entry.insert(0, str(prod["stock"]))
        self.desc_entry.delete(0, "end")
        self.desc_entry.insert(0, prod["description"] or "")

        self.form_title.configure(text=reshape_arabic(f"تعديل: {prod['name'][:20]}"))
        self.save_btn.pack_forget()
        self.edit_btns.pack(fill="x", padx=20, pady=(0, 8))
        self._update_barcode_preview()
        self._toast(reshape_arabic("وضع التعديل"), COLORS["info"])

    def _update_product(self):
        if not self._editing_id:
            return
        name = self.name_entry.get().strip()
        barcode = self.barcode_entry.get().strip()
        cat_disp = self.cat_menu.get()
        category = self.cat_map.get(cat_disp, cat_disp)
        price = self.price_entry.get().strip() or "0"
        stock = self.stock_entry.get().strip() or "0"
        desc = self.desc_entry.get().strip()
        if not name or not barcode:
            self._toast(reshape_arabic("اكمل البيانات"), COLORS["danger"])
        return
        try:
            path = generate_barcode_image(barcode, name)
        except Exception:
            path = None
        ok = update_product(self._editing_id, name=name, category=category, price=price, stock=stock, description=desc, barcode=barcode, barcode_path=path)
        if ok:
            self._toast(reshape_arabic("تم التحديث"), COLORS["success"])
            self._cancel_edit()
            self._refresh_table()
        else:
            self._toast(reshape_arabic("فشل التحديث - الباركود مكرر؟"), COLORS["danger"])

    def _cancel_edit(self):
        self._editing_id = None
        self.edit_btns.pack_forget()
        self.save_btn.pack(fill="x", padx=20, pady=(0, 8))
        self.form_title.configure(text=reshape_arabic("إضافة منتج"))
        self._clear_form()

    def _clear_form(self):
        self.name_entry.delete(0, "end")
        # لا تمسح الباركود بل ولّد جديد
        self._generate_new_barcode()
        self.price_entry.delete(0, "end")
        self.stock_entry.delete(0, "end")
        self.desc_entry.delete(0, "end")
        try:
            self.cat_menu.set(list(self.cat_map.keys())[0])
        except Exception:
            pass
        if self._editing_id:
            self._cancel_edit()

    def _delete_confirm(self, pid):
        prod = get_product_by_id(pid)
        if not prod:
            return
        win = ctk.CTkToplevel(self)
        win.title("")
        win.geometry("360x180")
        win.configure(fg_color=COLORS["bg_dark"])
        make_undecorated(win)
        enable_resize(win, 320, 160)
        x = (self.winfo_screenwidth() - 360)//2
        y = (self.winfo_screenheight() - 180)//2
        win.geometry(f"360x180+{x}+{y}")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(win, text=reshape_arabic("حذف المنتج؟"), font=FONT_BODY_BOLD, text_color="white").pack(pady=(24, 6))
        ctk.CTkLabel(win, text=reshape_arabic(prod["name"]), font=FONT_BODY, text_color=COLORS["text_light"]).pack()
        ctk.CTkLabel(win, text=prod["barcode"], font=FONT_SMALL, text_color=COLORS["accent"]).pack(pady=(0, 12))
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack()

        def do_delete():
            # شغّل الحذف في thread حتى لا يتجمد الـ UI لو القاعدة مقفولة
            def worker():
                try:
                    ok = delete_product(pid)
                except Exception as e:
                        ok = False
                        err = str(e)
                else:
                        err = ""
                def on_done():
                    try:
                        win.destroy()
                    except Exception:
                        pass
                try:
                    self._refresh_table()
                except Exception:
                    pass
                if ok:
                    self._toast(reshape_arabic("تم الحذف"), COLORS["success"])
                else:
                    msg = reshape_arabic("فشل الحذف — قاعدة البيانات مشغولة، حاول ثانية") if "locked" in err.lower() else reshape_arabic("فشل الحذف — المنتج مرتبط بمبيعات؟")
                    self._toast(msg, COLORS["danger"])
            try:
                self.after(0, on_done)
            except Exception:
                pass
        import threading
        threading.Thread(target=worker, daemon=True).start()

        ctk.CTkButton(row, text=reshape_arabic("حذف"), font=FONT_BODY_BOLD, width=90, height=34, fg_color=COLORS["danger"], hover_color="#a83232", text_color="white",
                  command=do_delete).pack(side="left", padx=6)
        ctk.CTkButton(row, text=reshape_arabic("إلغاء"), font=FONT_BODY, width=90, height=34, fg_color="transparent", border_width=1, border_color=COLORS["border"], text_color=COLORS["text_light"],
                  command=win.destroy).pack(side="left", padx=6)
        win.bind("<Escape>", lambda e: win.destroy())

    def _show_barcode(self, pid):
        prod = get_product_by_id(pid)
        if not prod:
            return
        code = prod["barcode"]
        name = prod["name"]
        # تأكد من وجود الصورة
        path = prod.get("barcode_path") or ""
        if not path or not os.path.exists(path):
            try:
                path = generate_barcode_image(code, name)
                update_product(pid, barcode_path=path)
            except Exception:
                path = ""
        win = ctk.CTkToplevel(self)
        win.title("")
        win.geometry("520x380")
        win.configure(fg_color=COLORS["bg_dark"])
        make_undecorated(win)
        enable_resize(win, 400, 300)
        x = (self.winfo_screenwidth() - 520)//2
        y = (self.winfo_screenheight() - 380)//2
        win.geometry(f"520x380+{x}+{y}")
        win.transient(self)
        win.grab_set()
        TitleBar(win, f"باركود {name}", win.destroy).pack(fill="x")
        win.bind("<Escape>", lambda e: win.destroy())
        container = ctk.CTkFrame(win, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=16)
        ctk.CTkLabel(container, text=reshape_arabic(name), font=FONT_HEADER, text_color=COLORS["accent"]).pack(pady=(6, 4))
        ctk.CTkLabel(container, text=code, font=(FONT_ARABIC, 14), text_color=COLORS["text_light"]).pack()
        if path and os.path.exists(path):
            try:
                img = Image.open(path)
                # تكبير للعرض
                w, h = img.size
                max_w = 480
                if w > max_w:
                    ratio = max_w / w
                    img = img.resize((max_w, int(h * ratio)), Image.LANCZOS)
                ctk_img = CTkImage(light_image=img, dark_image=img, size=img.size)
                lbl = ctk.CTkLabel(container, text="", image=ctk_img)
                lbl.pack(pady=12)
                lbl.image = ctk_img
            except Exception as e:
                ctk.CTkLabel(container, text=f"خطأ: {e}", text_color=COLORS["danger"]).pack(pady=20)
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(pady=(12, 0))
        ctk.CTkButton(btn_row, text=reshape_arabic("طباعة"), font=FONT_BODY_BOLD, width=120, height=36, fg_color=COLORS["info"], hover_color=COLORS["info_hover"], text_color="white",
                  command=lambda: self._print_barcode(pid, win)).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text=reshape_arabic("إغلاق"), font=FONT_BODY, width=120, height=36, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="white", command=win.destroy).pack(side="left", padx=6)

    def _print_barcode(self, pid, parent_win=None):
        prod = get_product_by_id(pid)
        if not prod:
            self._toast(reshape_arabic("المنتج غير موجود"), COLORS["danger"])
        return
        self._toast(reshape_arabic("جاري طباعة الباركود..."), COLORS["info"])
        def worker():
            try:
                # صورة ستيكر متناسبة مع مقاس الستيكر
                img = generate_product_sticker(prod)
                from printing import print_pil_image, printer_available
                if not printer_available():
                    self.after(0, lambda: self._toast(reshape_arabic("الطابعة غير متصلة"), COLORS["warning"]))
                return
                ok, msg = print_pil_image(img, copies=1)
                self.after(0, lambda: self._toast(reshape_arabic(msg), COLORS["success"] if ok else COLORS["danger"]))
                if ok and parent_win is not None:
                    try:
                        self.after(0, lambda: parent_win.destroy() if parent_win.winfo_exists() else None)
                    except Exception:
                        pass
            except Exception as e:
                self.after(0, lambda: self._toast(reshape_arabic(f"خطأ الطباعة: {e}"), COLORS["danger"]))
        threading.Thread(target=worker, daemon=True).start()

    # ==================== POS للمستخدم العادي (employee) - تم إكماله ====================
    def _build_pos_cart(self, parent):
        # تنظيف أي محتوى سابق لإعادة البناء عند تغيير حجم الخط
        try:
            for w in parent.winfo_children():
                w.destroy()
        except Exception:
            pass
        scale = self._get_cart_scale()
        fh = self._scaled_font(FONT_HEADER)
        fb = self._scaled_font(FONT_BODY)
        fbb = self._scaled_font(FONT_BODY_BOLD)
        fs = self._scaled_font(FONT_SMALL)
        hdr_h = self._scaled_height(48)
        frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=10)
        frame.pack(fill="both", expand=True)

        header = ctk.CTkFrame(frame, fg_color=COLORS["accent_dim"], height=hdr_h, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text=reshape_arabic("سلة المبيعات"), font=fh, text_color="white").pack(side="right", padx=self._scaled_width(15))
        ctk.CTkButton(header, text=reshape_arabic("مسح"), font=fs, width=self._scaled_width(60), height=self._scaled_height(28), corner_radius=6,
                  fg_color="transparent", border_width=1, border_color=COLORS["border_light"], hover_color=COLORS["bg_hover"], text_color="white",
                  command=self._clear_pos_cart).pack(side="left", padx=self._scaled_width(10))

        scan_row = ctk.CTkFrame(frame, fg_color="transparent")
        scan_row.pack(fill="x", padx=self._scaled_width(10), pady=(self._scaled_height(10), self._scaled_height(6)))
        ctk.CTkLabel(scan_row, text=reshape_arabic("باركود"), font=fs, text_color=COLORS["text_light"]).pack(side="right", padx=(0, self._scaled_width(6)))
        self.scan_entry = ctk.CTkEntry(scan_row, placeholder_text=reshape_arabic("امسح الباركود ثم Enter"), font=fb, height=self._scaled_height(44), corner_radius=8,
                                   fg_color=COLORS["bg_input"], border_color=COLORS["accent"], text_color="white", placeholder_text_color=COLORS["text_light"], justify="right")
        self.scan_entry.pack(side="right", fill="x", expand=True, padx=(0, self._scaled_width(6)))
        ctk.CTkButton(scan_row, text=reshape_arabic("إضافة"), font=fs, width=self._scaled_width(60), height=self._scaled_height(34), fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="white",
                  command=self._on_scan_enter).pack(side="right")
        self.scan_entry.bind("<Return>", lambda e: self._on_scan_enter())
        self.scan_entry.bind("<KP_Enter>", lambda e: self._on_scan_enter())
        self.after(500, lambda: self.scan_entry.focus_set() if self._pos_inited else None)
        self._scan_buffer = ""
        self.bind_all("<Key>", self._on_global_scan, add=True)
        def _ensure_scan_focus():
            try:
                if self._pos_inited and self.winfo_exists():
                    foc = self.focus_get()
                det_entry = getattr(self, 'det_qty_entry', None)
                det_inner = getattr(det_entry, '_entry', None) if det_entry else None
                scan_inner = getattr(self.scan_entry, '_entry', None)
                if foc not in (self.scan_entry, scan_inner, det_entry, det_inner):
                    try:
                        self.scan_entry.focus_set()
                    except Exception:
                        pass
            except Exception:
                pass
        try:
            self.after(1500, _ensure_scan_focus)
        except Exception:
            pass
        self.after(800, _ensure_scan_focus)
        self._pos_inited = True

        cols = ctk.CTkFrame(frame, fg_color=COLORS["bg_input"], corner_radius=0)
        cols.pack(fill="x", padx=self._scaled_width(10), pady=(self._scaled_height(4), 0))
        for txt, w in [(reshape_arabic("حذف"), 60), (reshape_arabic("المجموع"), 80), (reshape_arabic("الكمية"), 70), (reshape_arabic("السعر"), 80), (reshape_arabic("المنتج"), 140)]:
                ctk.CTkLabel(cols, text=txt, font=fbb, text_color=COLORS["accent"], width=self._scaled_width(w)).pack(side="right", padx=self._scaled_width(4), pady=self._scaled_height(8))

        self.cart_scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self.cart_scroll.pack(fill="both", expand=True, padx=self._scaled_width(10), pady=(self._scaled_height(6), self._scaled_height(6)))

        self.total_frame = ctk.CTkFrame(frame, fg_color=COLORS["bg_input"], corner_radius=8)
        self.total_frame.pack(fill="x", padx=self._scaled_width(10), pady=(self._scaled_height(6), self._scaled_height(10)))
        self.total_label = ctk.CTkLabel(self.total_frame, text=reshape_arabic("الإجمالي: 0.00 جنيه  |  0 قطعة"), font=fbb, text_color=COLORS["success"])
        self.total_label.pack(pady=self._scaled_height(10))

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=self._scaled_width(10), pady=(0, self._scaled_height(10)))
        self.pay_btn = ctk.CTkButton(btn_row, text=reshape_arabic("تم الدفع"), font=fbb, height=self._scaled_height(48), corner_radius=8,
                                 fg_color=COLORS["success"], hover_color=COLORS["success_hover"], text_color="white",
                                 command=self._checkout_pos)
        self.pay_btn.pack(side="left", fill="x", expand=True, padx=(0, self._scaled_width(6)))
        self.cancel_btn = ctk.CTkButton(btn_row, text=reshape_arabic("إلغاء"), font=fbb, height=self._scaled_height(48), corner_radius=8,
                                    fg_color=COLORS["danger"], hover_color="#a83232", text_color="white",
                                    command=self._clear_pos_cart)
        self.cancel_btn.pack(side="left", fill="x", expand=True, padx=(self._scaled_width(6), 0))
        self._pos_cart_frame = frame

    def _build_pos_details(self, parent):
        try:
            for w in parent.winfo_children():
                w.destroy()
        except Exception:
            pass
        scale = self._get_cart_scale()
        fh = self._scaled_font(FONT_HEADER)
        fb = self._scaled_font(FONT_BODY)
        fbb = self._scaled_font(FONT_BODY_BOLD)
        fs = self._scaled_font(FONT_SMALL)
        hdr_h = self._scaled_height(48)
        wrap = self._scaled_width(320)
        frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=10)
        frame.pack(fill="both", expand=True)

        header = ctk.CTkFrame(frame, fg_color=COLORS["accent_dim"], height=hdr_h, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text=reshape_arabic("تفاصيل المنتج"), font=fh, text_color="white").pack(expand=True)

        self.details_scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self.details_scroll.pack(fill="both", expand=True, padx=self._scaled_width(12), pady=self._scaled_width(12))

        self.det_name = ctk.CTkLabel(self.details_scroll, text=reshape_arabic("—"), font=fbb, text_color=COLORS["text_white"], wraplength=wrap, anchor="e", justify="right")
        self.det_name.pack(fill="x", pady=self._scaled_height(4))
        self.det_barcode = ctk.CTkLabel(self.details_scroll, text="—", font=fb, text_color=COLORS["text_light"])
        self.det_barcode.pack(fill="x", pady=self._scaled_height(2))
        self.det_serial = ctk.CTkLabel(self.details_scroll, text="—", font=fb, text_color=COLORS["accent"])
        self.det_serial.pack(fill="x", pady=self._scaled_height(2))
        self.det_price = ctk.CTkLabel(self.details_scroll, text="—", font=fbb, text_color=COLORS["success"])
        self.det_price.pack(fill="x", pady=self._scaled_height(2))
        self.det_stock = ctk.CTkLabel(self.details_scroll, text=reshape_arabic("المتاح: —"), font=fb, text_color=COLORS["text_light"])
        self.det_stock.pack(fill="x", pady=self._scaled_height(6))

        qty_row = ctk.CTkFrame(self.details_scroll, fg_color="transparent")
        qty_row.pack(fill="x", pady=self._scaled_height(10))
        ctk.CTkLabel(qty_row, text=reshape_arabic("العدد المطلوب"), font=fs, text_color=COLORS["text_light"]).pack(anchor="e", pady=(0, self._scaled_height(4)))
        qty_ctrl = ctk.CTkFrame(qty_row, fg_color="transparent")
        qty_ctrl.pack(fill="x")
        ctk.CTkButton(qty_ctrl, text="−", width=self._scaled_width(40), height=self._scaled_height(36), fg_color=COLORS["bg_input"], hover_color=COLORS["bg_hover"], text_color="white",
                  command=lambda: self._change_selected_qty(-1)).pack(side="right", padx=self._scaled_width(2))
        self.det_qty_entry = ctk.CTkEntry(qty_ctrl, width=self._scaled_width(80), height=self._scaled_height(36), justify="center", font=fb, fg_color=COLORS["bg_input"], text_color="white", border_color=COLORS["border"])
        self.det_qty_entry.insert(0, "1")
        self.det_qty_entry.pack(side="right", padx=self._scaled_width(4))
        self.det_qty_entry.bind("<KeyRelease>", lambda e: self._on_det_qty_typed())
        ctk.CTkButton(qty_ctrl, text="+", width=self._scaled_width(40), height=self._scaled_height(36), fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="white",
                  command=lambda: self._change_selected_qty(1)).pack(side="right", padx=self._scaled_width(2))
        ctk.CTkButton(qty_ctrl, text=reshape_arabic("تحديث"), font=fs, width=self._scaled_width(60), height=self._scaled_height(36), fg_color=COLORS["info"], hover_color=COLORS["info_hover"], text_color="white",
                  command=self._apply_det_qty).pack(side="right", padx=(self._scaled_width(6), 0))

        ctk.CTkLabel(self.details_scroll, text=reshape_arabic("مثال: القطعة 50 جنيه، الكمية 2 → الإجمالي 100"), font=fs, text_color=COLORS["text_light"], wraplength=wrap, justify="right").pack(fill="x", pady=(self._scaled_height(12), 0))
        self._refresh_pos_details(None)
        self._pos_details_frame = frame

    def _on_scan_enter(self):
        code = self.scan_entry.get().strip() if hasattr(self, 'scan_entry') else ""
        if not code:
            return
        prod = get_product_by_barcode(code)
        if not prod:
            self._toast(reshape_arabic(f"غير موجود: {code}"), COLORS["danger"])
            try:
                self.scan_entry.delete(0, "end")
            except Exception:
                pass
            return
        self._add_product_to_cart(prod)
        try:
            self.scan_entry.delete(0, "end")
            self.scan_entry.focus_set()
        except Exception:
            pass

    def _on_global_scan(self, event):
        if not getattr(self, '_pos_inited', False) or not hasattr(self, 'scan_entry'):
            return
        try:
            focused = self.focus_get()
            det = getattr(self, 'det_qty_entry', None)
            det_inner = getattr(det, '_entry', None) if det else None
            scan_inner = getattr(self.scan_entry, '_entry', None)
            if focused in (det, det_inner, self.scan_entry, scan_inner):
                return
            if event.keysym in ("Return", "KP_Enter", "Escape", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Up", "Down", "Left", "Right"):
                return
            if event.char and event.char.isprintable() and event.char not in ('\n','\r','\t'):
                try:
                    self.scan_entry.focus_set()
                    try:
                        self.scan_entry.insert("end", event.char)
                    except Exception:
                        try:
                            scan_inner.insert("end", event.char)
                        except Exception:
                            pass
                    return "break"
                except Exception:
                    pass
        except Exception:
            pass

    def _add_product_to_cart(self, prod):
        avail = int(prod.get("stock", 0))
        for item in self._cart:
            if item["product"]["id"] == prod["id"]:
                if item["qty"] + 1 > avail:
                    self._toast(reshape_arabic(f"المتاح فقط {avail}"), COLORS["warning"])
                    return
                item["qty"] += 1
                self._refresh_pos_cart()
                self._refresh_pos_details(prod)
                self._toast(reshape_arabic(f"تم زيادة {prod['name']}"), COLORS["info"])
                return
        if avail < 1:
            self._toast(reshape_arabic("نفد المخزون"), COLORS["danger"])
            return
        self._cart.append({"product": prod, "qty": 1})
        self._refresh_pos_cart()
        self._refresh_pos_details(prod)
        self._selected_product = prod

    def _refresh_pos_cart(self):
        if not hasattr(self, 'cart_scroll'):
            return
        for w in self.cart_scroll.winfo_children():
            w.destroy()
        scale = self._get_cart_scale()
        fb = self._scaled_font(FONT_BODY)
        fbb = self._scaled_font(FONT_BODY_BOLD)
        fs = ("DejaVu Sans", max(8, int(round(10 * scale))), "bold")
        if not self._cart:
            ctk.CTkLabel(self.cart_scroll, text=reshape_arabic("السلة فارغة — امسح باركود"), font=fb, text_color=COLORS["text_light"]).pack(pady=self._scaled_height(30))
            self._update_pos_total()
            return
        for idx, item in enumerate(self._cart):
            p = item["product"]
            qty = item["qty"]
            price = float(p.get("price", 0))
            total = price * qty
            bg = COLORS["bg_hover"] if idx % 2 == 0 else COLORS["bg_card"]
            row = ctk.CTkFrame(self.cart_scroll, fg_color=bg, corner_radius=6)
            row.pack(fill="x", pady=self._scaled_height(2))
            ctk.CTkButton(row, text="✕", font=fs, width=self._scaled_width(36), height=self._scaled_height(28), corner_radius=4,
                          fg_color=COLORS["danger"], hover_color="#a83232", text_color="white",
                          command=lambda i=idx: self._remove_cart_item(i)).pack(side="right", padx=self._scaled_width(4), pady=self._scaled_height(6))
            ctk.CTkLabel(row, text=f"{total:.2f}", font=fbb, text_color=COLORS["success"], width=self._scaled_width(80)).pack(side="right", padx=self._scaled_width(4), pady=self._scaled_height(6))
            qty_frame = ctk.CTkFrame(row, fg_color="transparent")
            qty_frame.pack(side="right", padx=self._scaled_width(4))
            ctk.CTkButton(qty_frame, text="−", width=self._scaled_width(28), height=self._scaled_height(22), fg_color=COLORS["bg_input"], hover_color=COLORS["bg_hover"], text_color="white",
                          command=lambda i=idx: self._change_cart_qty(i, -1)).pack(side="right", padx=self._scaled_width(1))
            ctk.CTkLabel(qty_frame, text=str(qty), font=fbb, text_color="white", width=self._scaled_width(30)).pack(side="right")
            ctk.CTkButton(qty_frame, text="+", width=self._scaled_width(28), height=self._scaled_height(22), fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="white",
                          command=lambda i=idx: self._change_cart_qty(i, 1)).pack(side="right", padx=self._scaled_width(1))
            ctk.CTkLabel(row, text=f"{price:.2f}", font=fb, text_color=COLORS["text_light"], width=self._scaled_width(80)).pack(side="right", padx=self._scaled_width(4), pady=self._scaled_height(6))
            # ضبط طول الاسم حسب الحجم لتفادي التداخل
            name_len = max(8, int(18 / max(1, scale ** 0.5))) if scale > 2 else 18
            ctk.CTkLabel(row, text=reshape_arabic(p["name"][:name_len]), font=fb, text_color="white", width=self._scaled_width(140)).pack(side="right", padx=self._scaled_width(4), pady=self._scaled_height(6))
            for ch in row.winfo_children():
                ch.bind("<Button-1>", lambda e, prod=p: self._refresh_pos_details(prod))
            row.bind("<Button-1>", lambda e, prod=p: self._refresh_pos_details(prod))
        self._update_pos_total()

    def _refresh_pos_details(self, prod):
        if prod is None:
            self.det_name.configure(text=reshape_arabic("اختر منتج أو امسح باركود"))
            self.det_barcode.configure(text="—")
            self.det_serial.configure(text="—")
            self.det_price.configure(text="—")
            self.det_stock.configure(text=reshape_arabic("المتاح: —"))
            try:
                self.det_qty_entry.delete(0, "end")
                self.det_qty_entry.insert(0, "1")
            except Exception:
                pass
            self._selected_product = None
            return
        self._selected_product = prod
        # إعادة قراءة المخزون الحالي من DB لضمان دقة المتاح
        try:
            fresh = get_product_by_id(prod["id"])
            if fresh:
                prod = fresh
        except Exception:
            pass
        self.det_name.configure(text=reshape_arabic(prod.get("name","—")))
        self.det_barcode.configure(text=reshape_arabic(f"باركود: {prod.get('barcode','—')}"))
        self.det_serial.configure(text=f"#{prod.get('id',0):04d}")
        self.det_price.configure(text=reshape_arabic(f"{float(prod.get('price',0)):.2f} جنيه"))
        self.det_stock.configure(text=reshape_arabic(f"المتاح: {int(prod.get('stock',0))} قطعة"))
        qty_in_cart = 1
        for it in self._cart:
            if it["product"]["id"] == prod["id"]:
                qty_in_cart = it["qty"]
            break
        try:
            self.det_qty_entry.delete(0, "end")
            self.det_qty_entry.insert(0, str(qty_in_cart))
        except Exception:
            pass

    def _update_pos_total(self):
        if not hasattr(self, 'total_label'):
            return
        total = sum(float(it["product"].get("price",0)) * it["qty"] for it in self._cart)
        count = sum(it["qty"] for it in self._cart)
        self.total_label.configure(text=reshape_arabic(f"{count} قطعة  |  الإجمالي: {total:.2f} جنيه"))

    def _remove_cart_item(self, idx):
        if 0 <= idx < len(self._cart):
            prod = self._cart[idx]["product"]
        del self._cart[idx]
        self._refresh_pos_cart()
        self._toast(reshape_arabic(f"تم حذف {prod['name']}"), COLORS["warning"])

    def _change_cart_qty(self, idx, delta):
        if not (0 <= idx < len(self._cart)):
            return
        item = self._cart[idx]
        # قراءة مخزون حديث
        try:
            fresh = get_product_by_id(item["product"]["id"])
            avail = int(fresh.get("stock", 0)) if fresh else int(item["product"].get("stock", 0))
        except Exception:
            avail = int(item["product"].get("stock", 0))
        new_qty = item["qty"] + delta
        if new_qty < 1:
            self._remove_cart_item(idx)
        return
        if new_qty > avail:
            self._toast(reshape_arabic(f"المتاح {avail}"), COLORS["warning"])
        return
        item["qty"] = new_qty
        self._refresh_pos_cart()
        if self._selected_product and self._selected_product["id"] == item["product"]["id"]:
            self._refresh_pos_details(item["product"])

    def _change_selected_qty(self, delta):
        if not self._selected_product:
            return
        for idx, it in enumerate(self._cart):
            if it["product"]["id"] == self._selected_product["id"]:
                self._change_cart_qty(idx, delta)
            return
        if delta > 0:
            self._add_product_to_cart(self._selected_product)

    def _on_det_qty_typed(self):
        pass

    def _apply_det_qty(self):
        if not self._selected_product:
            return
        try:
            qty = int(self.det_qty_entry.get().strip() or "1")
        except ValueError:
            return
        if qty < 1:
            qty = 1
        try:
            fresh = get_product_by_id(self._selected_product["id"])
            avail = int(fresh.get("stock", 0)) if fresh else int(self._selected_product.get("stock", 0))
        except Exception:
            avail = int(self._selected_product.get("stock", 0))
        if qty > avail:
            self._toast(reshape_arabic(f"المتاح {avail}"), COLORS["warning"])
        qty = avail
        for idx, it in enumerate(self._cart):
            if it["product"]["id"] == self._selected_product["id"]:
                it["qty"] = qty
            self._refresh_pos_cart()
            return
        if qty <= avail:
            self._cart.append({"product": self._selected_product, "qty": qty})
        self._refresh_pos_cart()

    def _clear_pos_cart(self):
        if not self._cart:
            return
        self._cart.clear()
        self._refresh_pos_cart()
        self._refresh_pos_details(None)
        self._toast(reshape_arabic("تم إلغاء السلة"), COLORS["text_light"])

    def _checkout_pos(self):
        if not self._cart:
            self._toast(reshape_arabic("السلة فارغة"), COLORS["warning"])
        return
        total = sum(float(it["product"].get("price",0)) * it["qty"] for it in self._cart)
        count = sum(it["qty"] for it in self._cart)
        # التحقق من إعداد تخزين المبيعات (قائمة المبيعات)
        sales_enabled = True
        try:
            sales_enabled = is_sales_enabled()
        except Exception:
            sales_enabled = True
        try:
            if sales_enabled:
                for it in self._cart:
                    p = it["product"]
                    qty = it["qty"]
                # add_sale يخصم المخزون تلقائياً — لا نستدعي update_product منفصل
                    add_sale(p["id"], p["name"], p["barcode"], float(p.get("price",0)), qty)
                create_sale_group(total, count)
            else:
                # التخزين متوقف: خصم المخزون فقط بدون إدخال في المبيعات
                for it in self._cart:
                    p = it["product"]
                    qty = it["qty"]
                    try:
                        fresh = get_product_by_id(p["id"])
                        cur_stock = int(fresh.get("stock", 0)) if fresh else int(p.get("stock", 0))
                    except Exception:
                        cur_stock = int(p.get("stock", 0))
                    new_stock = max(0, cur_stock - int(qty))
                    update_product(p["id"], stock=new_stock)
        except Exception as e:
            self._toast(reshape_arabic(f"خطأ حفظ: {e}"), COLORS["danger"])
        return
        if sales_enabled:
            self._toast(reshape_arabic(f"تم الدفع {total:.2f} جنيه — تم التخزين"), COLORS["success"])
        else:
            self._toast(reshape_arabic(f"تم الدفع {total:.2f} جنيه — بدون تخزين"), COLORS["warning"])
        self._cart.clear()
        self._refresh_pos_cart()
        self._refresh_pos_details(None)
        # تحديث جدول المنتجات لو الأدمن فاتحه في نفس الجلسة (اختياري)
        try:
            if hasattr(self, 'scroll') and self.user.get("role") == "admin":
                self._refresh_table()
        except Exception:
            pass
        # طباعة فاتورة مبسطة — تحترم إعدادات الأدمن وصلاحيات المستخدم
        try:
            can_print = True
            try:
                can_print = is_invoice_enabled()
            except Exception:
                can_print = True
            # صلاحيات المستخدم العادي
            if can_print and self.user.get("role") != "admin":
                try:
                    if not is_user_invoice_enabled():
                        can_print = False
                except Exception:
                    pass
            if not can_print:
                # الطباعة موقوفة حسب الإعدادات — لا تطبع
                pass
            else:
                from printing import printer_available
            if printer_available():
                from printing import print_pil_image
                from PIL import ImageDraw, ImageFont
                W, H = 384, 280
                img = Image.new("RGB", (W, H), "white")
                draw = ImageDraw.Draw(img)
                try:
                    f = ImageFont.truetype("assets/fonts/Cairo.ttf", 20)
                except Exception:
                    f = ImageFont.load_default()
                draw.text((W//2, 20), reshape_arabic(f"فاتورة - {count} قطعة"), fill="black", font=f, anchor="mm")
                draw.text((W//2, 55), f"{total:.2f} جنيه", fill="black", font=f, anchor="mm")
                draw.text((W//2, 90), datetime.now().strftime("%Y/%m/%d %H:%M"), fill="black", font=f, anchor="mm")
                def worker():
                    try:
                        print_pil_image(img, copies=1)
                    except Exception:
                        pass
                threading.Thread(target=worker, daemon=True).start()
        except Exception:
            pass

    def _open_search(self):
        # للادمن: focus على search_entry — للمستخدم: focus على scan_entry
        try:
            if getattr(self, '_pos_inited', False) and hasattr(self, 'scan_entry'):
                self.scan_entry.focus_set()
            else:
                self.search_entry.focus_set()
        except Exception:
            pass

    def _open_settings(self):
        """نافذة الإعدادات — للأدمن: كل الخيارات، للمستخدم العادي: حجم خط السلة فقط (نافذة إعدادات في صلاحيات المستخدم)"""
        is_admin = self.user.get("role") == "admin"
        win = ctk.CTkToplevel(self)
        win.title("")
        win.geometry("520x640")
        win.configure(fg_color=COLORS["bg_dark"])
        make_undecorated(win)
        enable_resize(win, 480, 420)
        x = (self.winfo_screenwidth() - 520)//2
        y = (self.winfo_screenheight() - 640)//2
        win.geometry(f"520x640+{x}+{y}")
        win.transient(self)
        win.grab_set()
        win.attributes("-topmost", True)
        win.after(200, lambda: win.attributes("-topmost", False) if win.winfo_exists() else None)
        TitleBar(win, "الإعدادات", win.destroy).pack(fill="x")
        win.bind("<Escape>", lambda e: win.destroy())
        try:
            save_window_state("prot_settings", win.geometry())
        except Exception:
            pass

        container = ctk.CTkScrollableFrame(win, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=18, pady=14)

        if is_admin:
                # كارت تخزين المبيعات
            sales_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
            sales_frame.pack(fill="x", pady=(6, 12))
            ctk.CTkLabel(sales_frame, text=reshape_arabic("قائمة المبيعات"), font=FONT_HEADER, text_color=COLORS["accent"]).pack(anchor="e", padx=14, pady=(12, 4))
            ctk.CTkLabel(sales_frame, text=reshape_arabic("عند التفعيل سيتم حفظ كل عملية دفع في جدول المبيعات (sales + sale_groups) وخصم المخزون. عند الإيقاف سيتم خصم المخزون فقط بدون تخزين."), font=FONT_SMALL, text_color=COLORS["text_light"], anchor="e", wraplength=420, justify="right").pack(fill="x", padx=14, pady=(0, 10))

            # سويتش التفعيل
            enabled = is_sales_enabled()
            self._sales_enabled_var = ctk.BooleanVar(value=enabled)
            status_label = ctk.CTkLabel(sales_frame, text="", font=FONT_SMALL, wraplength=420, justify="right")
            status_label.pack(fill="x", padx=14, pady=(0, 8))
            def _update_status():
                en = self._sales_enabled_var.get()
                if en:
                    status_label.configure(text=reshape_arabic(f"مفعل — يتم التخزين (عدد المسجل: {get_sales_count()} عملية)"), text_color=COLORS["success"])
                else:
                    status_label.configure(text=reshape_arabic("متوقف — لن يتم التخزين"), text_color=COLORS["warning"])
            _update_status()

            def _on_toggle():
                en = self._sales_enabled_var.get()
                try:
                    set_sales_enabled(en)
                    _update_status()
                    self._toast(reshape_arabic("تم التفعيل — سيتم التخزين" if en else "تم الإيقاف — بدون تخزين"), COLORS["success"] if en else COLORS["warning"])
                except Exception as e:
                    self._toast(reshape_arabic(f"خطأ: {e}"), COLORS["danger"])

            switch = ctk.CTkSwitch(sales_frame, text=reshape_arabic("تفعيل تخزين المبيعات"), font=FONT_BODY_BOLD, variable=self._sales_enabled_var, command=_on_toggle, progress_color=COLORS["accent"], button_color=COLORS["text_white"], fg_color=COLORS["bg_input"], text_color=COLORS["text_light"])
            switch.pack(anchor="e", padx=14, pady=(0, 12))

            # أزرار عرض ومسح المبيعات
            btn_row = ctk.CTkFrame(sales_frame, fg_color="transparent")
            btn_row.pack(fill="x", padx=14, pady=(0, 14))
            ctk.CTkButton(btn_row, text=reshape_arabic("عرض المبيعات"), font=FONT_BODY_BOLD, height=38, corner_radius=8, fg_color=COLORS["info"], hover_color=COLORS["info_hover"], text_color="white", command=lambda: (win.destroy(), self._show_sales_list())).pack(side="right", padx=(0, 6), fill="x", expand=True)
            def _clear_sales():
                from prot.db.database import clear_all_sales
                # تأكيد
                confirm = ctk.CTkToplevel(win)
                confirm.geometry("320x160")
                confirm.configure(fg_color=COLORS["bg_dark"])
                make_undecorated(confirm)
                x2 = (self.winfo_screenwidth()-320)//2
                y2 = (self.winfo_screenheight()-160)//2
                confirm.geometry(f"320x160+{x2}+{y2}")
                confirm.transient(win)
                confirm.grab_set()
                ctk.CTkLabel(confirm, text=reshape_arabic("حذف كل المبيعات؟"), font=FONT_BODY_BOLD, text_color="white").pack(pady=(20, 8))
                ctk.CTkLabel(confirm, text=reshape_arabic("لا يمكن التراجع"), font=FONT_SMALL, text_color=COLORS["danger"]).pack()
                row = ctk.CTkFrame(confirm, fg_color="transparent")
                row.pack(pady=14)
                def do_clear():
                    try:
                        clear_all_sales()
                        _update_status()
                        self._toast(reshape_arabic("تم حذف المبيعات"), COLORS["success"])
                    except Exception as e:
                        self._toast(reshape_arabic(f"خطأ: {e}"), COLORS["danger"])
                    try:
                        confirm.destroy()
                    except Exception:
                        pass
                ctk.CTkButton(row, text=reshape_arabic("حذف"), width=80, height=32, fg_color=COLORS["danger"], hover_color="#a83232", text_color="white", command=do_clear).pack(side="left", padx=4)
                ctk.CTkButton(row, text=reshape_arabic("إلغاء"), width=80, height=32, fg_color="transparent", border_width=1, border_color=COLORS["border"], text_color=COLORS["text_light"], command=confirm.destroy).pack(side="left", padx=4)
                confirm.bind("<Escape>", lambda e: confirm.destroy())
            ctk.CTkButton(btn_row, text=reshape_arabic("مسح"), font=FONT_BODY, width=70, height=38, corner_radius=8, fg_color="transparent", border_width=1, border_color=COLORS["border"], hover_color=COLORS["bg_hover"], text_color=COLORS["text_light"], command=_clear_sales).pack(side="right")

                # كارت طباعة الفاتورة (صلاحيات الأدمن)
            invoice_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
            invoice_frame.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(invoice_frame, text=reshape_arabic("طباعة الفاتورة"), font=FONT_HEADER, text_color=COLORS["accent"]).pack(anchor="e", padx=14, pady=(12, 4))
            ctk.CTkLabel(invoice_frame, text=reshape_arabic("التحكم في طباعة فاتورة مبسطة بعد كل عملية دفع (عند توفر الطابعة)."), font=FONT_SMALL, text_color=COLORS["text_light"], anchor="e", wraplength=440, justify="right").pack(fill="x", padx=14, pady=(0, 10))
            inv_enabled = is_invoice_enabled()
            self._invoice_enabled_var = ctk.BooleanVar(value=inv_enabled)
            inv_status = ctk.CTkLabel(invoice_frame, text="", font=FONT_SMALL, wraplength=440, justify="right")
            inv_status.pack(fill="x", padx=14, pady=(0, 8))
            def _update_inv_status():
                en = self._invoice_enabled_var.get()
                inv_status.configure(text=reshape_arabic("مفعل — ستُطبع الفاتورة بعد الدفع" if en else "متوقف — لن تُطبع الفاتورة"), text_color=COLORS["success"] if en else COLORS["warning"])
            _update_inv_status()
            def _on_invoice_toggle():
                en = self._invoice_enabled_var.get()
                try:
                    set_invoice_enabled(en)
                    _update_inv_status()
                    try:
                        _update_user_inv_status()
                    except Exception:
                        pass
                    self._toast(reshape_arabic("تم تفعيل طباعة الفاتورة" if en else "تم إيقاف طباعة الفاتورة"), COLORS["success"] if en else COLORS["warning"])
                except Exception as e:
                    self._toast(reshape_arabic(f"خطأ: {e}"), COLORS["danger"])
            invoice_switch = ctk.CTkSwitch(invoice_frame, text=reshape_arabic("السماح بطباعة الفاتورة بعد الدفع"), font=FONT_BODY_BOLD, variable=self._invoice_enabled_var, command=_on_invoice_toggle, progress_color=COLORS["accent"], button_color=COLORS["text_white"], fg_color=COLORS["bg_input"], text_color=COLORS["text_light"])
            invoice_switch.pack(anchor="e", padx=14, pady=(0, 14))

                # كارت صلاحيات المستخدم العادي
            user_perm_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
            user_perm_frame.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(user_perm_frame, text=reshape_arabic("صلاحيات المستخدم العادي"), font=FONT_HEADER, text_color=COLORS["accent"]).pack(anchor="e", padx=14, pady=(12, 4))
            ctk.CTkLabel(user_perm_frame, text=reshape_arabic("التحكم فيما يُسمح به للمستخدم العادي (employee / 0000) داخل نظام الكاشير."), font=FONT_SMALL, text_color=COLORS["text_light"], anchor="e", wraplength=440, justify="right").pack(fill="x", padx=14, pady=(0, 10))
            user_inv_enabled = is_user_invoice_enabled()
            self._user_invoice_var = ctk.BooleanVar(value=user_inv_enabled)
            user_inv_status = ctk.CTkLabel(user_perm_frame, text="", font=FONT_SMALL, wraplength=440, justify="right")
            user_inv_status.pack(fill="x", padx=14, pady=(0, 8))
            def _update_user_inv_status():
                en = self._user_invoice_var.get()
                # لو الطباعة العامة متوقفة، يظهر تنبيه إضافي
                if not is_invoice_enabled():
                    user_inv_status.configure(text=reshape_arabic("متوقف عام — الطباعة موقوفة للجميع من الإعداد أعلاه"), text_color=COLORS["danger"])
                else:
                    user_inv_status.configure(text=reshape_arabic("مسموح للمستخدم بطباعة الفاتورة" if en else "ممنوع على المستخدم طباعة الفاتورة"), text_color=COLORS["success"] if en else COLORS["warning"])
            _update_user_inv_status()
            def _on_user_invoice_toggle():
                en = self._user_invoice_var.get()
                try:
                    set_user_invoice_enabled(en)
                    _update_user_inv_status()
                    self._toast(reshape_arabic("تم السماح للمستخدم بالطباعة" if en else "تم منع المستخدم من الطباعة"), COLORS["success"] if en else COLORS["warning"])
                except Exception as e:
                    self._toast(reshape_arabic(f"خطأ: {e}"), COLORS["danger"])
            ctk.CTkSwitch(user_perm_frame, text=reshape_arabic("السماح للمستخدم العادي بطباعة الفاتورة"), font=FONT_BODY_BOLD, variable=self._user_invoice_var, command=_on_user_invoice_toggle, progress_color=COLORS["accent"], button_color=COLORS["text_white"], fg_color=COLORS["bg_input"], text_color=COLORS["text_light"]).pack(anchor="e", padx=14, pady=(0, 14))

        
        # كارت حجم خط السلة — نافذة إعدادات في صلاحيات المستخدم (الإجمالي والدفع/الإلغاء)
        font_scale_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        font_scale_frame.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(font_scale_frame, text=reshape_arabic("حجم خط السلة — صلاحيات المستخدم"), font=FONT_HEADER, text_color=COLORS["accent"]).pack(anchor="e", padx=14, pady=(12, 4))
        ctk.CTkLabel(font_scale_frame, text=reshape_arabic("تكبير خط السلة والإجمالي وأزرار الدفع والإلغاء حتى 5 أضعاف مع ضبط عرض الأعمدة تلقائياً لمنع التداخل."), font=FONT_SMALL, text_color=COLORS["text_light"], anchor="e", wraplength=440, justify="right").pack(fill="x", padx=14, pady=(0, 10))
        # عرض الحجم الحالي
        try:
            cur_scale = float(get_cart_font_scale())
        except Exception:
            cur_scale = 1.0
        scale_value_label = ctk.CTkLabel(font_scale_frame, text=f"{cur_scale:.1f}x  —  {int(16*cur_scale)}px", font=FONT_BODY_BOLD, text_color=COLORS["accent"])
        scale_value_label.pack(anchor="e", padx=14, pady=(0, 6))
        scale_info = ctk.CTkLabel(font_scale_frame, text=reshape_arabic(f"الأساسي 16px × {cur_scale:.1f} = {int(16*cur_scale)}px"), font=FONT_SMALL, text_color=COLORS["text_light"])
        scale_info.pack(anchor="e", padx=14, pady=(0, 8))
        # سلايدر + أزرار
        slider_row = ctk.CTkFrame(font_scale_frame, fg_color="transparent")
        slider_row.pack(fill="x", padx=14, pady=(0, 8))
        # أزرار - و + و افتراضي
        btn_minus = ctk.CTkButton(slider_row, text="−", width=36, height=32, fg_color=COLORS["bg_input"], hover_color=COLORS["bg_hover"], text_color="white")
        btn_minus.pack(side="left", padx=(0, 6))
        btn_plus = ctk.CTkButton(slider_row, text="+", width=36, height=32, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="white")
        btn_plus.pack(side="left", padx=(0, 6))
        btn_reset = ctk.CTkButton(slider_row, text=reshape_arabic("افتراضي"), font=FONT_SMALL, width=70, height=32, fg_color="transparent", border_width=1, border_color=COLORS["border"], hover_color=COLORS["bg_hover"], text_color=COLORS["text_light"])
        btn_reset.pack(side="left")
        # سلايدر
        font_slider = ctk.CTkSlider(slider_row, from_=1.0, to=5.0, number_of_steps=40, progress_color=COLORS["accent"], button_color=COLORS["accent_hover"], button_hover_color=COLORS["accent"])
        font_slider.set(cur_scale)
        font_slider.pack(side="right", fill="x", expand=True, padx=(12, 0))
        def _apply_scale(new_scale, save=True):
            try:
                v = float(new_scale)
                v = max(1.0, min(5.0, v))
                v = round(v, 1)  # تقريب لـ 0.1 للسماح حتى 5.0 بدقة
                # حدث العرض
                scale_value_label.configure(text=f"{v:.1f}x  —  {int(16*v)}px")
                scale_info.configure(text=reshape_arabic(f"الأساسي 16px × {v:.1f} = {int(16*v)}px"))
                font_slider.set(v)
                if save:
                    set_cart_font_scale(v)
                    self._toast(reshape_arabic(f"حجم الخط {v:.1f}x"), COLORS["success"])
                    # إعادة بناء واجهة السلة مع ضبط العرض تلقائياً لمنع التداخل
                    self._rebuild_pos_ui()
            except Exception as e:
                self._toast(reshape_arabic(f"خطأ: {e}"), COLORS["danger"])
        def _on_slider(v):
            # v يأتي float من السلايدر
            try:
                _apply_scale(float(v), save=False)
            except Exception:
                pass
        def _on_slider_release(event=None):
            try:
                v = float(font_slider.get())
                _apply_scale(v, save=True)
            except Exception:
                pass
        font_slider.configure(command=_on_slider)
        font_slider.bind("<ButtonRelease-1>", _on_slider_release)
        # أزرار التحكم
        def _step(delta):
            try:
                cur = float(get_cart_font_scale())
            except Exception:
                cur = 1.0
            _apply_scale(cur + delta, save=True)
        btn_minus.configure(command=lambda: _step(-0.5))
        btn_plus.configure(command=lambda: _step(0.5))
        btn_reset.configure(command=lambda: _apply_scale(1.0, save=True))

        # كارت معلومات إضافية
        info_frame = ctk.CTkFrame(container, fg_color="transparent")
        info_frame.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(info_frame, text=reshape_arabic("الإعدادات تُحفظ في جدول settings داخل prot/db/products.db"), font=FONT_SMALL, text_color=COLORS["text_light"], wraplength=440, justify="right").pack(anchor="e")
        ctk.CTkButton(container, text=reshape_arabic("إغلاق"), font=FONT_BODY_BOLD, height=42, corner_radius=8, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="white", command=win.destroy).pack(fill="x", pady=(14, 0))

    def _show_sales_list(self):
        """نافذة عرض قائمة المبيعات (المخزنة عند تفعيل الإعداد)"""
        win = ctk.CTkToplevel(self)
        win.title("")
        win.geometry("820x540")
        win.configure(fg_color=COLORS["bg_dark"])
        make_undecorated(win)
        enable_resize(win, 700, 400)
        x = (self.winfo_screenwidth() - 820)//2
        y = (self.winfo_screenheight() - 540)//2
        win.geometry(f"820x540+{x}+{y}")
        win.transient(self)
        win.grab_set()
        TitleBar(win, "قائمة المبيعات", win.destroy).pack(fill="x")
        win.bind("<Escape>", lambda e: win.destroy())

        header = ctk.CTkFrame(win, fg_color=COLORS["bg_card"], height=44, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text=reshape_arabic(f"إجمالي العمليات: {get_sales_count()}"), font=FONT_BODY_BOLD, text_color=COLORS["accent"]).pack(side="right", padx=14)
        ctk.CTkButton(header, text=reshape_arabic("تحديث"), font=FONT_SMALL, width=70, height=28, corner_radius=6, fg_color="transparent", border_width=1, border_color=COLORS["border_light"], hover_color=COLORS["bg_hover"], text_color="white", command=lambda: _refresh()).pack(side="left", padx=12)

        cols = ctk.CTkFrame(win, fg_color=COLORS["bg_input"], corner_radius=0)
        cols.pack(fill="x", padx=12, pady=(10, 0))
        for txt, w in [(reshape_arabic("التاريخ"), 150), (reshape_arabic("المجموع"), 80), (reshape_arabic("الكمية"), 60), (reshape_arabic("السعر"), 80), (reshape_arabic("الباركود"), 130), (reshape_arabic("المنتج"), 160)]:
                ctk.CTkLabel(cols, text=txt, font=FONT_BODY_BOLD, text_color=COLORS["accent"], width=w).pack(side="right", padx=4, pady=8)

        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        def _refresh(search=""):
            for w in scroll.winfo_children():
                w.destroy()
            rows = get_all_sales(limit=300, search=search)
            if not rows:
                msg = reshape_arabic("لا توجد مبيعات محفوظة — فعّل التخزين من الإعدادات") if not is_sales_enabled() else reshape_arabic("لا توجد مبيعات بعد")
                ctk.CTkLabel(scroll, text=msg, font=FONT_BODY, text_color=COLORS["text_light"]).pack(pady=40)
                return
            for i, s in enumerate(rows):
                bg = COLORS["bg_hover"] if i % 2 == 0 else COLORS["bg_card"]
                row = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=6)
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=str(s["created_at"])[:19], font=FONT_SMALL, text_color=COLORS["text_light"], width=150).pack(side="right", padx=4, pady=6)
                ctk.CTkLabel(row, text=f"{float(s['total']):.2f}", font=FONT_BODY_BOLD, text_color=COLORS["success"], width=80).pack(side="right", padx=4, pady=6)
                ctk.CTkLabel(row, text=str(s["quantity"]), font=FONT_BODY, text_color="white", width=60).pack(side="right", padx=4, pady=6)
                ctk.CTkLabel(row, text=f"{float(s['price']):.2f}", font=FONT_BODY, text_color=COLORS["text_light"], width=80).pack(side="right", padx=4, pady=6)
                ctk.CTkLabel(row, text=s["barcode"], font=FONT_SMALL, text_color=COLORS["text_light"], width=130).pack(side="right", padx=4, pady=6)
                ctk.CTkLabel(row, text=reshape_arabic(s["product_name"][:18]), font=FONT_BODY, text_color="white", width=160).pack(side="right", padx=4, pady=6)
        _refresh()

        # بحث سريع
        search_row = ctk.CTkFrame(win, fg_color="transparent")
        search_row.pack(fill="x", padx=12, pady=(0, 10))
        search_entry = ctk.CTkEntry(search_row, placeholder_text=reshape_arabic("بحث باسم المنتج أو الباركود"), font=FONT_SMALL, height=34, fg_color=COLORS["bg_input"], text_color="white", border_color=COLORS["border"], justify="right")
        search_entry.pack(side="right", fill="x", expand=True, padx=(0, 6))
        search_entry.bind("<KeyRelease>", lambda e: _refresh(search_entry.get().strip()))
        ctk.CTkButton(search_row, text="⌕", width=40, height=34, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color="white", command=lambda: _refresh(search_entry.get().strip())).pack(side="right")

    def _show_toast(self, msg, color):
        # alias للتوافق مع كود main.py الرئيسي
        return self._toast(msg, color)

    def _toast(self, msg, color):
        try:
            t = ctk.CTkToplevel(self)
            make_undecorated(t)
            t.configure(fg_color=color)
            t.attributes("-topmost", True)
            w, h = 360, 52
            x = (self.winfo_screenwidth() - w)//2
            y = self.winfo_screenheight() - 80
            t.geometry(f"{w}x{h}+{x}+{y}")
            ctk.CTkLabel(t, text=msg, font=FONT_BODY_BOLD, text_color="white").pack(expand=True)
            t.after(1800, t.destroy)
        except Exception:
            pass


if __name__ == "__main__":
    init_db()
    # تشغيل عبر تسجيل الدخول أولاً (مطلوب) — fallback مباشر لو فشل الاستيراد
    try:
        from prot.login import ProtLoginWindow
        app = ProtLoginWindow()
    except Exception:
        app = ProtWindow()
    app.mainloop()
