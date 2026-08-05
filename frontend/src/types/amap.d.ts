// 高德 JS API 全局声明（通过后端 map-config 动态加载，不打进 bundle）
export {};

declare global {
  interface Window {
    _AMapSecurityConfig?: { serviceHost?: string };
    AMap?: any;
  }
}
