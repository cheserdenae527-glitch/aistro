# D6 Findings

- Starlette TestClient 会等待 BackgroundTasks 完成，便于测试异步任务。
- 缩略图统一 JPEG，最长边 320px。
- 菜单版本快照存整行 JSON，restore 后 version 自增。