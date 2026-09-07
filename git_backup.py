# prot/git_backup.py — نسخ احتياطي عبر git لمشروع prot (barcode) مع جدولة
# نفس منطق cashier/git_backup.py لكن لمستودع prot المنفصل (https://github.com/ABDelrahmanmohamed555/barcode.git)
# الاستخدام:
#   ./venv/bin/python prot/git_backup.py                  # نسخ فوري
#   ./venv/bin/python prot/git_backup.py --check          # يفحص الجدولة وينفذ لو حان الوقت
#   ./venv/bin/python prot/git_backup.py --install-cron   # تثبيت cron حسب الإعدادات

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, date

_IS_WINDOWS = platform.system().lower().startswith("win")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "assets", "backup_config.json")
TOKEN_PATHS = [
    os.path.expanduser("~/.config/cashier/github_token"),
    os.path.expanduser("~/.config/prot/github_token"),
    os.path.join(BASE_DIR, "assets", ".github_token"),
    os.path.join(BASE_DIR, ".github_token"),
]

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


def _get_token_path():
    for p in TOKEN_PATHS:
        if os.path.exists(p):
            return p
    return TOKEN_PATHS[0]

def load_github_token():
    for p in TOKEN_PATHS:
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    tok = f.read().strip()
                if tok:
                    return tok
        except Exception:
            continue
    return None

def save_github_token(token):
    token = (token or "").strip().split()[0] if token else ""
    if not token:
        return False, "التوكن فارغ"
    path = _get_token_path()
    if not os.path.exists(os.path.dirname(path)):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:
            pass
    path = TOKEN_PATHS[0]
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(token + "\n")
        os.chmod(path, 0o600)
        try:
            alt = TOKEN_PATHS[2]
            os.makedirs(os.path.dirname(alt), exist_ok=True)
            with open(alt, "w", encoding="utf-8") as f:
                f.write(token + "\n")
            os.chmod(alt, 0o600)
        except Exception:
            pass
        return True, f"تم حفظ التوكن ✓ ({path})"
    except Exception as e:
        return False, f"فشل حفظ التوكن: {e}"

def clear_github_token():
    removed = []
    for p in TOKEN_PATHS:
        try:
            if os.path.exists(p):
                os.remove(p)
                removed.append(p)
        except Exception:
            pass
    return removed

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

    token = load_github_token()
    def _try_push_with_token(tok):
        try:
            r_remote = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=cwd, capture_output=True, text=True, timeout=10)
            remote_url = (r_remote.stdout or "").strip()
            if not remote_url:
                remote_url = "https://github.com/ABDelrahmanmohamed555/barcode.git"
            if remote_url.startswith("git@"):
                try:
                    part = remote_url.split(":", 1)[1]
                    remote_url = f"https://github.com/{part}"
                except Exception:
                    remote_url = "https://github.com/ABDelrahmanmohamed555/barcode.git"
            if "github.com" in remote_url and tok:
                if "@" not in remote_url.split("github.com")[0]:
                    remote_url = remote_url.replace("https://", f"https://{tok}@")
                try:
                    br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=10)
                    branch = (br.stdout or "main").strip() or "main"
                except Exception:
                    branch = "main"
                r = subprocess.run(["git", "push", remote_url, f"HEAD:{branch}"], cwd=cwd, capture_output=True, text=True, timeout=60)
                return r
            return subprocess.run(["git", "push"], cwd=cwd, capture_output=True, text=True, timeout=60)
        except Exception as e:
            return subprocess.CompletedProcess(args=["git","push"], returncode=1, stdout="", stderr=str(e))

    try:
        r3 = subprocess.run(["git", "push"], cwd=cwd, capture_output=True, text=True, timeout=60)
        if r3.returncode == 0:
            return True, f"تم الرفع بنجاح (prot) — {msg}"
        err = r3.stderr or r3.stdout or ""
        needs_token = any(x in err.lower() for x in ["could not read username", "authentication failed", "invalid username or password", "support for password authentication was removed", "403", "401"])
        if needs_token and token:
            r_tok = _try_push_with_token(token)
            if r_tok.returncode == 0:
                return True, f"تم الرفع بنجاح عبر التوكن (prot) — {msg}"
            err2 = r_tok.stderr or r_tok.stdout or ""
            return False, f"فشل push حتى مع التوكن (prot): {err2[:500]} — تأكد أن التوكن صحيح (ghp_...) وله صلاحية repo"
        if "could not read" in err.lower() or "no configured push destination" in err.lower():
            if token:
                return False, f"فشل push (prot): {err[:300]} — جرّب التوكن المحفوظ"
            return False, f"فشل push (prot): {err[:300]} — أدخل GitHub Token مرة واحدة من الإعدادات"
        return False, f"فشل push (prot): {err[:500]}"
    except Exception as e:
        return False, f"خطأ push: {e}"


def install_cron(frequency=None, time_str=None):
    """تثبيت جدولة يشغل prot/git_backup.py --check في الوقت المحدد. يكتشف النظام تلقائياً."""
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

    if _IS_WINDOWS:
        task_name = "ProtBackup"
        time_str_win = f"{hh:02d}:{mm:02d}"
        cmd = f'"{sys.executable}" "{os.path.join(BASE_DIR, "git_backup.py")}" --check'
        try:
            subprocess.run(["schtasks", "/delete", "/tn", task_name, "/f"], capture_output=True, text=True, timeout=10)
        except Exception:
            pass
        try:
            r = subprocess.run(["schtasks", "/create", "/tn", task_name, "/tr", cmd, "/sc", "daily", "/st", time_str_win, "/f"], capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                print(f"تم تثبيت جدولة ويندوز: {task_name} يومياً {time_str_win}")
                return True
            print(f"فشل schtasks: {r.stderr or r.stdout}")
            return False
        except Exception as e:
            print(f"فشل Task Scheduler: {e}")
            return False

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
    if _IS_WINDOWS:
        task_name = "ProtBackup"
        try:
            r = subprocess.run(["schtasks", "/delete", "/tn", task_name, "/f"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0 or "ERROR: The system cannot find the file" in (r.stderr or ""):
                print("تمت إزالة جدولة ويندوز")
                return True
            print(f"فشل حذف Task: {r.stderr or r.stdout}")
            return False
        except Exception as e:
            print(f"cron remove err: {e}")
            return False
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
    ap.add_argument("--set-token", help="حفظ GitHub Token لمرة واحدة (ghp_...)")
    ap.add_argument("--clear-token", action="store_true", help="حذف التوكن المحفوظ")
    ap.add_argument("--token-status", action="store_true", help="عرض حالة التوكن")
    args = ap.parse_args()

    if args.set_token is not None:
        ok, msg = save_github_token(args.set_token)
        print(msg)
        sys.exit(0 if ok else 1)
    if args.clear_token:
        removed = clear_github_token()
        print(f"تم حذف التوكن من: {', '.join(removed) if removed else 'لا يوجد توكن'}")
        sys.exit(0)
    if args.token_status:
        tok = load_github_token()
        if tok:
            masked = tok[:4] + "*"*(len(tok)-8) + tok[-4:] if len(tok) > 8 else "***"
            print(f"التوكن محفوظ ✓ {masked} ({_get_token_path()})")
        else:
            print("لا يوجد توكن محفوظ — أدخل واحداً عبر --set-token أو من الإعدادات")
        sys.exit(0)

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
