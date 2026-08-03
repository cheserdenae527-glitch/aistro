"""启动 AiRestro 前后端服务（detached，不随终端关闭）。"""
import subprocess
import sys
import os
import time

DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

# 先杀掉旧进程
subprocess.run(["taskkill", "/F", "/IM", "node.exe"], capture_output=True)
subprocess.run(["taskkill", "/F", "/IM", "python.exe"], capture_output=True)
time.sleep(2)

env = os.environ.copy()
env["PYTHONPATH"] = r"D:\two\backend\services"

backend = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
    cwd=r"D:\two\backend",
    env=env,
    stdout=open(r"D:\two\backend.log", "w", encoding="utf-8"),
    stderr=subprocess.STDOUT,
    creationflags=DETACHED,
)
print("Backend PID:", backend.pid)

frontend = subprocess.Popen(
    ["npm", "run", "dev"],
    cwd=r"D:\two\frontend",
    stdout=open(r"D:\two\frontend.log", "w", encoding="utf-8"),
    stderr=subprocess.STDOUT,
    creationflags=DETACHED,
    shell=True,
)
print("Frontend PID:", frontend.pid)
