// 预加载脚本：保持最小权限，仅暴露版本信息。
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("aistroDesktop", {
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
  },
});