"""XHS 运行时单例 — 爬虫/订阅共用。"""
from __future__ import annotations

import os
import shutil
import sys
import threading

from crawler.config import get_cookie

_XHS_RT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "crawler", "xhs", "scripts", "runtime", "spider_xhs_core")
)

_xhs_api = None
_xhs_auth = None
_xhs_api_lock = threading.Lock()


def get_xhs_api():
    """初始化并缓存 Spider_XHS 运行时 API 单例。"""
    global _xhs_api, _xhs_auth
    with _xhs_api_lock:
        if _xhs_api is not None:
            return _xhs_api
        if _XHS_RT not in sys.path:
            sys.path.insert(0, _XHS_RT)
        old = os.getcwd()
        os.chdir(_XHS_RT)
        node = shutil.which("node")
        node_dir = os.path.dirname(node) if node else None
        if not node_dir:
            raise RuntimeError("Node.js 未安装，无法初始化小红书 API")
        if node_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = node_dir + os.pathsep + os.environ.get("PATH", "")
        try:
            from xhs_utils.xhs_pc import XHSPcAuth
            from apis.xhs_pc_apis import XHS_Apis
            _xhs_auth = XHSPcAuth.from_cookie(get_cookie())
            _xhs_api = XHS_Apis(_xhs_auth)
            return _xhs_api
        finally:
            os.chdir(old)
