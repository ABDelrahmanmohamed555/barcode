#!/usr/bin/env python3
# prot/updater.py — تحديث تلقائي من GitHub (prot فقط)
# الفكرة: ترفع التحديث على GitHub بكومنت update1, update2... والسيستم يفحص يومياً عند HH:MM
# قبل التحديث يعمل push احتياطي لقاعدة البيانات، ثم يقارن الملفات وينزل المتغير فقط عبر git pull
# ويتأكد أن المحلي == GitHub بعد السحب

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import hashlib
from datetime import datetime, date

_IS_WINDOWS = platform.system().lower().startswith("win")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "assets", "updater_config.json")
BACKUP_CONFIG_PATH = os.path.join(BASE_DIR, "assets", "backup_config.json")

DEFAULT_CONFIG = {
    "enabled": False,
    "time": "03:00",  # وقت الفحص اليومي
    "last_check": "",  # YYYY-MM-DD
    "last_update": "",  # YYYY-MM-DD HH:MM commit
}

# نمط كومنت التحديث: update1, update2, update 1, Update1, update:1, v1.2.3, version 1.2.3
UPDATE_PATTERNS = [
    re.compile(r"^\s*update\s*[:\-]?\s*\d+\s*$", re.IGNORECASE),  # update1, update:1, update-1
    re.compile(r"^\s*update\s+\d+\s*$", re.IGNORECASE),  # update 1
    re.compile(r"^\s*v\d+\.\d+.*$", re.IGNORECASE),  # v1.2.3
    re.compile(r"^\s*version\s*[:\-]?\s*\d+.*$", re.IGNORECASE),
]

def _is_update_commit(msg):
    msg = (msg or "").strip()
    # أول سطر فقط
    first = msg.splitlines()[0].strip()
    for pat in UPDATE_PATTERNS:
        if pat.match(first):
            return True
    # أيضاً لو يبدأ بـ update:
    if first.lower().startswith("update"):
        # تأكد أن بعده رقم أو : أو مسافة
        rest = first[6:].strip(" :-\t")
        if rest and rest[0].isdigit():
            return True
    return False

def load_updater_config():
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return {
            "enabled": bool(d.get("enabled", False)),
            "time": str(d.get("time", "03:00")).strip() or "03:00",
            "last_check": str(d.get("last_check", "")).strip(),
            "last_update": str(d.get("last_update", "")).strip(),
        }
    except Exception:
        return dict(DEFAULT_CONFIG)

def save_updater_config(enabled=None, time_str=None, last_check=None, last_update=None):
    cfg = load_updater_config()
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if time_str is not None:
        cfg["time"] = str(time_str).strip() or "03:00"
    if last_check is not None:
        cfg["last_check"] = str(last_check).strip()
    if last_update is not None:
        cfg["last_update"] = str(last_update).strip()
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg

def _run(cmd, cwd=BASE_DIR, timeout=30):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)

def _get_local_commit():
    r = _run(["git", "rev-parse", "HEAD"])
    return r.stdout.strip() if r.returncode == 0 else None

def _get_remote_commits():
    # يجلب origin/main ويعيد قائمة commits الجديدة (HEAD..origin/main) مع رسائلها
    # أولاً fetch
    fr = _run(["git", "fetch", "origin", "main"], timeout=60)
    if fr.returncode != 0:
        return None, f"فشل git fetch: {fr.stderr or fr.stdout}"
    # احصل على commits الجديدة
    r = _run(["git", "log", "HEAD..origin/main", "--pretty=format:%H %s", "--no-merges"])
    if r.returncode != 0:
        return None, f"فشل git log: {r.stderr or r.stdout}"
    commits = []
    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.strip().split(" ", 1)
        if len(parts) == 2:
            commits.append((parts[0], parts[1]))
        else:
            commits.append((parts[0], ""))
    return commits, None

def _backup_db_push():
    # يعمل push احتياطي لقاعدة البيانات قبل التحديث (لا يستخدم كومنت update حتى لا يُعتبر تحديثاً)
    try:
        from git_backup import do_git_backup
        # فقط db/ والملفات المهمة، لكن do_git_backup يعمل add . — نستخدمه كما هو لكن برسالة backup
        ok, msg = do_git_backup(custom_message=f"backup pre-update {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        return ok, msg
    except Exception as e:
        return False, f"فشل النسخ الاحتياطي: {e}"

def _verify_files_match():
    # يتأكد أن المحلي == origin/main بعد pull عبر مقارنة sha
    # git diff --name-only HEAD origin/main يجب أن يكون فارغ
    r = _run(["git", "diff", "--name-only", "HEAD", "origin/main"])
    if r.returncode != 0:
        return False, f"فشل التحقق: {r.stderr or r.stdout}"
    if r.stdout.strip():
        return False, f"لا تزال هناك اختلافات بعد السحب: {r.stdout.strip()[:500]}"
    # أيضاً تحقق عبر ls-tree
    r1 = _run(["git", "ls-tree", "-r", "HEAD", "--name-only"])
    r2 = _run(["git", "ls-tree", "-r", "origin/main", "--name-only"])
    if r1.returncode == 0 and r2.returncode == 0:
        if set(r1.stdout.splitlines()) != set(r2.stdout.splitlines()):
            return False, "قائمة الملفات غير متطابقة بعد السحب"
    return True, "الملفات متطابقة ✓"

def check_for_update():
    # يفحص هل يوجد تحديث update1,2... على GitHub بدون تثبيت
    commits, err = _get_remote_commits()
    if err:
        return False, err, []
    if not commits:
        return False, "لا يوجد تحديث — المحلي محدث", []
    # فلتر فقط commits التي رسالتها update
    update_commits = [(h, m) for h, m in commits if _is_update_commit(m)]
    if not update_commits:
        return False, f"يوجد {len(commits)} commit جديد لكن ليس update1,2... (آخر: {commits[0][1][:60]})", commits
    return True, f"يوجد تحديث ✓ {len(update_commits)} commit من نوع update", update_commits

def do_update():
    # 1) نسخ احتياطي لل DB
    ok_bak, msg_bak = _backup_db_push()
    # حتى لو فشل النسخ، نتابع لكن ننبه
    # 2) فحص التحديث
    has_update, msg, commits = check_for_update()
    if not has_update:
        return False, msg
    # 3) حفظ حالة قبل التحديث للاسترجاع لو فشل
    local_before = _get_local_commit()
    # 4) stash أي تعديلات محلية غير محفوظة (ما عدا db)
    _run(["git", "stash", "push", "-m", "pre-update stash", "--keep-index"])
    # 5) pull
    r_pull = _run(["git", "pull", "--rebase", "origin", "main"], timeout=120)
    if r_pull.returncode != 0:
        # حاول reset hard
        r_pull2 = _run(["git", "reset", "--hard", "origin/main"], timeout=60)
        if r_pull2.returncode != 0:
            return False, f"فشل السحب: {r_pull.stderr or r_pull.stdout} | {r_pull2.stderr or r_pull2.stdout}"
    # 6) تحقق
    ok_ver, msg_ver = _verify_files_match()
    if not ok_ver:
        return False, f"تم السحب لكن التحقق فشل: {msg_ver}"
    # 7) حدث last_update
    try:
        cfg = load_updater_config()
        save_updater_config(enabled=cfg["enabled"], time_str=cfg["time"], last_check=datetime.now().strftime("%Y-%m-%d"), last_update=datetime.now().strftime("%Y-%m-%d %H:%M") + f" ({commits[0][1]})")
    except Exception:
        pass
    # 8) حاول استعادة stash لو لم يكن هناك تعارض
    _run(["git", "stash", "pop"])
    return True, f"تم التحديث ✓ {len(commits)} ملف — آخر: {commits[0][1]} — {msg_ver}"

def install_cron(time_str="03:00"):
    try:
        hh, mm = [int(x) for x in str(time_str).strip().split(":")]
        hh = max(0, min(23, hh)); mm = max(0, min(59, mm))
    except Exception:
        hh, mm = 3, 0
    if _IS_WINDOWS:
        task_name = "ProtUpdater"
        time_str_win = f"{hh:02d}:{mm:02d}"
        cmd = f'"{sys.executable}" "{os.path.join(BASE_DIR, "updater.py")}" --check'
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
    cmd = f"cd {BASE_DIR} && {sys.executable} {os.path.join(BASE_DIR, 'updater.py')} --check >> {os.path.join(BASE_DIR, 'reports', 'updater_cron.log')} 2>&1"
    entry = f"{mm} {hh} * * * {cmd}\n"
    try:
        cr = _run(["crontab", "-l"])
        existing = cr.stdout if cr.returncode == 0 else ""
    except Exception:
        existing = ""
    marker = "updater.py --check"
    if marker in existing:
        lines = [ln for ln in existing.splitlines() if marker not in ln]
        existing = "\n".join(lines) + ("\n" if lines else "")
    new = existing + entry
    try:
        subprocess.run(["crontab", "-"], input=new, text=True, check=True)
        print(f"تم تثبيت جدولة التحديث: {entry.strip()}")
        return True
    except Exception as e:
        print(f"فشل crontab: {e}")
        return False

def remove_cron():
    if _IS_WINDOWS:
        task_name = "ProtUpdater"
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
        cr = _run(["crontab", "-l"])
        existing = cr.stdout if cr.returncode == 0 else ""
        marker = "updater.py --check"
        if marker not in existing:
            return True
        lines = [ln for ln in existing.splitlines() if marker not in ln]
        new = "\n".join(lines) + ("\n" if lines else "")
        subprocess.run(["crontab", "-"], input=new, text=True, check=True)
        print("تمت إزالة جدولة التحديث")
        return True
    except Exception as e:
        print(f"cron remove err: {e}")
        return False

def main():
    ap = argparse.ArgumentParser(description="محدث prot التلقائي")
    ap.add_argument("--check", action="store_true", help="يفحص ولو وجد update1,2... يحدث تلقائياً (يُستدعى من cron)")
    ap.add_argument("--check-only", action="store_true", help="يفحص فقط بدون تثبيت")
    ap.add_argument("--install-cron", action="store_true", help="تثبيت فحص يومي")
    ap.add_argument("--remove-cron", action="store_true", help="إزالة الجدولة")
    ap.add_argument("--force", action="store_true", help="تحديث فوري حتى لو ليس وقت الجدولة")
    ap.add_argument("--time", help="وقت الفحص HH:MM")
    args = ap.parse_args()

    if args.install_cron:
        cfg = load_updater_config()
        t = args.time or cfg.get("time", "03:00")
        install_cron(t)
        save_updater_config(enabled=True, time_str=t)
        return
    if args.remove_cron:
        remove_cron()
        save_updater_config(enabled=False)
        return

    if args.check or args.check_only:
        cfg = load_updater_config()
        if not cfg.get("enabled") and not args.force and not args.check_only:
            print("المحدث معطل")
            return
        now = datetime.now()
        if not args.force and not args.check_only:
            target = cfg.get("time", "03:00")
            cur = now.strftime("%H:%M")
            if cur != target:
                try:
                    ch, cm = map(int, cur.split(":"))
                    th, tm = map(int, target.split(":"))
                    if abs((ch*60+cm)-(th*60+tm)) > 1:
                        print(f"ليس وقت الفحص {cur} != {target}")
                        return
                except Exception:
                    if cur != target:
                        return
        if args.check_only:
            has_update, msg, commits = check_for_update()
            print(msg)
            if commits:
                for h, m in commits[:5]:
                    print(f"  {h[:7]} {m}")
            sys.exit(0 if has_update else 1)
        else:
            # فحص وتحديث فعلي
            # حدث last_check
            try:
                save_updater_config(enabled=cfg.get("enabled", True), time_str=cfg.get("time", "03:00"), last_check=now.strftime("%Y-%m-%d"))
            except Exception:
                pass
            ok, msg = do_update()
            print(msg)
            sys.exit(0 if ok else 1)

    # افتراضي: فحص سريع
    has_update, msg, commits = check_for_update()
    print(msg)
    if commits:
        for h, m in commits[:5]:
            print(f"  {h[:7]} {m}")

if __name__ == "__main__":
    main()
