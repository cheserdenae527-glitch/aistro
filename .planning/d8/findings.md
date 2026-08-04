# D8 Findings

- React Compiler lint（react-hooks/immutability）要求 useCallback 在引用前声明；组件内函数先定义再使用。
- antd Upload beforeUpload 里 `list` 可能含被 LIST_IGNORE 的文件，需二次按类型/大小过滤。
- Vite dev server 绑定 ::1:3000（IPv6），127.0.0.1 探测会误判离线。
- 重启服务：start_services.py 的 taskkill 对旧 PID 可能失败导致端口占用，需先释放 8000。
- 复用历史卡组打开编辑器时，「下一步」不应重置模板/色板，否则预览与选中态不一致。
