import { Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { Menu, Spin, Button, Dropdown } from "antd";
import { LogoutOutlined, UserOutlined, SettingOutlined } from "@ant-design/icons";
import { lazy, Suspense, useEffect, useState } from "react";
import { useAuthStore } from "./store/auth";
import { getMe, localLogin } from "./services/auth";
import SettingsDrawer from "./components/SettingsDrawer";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const MerchantsPage = lazy(() => import("./pages/MerchantsPage"));
const ProfileIndexPage = lazy(() => import("./pages/ProfileIndexPage"));
const ProfileEditorPage = lazy(() => import("./pages/ProfileEditorPage"));
const CrawlJobsPage = lazy(() => import("./pages/CrawlJobsPage"));
const KnowledgeBasePage = lazy(() => import("./pages/KnowledgeBasePage"));
const MerchantDetailPage = lazy(() => import("./pages/MerchantDetailPage"));
const DesignIndexPage = lazy(() => import("./pages/DesignIndexPage"));
const DesignEditorPage = lazy(() => import("./pages/DesignEditorPage"));
const ReputationIndexPage = lazy(() => import("./pages/ReputationIndexPage"));
const ReputationWorkbenchPage = lazy(() => import("./pages/ReputationWorkbenchPage"));
const StudioIndexPage = lazy(() => import("./pages/StudioIndexPage"));
const DistrictIndexPage = lazy(() => import("./pages/DistrictIndexPage"));
const DistrictDetailPage = lazy(() => import("./pages/DistrictDetailPage"));
const StudioEditorPage = lazy(() => import("./pages/StudioEditorPage"));
const DealIndexPage = lazy(() => import("./pages/DealIndexPage"));
const DealEditorPage = lazy(() => import("./pages/DealEditorPage"));
const LiveIndexPage = lazy(() => import("./pages/LiveIndexPage"));
const LiveEditorPage = lazy(() => import("./pages/LiveEditorPage"));

const MENU_ITEMS = [
  { key: "/", label: "总看板" },
  { key: "/merchants", label: "商家管理" },
  { key: "/knowledge", label: "知识库" },
  { key: "/crawl", label: "达人寻觅" },
  { key: "/profile", label: "账号装修" },
  { key: "/design", label: "视觉设计" },
  { key: "/studio", label: "内容工坊" },
  { key: "/reputation", label: "口碑管理" },
  { key: "/district", label: "商圈分析" },
  { key: "/deals", label: "团购工坊" },
  { key: "/live", label: "直播工坊" },
];

const TICKER_ITEMS = [
  "本地运行 LOCAL RUN",
  "PostgreSQL 在线",
  "本地文件存储",
  "免登录模式",
  "1PX 网格",
  "直角 90°",
  "碳墨文字",
  "危险红强调",
];

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RegMark() {
  return (
    <span className="regmark" role="img" aria-label="印刷套准标记">
      <span className="rx" />
      <span className="ry" />
    </span>
  );
}

function AppLayout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const selectedKey =
    MENU_ITEMS.find(
      (item) =>
        location.pathname === item.key ||
        location.pathname.startsWith(`${item.key}/`)
    )?.key || location.pathname;

  const pageTitle = MENU_ITEMS.find((item) => item.key === selectedKey)?.label || "工作台";

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const today = new Date().toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });

  return (
    <div className="app-shell">
      <aside className="app-sider">
        <div className="app-brand">
          <div className="app-brand-word">
            <RegMark />
            <b>AiRestro</b>
          </div>
          <div className="app-brand-meta">本地工作台 · LOCAL WORKBENCH</div>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={MENU_ITEMS.map((item) => ({
            key: item.key,
            label: <span className="app-nav-label">[ {item.label} ]</span>,
          }))}
          onClick={({ key }) => navigate(key)}
        />
        <div className="app-sider-footer">NO.001 / 内部工具</div>
      </aside>
      <div className="app-main">
        <header className="app-topbar">
          <span className="app-micro">[ AiRestro / {pageTitle} ]</span>
          <div className="app-page-title">{pageTitle}</div>
          <div style={{ flex: 1 }} />
          <span className="app-micro">{today}</span>
          <Button type="text" icon={<SettingOutlined />} onClick={() => setSettingsOpen(true)} title="设置" />
          <Dropdown
            menu={{
              items: [
                { key: "logout", icon: <LogoutOutlined />, label: "退出登录", onClick: handleLogout },
              ],
            }}
          >
            <Button type="text" icon={<UserOutlined />}>
              {user?.name || "用户"}
            </Button>
          </Dropdown>
          <span className="blink" aria-hidden="true" />
        </header>
        <div className="app-ticker">
          <span className="app-ticker-label">{">>> "}本地 / PRESS</span>
          <div className="app-ticker-track">
            <span className="app-ticker-text">
              {TICKER_ITEMS.map((t) => `[ ${t} ]`).join(" · ")} ·&nbsp;
            </span>
          </div>
        </div>
        <main className="app-content">
          <div key={location.pathname} className="page-enter">
            {children}
          </div>
        </main>
      </div>
      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

export default function App() {
  const [loading, setLoading] = useState(true);
  const setAuth = useAuthStore((s) => s.setAuth);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    if (token && !user) {
      getMe()
        .then((u) => setAuth(token, u))
        .catch(() => {})
        .finally(() => setLoading(false));
    } else if (!token) {
      // 本地内部工具：自动换取本机登录态，失败时回到登录页
      localLogin()
        .then((res) => setAuth(res.access_token, res.user))
        .catch(() => {})
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [setAuth, token, user]);

  if (loading)
    return (
      <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center" }}>
        <Spin size="large" />
      </div>
    );

  return (
    <Suspense
      fallback={
        <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center" }}>
          <Spin size="large" />
        </div>
      }
    >
      <Routes>
        <Route path="/login" element={token ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DashboardPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/merchants"
        element={
          <ProtectedRoute>
            <AppLayout>
              <MerchantsPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/knowledge"
        element={
          <ProtectedRoute>
            <AppLayout>
              <KnowledgeBasePage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/crawl"
        element={
          <ProtectedRoute>
            <AppLayout>
              <CrawlJobsPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/merchants/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <MerchantDetailPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/profile"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ProfileIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/design"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DesignIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/design/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DesignEditorPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/studio"
        element={
          <ProtectedRoute>
            <AppLayout>
              <StudioIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/studio/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <StudioEditorPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/reputation"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ReputationIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/reputation/:shop_id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ReputationWorkbenchPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/district"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DistrictIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/district/:shop_id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DistrictDetailPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/deals"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DealIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/deals/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DealEditorPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/live"
        element={
          <ProtectedRoute>
            <AppLayout>
              <LiveIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/live/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <LiveEditorPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/shops/:shop_id/profile/:platform"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ProfileEditorPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}