#!/usr/bin/env python3
import os, sys
BASE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(BASE)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from prot.db.database import init_db
try:
    from prot.login import ProtLoginWindow
    HAS_LOGIN = True
except Exception:
    HAS_LOGIN = False
from prot.main import ProtWindow

if __name__ == "__main__":
    init_db()
    if HAS_LOGIN:
        app = ProtLoginWindow()
    else:
        app = ProtWindow()
    app.mainloop()
