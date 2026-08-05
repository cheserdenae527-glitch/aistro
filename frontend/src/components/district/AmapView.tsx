// 高德地图视图 — 通过后端 /district/map-config 取 JS Key 动态加载，securityJsCode 走后端代理。
// 未配置 JS Key（503）时回退为占位提示，不影响列表/统计功能。
import { useEffect, useRef, useState } from "react";
import { Alert, Spin } from "antd";
import { districtService } from "../../services/district";

export interface MapPoint {
  lng: number;
  lat: number;
  name: string;
  kind: "center" | "competitor" | "poi";
}

interface AmapViewProps {
  center: { lng: number; lat: number } | null;
  points: MapPoint[];
  height?: number;
}

const PIN_STYLES: Record<MapPoint["kind"], string> = {
  center:
    "background:#1677ff;color:#fff;border-radius:50%;width:22px;height:22px;display:flex;align-items:center;justify-content:center;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.3);font-size:10px;",
  competitor:
    "background:#ff4d4f;color:#fff;border-radius:50%;width:16px;height:16px;display:flex;align-items:center;justify-content:center;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.3);",
  poi: "background:#8c8c8c;color:#fff;border-radius:50%;width:12px;height:12px;display:flex;align-items:center;justify-content:center;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.3);",
};

let scriptPromise: Promise<void> | null = null;

function loadAmapScript(jsKey: string): Promise<void> {
  if (window.AMap) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  const url = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(jsKey)}`;
  scriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-amap="1"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("高德地图脚本加载失败")));
      return;
    }
    const script = document.createElement("script");
    script.src = url;
    script.async = true;
    script.dataset.amap = "1";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("高德地图脚本加载失败"));
    document.head.appendChild(script);
  });
  return scriptPromise;
}

type ViewState = "loading" | "init" | "ready" | "unconfigured" | "error";

export default function AmapView({ center, points, height = 360 }: AmapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const [state, setState] = useState<ViewState>("loading");
  const [errorText, setErrorText] = useState("");

  // 阶段一：取 map-config + 加载脚本（只执行一次）
  useEffect(() => {
    let disposed = false;
    (async () => {
      let config;
      try {
        config = (await districtService.mapConfig()).data;
      } catch {
        if (!disposed) setState("unconfigured");
        return;
      }
      window._AMapSecurityConfig = { serviceHost: config.proxy_path };
      try {
        await loadAmapScript(config.amap_js_key);
      } catch (e) {
        if (!disposed) {
          setState("error");
          setErrorText(e instanceof Error ? e.message : "地图加载失败");
        }
        return;
      }
      if (!disposed) setState("init");
    })();
    return () => {
      disposed = true;
    };
  }, []);

  // 阶段二：脚本就绪后初始化地图（容器此时已渲染）
  useEffect(() => {
    if (state !== "init" || !containerRef.current || !window.AMap) return;
    const map = new window.AMap.Map(containerRef.current, {
      zoom: 14,
      center: center ? [center.lng, center.lat] : undefined,
    });
    mapRef.current = map;
    setState("ready");
  }, [state, center]);

  // 标记刷新
  useEffect(() => {
    const map = mapRef.current;
    if (!map || state !== "ready") return;
    map.clearMap();
    const markers: any[] = [];
    if (center) {
      markers.push(
        new window.AMap.Marker({
          position: [center.lng, center.lat],
          content: `<div style="${PIN_STYLES.center}">店</div>`,
          offset: new window.AMap.Pixel(-11, -11),
        })
      );
    }
    for (const p of points) {
      markers.push(
        new window.AMap.Marker({
          position: [p.lng, p.lat],
          title: p.name,
          content: `<div style="${PIN_STYLES[p.kind]}"></div>`,
          offset: new window.AMap.Pixel(-8, -8),
        })
      );
    }
    map.add(markers);
    if (markers.length > 0) map.setFitView(markers, false, [40, 40, 40, 40]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [center, points, state]);

  // 卸载清理
  useEffect(() => {
    return () => {
      if (mapRef.current) {
        mapRef.current.destroy();
        mapRef.current = null;
      }
    };
  }, []);

  if (state === "unconfigured") {
    return (
      <Alert
        type="warning"
        showIcon
        message="地图未配置"
        description="请在 backend/.env 配置 AMAP_JS_KEY 与 AMAP_SECURITY_JS_CODE 后重启后端，即可显示地图。当前仍可通过下方列表查看商圈数据。"
        style={{ marginBottom: 8 }}
      />
    );
  }
  if (state === "error") {
    return (
      <Alert type="error" showIcon message="地图加载失败" description={errorText} style={{ marginBottom: 8 }} />
    );
  }
  return (
    <div style={{ position: "relative" }}>
      <div ref={containerRef} style={{ width: "100%", height, borderRadius: 8 }} data-testid="amap-view" />
      {state !== "ready" && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "#fafafa",
            borderRadius: 8,
          }}
        >
          <Spin tip="地图加载中…">
            <div style={{ width: 120, height: 60 }} />
          </Spin>
        </div>
      )}
    </div>
  );
}
