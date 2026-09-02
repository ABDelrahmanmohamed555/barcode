# نظام المنتجات - prot

نظام منفصل لتخزين المنتجات وإنشاء باركود لكل منتج، بنفس ستايل وثيم المشروع الأساسي (كاشير).

## الهيكل
```
prot/
  config.py          # إعدادات وثيم (يورث COLORS من المشروع)
  db/database.py     # SQLite: جدول products
  barcode_utils.py   # توليد باركود Code128 + QR fallback
  main.py            # الواجهة الرئيسية CustomTkinter
  run.py             # تشغيل
  assets/barcodes/   # صور الباركود
```

## المميزات الحالية (البنية الأساسية)
- إضافة منتج: اسم، باركود تلقائي EAN13، فئة، سعر، مخزون، وصف
- باركود منفرد لكل منتج + معاينة حية
- جدول منتجات مع بحث فوري، تعديل ذهبي ✏، حذف أحمر ✕، عرض باركود أخضر ↻
- نفس الثيم الداكن #0d1117 + الذهبي #c8943a + TitleBar + مؤشر ذهبي

## التشغيل
```bash
./venv/bin/python prot/run.py
# أو
./venv/bin/python prot/main.py
```

## قاعدة البيانات
`prot/db/products.db` — جدول `products(id, name, barcode UNIQUE, category, price, stock, description, barcode_path, created_at)`
