"""让 pytest 从仓库根目录也能直接运行 benchmarks。"""
from __future__ import annotations

import sys
from pathlib import Path

backend_dir = str(Path(__file__).resolve().parents[1])
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
