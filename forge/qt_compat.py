from __future__ import annotations

import krita

try:
    if hasattr(krita, 'qVersion') and int(krita.qVersion().split('.')[0]) >= 6:
        from PyQt6.QtCore import *
        from PyQt6.QtGui import *
        from PyQt6.QtWidgets import *
    else:
        raise ImportError
except (ImportError, AttributeError):
    from PyQt5.QtCore import *
    from PyQt5.QtGui import *
    from PyQt5.QtWidgets import *
