# D7 Findings

- Starlette request.form() 返回的 UploadFile 用 `isinstance(f, fastapi.UploadFile)` 过滤会返回空（版本差异），改用 `hasattr(f, "filename")` 过滤。
- 进程内登录限流（200 次/15 分钟）会让整套测试跑一半后 login 429；conftest 模块结束后清空 auth._login_attempts。
- PIL 4-band 密度按行统计会因字形行间空隙低估内容；对内容行做 ≤30px 间隙闭合（形态学 close）后与 DOM line-box 口径一致。
- 灰度面板（swiss grey-1 与 paper 差 30）不满足 30 阈值，改实心 accent 面板既符合 Swiss 风格又满足密度。
- 内容页用两栏布局（左文右图）可保证任意标题长度下密度 ≥75%；纯文字页在浅色 paper-2 主题下也可能通过（面板背景计入内容）。
- 渲染为同步（asyncio.to_thread），4-8 页约 10-30s，MVP 接受。
