
"""实测：AiRestro 上传主播视频 → 一键生成 LiveTalking 引擎形象 → 轮询 → 验证 data/avatars"""
import time, uuid
import httpx

BASE = "http://localhost:8000/api/v1"
ENGINE = "http://localhost:8010"
client = httpx.Client(base_url=BASE, timeout=180.0)
email = f"avatest-{uuid.uuid4().hex[:8]}@test.com"
client.post("/auth/register", json={"email": email, "password": "admin123", "name": "形象实测"})
r = client.post("/auth/login", json={"email": email, "password": "admin123"})
h = {"Authorization": f"Bearer {r.json()['access_token']}"}

# 1) 上传测试视频
with open(r"D:/two/.planning/livestream/test_avatar_video.mp4", "rb") as f:
    up = client.post("/live-avatars/upload-video", files={"file": ("test_avatar.mp4", f.read(), "video/mp4")}, headers=h)
assert up.status_code == 200, up.text
video_url = up.json()["url"]
print("上传视频 ok:", video_url[:80], "...")

# 2) 建形象
av = client.post("/live-avatars", json={
    "name": "实测主播", "avatar_type": "video",
    "video_url": video_url, "engine_base_url": ENGINE,
    "persona": {"identity": "实测主播", "tone": "亲切"},
    "status": "ready",
}, headers=h)
assert av.status_code == 200, av.text
avatar_id = av.json()["id"]
print("形象已建:", avatar_id)

# 3) 生成引擎形象
t0 = time.time()
r = client.post(f"/live-avatars/{avatar_id}/engine-avatar", headers=h)
print("engine-avatar ->", r.status_code, r.text[:200])
assert r.status_code == 200, r.text
task_id = r.json()["task_id"]
engine_aid = r.json()["avatar_id"]
print("task_id:", task_id, "| engine_avatar_id:", engine_aid)

# 4) 轮询
last = ""
for i in range(120):
    time.sleep(3)
    st = client.get(f"/live-avatars/{avatar_id}/engine-avatar/status", headers=h)
    d = st.json()
    line = f"[{i*3}s] status={d['status']} progress={d['progress']}"
    if d.get("error_msg"):
        line += f" error={d['error_msg'][:120]}"
    if line != last:
        print(line)
        last = line
    if d["status"] in ("completed", "failed"):
        break

# 5) 引擎侧验证新形象目录
import subprocess, os
avatars_dir = r"D:/two/.planning/livestream/engines/data/avatars"
dirs = [d for d in os.listdir(avatars_dir) if d.startswith("airestro_") or "test" in d or "airestro" in d]
print("引擎 data/avatars 新增:", dirs)
client.delete(f"/live-avatars/{avatar_id}", headers=h)
print("done")
