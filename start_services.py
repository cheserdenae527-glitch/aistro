"""启动 AiRestro 前后端服务（detached，不随终端关闭）。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
PID_FILE = ROOT / ".service-pids.json"
DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def _load_pids() -> dict[str, int]:
    if not PID_FILE.exists():
        return {}
    try:
        return json.loads(PID_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _stop_previous() -> None:
    pids = _load_pids()
    for name in ("backend", "frontend"):
        pid = pids.get(name)
        if pid:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
            )
            time.sleep(0.5)


def _save_pids(backend_pid: int, frontend_pid: int) -> None:
    PID_FILE.write_text(
        json.dumps({"backend": backend_pid, "frontend": frontend_pid}),
        encoding="utf-8",
    )


def main() -> None:
    _stop_previous()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR / "services")
    backend_log = (ROOT / "backend.log").open("w", encoding="utf-8")
    frontend_log = (ROOT / "frontend.log").open("w", encoding="utf-8")

    try:
        backend = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
            ],
            cwd=str(BACKEND_DIR),
            env=env,
            stdout=backend_log,
            stderr=subprocess.STDOUT,
            creationflags=DETACHED,
        )
        frontend = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(FRONTEND_DIR),
            stdout=frontend_log,
            stderr=subprocess.STDOUT,
            creationflags=DETACHED,
            shell=True,
        )
        _save_pids(backend.pid, frontend.pid)
        print(f"Backend PID: {backend.pid}")
        print(f"Frontend PID: {frontend.pid}")
    finally:
        backend_log.close()
        frontend_log.close()


if __name__ == "__main__":
    main()
