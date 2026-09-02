# prot/login.py — نافذة دخول بخلفية متدرجة على كامل النافذة بدون فريم + عناوين ذهبية فاتحة
import os
import sys
BASE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_PARENT not in sys.path:
    sys.path.insert(0, BASE_PARENT)

import tkinter as tk
import customtkinter as ctk
from customtkinter import CTkImage
from PIL import Image, ImageDraw, ImageTk
from prot.config import FONT_TITLE, FONT_BODY, FONT_BODY_BOLD, FONT_SMALL, COLORS, BASE_DIR as PROT_BASE
from prot.db.database import authenticate
from utils import reshape_arabic, save_window_state, restore_or_center, apply_gold_cursor, make_undecorated, enable_resize
from config import BASE_DIR as MAIN_BASE

LOGO_PATH = os.path.join(MAIN_BASE, "icon.png")
if not os.path.exists(LOGO_PATH):
    LOGO_PATH = os.path.join(PROT_BASE, "icon.png")
APP_TITLE = "شركة النحال لقطع الغيار"

BRONZE = "#8c6239"
BRONZE_HOVER = "#a67c52"
LIGHT_GOLD = "#e8c9a0"


class ProtLoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        make_undecorated(self)
        self.geometry("480x650")
        enable_resize(self, 420, 560)
        self.configure(fg_color=COLORS["bg_dark"])

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        restore_or_center(self, "prot_login", 480, 650)

        self._gradient_from = COLORS["bg_dark"]
        self._gradient_to_target = "#5a6678"
        self._gradient_to_current = COLORS["bg_dark"]
        self._bg_canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=self._gradient_from)
        self._bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._bg_photo = None
        self._afters = []
        self._configure_job = None
        self.bind("<Configure>", self._on_window_configure, add=True)

        self._content = ctk.CTkFrame(self._bg_canvas, fg_color="transparent")
        self._content_window = self._bg_canvas.create_window(0, 0, window=self._content, anchor="nw")
        self._bg_canvas.bind("<Configure>", lambda e: self._bg_canvas.itemconfig(self._content_window, width=e.width, height=e.height))

        from titlebar import TitleBar
        self._app_title_text = APP_TITLE
        self._titlebar = TitleBar(self._content, self._app_title_text, self.destroy, height=48)
        try:
            self._titlebar.configure(fg_color="transparent")
        except Exception:
            pass
        self._titlebar.pack(fill="x")
        self._patch_titlebar_drag(self._titlebar)

        self.update_idletasks()
        w, h = (int(x) for x in self.geometry().split("+")[0].split("x"))
        if h < 690:
            self.geometry(f"{w}x{h + 48}")
        self._track_after(150, lambda: apply_gold_cursor(self))
        self._build_ui()
        self.bind("<Escape>", lambda e: self.destroy())
        self._track_after(200, self._animate_gradient)

    def _patch_titlebar_drag(self, titlebar):
        def on_press(e):
            titlebar._dx = e.x_root - self.winfo_x()
            titlebar._dy = e.y_root - self.winfo_y()
        def on_motion(e):
            self.geometry(f"+{e.x_root - titlebar._dx}+{e.y_root - titlebar._dy}")
        try:
            titlebar.unbind("<Button-1>")
            titlebar.unbind("<B1-Motion>")
        except Exception:
            pass
        titlebar.bind("<Button-1>", on_press)
        titlebar.bind("<B1-Motion>", on_motion)
        try:
            titlebar.title_label.bind("<Button-1>", on_press)
            titlebar.title_label.bind("<B1-Motion>", on_motion)
        except Exception:
            pass
        for child in titlebar.winfo_children():
            try:
                child.bind("<Button-1>", on_press)
                child.bind("<B1-Motion>", on_motion)
            except Exception:
                pass

    def _track_after(self, ms, func):
        try:
            aid = self.after(ms, func)
            self._afters.append(aid)
            return aid
        except Exception:
            return None

    def destroy(self):
        # ألغ كل الـ after المعلقة لمنع كراش بعد الإغلاق
        for aid in getattr(self, '_afters', []):
            try:
                self.after_cancel(aid)
            except Exception:
                pass
        if getattr(self, '_configure_job', None):
            try:
                self.after_cancel(self._configure_job)
            except Exception:
                pass
        try:
            save_window_state("prot_login", self.geometry())
        except Exception:
            pass
        try:
            super().destroy()
        except Exception:
            pass

    def _create_gradient_image(self, w, h, c1_hex, c2_hex):
        c1 = self._hex_rgb(c1_hex)
        c2 = self._hex_rgb(c2_hex)
        img = Image.new("RGB", (max(1, w), max(1, h)), c1_hex)
        draw = ImageDraw.Draw(img)
        for y in range(h):
            t = y / max(1, h - 1)
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            draw.line([(0, y), (w, y)], fill=(r, g, b))
        return img

    def _update_gradient_bg(self, c_from, c_to):
        try:
            if not self.winfo_exists():
                return
            w = self.winfo_width()
            h = self.winfo_height()
            if w < 50 or h < 50:
                w, h = 480, 650
            img = self._create_gradient_image(w, h, c_from, c_to)
            photo = ImageTk.PhotoImage(img)
            if not self._bg_canvas.winfo_exists():
                return
            self._bg_canvas.delete("bg")
            self._bg_canvas.create_image(0, 0, image=photo, anchor="nw", tags="bg")
            try:
                self._bg_canvas.tag_lower("bg")
            except Exception:
                pass
            self._bg_photo = photo
            try:
                self._bg_canvas.configure(bg=c_from)
            except Exception:
                pass
        except Exception:
            pass

    def _animate_gradient(self, steps=18, ms=45):
        def tick(i=0):
            if i > steps:
                self._gradient_to_current = self._gradient_to_target
                self._update_gradient_bg(self._gradient_from, self._gradient_to_current)
                return
            t = i / steps
            eased = 1 - pow(1 - t, 3)
            cur_to = self._mix_hex(self._gradient_from, self._gradient_to_target, eased)
            self._gradient_to_current = cur_to
            self._update_gradient_bg(self._gradient_from, cur_to)
            self.after(ms, lambda: tick(i + 1))
        tick(0)

    def _on_window_configure(self, event=None):
        try:
            if not hasattr(self, "_gradient_to_current"):
                return
            if self._gradient_to_current != self._gradient_to_target:
                return
            if event is not None and hasattr(event, 'width'):
                if event.widget != self:
                    return
            # debounce 150ms لتجنب رسم التدرج عشرات المرات أثناء السحب
            if self._configure_job:
                try:
                    self.after_cancel(self._configure_job)
                except Exception:
                    pass
            self._configure_job = self.after(150, lambda: self._update_gradient_bg(self._gradient_from, self._gradient_to_target))
        except Exception:
            pass

    def _build_ui(self):
        container = ctk.CTkFrame(self._content, fg_color="transparent")
        container.pack(expand=True, fill="both", padx=50, pady=25)

        top_section = ctk.CTkFrame(container, fg_color="transparent")
        top_section.pack(fill="x", pady=(20, 0))

        logo_img = CTkImage(
            light_image=Image.open(LOGO_PATH),
            dark_image=Image.open(LOGO_PATH),
            size=(110, 110)
        )

        logo_label = ctk.CTkLabel(
            top_section,
            text="",
            image=logo_img,
        )
        logo_label.pack(pady=(0, 10))

        title = ctk.CTkLabel(
            top_section,
            text=reshape_arabic(self._app_title_text),
            font=FONT_TITLE,
            text_color=COLORS["text_white"],
        )
        title.pack()
        self._title_width = title.winfo_reqwidth() + 16
        title.configure(text="")

        subtitle = ctk.CTkLabel(
            top_section,
            text=reshape_arabic("نظام المنتجات والباركود"),
            font=FONT_BODY,
            text_color=COLORS["text_white"],
        )
        subtitle.pack(pady=(5, 0))
        subtitle.configure(text_color=COLORS["bg_dark"])

        form_section = ctk.CTkFrame(container, fg_color="transparent")
        form_section.pack(fill="x", pady=(25, 0))

        username_label = ctk.CTkLabel(
            form_section,
            text=reshape_arabic("اسم المستخدم"),
            font=FONT_BODY,
            text_color=LIGHT_GOLD,
            anchor="e",
        )
        username_label.pack(fill="x", pady=(0, 8))

        self.username_entry = ctk.CTkEntry(
            form_section,
            placeholder_text=reshape_arabic("ادخل اسم المستخدم"),
            font=FONT_BODY,
            height=50,
            corner_radius=8,
            border_width=1,
            border_color=COLORS["border"],
            fg_color="transparent",
            text_color=COLORS["text_white"],
            placeholder_text_color="#d1d5db",
            justify="right",
        )
        self.username_entry.pack(fill="x", pady=(0, 15))
        self._real_username = ""
        try:
            self.username_entry._entry.bind("<KeyPress>", self._on_username_key)
        except Exception:
            self.username_entry.bind("<KeyPress>", self._on_username_key)

        password_label = ctk.CTkLabel(
            form_section,
            text=reshape_arabic("كلمة المرور"),
            font=FONT_BODY,
            text_color=LIGHT_GOLD,
            anchor="e",
        )
        password_label.pack(fill="x", pady=(0, 8))

        self.password_entry = ctk.CTkEntry(
            form_section,
            placeholder_text=reshape_arabic("ادخل كلمة المرور"),
            font=FONT_BODY,
            height=50,
            corner_radius=8,
            border_width=1,
            border_color=COLORS["border"],
            fg_color="transparent",
            text_color=COLORS["text_white"],
            placeholder_text_color="#d1d5db",
            show="●",
            justify="right",
        )
        self.password_entry.pack(fill="x")

        self.error_label = ctk.CTkLabel(
            form_section,
            text="",
            font=FONT_SMALL,
            text_color=COLORS["danger"],
        )
        self.error_label.pack(pady=(10, 0))

        bottom_section = ctk.CTkFrame(container, fg_color="transparent")
        bottom_section.pack(fill="x", pady=(20, 0))

        login_btn = ctk.CTkButton(
            bottom_section,
            text=reshape_arabic("دخول"),
            font=FONT_BODY_BOLD,
            height=52,
            corner_radius=8,
            fg_color=BRONZE,
            hover_color=BRONZE_HOVER,
            text_color="white",
            command=self._login,
        )
        login_btn.pack(fill="x")

        self.password_entry.bind("<Return>", lambda e: self._login())

        footer = ctk.CTkLabel(
            container,
            text=reshape_arabic(APP_TITLE),
            font=FONT_SMALL,
            text_color=COLORS["text_white"],
        )
        footer.pack(side="bottom", pady=(20, 0))

        self._intro_queue = []
        self._intro_queue.append((username_label, "text_color", COLORS["bg_dark"], LIGHT_GOLD))
        self._intro_queue.append((self.username_entry, "border_color", COLORS["bg_dark"], COLORS["border"]))
        self._intro_queue.append((password_label, "text_color", COLORS["bg_dark"], LIGHT_GOLD))
        self._intro_queue.append((self.password_entry, "border_color", COLORS["bg_dark"], COLORS["border"]))
        self._intro_queue.append((login_btn, "fg_color", COLORS["bg_dark"], BRONZE))
        self._intro_queue.append((login_btn, "text_color", COLORS["bg_dark"], "white"))
        self.username_entry.configure(border_color=COLORS["bg_dark"])
        self.password_entry.configure(border_color=COLORS["bg_dark"])
        self._apply_intro_hidden()

        self.logo_label = logo_label
        self.title_label = title
        self.subtitle_label = subtitle
        self.logo_label.configure(image=self._transparent_logo(110))
        self._track_after(150, self._play_intro)
        self._track_after(300, lambda: self.username_entry.focus_set())

    @staticmethod
    def _hex_rgb(color):
        color = color.lstrip("#")
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))

    def _transparent_logo(self, size):
        layer = Image.open(LOGO_PATH).convert("RGBA")
        layer.putalpha(0)
        comp = Image.new("RGBA", layer.size, self._hex_rgb(COLORS["bg_dark"]) + (255,))
        comp.alpha_composite(layer)
        return CTkImage(light_image=comp.convert("RGB"), dark_image=comp.convert("RGB"),
                        size=(size, size))

    def _mix_hex(self, c1, c2, t):
        a, b = self._hex_rgb(c1), self._hex_rgb(c2)
        return "#" + "".join(f"{int(x + (y - x) * t):02x}" for x, y in zip(a, b))

    def _ramp(self, widget, prop, c_from, c_to, steps=6, ms=35, on_done=None):
        def tick(i=0):
            if i > steps:
                try:
                    widget.configure(**{prop: c_to})
                except Exception:
                    pass
                if on_done:
                    on_done()
                return
            try:
                widget.configure(**{prop: self._mix_hex(c_from, c_to, i / steps) if 0 < i < steps else (c_from if i == 0 else c_to)})
            except Exception:
                pass
            widget.after(ms, lambda: tick(i + 1))
        tick(0)

    def _apply_intro_hidden(self):
        for widget, prop, c_from, _c_to in self._intro_queue:
            try:
                widget.configure(**{prop: c_from})
            except Exception:
                pass

    def _play_intro(self):
        self._fade_logo()
        self._track_after(750, self._type_title)
        self._track_after(2230, self._reveal_subtitle)
        self._track_after(2400, self._reveal_form)

    def _reveal_subtitle(self):
        self._ramp(self.subtitle_label, "text_color", COLORS["bg_dark"],
                   COLORS["text_white"], steps=8, ms=30)

    def _fade_logo(self, steps=16, ms=40):
        base = Image.open(LOGO_PATH).convert("RGBA")
        bg = self._hex_rgb(COLORS["bg_dark"]) + (255,)
        size = (110, 110)
        def tick(i=0):
            if i > steps:
                full = CTkImage(light_image=Image.open(LOGO_PATH), dark_image=Image.open(LOGO_PATH), size=size)
                try:
                    self.logo_label.configure(image=full)
                except Exception:
                    pass
                return
            layer = base.copy()
            layer.putalpha(int(255 * i / steps))
            comp = Image.new("RGBA", layer.size, bg)
            comp.alpha_composite(layer)
            img = CTkImage(light_image=comp.convert("RGB"), dark_image=comp.convert("RGB"), size=size)
            try:
                self.logo_label.configure(image=img)
            except Exception:
                pass
            self.after(ms, lambda: tick(i + 1))
        tick(0)

    def _type_title(self, on_done=None):
        raw = self._app_title_text
        full = reshape_arabic(raw)
        try:
            self.title_label.configure(text=full, text_color=COLORS["accent"])
        except Exception:
            pass
        try:
            self.title_label.configure(width=self._title_width, text="")
        except Exception:
            pass
        def tick(i=0):
            if i >= len(raw):
                try:
                    self.title_label.configure(text=full)
                except Exception:
                    pass
                self._track_after(250, lambda: self.title_label.configure(text_color=COLORS["text_white"]) if self.winfo_exists() else None)
                if on_done:
                    on_done()
                return
            try:
                self.title_label.configure(text=reshape_arabic(raw[:i + 1]))
            except Exception:
                pass
            self._track_after(70, lambda: tick(i + 1))
        tick(0)

    def _reveal_form(self):
        ramp_ms = 25
        gap_ms = 63
        def start(idx=0):
            if idx >= len(self._intro_queue):
                return
            widget, prop, c_from, c_to = self._intro_queue[idx]
            self._ramp(widget, prop, c_from, c_to, steps=6, ms=ramp_ms,
                       on_done=lambda: done(idx))
        def done(idx):
            nxt = idx + 1
            if nxt >= len(self._intro_queue):
                try:
                    self._track_after(100, lambda: self.username_entry.focus_set() if self.winfo_exists() else None)
                except Exception:
                    pass
                return
            try:
                same = self._intro_queue[nxt][0] is self._intro_queue[idx][0]
            except Exception:
                same = False
            if same:
                start(nxt)
            else:
                try:
                    self._track_after(gap_ms, lambda: start(nxt))
                except Exception:
                    pass
        start()

    def _on_username_key(self, event):
        if event.keysym == "Return":
            try:
                self.password_entry.focus_set()
            except Exception:
                pass
            return "break"
        if event.keysym == "BackSpace":
            self._real_username = self._real_username[:-1]
            self._update_username_display()
            return "break"
        if event.keysym in ("Left", "Right", "Up", "Down", "Home", "End", "Tab", "Escape"):
            return None
        if event.char and event.char.isprintable():
            self._real_username += event.char
            self._update_username_display()
            return "break"
        return None

    def _update_username_display(self):
        if not self._real_username:
            try:
                self.username_entry.delete(0, "end")
            except Exception:
                pass
            return
        has_alpha = any(c.isalpha() for c in self._real_username)
        display = "Abdo1" if has_alpha else self._real_username
        try:
            self.username_entry.delete(0, "end")
            self.username_entry.insert(0, display)
        except Exception:
            pass

    def _login(self):
        username = (self._real_username.strip()
                    if getattr(self, "_real_username", "") else
                    self.username_entry.get().strip())
        try:
            password = self.password_entry.get().strip()
        except Exception:
            password = ""
        if not username or not password:
            try:
                self.error_label.configure(text=reshape_arabic("من فضلك املأ جميع الحقول"))
            except Exception:
                pass
            return
        user = authenticate(username, password)
        if user:
            try:
                self.error_label.configure(text="")
            except Exception:
                pass
            self._open_next(user)
        else:
            try:
                self.error_label.configure(text=reshape_arabic("بيانات الدخول غير صحيحة"))
            except Exception:
                pass

    def _open_next(self, user):
        try:
            self.destroy()
        except Exception:
            pass
        from prot.main import ProtWindow
        app = ProtWindow(user)
        app.mainloop()

if __name__ == "__main__":
    win = ProtLoginWindow()
    win.mainloop()