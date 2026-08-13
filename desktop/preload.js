// 预加载脚本：保持最小权限，暴露版本信息 + 小红书扫码登录能力。
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("aistroDesktop", {
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
  },
  // 打开小红书登录窗口，扫码后自动抓取 Cookie 写入池
  // 返回 { ok, action, cookieId?, evicted?, reason?, error? }
  // action: added | replaced | cancel | timeout | token_expired | verify_failed | pool_full | network_error
  login: (token) => ipcRenderer.invoke("xhs:login", token),
});