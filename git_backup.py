# prot/git_backup.py — نسخ احتياطي عبر git لمشروع prot (barcode) مع جدولة
# نفس منطق cashier/git_backup.py لكن لمستودع prot المنفصل (https://github.com/ABDelrahmanmohamed555/barcode.git)
# الاستخدام:
#   ./venv/bin/python prot/git_backup.py                  # نسخ فوري
#   ./venv/bin/python prot/git_backup.py --check          # يفحص الجدولة وينفذ لو حان الوقت
#   ./venv/bin/python prot/git_backup.py --install-cron   # تثبيت cron حسب الإعدادات

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "assets", "backup_config.json")

DEFAULT_CONFIG = {
    "enabled": False,
    "frequency": "daily",  # daily | every2days | weekly | monthly
    "time": "02:00",
    "last_run": "",  # YYYY-MM-DD
}


def load_backup_config():
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return {
            "enabled": bool(d.get("enabled", False)),
            "frequency": str(d.get("frequency", "daily")).strip() or "daily",
            "time": str(d.get("time", "02:00")).strip() or "02:00",
            "last_run": str(d.get("last_run", "")).strip(),
        }
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_backup_config(enabled, frequency, time_str, last_run=None):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    cur = load_backup_config()
    if last_run is None:
        last_run = cur.get("last_run", "")
    data = {
        "enabled": bool(enabled),
        "frequency": str(frequency).strip() or "daily",
        "time": time_str.strip(),
        "last_run": str(last_run).strip(),
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def _parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def should_run_today(frequency, last_run_str, today=None):
    """هل يجب تنفيذ النسخ اليوم حسب التكرار؟"""
    if today is None:
        today = date.today()
    last = _parse_date(last_run_str) if last_run_str else None
    if not last:
        return True  # أول مرة
    delta = (today - last).days
    if delta < 0:
        return False
    if frequency == "daily":
        return delta >= 1
    elif frequency == "every2days":
        return delta >= 2
    elif frequency == "weekly":
        return delta >= 7
    elif frequency == "monthly":
        if delta >= 30:
            return True
        if today.month != last.month or today.year != last.year:
            return True
        return False
    else:
        return delta >= 1


def do_git_backup(custom_message=None):
    """تنفيذ git add . && git commit -m "backup" && git push داخل prot فقط"""
    cwd = BASE_DIR
    if not os.path.exists(os.path.join(cwd, ".git")):
        return False, "المجلد ليس مستودع git — تأكد أن prot مستودع منفصل"

    try:
        r1 = subprocess.run(["git", "add", "."], cwd=cwd, capture_output=True, text=True, timeout=30)
        if r1.returncode != 0:
            return False, f"فشل git add: {r1.stderr or r1.stdout}"
    except Exception as e:
        return False, f"خطأ git add: {e}"

    try:
        status = subprocess.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, timeout=10)
        if not status.stdout.strip():
            return True, "لا يوجد تغييرات للرفع — كل شيء محدث (prot)"
    except Exception:
        pass

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = custom_message or f"prot backup {now_str}"
    try:
        r2 = subprocess.run(["git", "commit", "-m", msg], cwd=cwd, capture_output=True, text=True, timeout=30)
        if r2.returncode != 0:
            out = (r2.stdout + " " + r2.stderr).lower()
            if "nothing to commit" in out or "no changes added" in out:
                return True, "لا يوجد تغييرات للـ commit (prot)"
            return False, f"فشل commit: {r2.stderr or r2.stdout}"
    except Exception as e:
        return False, f"خطأ commit: {e}"

    try:
        r3 = subprocess.run(["git", "push"], cwd=cwd, capture_output=True, text=True, timeout=60)
        if r3.returncode != 0:
            err = r3.stderr or r3.stdout
            if "no configured push destination" in err.lower() or "could not read" in err.lower():
                return False, f"فشل push (تأكد من إعداد GitHub لـ prot): {err[:300]}"
            return False, f"فشل push (prot): {err[:500]}"
    except Exception as e:
        return False, f"خطأ push: {e}"

    return True, f"تم الرفع بنجاح (prot) — {msg}"


def install_cron(frequency=None, time_str=None):
    """تثبيت cron يشغل prot/git_backup.py --check في الوقت المحدد."""
    cfg = load_backup_config()
    if frequency is None:
        frequency = cfg.get("frequency", "daily")
    if time_str is None:
        time_str = cfg.get("time", "02:00")
    try:
        hh, mm = [int(x) for x in str(time_str).strip().split(":")]
        hh = max(0, min(23, hh))
        mm = max(0, min(59, mm))
    except Exception:
        hh, mm = 2, 0

    # الأمر: يومياً عند HH:MM يشغل السكربت مع --check — السكربت يراعي التكرار
    # نستخدم sys.executable الحالي (قد يكون venv الخاص بـ prot أو cashier)
    cmd = " ".join([
        f"cd {BASE_DIR} &&",
        f"{sys.executable} {os.path.join(BASE_DIR, 'git_backup.py')} --check",
        f">> {os.path.join(BASE_DIR, 'reports', 'backup_cron.log')} 2>&1",
    ])
    entry = f"{mm} {hh} * * * {cmd}\n"
    try:
        cr = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = cr.stdout if cr.returncode == 0 else ""
    except Exception:
        existing = ""
    # احذف أي جدولة قديمة لنفس السكربت (prot/git_backup.py)
    marker = "prot/git_backup.py"
    if marker in existing:
        lines = [ln for ln in existing.splitlines() if marker not in ln]
        existing = "\n".join(lines) + ("\n" if lines else "")
        print("تم تحديث جدولة النسخ القديمة لـ prot.")
    new = existing + entry
    try:
        subprocess.run(["crontab", "-"], input=new, text=True, check=True)
        print("اتثبتت جدولة النسخ لـ prot في crontab:")
        print(entry)
        return True
    except Exception as e:
        print(f"فشل تثبيت crontab لـ prot: {e}")
        print(f"أضف يدوياً:\n{entry}")
        return False


def remove_cron():
    try:
        cr = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = cr.stdout if cr.returncode == 0 else ""
        marker = "prot/git_backup.py"
        if marker not in existing:
            return True
        lines = [ln for ln in existing.splitlines() if marker not in ln]
        new = "\n".join(lines) + ("\n" if lines else "")
        subprocess.run(["crontab", "-"], input=new, text=True, check=True)
        print("تمت إزالة جدولة النسخ لـ prot من crontab")
        return True
    except Exception as e:
        print(f"cron remove err (prot): {e}")
        return False


def main():
    ap = argparse.ArgumentParser(description="نسخ احتياطي git لـ prot")
    ap.add_argument("--check", action="store_true", help="يفحص الجدولة وينفذ لو حان الوقت")
    ap.add_argument("--install-cron", action="store_true", help="تثبيت cron")
    ap.add_argument("--remove-cron", action="store_true", help="إزالة cron")
    ap.add_argument("--message", help="رسالة commit مخصصة")
    args = ap.parse_args()

    if args.install_cron:
        install_cron()
        return
    if args.remove_cron:
        remove_cron()
        return

    if args.check:
        cfg = load_backup_config()
        if not cfg.get("enabled"):
            print("النسخ معطل (prot)")
            return
        now = datetime.now()
        cur_time = now.strftime("%H:%M")
        target = cfg.get("time", "02:00")
        today_str = now.strftime("%Y-%m-%d")
        freq = cfg.get("frequency", "daily")
        last = cfg.get("last_run", "")
        if cur_time != target:
            try:
                ch, cm = map(int, cur_time.split(":"))
                th, tm = map(int, target.split(":"))
                diff = abs((ch*60+cm) - (th*60+tm))
                if diff > 1:
                    print(f"ليس وقت التنفيذ الآن {cur_time} != {target} (prot)")
                    return
            except Exception:
                if cur_time != target:
                    return
        if not should_run_today(freq, last, now.date()):
            print(f"ليس موعد التكرار ({freq}) — آخر تشغيل {last} (prot)")
            return
        ok, msg = do_git_backup(args.message)
        print(msg)
        if ok:
            try:
                save_backup_config(cfg["enabled"], freq, target, last_run=today_str)
            except Exception:
                pass
        sys.exit(0 if ok else 1)
    else:
        ok, msg = do_git_backup(args.message)
        print(msg)
        if ok:
            try:
                cfg = load_backup_config()
                today_str = datetime.now().strftime("%Y-%m-%d")
                save_backup_config(cfg.get("enabled", False), cfg.get("frequency", "daily"), cfg.get("time", "02:00"), last_run=today_str)
            except Exception:
                pass
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
