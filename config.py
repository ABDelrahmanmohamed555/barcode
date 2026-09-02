import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# قاعدة بيانات المنتجات منفصلة تماماً عن المشروع الأساسي
DB_PATH = os.path.join(BASE_DIR, "db", "products.db")
BARCODES_DIR = os.path.join(BASE_DIR, "assets", "barcodes")
IMAGES_DIR = os.path.join(BASE_DIR, "assets", "images")
FONTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "assets", "fonts")
if not os.path.exists(FONTS_DIR):
    FONTS_DIR = os.path.join(BASE_DIR, "assets", "fonts")

APP_NAME = "نظام المنتجات - الباركود"

# ثيم منفصل مطابق للمشروع الأساسي (نسخة مستقلة لعدم الاعتماد عليه)
FONT_ARABIC = "Cairo"
FONT_ARABIC_BOLD = "Cairo"
FONT_SIZE_TITLE = 32
FONT_SIZE_HEADER = 18
FONT_SIZE_BODY = 16
FONT_SIZE_SMALL = 15
FONT_TITLE = (FONT_ARABIC_BOLD, FONT_SIZE_TITLE)
FONT_HEADER = (FONT_ARABIC_BOLD, FONT_SIZE_HEADER)
FONT_BODY = (FONT_ARABIC, FONT_SIZE_BODY)
FONT_BODY_BOLD = (FONT_ARABIC_BOLD, FONT_SIZE_BODY, "bold")
FONT_SMALL = (FONT_ARABIC, FONT_SIZE_SMALL)

COLORS = {
    "bg_dark": "#0d1117",
    "bg_card": "#151b23",
    "bg_input": "#1c2333",
    "bg_hover": "#252d3d",
    "accent": "#c8943a",
    "accent_hover": "#dbaa55",
    "accent_dim": "#a8782e",
    "text_white": "#f5f0e3",
    "text_light": "#9e9e9e",
    "success": "#2d8a4e",
    "success_hover": "#3aa05e",
    "danger": "#c73e3e",
    "warning": "#c8943a",
    "info": "#3a86c8",
    "info_hover": "#5aa0e0",
    "border": "#2d3543",
    "border_light": "#3d4758",
}

# فئات افتراضية
CATEGORIES = [
    "عام",
    "أجهزة",
    "قطع غيار",
    "إكسسوارات",
    "أخرى",
]

# إعدادات الباركود
BARCODE_TYPE = "code128"

# حسابات منفصلة لـ prot (لا تعتمد على المشروع الأساسي)
ADMIN_USERNAME = "codex"
ADMIN_PASSWORD = "010100"
EMPLOYEE_USERNAME = "0000"
EMPLOYEE_PASSWORD = "0000"

__all__ = ["BASE_DIR", "DB_PATH", "BARCODES_DIR", "IMAGES_DIR", "FONTS_DIR", "APP_NAME", "CATEGORIES", "BARCODE_TYPE",
           "COLORS", "FONT_ARABIC", "FONT_ARABIC_BOLD", "FONT_TITLE", "FONT_HEADER", "FONT_BODY", "FONT_BODY_BOLD", "FONT_SMALL",
           "ADMIN_USERNAME", "ADMIN_PASSWORD", "EMPLOYEE_USERNAME", "EMPLOYEE_PASSWORD"]
