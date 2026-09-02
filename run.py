#!/usr/bin/env python3
import os, sys
BASE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(BASE)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)
if BASE not in sys.path:
    sys.path.insert(0, BASE)
# أيضاً أضف cashier لو sibling (Desktop/prot + Desktop/cashier)
for _cand in [os.path.join(PARENT, "cashier"), os.path.join(os.path.dirname(PARENT), "cashier")]:
    if os.path.exists(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)
        _par = os.path.dirname(_cand)
        if _par not in sys.path:
            sys.path.insert(0, _par)

try:
    from prot.db.database import init_db
    from prot.login import ProtLoginWindow
    from prot.main import ProtWindow
    HAS_LOGIN = True
except ImportError:
    from db.database import init_db
    try:
        from login import ProtLoginWindow
        HAS_LOGIN = True
    except Exception:
        HAS_LOGIN = False
    from main import ProtWindow

if __name__ == "__main__":
    init_db()
    if HAS_LOGIN:
        app = ProtLoginWindow()
    else:
        app = ProtWindow()
    app.mainloop()
