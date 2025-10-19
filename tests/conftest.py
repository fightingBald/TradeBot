from __future__ import annotations

import sys
from pathlib import Path

# Ensure the application package is importable when running tests directly via pytest.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
